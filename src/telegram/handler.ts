/**
 * NEXUM v5 — Telegram Message Handler
 * Full pipeline: voice → text → intent → tools → response
 * - Photos: silent retry, no API key errors shown to users
 * - Voice: multilingual auto-detect
 * - Reactions: on message, not as text
 */
import type { Bot, Context } from "grammy";
import { InputFile } from "grammy";
import type { BotContext, ChatType } from "./bot.js";
import { Db } from "../core/db.js";
import { ask, vision } from "../agent/engine.js";
import { buildSystemPrompt, afterTurn, extractFast } from "../agent/memory.js";
import { detectIntent, extractLinkCode } from "../agent/router.js";
import { needsPlanning, createPlan, formatPlan } from "../agent/planner.js";
import { executePlan, isSensitive } from "../agent/executor.js";
import { consumeLinkCode, sendToAgent, isAgentOnline } from "../agent/pcagent.js";
import { send } from "./send.js";
import { stt } from "../tools/stt.js";
import { tts } from "../tools/tts.js";
import { smartReact } from "./reactions.js";
import { parseFinanceFromText, getFinanceContext } from "../tools/finance.js";
import { webSearch } from "../tools/search.js";
import { isAlarmRequest, parseAlarmTime } from "../tools/alarm.js";
import { tryExtractAndSaveTask } from "../tools/tasks.js";
import { tryExtractNote } from "../tools/notes.js";
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

