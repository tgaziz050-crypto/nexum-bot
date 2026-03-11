import type { Bot, Context } from "grammy";
import { InputFile } from "grammy";
import type { BotContext, ChatType } from "./bot.js";
import { Db } from "../core/db.js";
import { ask, vision } from "../ai/engine.js";
import { buildSystemPrompt } from "../memory/prompt.js";
import { send } from "./send.js";
import { stt } from "../tools/stt.js";
import { tts } from "../tools/tts.js";
import { afterTurn } from "../memory/extractor.js";
import { smartReact } from "../ai/reactions.js";
import { parseFinanceFromText, getFinanceContext, sendFinanceDashboard } from "../finance/finance.js";
import { log } from "../core/logger.js";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";

async function isMentionedOrReplied(ctx: Context, botUsername: string): Promise<boolean> {
  const msg = ctx.message;
  if (!msg) return false;
  const text = msg.text ?? msg.caption ?? "";
  const myMention = "@" + botUsername.toLowerCase();
  if (msg.reply_to_message?.from?.id === ctx.me.id) return true;
  if (text.toLowerCase().includes(myMention)) return true;
  for (const e of msg.entities ?? []) {
    if (e.type === "mention" && text.slice(e.offset, e.offset + e.length).toLowerCase() === myMention) return true;
    if (e.type === "text_mention" && e.user?.id === ctx.me.id) return true;
  }
  return false;
}

async function aiRespond(ctx: BotContext, userText: string, task: "general"|"code"|"analysis" = "general") {
  const uid    = ctx.from!.id;
  const chatId = ctx.chat!.id;
  const ct     = ctx.chat!.type as ChatType;

  await ctx.replyWithChatAction("typing");

  const sys  = buildSystemPrompt(uid, chatId, ct, userText);
  const hist = Db.getHistory(uid, chatId, 14);
  const msgs = [
    { role: "system" as const, content: sys },
    ...hist.map(h => ({ role: h.role as "user"|"assistant", content: h.content })),
    { role: "user" as const, content: userText },
  ];

  const resp = await ask(msgs, task);

  Db.addMsg(uid, chatId, "user", userText);
  Db.addMsg(uid, chatId, "assistant", resp);

  // Voice mode — если пользователь включил голос, отвечаем голосом
  const user = Db.getUser(uid);
  if (user?.voice_mode && ct === "private") {
    await ctx.replyWithChatAction("record_voice");
    const lang = user?.lang ?? "ru";
    const audio = await tts(resp, lang);
    if (audio) {
      await ctx.replyWithVoice(new InputFile(audio, "nexum.mp3"));
      await send(ctx, resp); // also send text
      void afterTurn(uid, userText, resp, ct === "private");
      return;
    }
  }

  await send(ctx, resp);
  void afterTurn(uid, userText, resp, ct === "private");

  // React occasionally
  void smartReact(ctx.api as any, chatId, ctx.message!.message_id, userText).catch(()=>{});
}

