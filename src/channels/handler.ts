import type { Bot, Context } from "grammy";
import { InputFile } from "grammy";
import type { BotContext } from "./bot.js";
import { Db } from "../core/db.js";
import { ask, vision } from "../ai/engine.js";
import { buildSystemPrompt, type ChatType } from "../memory/prompt.js";
import { send } from "./send.js";
import { afterTurn } from "../memory/extractor.js";
import { shouldAck, setReaction, clearReaction, smartReact } from "../ai/reactions.js";
import { webSearch, readPage } from "../tools/search.js";
import { tts } from "../tools/tts.js";
import { stt } from "../tools/stt.js";
import { log } from "../core/logger.js";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";

// Per-user lock — предотвращает гонку запросов одного юзера
const locks = new Map<number, boolean>();

async function withLock(uid: number, fn: () => Promise<void>) {
  if (locks.get(uid)) return;
  locks.set(uid, true);
  try { await fn(); } finally { locks.delete(uid); }
}

async function isMentionedOrReplied(ctx: Context, botUsername: string): Promise<boolean> {
  const msg  = ctx.message;
  if (!msg) return false;
  const text = msg.text ?? msg.caption ?? "";
  if (msg.reply_to_message?.from?.username === botUsername) return true;
  if (msg.reply_to_message?.from?.id === ctx.me.id)         return true;
  const myMention = `@${botUsername}`.toLowerCase();
  if (text.toLowerCase().includes(myMention)) return true;
  const entities = msg.entities ?? msg.caption_entities ?? [];
  for (const e of entities) {
    if (e.type === "mention" && text.slice(e.offset, e.offset + e.length).toLowerCase() === myMention) return true;
    if (e.type === "text_mention" && e.user?.id === ctx.me.id) return true;
  }
  return false;
}

const URL_RE = /https?:\/\/[^\s]+/g;

async function aiRespond(
  ctx: BotContext,
  userText: string,
  task: "general" | "code" | "analysis" | "fast" = "general"
) {
  const uid    = ctx.from!.id;
  const chatId = ctx.chat!.id;
  const ct     = ctx.chat!.type as ChatType;
  const msgId  = ctx.message?.message_id!;

  await withLock(uid, async () => {
    let ackSet = false;
    if (shouldAck(userText) && ct === "private") {
      await setReaction(ctx.api as unknown as Parameters<typeof setReaction>[0], chatId, msgId, "👀");
      ackSet = true;
    }

    try {
      await ctx.replyWithChatAction("typing");

      // URL auto-read
      const urls  = userText.match(URL_RE) ?? [];
      let webData = "";
      if (urls.length) {
        const content = await readPage(urls[0]!);
        if (content) webData = `\n\n[🔗 Page content: ${urls[0]}]\n${content.slice(0, 3000)}`;
      }

      // Web search trigger
      const needsSearch = /(?:найди|поищи|узнай|что сейчас|последние|today|latest|news|find|search)/i.test(userText);
      if (needsSearch && !webData) {
        const results = await webSearch(userText.slice(0, 200));
        if (results) webData = `\n\n[🌐 Web data]\n${results}`;
      }

      // Строим промпт только для этого uid — данные других пользователей не попадают
      const sys  = buildSystemPrompt(uid, chatId, ct, userText);
      const hist = Db.getHistory(uid, chatId, 16);
      const msgs = [
        { role: "system" as const, content: sys + webData },
        ...hist.map(h => ({ role: h.role as "user" | "assistant", content: h.content })),
        { role: "user" as const, content: userText },
      ];

      const resp = await ask(msgs, task);

      // Сохраняем строго по uid
      Db.addMsg(uid, chatId, "user",      userText);
      Db.addMsg(uid, chatId, "assistant", resp);

      if (ackSet) await clearReaction(ctx.api as unknown as Parameters<typeof clearReaction>[0], chatId, msgId);
      void smartReact(ctx.api as unknown as Parameters<typeof smartReact>[0], chatId, msgId, userText);

      await send(ctx, resp);
      void afterTurn(uid, userText, resp, ct === "private");

    } catch (e: unknown) {
      if (ackSet) await clearReaction(ctx.api as unknown as Parameters<typeof clearReaction>[0], chatId, msgId);
      const err = e instanceof Error ? e.message : String(e);
      log.error(`AI respond uid=${uid}: ${err}`);
      if (ct === "private") {
        await ctx.reply(`❌ ${err.includes("провайдеры") ? err : "AI временно недоступен. Попробуй ещё раз."}`);
      }
    }
  });
}