// ── Core AI respond pipeline ──────────────────────────────────────────────
async function aiRespond(ctx: BotContext, userText: string, task: "general" | "code" | "analysis" = "general") {
  const uid    = ctx.from!.id;
  const chatId = ctx.chat!.id;
  const ct     = ctx.chat!.type as ChatType;

  await ctx.replyWithChatAction("typing");

  const { intent } = detectIntent(userText);

  // Link code detection
  if (intent === "link_code") {
    const code = extractLinkCode(userText);
    if (code) {
      const ok = await consumeLinkCode(uid, code);
      await ctx.reply(
        ok
          ? "✅ *Device linked!*\n\nPC Agent connected to your account. Use /pc to manage."
          : "❌ Invalid or expired code. Restart the agent to get a new code.",
        { parse_mode: "Markdown" }
      );
      return;
    }
  }

  // Web search
  const SEARCH_PATTERNS = [
    /сегодня|сейчас|новости|последн|актуальн|курс\s+(?:валют|доллар|евро|USD|EUR)|погода|прогноз/i,
    /кто\s+(?:сейчас|является|президент|премьер)|что\s+(?:сейчас|происходит)/i,
    /today|right now|latest|current|breaking|news|weather forecast/i,
    /bugun|hozir|yangilik|ob-havo/i, // Uzbek
    /bugün|şimdi|haber|hava durumu/i, // Turkish
  ];
  const needsSearch = SEARCH_PATTERNS.some(p => p.test(userText)) || intent === "search";
  let searchCtx = "";
  if (needsSearch && ct === "private") {
    try {
      await ctx.replyWithChatAction("typing");
      searchCtx = await webSearch(userText) ?? "";
    } catch {}
  }

  // Finance auto-detect
  if (intent === "finance" && ct === "private") {
    try {
      const tx = await parseFinanceFromText(userText);
      if (tx) {
        const finCtx = getFinanceContext(uid);
        const sys = buildSystemPrompt(uid, chatId, ct, userText);
        const resp = await ask([
          { role: "system", content: sys + "\n\n[FINANCE]\n" + finCtx },
          { role: "user",   content: userText },
        ]);
        Db.addMsg(uid, chatId, "user", userText);
        Db.addMsg(uid, chatId, "assistant", resp);
        await send(ctx, resp);
        await afterTurn(uid, chatId, userText, resp);
        return;
      }
    } catch {}
  }

  // Alarm auto-detect
  if (intent === "alarm" && ct === "private") {
    try {
      const alarm = parseAlarmTime(userText);
      if (alarm) {
        Db.addAlarm(uid, chatId, userText, alarm);
        await ctx.reply(`🔔 Alarm set for ${alarm.toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" })}`);
        return;
      }
    } catch {}
  }

  // Note auto-extract
  if (intent === "note" && ct === "private") {
    const noteResult = tryExtractNote(uid, userText);
    if (noteResult?.saved) {
      await ctx.reply("📝 Note saved!");
      return;
    }
  }

  // Task auto-extract
  if (intent === "task" && ct === "private") {
    const saved = await tryExtractAndSaveTask(uid, chatId, userText);
    if (saved) {
      await ctx.reply("✅ Task added!");
      return;
    }
  }

  // Direct tool creation request
  if (/создай.*(?:тул|инструмент|tool)|разработай.*тул|сделай.*тул|make.*tool|build.*tool|create.*tool/i.test(userText) && ct === "private") {
    const { generateAndRegisterTool, listDynamicTools } = await import("../tools/tool_registry.js");
    const msg = await ctx.reply("🔨 *Developing new tool...*\n\nGenerating code, please wait.", { parse_mode: "Markdown" });
    const result = await generateAndRegisterTool(uid, userText);
    const toolCount = listDynamicTools().length;
    await ctx.api.editMessageText(
      chatId,
      msg.message_id,
      result.success
        ? `✅ *New tool created and connected!*\n\n${result.message}\n\n🧰 Total dynamic tools: ${toolCount}\nUse /tools to see all.`
        : `❌ *Tool creation failed*\n\n${result.message}`,
      { parse_mode: "Markdown" }
    ).catch(() => {});
    return;
  }

  // Complex task planning
  if (needsPlanning(userText) && ct === "private") {
    await ctx.reply("🗺 Building execution plan...");
    const context = `User has PC agent: ${isAgentOnline(uid) ? "YES" : "NO"}`;
    const plan = await createPlan(uid, userText, context);
    if (plan) {
      await ctx.reply(formatPlan(plan), { parse_mode: "Markdown" });
      await ctx.reply("▶️ Start executing this plan?", {
        reply_markup: {
          inline_keyboard: [[
            { text: "✅ Execute", callback_data: `plan:run:${plan.id}` },
            { text: "❌ Cancel",  callback_data: `plan:cancel:${plan.id}` },
          ]],
        },
      });
      return;
    }
  }

  const sys  = buildSystemPrompt(uid, chatId, ct, userText);
  const hist = Db.getHistory(uid, chatId, 50);
  const userContent = searchCtx ? `[WEB SEARCH]\n${searchCtx}\n---\n${userText}` : userText;

  const msgs = [
    { role: "system" as const, content: sys },
    ...hist.map(h => ({ role: h.role as "user" | "assistant", content: h.content })),
    { role: "user" as const, content: userContent },
  ];

  const resp = await ask(msgs, task);

  Db.addMsg(uid, chatId, "user", userText);
  Db.addMsg(uid, chatId, "assistant", resp);

  const user = Db.getUser(uid);
  if (user?.voice_mode && ct === "private") {
    await ctx.replyWithChatAction("record_voice");
    const lang = user?.lang ?? "ru";
    const audioText = resp.replace(/[*_`#>~|]/g, "").replace(/\[([^\]]+)\]\([^)]+\)/g, "$1").trim();
    const audio = await tts(audioText, lang);
    if (audio) {
      await ctx.replyWithVoice(new InputFile(audio, "nexum.mp3"));
    } else {
      await send(ctx, resp);
    }
  } else {
    await send(ctx, resp);
  }

  await afterTurn(uid, chatId, userText, resp);
}

// ── Register all handlers ─────────────────────────────────────────────────
export function registerHandlers(bot: Bot<BotContext>) {

  // ── Plan execution callback ───────────────────────────────────────────
  bot.callbackQuery(/^plan:(run|cancel):(\d+)$/, async (ctx) => {
    await ctx.answerCallbackQuery();
    const uid    = ctx.from!.id;
    const action = ctx.match[1];
    const planId = parseInt(ctx.match[2]);

    if (action === "cancel") {
      const { DbV5 } = await import("../core/db.js");
      DbV5.updatePlanStatus(planId, "cancelled");
      await ctx.editMessageText("❌ Plan cancelled.");
      return;
    }

    const { DbV5 } = await import("../core/db.js");
    const plans = DbV5.getActivePlans(uid);
    const plan  = plans.find(p => p.id === planId);
    if (!plan) { await ctx.editMessageText("❌ Plan not found."); return; }

    const steps = JSON.parse(plan.steps);
    await ctx.editMessageText("⚙️ Executing plan...");

    const pcSend = isAgentOnline(uid) ? sendToAgent : undefined;
    const results = await executePlan(uid, planId, steps, pcSend, async (r) => {
      await bot.api.sendMessage(ctx.chat!.id,
        `${r.success ? "✅" : "❌"} Step ${r.step.id}: ${r.step.action}\n${r.output ? `\`${r.output.slice(0, 200)}\`` : ""}`,
        { parse_mode: "Markdown" }
      ).catch(() => {});
    });

    const done = results.filter(r => r.success).length;
    await bot.api.sendMessage(ctx.chat!.id,
      `📊 *Plan complete:* ${done}/${results.length} steps done.`,
      { parse_mode: "Markdown" }
    ).catch(() => {});
  });

  // ── PC confirmation callbacks ─────────────────────────────────────────
  bot.callbackQuery(/^pc:(approve|deny):(.+)$/, async (ctx) => {
    await ctx.answerCallbackQuery();
    const action = ctx.match[1];
    if (action === "approve") {
      await ctx.editMessageText("✅ Command executing...");
    } else {
      await ctx.editMessageText("❌ Command cancelled.");
    }
  });

  // ── TEXT messages ─────────────────────────────────────────────────────
  bot.on("message:text", async (ctx) => {
    const uid  = ctx.from!.id;
    const ct   = ctx.chat!.type as ChatType;
    const text = ctx.message.text ?? "";

    Db.ensureUser(uid, ctx.from!.first_name ?? "", ctx.from!.username ?? "");

    if (ct !== "private") {
      const mentioned = await isMentionedOrReplied(ctx, (await ctx.me).username ?? "");
      if (!mentioned) return;
    }

    if (!text.trim() || text.startsWith("/")) return;

    // Set reaction on the user's message (async, don't block)
    smartReact(bot as any, ctx.chat!.id, ctx.message!.message_id, text).catch(() => {});

    // Agent file request detection (multilingual)
    const agentRequest = /скачай агент|пришли агент|send agent|agent file|агент файл|agent install|установить агент|yubor agent|agent yuklab/i.test(text);
    if (agentRequest && ct === "private") {
      try {
        const agentPath = path.join(process.cwd(), "nexum_agent.py");
        if (fs.existsSync(agentPath)) {
          await ctx.replyWithDocument(new InputFile(agentPath, "nexum_agent.py"),
            { caption: "🤖 *NEXUM PC Agent*\n\n1. Install Python 3.8+\n2. `pip install websockets pyautogui pillow psutil`\n3. `python nexum_agent.py`\n4. Send the 6-char code with `/link CODE`", parse_mode: "Markdown" }
          );
          return;
        }
      } catch {}
    }

    try {
      const taskType = /```|код|функция|function|code|class|script/i.test(text) ? "code" : "general";
      await aiRespond(ctx, text, taskType as any);
    } catch (e: any) {
      log.error(`Handler text error: ${e.message}`);
      await ctx.reply("😕 Something went wrong. Please try again.");
    }
  });

  // ── VOICE messages ────────────────────────────────────────────────────
  bot.on("message:voice", async (ctx) => {
    const uid = ctx.from!.id;
    const ct  = ctx.chat!.type as ChatType;
    Db.ensureUser(uid, ctx.from!.first_name ?? "", ctx.from!.username ?? "");

    if (ct !== "private") {
      const mentioned = await isMentionedOrReplied(ctx, (await ctx.me).username ?? "");
      if (!mentioned) return;
    }

    await ctx.replyWithChatAction("typing");
    try {
      const file = await ctx.getFile();
      const url  = `https://api.telegram.org/file/bot${process.env.BOT_TOKEN}/${file.file_path}`;
      const res  = await fetch(url);
      const buf  = Buffer.from(await res.arrayBuffer());
      const tmp  = path.join(os.tmpdir(), `nexum_voice_${Date.now()}.ogg`);
      fs.writeFileSync(tmp, buf);

      const transcript = await stt(tmp);
      fs.unlinkSync(tmp);

      if (!transcript) {
        // Retry once with a different message
        await ctx.reply("🎙 Could not recognize. Please try speaking clearly.");
        return;
      }

      await ctx.reply(`🎙 *Heard:* _${transcript}_`, { parse_mode: "Markdown" });
      await aiRespond(ctx, transcript);
    } catch (e: any) {
      log.error(`Voice handler: ${e.message}`);
      await ctx.reply("😕 Voice processing error. Try again.");
    }
  });

  // ── VIDEO NOTE (circle) ───────────────────────────────────────────────
  bot.on("message:video_note", async (ctx) => {
    const uid = ctx.from!.id;
    const ct  = ctx.chat!.type as ChatType;
    if (ct !== "private") return;
    Db.ensureUser(uid, ctx.from!.first_name ?? "", ctx.from!.username ?? "");

    await ctx.replyWithChatAction("typing");
    try {
      const file = await ctx.getFile();
      const url  = `https://api.telegram.org/file/bot${process.env.BOT_TOKEN}/${file.file_path}`;
      const res  = await fetch(url);
      const buf  = Buffer.from(await res.arrayBuffer());
      const tmp  = path.join(os.tmpdir(), `nexum_vidnote_${Date.now()}.mp4`);
      fs.writeFileSync(tmp, buf);

      const transcript = await stt(tmp);
      fs.unlinkSync(tmp);

      if (!transcript) {
        await ctx.reply("🎥 Couldn't transcribe the video. Try sending a voice message.");
        return;
      }

      await ctx.reply(`🎥 *Video note:* _${transcript}_`, { parse_mode: "Markdown" });
      await aiRespond(ctx, transcript);
    } catch (e: any) {
      log.error(`Video note: ${e.message}`);
    }
  });

  // ── PHOTO messages ────────────────────────────────────────────────────
  bot.on("message:photo", async (ctx) => {
    const uid = ctx.from!.id;
    const ct  = ctx.chat!.type as ChatType;
    if (ct !== "private") return;
    Db.ensureUser(uid, ctx.from!.first_name ?? "", ctx.from!.username ?? "");

    await ctx.replyWithChatAction("typing");
    try {
      const photos = ctx.message.photo!;
      const best   = photos[photos.length - 1];
      const file   = await ctx.api.getFile(best.file_id);
      const url    = `https://api.telegram.org/file/bot${process.env.BOT_TOKEN}/${file.file_path}`;
      const res    = await fetch(url);
      const buf    = Buffer.from(await res.arrayBuffer());
      const b64    = buf.toString("base64");
      const caption = ctx.message.caption ?? "What's in this image?";

      let analysis = "";
      try {
        analysis = await vision(b64, caption);
      } catch (e: any) {
        // Internal error — log it but don't expose API details to user
        log.error(`Vision error: ${e.message}`);
        // Try to still respond using just the caption
        analysis = "[Image provided by user]";
      }

      const sys  = buildSystemPrompt(uid, ctx.chat!.id, ct, caption);
      const hist = Db.getHistory(uid, ctx.chat!.id, 20);
      const msgs = [
        { role: "system" as const, content: sys },
        ...hist.map(h => ({ role: h.role as "user" | "assistant", content: h.content })),
        { role: "user" as const, content: `[IMAGE ANALYSIS]\n${analysis}\n\nUser: ${caption}` },
      ];

      const resp = await ask(msgs);
      Db.addMsg(uid, ctx.chat!.id, "user", caption);
      Db.addMsg(uid, ctx.chat!.id, "assistant", resp);
      await send(ctx, resp);
    } catch (e: any) {
      log.error(`Photo handler: ${e.message}`);
      await ctx.reply("👁 Couldn't analyze the image. Please try again.");
    }
  });

  // ── STICKER ───────────────────────────────────────────────────────────
  bot.on("message:sticker", async (ctx) => {
    const ct = ctx.chat!.type;
    if (ct !== "private") return;
    const emojis = ["👍", "🔥", "❤️", "😎", "✨", "🤩", "💯"];
    const pick = emojis[Math.floor(Math.random() * emojis.length)];
    // Set reaction on sticker instead of replying with text
    try {
      await (bot.api as any).setMessageReaction({
        chat_id: ctx.chat!.id,
        message_id: ctx.message!.message_id,
        reaction: [{ type: "emoji", emoji: pick }],
        is_big: false,
      });
    } catch {
      // Fallback to reply if reaction fails
      await ctx.reply(pick!).catch(() => {});
    }
  });
}