export function registerHandlers(bot: Bot<BotContext>) {

  // ── Text messages ────────────────────────────────────────────────────
  bot.on("message:text", async (ctx) => {
    const uid  = ctx.from!.id;
    const ct   = ctx.chat!.type;
    if (ct !== "private") {
      const mentioned = await isMentionedOrReplied(ctx, ctx.me.username ?? "");
      if (!mentioned) {
        if (ct !== "private") Db.grpSave(ctx.chat!.id, uid, ctx.from!.first_name??"", ctx.from!.username??"");
        return;
      }
    }
    Db.ensureUser(uid, ctx.from!.first_name ?? "", ctx.from!.username ?? "");

    const text = ct !== "private"
      ? ctx.message.text.replace(new RegExp(`@${ctx.me.username}\\s*`,"gi"),"").trim() || "привет"
      : ctx.message.text ?? "";

    // Check voice mode toggle
    const lower = text.toLowerCase();
    if (/голосов|voice mode|давай голос|отвечай голосом|voice chat|speak|говори голосом/.test(lower)) {
      Db.setVoiceMode(uid, true);
      await ctx.reply("🎤 Включил голосовой режим! Буду отвечать голосом.");
      return;
    }
    if (/выключи голос|текстом|stop voice|text mode|без голоса/.test(lower)) {
      Db.setVoiceMode(uid, false);
      await ctx.reply("💬 Переключился на текст.");
      return;
    }

    // Finance auto-detection
    if (ct === "private") {
      const fin = await parseFinanceFromText(text);
      if (fin?.detected && fin.amount && fin.amount > 0) {
        const accounts = Db.finGetAccounts(uid);
        Db.finEnsureDefaults(uid);
        const accs = Db.finGetAccounts(uid);
        const accountId = accs[0]?.id ?? null;
        const type = fin.type ?? "expense";
        const category = fin.category ?? "Прочее";
        Db.finAddTransaction(uid, type, fin.amount, category, accountId, fin.note ?? "", "", "UZS");
        const sign = type === "income" ? "+" : "-";
        const icon = type === "income" ? "💵" : "💸";
        await ctx.reply(
          `${icon} Записал!\n${sign}${fin.amount.toLocaleString("ru-RU")} UZS · ${category}${fin.note ? " · " + fin.note : ""}`,
          { reply_markup: { inline_keyboard: [[{ text:"📊 Открыть Finance", callback_data:"fin:dashboard" }]] } }
        );
        void afterTurn(uid, text, `Записал транзакцию: ${type} ${fin.amount} ${category}`, true);
        return;
      }
    }

    // Task routing
    let task: "general"|"code"|"analysis" = "general";
    if (/код|python|javascript|typescript|функция|алгоритм|debug/.test(lower)) task = "code";
    else if (/найди|новости|актуальн|сегодня|последн|поиск/.test(lower)) task = "analysis";

    await aiRespond(ctx, text, task);
  });

  // ── Voice messages ───────────────────────────────────────────────────
  bot.on("message:voice", async (ctx) => {
    const uid = ctx.from!.id;
    const ct  = ctx.chat!.type;
    if (ct !== "private") {
      const mentioned = await isMentionedOrReplied(ctx, ctx.me.username ?? "");
      if (!mentioned) return;
    }
    Db.ensureUser(uid, ctx.from!.first_name ?? "", ctx.from!.username ?? "");
    await ctx.replyWithChatAction("record_voice");

    const file    = await ctx.getFile();
    const tmpPath = path.join(os.tmpdir(), `nexum_voice_${uid}_${Date.now()}.ogg`);
    try {
      await downloadFile(ctx.api.token, file.file_path!, tmpPath);
      const text = await stt(tmpPath);
      if (!text) { await ctx.reply("🎤 Не разобрал речь."); return; }

      await ctx.reply(`🎤 _${text}_`, { parse_mode: "Markdown" });

      // Auto-enable voice mode if user sends voice
      const user = Db.getUser(uid);
      if (!user?.voice_mode) Db.setVoiceMode(uid, true);

      const chatId = ctx.chat!.id;
      const sys    = buildSystemPrompt(uid, chatId, ct as ChatType, text);
      const hist   = Db.getHistory(uid, chatId, 12);
      const msgs   = [
        { role: "system" as const, content: sys },
        ...hist.map(h => ({ role: h.role as "user"|"assistant", content: h.content })),
        { role: "user" as const, content: text },
      ];
      const resp = await ask(msgs);

      Db.addMsg(uid, chatId, "user", `[voice] ${text}`);
      Db.addMsg(uid, chatId, "assistant", resp);

      const lang  = user?.lang ?? "ru";
      const audio = await tts(resp, lang);
      if (audio) {
        await ctx.replyWithVoice(new InputFile(audio, "nexum.mp3"));
        await send(ctx, resp);
      } else {
        await send(ctx, resp);
      }
      void afterTurn(uid, text, resp, ct === "private");
    } finally {
      try { fs.unlinkSync(tmpPath); } catch {}
    }
  });

  // ── Video notes (circles) ────────────────────────────────────────────
  bot.on("message:video_note", async (ctx) => {
    const uid = ctx.from!.id;
    if (ctx.chat!.type !== "private") return;
    Db.ensureUser(uid, ctx.from!.first_name ?? "", ctx.from!.username ?? "");
    await ctx.replyWithChatAction("record_voice");
    const file    = await ctx.getFile();
    const tmpPath = path.join(os.tmpdir(), `nexum_circle_${uid}_${Date.now()}.mp4`);
    try {
      await downloadFile(ctx.api.token, file.file_path!, tmpPath);
      const text = await stt(tmpPath);
      if (!text) { await ctx.reply("🎥 Не разобрал речь из кружка."); return; }
      await ctx.reply(`🎥 _${text}_`, { parse_mode:"Markdown" });
      await aiRespond(ctx, text);
    } finally {
      try { fs.unlinkSync(tmpPath); } catch {}
    }
  });

  // ── Photos ───────────────────────────────────────────────────────────
  bot.on("message:photo", async (ctx) => {
    const uid = ctx.from!.id;
    const ct  = ctx.chat!.type;
    if (ct !== "private") {
      const mentioned = await isMentionedOrReplied(ctx, ctx.me.username ?? "");
      if (!mentioned) return;
    }
    Db.ensureUser(uid, ctx.from!.first_name ?? "", ctx.from!.username ?? "");
    await ctx.replyWithChatAction("typing");

    const cap    = ctx.message.caption || "Детально опиши это изображение.";
    const chatId = ctx.chat!.id;
    try {
      const photo   = ctx.message.photo.at(-1)!;
      const file    = await ctx.api.getFile(photo.file_id);
      const tmpPath = path.join(os.tmpdir(), `nexum_photo_${uid}_${Date.now()}.jpg`);
      await downloadFile(ctx.api.token, file.file_path!, tmpPath);
      const b64 = fs.readFileSync(tmpPath).toString("base64");
      fs.unlinkSync(tmpPath);
      const result = await vision(b64, cap);
      Db.addMsg(uid, chatId, "user", `[фото] ${cap}`);
      Db.addMsg(uid, chatId, "assistant", result);
      await send(ctx, result);
    } catch (e: any) {
      log.error(`Photo uid=${uid}: ${e.message}`);
      if (ct === "private") await ctx.reply("😕 Не смог проанализировать изображение.");
    }
  });

  // ── Documents ────────────────────────────────────────────────────────
  bot.on("message:document", async (ctx) => {
    if (ctx.chat!.type !== "private") return;
    const doc = ctx.message.document;
    await ctx.reply(`📄 Получил: **${doc.file_name ?? "файл"}** (${Math.round((doc.file_size ?? 0)/1024)}KB)\n\n_Анализ документов в разработке._`, { parse_mode:"Markdown" });
  });

  // ── Stickers ─────────────────────────────────────────────────────────
  bot.on("message:sticker", async (ctx) => {
    if (ctx.chat!.type !== "private") return;
    const emoji = ctx.message.sticker.emoji ?? "😊";
    await smartReact(ctx.api as any, ctx.chat!.id, ctx.message.message_id, emoji).catch(()=>{});
  });

  log.info("Handlers registered");
}

async function downloadFile(token: string, filePath: string, dest: string) {
  const url = `https://api.telegram.org/file/bot${token}/${filePath}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Download failed: ${res.status}`);
  fs.writeFileSync(dest, Buffer.from(await res.arrayBuffer()));
}