export function registerHandlers(bot: Bot<BotContext>) {

  // ── Текстовые сообщения ──────────────────────────────────────────────
  bot.on("message:text", async (ctx) => {
    const uid    = ctx.from.id;
    const chatId = ctx.chat.id;
    const ct     = ctx.chat.type;
    const text   = ctx.message.text ?? "";

    Db.ensureUser(uid, ctx.from.first_name ?? "", ctx.from.username ?? "");
    if (ct !== "private") Db.grpSave(chatId, uid, ctx.from.first_name ?? "", ctx.from.username ?? "");

    if (ct === "group" || ct === "supergroup") {
      const mentioned = await isMentionedOrReplied(ctx, ctx.me.username ?? "");
      if (!mentioned) return;
      const cleanText = text.replace(new RegExp(`@${ctx.me.username}\\s*`, "gi"), "").trim() || "привет";
      await aiRespond(ctx, cleanText);
      return;
    }

    let task: "general" | "code" | "analysis" = "general";
    const tl = text.toLowerCase();
    if (/код|python|javascript|typescript|функция|алгоритм|debug|написать код/.test(tl)) task = "code";
    else if (/найди|новости|актуальн|сегодня|последн|поиск/.test(tl)) task = "analysis";

    await aiRespond(ctx, text, task);
  });

  // ── Голосовые сообщения ──────────────────────────────────────────────
  bot.on("message:voice", async (ctx) => {
    const uid = ctx.from.id;
    const ct  = ctx.chat.type;
    if (ct !== "private") {
      const mentioned = await isMentionedOrReplied(ctx, ctx.me.username ?? "");
      if (!mentioned) return;
    }
    Db.ensureUser(uid, ctx.from.first_name ?? "", ctx.from.username ?? "");
    await ctx.replyWithChatAction("record_voice");

    const file    = await ctx.getFile();
    const tmpPath = path.join(os.tmpdir(), `nexum_voice_${uid}_${Date.now()}.ogg`);
    try {
      await downloadFile(ctx.api.token, file.file_path!, tmpPath);
      const text = await stt(tmpPath);
      if (!text) { await ctx.reply("🎤 Не разобрал речь. Попробуй ещё раз."); return; }

      await ctx.reply(`🎤 _${text}_`, { parse_mode: "Markdown" });

      const chatId = ctx.chat.id;
      const sys    = buildSystemPrompt(uid, chatId, ct as ChatType, text);
      const hist   = Db.getHistory(uid, chatId, 12);
      const msgs   = [
        { role: "system" as const, content: sys },
        ...hist.map(h => ({ role: h.role as "user" | "assistant", content: h.content })),
        { role: "user" as const, content: text },
      ];
      const resp = await ask(msgs);

      Db.addMsg(uid, chatId, "user",      `[voice] ${text}`);
      Db.addMsg(uid, chatId, "assistant", resp);

      const user  = Db.getUser(uid);
      const lang  = user?.lang ?? "ru";
      const audio = await tts(resp, lang);
      if (audio) {
        await ctx.replyWithVoice(new InputFile(audio, "nexum.mp3"));
      } else {
        await send(ctx, resp);
      }
      void afterTurn(uid, text, resp, ct === "private");
    } finally {
      try { fs.unlinkSync(tmpPath); } catch {}
    }
  });

  // ── Фото ─────────────────────────────────────────────────────────────
  bot.on("message:photo", async (ctx) => {
    const uid = ctx.from.id;
    const ct  = ctx.chat.type;
    if (ct !== "private") {
      const mentioned = await isMentionedOrReplied(ctx, ctx.me.username ?? "");
      if (!mentioned) return;
    }
    Db.ensureUser(uid, ctx.from.first_name ?? "", ctx.from.username ?? "");
    await ctx.replyWithChatAction("typing");

    const cap    = ctx.message.caption || "Детально опиши это изображение: объекты, текст, контекст, эмоции.";
    const chatId = ctx.chat.id;
    try {
      const photo   = ctx.message.photo.at(-1)!;
      const file    = await ctx.api.getFile(photo.file_id);
      const tmpPath = path.join(os.tmpdir(), `nexum_photo_${uid}_${Date.now()}.jpg`);
      await downloadFile(ctx.api.token, file.file_path!, tmpPath);
      const b64 = fs.readFileSync(tmpPath).toString("base64");
      fs.unlinkSync(tmpPath);
      const result = await vision(b64, cap);
      Db.addMsg(uid, chatId, "user",      `[фото] ${cap}`);
      Db.addMsg(uid, chatId, "assistant", result);
      await send(ctx, result);
    } catch (e: unknown) {
      const err = e instanceof Error ? e.message : String(e);
      log.error(`Photo uid=${uid}: ${err}`);
      if (ct === "private") {
        await ctx.reply(
          "😕 Не смог проанализировать фото.\n\nДобавь ключ для vision:\n• `G1` — Gemini\n• `CL1` — Claude\n• `OR1` — OpenRouter",
          { parse_mode: "Markdown" }
        );
      }
    }
  });

  // ── Документы (только в личке) ───────────────────────────────────────
  bot.on("message:document", async (ctx) => {
    const uid = ctx.from.id;
    const ct  = ctx.chat.type;
    if (ct !== "private") return;
    Db.ensureUser(uid, ctx.from.first_name ?? "", ctx.from.username ?? "");
    const doc = ctx.message.document;
    await ctx.reply(
      `📄 Получил: **${doc.file_name ?? "файл"}** (${Math.round((doc.file_size ?? 0) / 1024)}KB)\n\n_Анализ документов в разработке._`,
      { parse_mode: "Markdown" }
    );
  });

  // ── Стикеры ──────────────────────────────────────────────────────────
  bot.on("message:sticker", async (ctx) => {
    if (ctx.chat.type !== "private") return;
    const emoji = ctx.message.sticker.emoji ?? "😊";
    await smartReact(
      ctx.api as unknown as Parameters<typeof smartReact>[0],
      ctx.chat.id, ctx.message.message_id, emoji
    );
  });

  log.info("Message handlers registered");
}

async function downloadFile(token: string, filePath: string, dest: string) {
  const url = `https://api.telegram.org/file/bot${token}/${filePath}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Download failed: ${res.status}`);
  fs.writeFileSync(dest, Buffer.from(await res.arrayBuffer()));
}
