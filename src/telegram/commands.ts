/**
 * NEXUM v5 — Commands
 * Language-adaptive commands. Responses adapt to user's language automatically.
 * Help button works. PC Agent install instructions included.
 */
import type { Bot } from "grammy";
import type { BotContext } from "./bot.js";
import { Db, DbV5 } from "../core/db.js";
import { Config } from "../core/config.js";
import { send } from "./send.js";
import { webSearch } from "../tools/search.js";
import { parseReminderTime } from "../tools/reminder.js";
import { ask } from "../agent/engine.js";
import { buildSystemPrompt } from "../agent/memory.js";
import { sendFinanceDashboard } from "../tools/finance.js";
import { isAgentOnline, sendToAgent, getAgentInfo } from "../agent/pcagent.js";
import { getHealthStatus } from "../core/heartbeat.js";
import { silenceAlerts } from "../core/heartbeat.js";
import { log } from "../core/logger.js";
import * as crypto from "crypto";

function isAdmin(uid: number) { return Config.ADMIN_IDS.includes(uid); }

function getMiniAppBtns(uid: number) {
  if (!Config.WEBAPP_URL) return null;
  const token = crypto.createHmac("sha256", Config.BOT_TOKEN).update(String(uid)).digest("hex").slice(0, 16);
  const base = Config.WEBAPP_URL;
  const q = `?uid=${uid}&token=${token}`;
  return {
    inline_keyboard: [
      [
        { text: "💰 Finance", web_app: { url: base + q } },
        { text: "📝 Notes",   web_app: { url: base + "/notes" + q } },
      ],
      [
        { text: "✅ Tasks",   web_app: { url: base + "/tasks" + q } },
        { text: "🎯 Habits",  web_app: { url: base + "/habits" + q } },
      ],
    ],
  };
}

async function setupMenuButton(bot: Bot<BotContext>) {
  if (!Config.WEBAPP_URL) return;
  try {
    await (bot.api as any).setChatMenuButton({
      menu_button: {
        type: "web_app",
        text: "📱 Apps",
        web_app: { url: `${Config.WEBAPP_URL}/hub` },
      },
    });
  } catch {}
}

// Detect user language from DB, fallback to "en"
function getUserLang(uid: number): string {
  try {
    const user = Db.getUser(uid);
    return user?.lang ?? "en";
  } catch { return "en"; }
}

// Get localized start message via AI (cached in memory briefly)
const startMsgCache = new Map<string, { text: string; ts: number }>();
async function getLocalizedMsg(key: string, lang: string, fallback: string): Promise<string> {
  const cacheKey = `${key}:${lang}`;
  const cached = startMsgCache.get(cacheKey);
  if (cached && Date.now() - cached.ts < 3_600_000) return cached.text;
  // For non-English/Russian, use AI to translate
  if (lang === "en" || lang === "ru") return fallback;
  try {
    const result = await ask([{
      role: "user",
      content: `Translate this message to ${lang} language naturally. Keep all emojis and formatting:\n\n${fallback}`
    }], "fast");
    if (result?.trim()) {
      startMsgCache.set(cacheKey, { text: result.trim(), ts: Date.now() });
      return result.trim();
    }
  } catch {}
  return fallback;
}

export function registerCommands(bot: Bot<BotContext>) {
  setTimeout(() => setupMenuButton(bot), 3000);

  // ── /start ───────────────────────────────────────────────────────────
  bot.command("start", async (ctx) => {
    const uid  = ctx.from!.id;
    const name = ctx.from!.first_name ?? "";
    Db.ensureUser(uid, name, ctx.from!.username ?? "");
    Db.finEnsureDefaults(uid);

    // Detect language from Telegram interface language
    const tgLang = ctx.from!.language_code ?? "en";
    try {
      const user = Db.getUser(uid);
      if (user && (!user.lang || user.lang === "ru")) {
        // Update lang based on Telegram language_code
        Db.setLang(uid, tgLang.split("-")[0]);
      }
    } catch {}

    const startMsg =
      `👋 Hi${name ? `, ${name}` : ""}! I'm **NEXUM** — your autonomous AI agent.\n\n` +
      `🧠 I remember everything about you\n` +
      `🌐 I search the internet in real time\n` +
      `🎤 I understand voice messages\n` +
      `👁 I analyze photos\n` +
      `💰 Finance · 📝 Notes · ✅ Tasks · 🎯 Habits\n` +
      `⏰ Reminders · 🔔 Alarms\n` +
      `💻 PC Agent — I control your computer\n` +
      `🗺 I plan and execute complex tasks\n\n` +
      `Just write to me — I understand everything!\n` +
      `📱 Apps — button at the bottom left`;

    await ctx.reply(startMsg, {
      parse_mode: "Markdown",
      reply_markup: { remove_keyboard: true },
    });

    if (Config.WEBAPP_URL) {
      const kb = getMiniAppBtns(uid);
      if (kb) await ctx.reply("📱 *NEXUM Apps:*", { parse_mode: "Markdown", reply_markup: kb });
    }
  });

  // ── /apps ────────────────────────────────────────────────────────────
  bot.command("apps", async (ctx) => {
    const uid = ctx.from!.id;
    Db.ensureUser(uid, ctx.from!.first_name ?? "", ctx.from!.username ?? "");
    if (!Config.WEBAPP_URL) {
      await ctx.reply("⚙️ Mini apps are not configured yet. WEBAPP_URL is not set.");
      return;
    }
    const kb = getMiniAppBtns(uid);
    if (kb) await ctx.reply("📱 *NEXUM Apps:*", { parse_mode: "Markdown", reply_markup: kb });
    else await ctx.reply("⚙️ Apps are loading...");
  });

  // ── /help ────────────────────────────────────────────────────────────
  bot.command("help", async (ctx) => {
    const uid = ctx.from!.id;
    Db.ensureUser(uid, ctx.from!.first_name ?? "", ctx.from!.username ?? "");

    const helpText =
      `📖 *NEXUM v${Config.VERSION} — Commands*\n\n` +
      `*Main:*\n` +
      `/start — welcome\n` +
      `/apps — mini applications\n` +
      `/new — new conversation\n` +
      `/memory — what I remember\n` +
      `/forget — clear memory\n` +
      `/status — system status\n` +
      `/brief — daily digest\n\n` +
      `*Finance:*\n` +
      `/finance · /history · /accounts · /budgets\n\n` +
      `*Tasks & Notes:*\n` +
      `/tasks · /task <text>\n` +
      `/notes · /note <text>\n` +
      `/habits\n\n` +
      `*Tools:*\n` +
      `/remind <text> — set reminder\n` +
      `/reminders — list reminders\n` +
      `/search <query>\n\n` +
      `*PC Agent:*\n` +
      `/pc — agent status\n` +
      `/pc_connect — install agent\n` +
      `/link CODE — link device\n` +
      `/screenshot — take screenshot\n` +
      `/run <command> — run on PC\n` +
      `/sysinfo — system info\n\n` +
      `💬 Or just chat with me naturally!`;

    await ctx.reply(helpText, { parse_mode: "Markdown" });
  });

  // ── /new ─────────────────────────────────────────────────────────────
  bot.command(["new", "reset", "clear"], async (ctx) => {
    Db.clearHistory(ctx.from!.id, ctx.chat!.id);
    await ctx.reply("🔄 Starting fresh!");
  });

  // ── /link CODE — device linking ──────────────────────────────────────
  bot.command("link", async (ctx) => {
    const uid  = ctx.from!.id;
    const code = ctx.match?.trim().toUpperCase();
    if (!code) {
      await ctx.reply(
        `🔗 *Link PC Agent*\n\n` +
        `1. Start the agent on your computer\n` +
        `2. Agent will show a 6-char code\n` +
        `3. Send it here: \`/link ABCDEF\``,
        { parse_mode: "Markdown" }
      );
      return;
    }

    const { consumeLinkCode } = await import("../agent/pcagent.js");
    const ok = await consumeLinkCode(uid, code);
    if (ok) {
      await ctx.reply(
        `✅ *Device linked!*\n\nPC Agent is connected to your account.\nUse /pc to control it.`,
        { parse_mode: "Markdown" }
      );
    } else {
      await ctx.reply("❌ Invalid or expired code. Restart the agent to get a new code.");
    }
  });

  // ── /pc — PC agent status and control ────────────────────────────────
  bot.command("pc", async (ctx) => {
    const uid = ctx.from!.id;
    const online = isAgentOnline(uid);
    const agent  = getAgentInfo(uid);
    const devices = DbV5.getLinkedDevices(uid);

    let text = `💻 *PC Agent*\n\n`;
    if (online && agent) {
      text += `🟢 *Online*\n`;
      text += `📟 ${agent.name} (${agent.platform})\n`;
      text += `🛡 Mode: ${agent.mode}\n\n`;
      text += `Commands:\n/screenshot · /sysinfo · /run <command>`;
    } else if (devices.length) {
      text += `🔴 *Device offline*\n\n`;
      for (const d of devices) {
        text += `📟 ${d.device_name} (${d.platform})\n`;
        text += `   Last seen: ${new Date(d.last_seen).toLocaleString("en")}\n`;
      }
      text += `\nStart the agent on your computer.`;
    } else {
      text += `❌ *Not connected*\n\nUse /pc_connect for setup instructions.`;
    }

    await ctx.reply(text, { parse_mode: "Markdown" });
  });

  // ── /pc_connect ───────────────────────────────────────────────────────
  bot.command("pc_connect", async (ctx) => {
    await ctx.reply(
      `💻 *Install PC Agent*\n\n` +
      `**Method 1: Quick install**\n` +
      `1️⃣ Install Python 3.8+\n\n` +
      `2️⃣ Install dependencies:\n` +
      `\`\`\`\npip install websockets pyautogui pillow psutil\n\`\`\`\n\n` +
      `3️⃣ Run the agent:\n` +
      `\`\`\`\npython nexum_agent.py\n\`\`\`\n\n` +
      `4️⃣ Agent shows a 6-char code\n\n` +
      `5️⃣ Send here: \`/link ABCDEF\`\n\n` +
      `📥 *Get agent file:* just write "send agent file" and I'll send it`,
      { parse_mode: "Markdown" }
    );
  });

  // ── /screenshot ──────────────────────────────────────────────────────
  bot.command("screenshot", async (ctx) => {
    const uid = ctx.from!.id;
    if (!isAgentOnline(uid)) {
      await ctx.reply("❌ PC Agent is offline. Start the agent on your computer.");
      return;
    }
    await ctx.reply("📸 Taking screenshot...");
    await sendToAgent(uid, "screenshot", { chatId: ctx.chat!.id });
  });

  // ── /run ─────────────────────────────────────────────────────────────
  bot.command("run", async (ctx) => {
    const uid = ctx.from!.id;
    const cmd = ctx.match?.trim();
    if (!cmd) { await ctx.reply("Usage: /run <command>"); return; }
    if (!isAgentOnline(uid)) { await ctx.reply("❌ PC Agent is offline."); return; }

    const dangerous = /rm\s+-rf|format|del\s+\/|shutdown|mkfs|dd\s+if/i.test(cmd);
    if (dangerous) {
      await ctx.reply(
        `⚠️ *Dangerous command*\n\n\`${cmd}\`\n\nExecute?`,
        {
          parse_mode: "Markdown",
          reply_markup: {
            inline_keyboard: [[
              { text: "✅ Yes, run", callback_data: `pc_run_confirm:${cmd}` },
              { text: "❌ Cancel",   callback_data: "pc_run_cancel" },
            ]],
          },
        }
      );
      return;
    }

    const msg = await ctx.reply(`⚙️ Running: \`${cmd}\``, { parse_mode: "Markdown" });
    const result = await sendToAgent(uid, "run", { command: cmd });
    await ctx.api.editMessageText(ctx.chat!.id, msg.message_id,
      `✅ \`${cmd}\`\n\n\`\`\`\n${(result ?? "No output").slice(0, 2000)}\n\`\`\``,
      { parse_mode: "Markdown" }
    ).catch(() => {});
  });

  bot.callbackQuery("pc_run_cancel", async (ctx) => {
    await ctx.answerCallbackQuery();
    await ctx.editMessageText("❌ Command cancelled.");
  });

  bot.callbackQuery(/^pc_run_confirm:(.+)$/, async (ctx) => {
    await ctx.answerCallbackQuery();
    const uid = ctx.from!.id;
    const cmd = ctx.match[1];
    await ctx.editMessageText(`⚙️ Running: \`${cmd}\``, { parse_mode: "Markdown" });
    const result = await sendToAgent(uid, "run", { command: cmd });
    await ctx.editMessageText(
      `✅ \`${cmd}\`\n\n\`\`\`\n${(result ?? "No output").slice(0, 2000)}\n\`\`\``,
      { parse_mode: "Markdown" }
    ).catch(() => {});
  });

  // ── /sysinfo ─────────────────────────────────────────────────────────
  bot.command("sysinfo", async (ctx) => {
    const uid = ctx.from!.id;
    if (!isAgentOnline(uid)) { await ctx.reply("❌ PC Agent is offline."); return; }
    const info = await sendToAgent(uid, "sysinfo", {});
    await ctx.reply(info ? `💻 *System info:*\n\`\`\`\n${info.slice(0, 1500)}\n\`\`\`` : "❌ No data.", { parse_mode: "Markdown" });
  });

  // ── /finance ─────────────────────────────────────────────────────────
  bot.command("finance", async (ctx) => {
    const uid = ctx.from!.id;
    Db.ensureUser(uid, ctx.from!.first_name ?? "", ctx.from!.username ?? "");
    Db.finEnsureDefaults(uid);
    if (Config.WEBAPP_URL) {
      const token = crypto.createHmac("sha256", Config.BOT_TOKEN).update(String(uid)).digest("hex").slice(0, 16);
      const url = `${Config.WEBAPP_URL}?uid=${uid}&token=${token}`;
      await ctx.reply("💰 *NEXUM Finance*", {
        parse_mode: "Markdown",
        reply_markup: { inline_keyboard: [[{ text: "💰 Open Finance", web_app: { url } }]] },
      });
    } else {
      await sendFinanceDashboard(bot as any, ctx.chat!.id, uid);
    }
  });

  // ── /history ─────────────────────────────────────────────────────────
  bot.command("history", async (ctx) => {
    const uid = ctx.from!.id;
    const txs = Db.finGetTxs(uid, 15);
    if (!txs.length) { await ctx.reply("📋 Transaction history is empty."); return; }
    const fmt = (n: number) => Math.round(n).toLocaleString() + " UZS";
    let text = `📋 *Recent transactions:*\n━━━━━━━━━━━━\n\n`;
    for (const tx of txs) {
      const icon = tx.type === "income" ? "🟢" : tx.type === "transfer" ? "🔵" : "🔴";
      const sign = tx.type === "income" ? "+" : tx.type === "transfer" ? "⟷" : "-";
      const date = new Date(tx.ts).toLocaleDateString("en", { day: "numeric", month: "short" });
      text += `${icon} ${sign}${fmt(tx.amount)}\n   ${tx.category}${tx.note ? " · " + tx.note : ""} · _${date}_\n\n`;
    }
    await ctx.reply(text, { parse_mode: "Markdown" });
  });

  // ── /notes ───────────────────────────────────────────────────────────
  bot.command("notes", async (ctx) => {
    const uid = ctx.from!.id;
    if (Config.WEBAPP_URL) {
      const token = crypto.createHmac("sha256", Config.BOT_TOKEN).update(String(uid)).digest("hex").slice(0, 16);
      const url = `${Config.WEBAPP_URL}/notes?uid=${uid}&token=${token}`;
      await ctx.reply("📝 *Notes*", {
        parse_mode: "Markdown",
        reply_markup: { inline_keyboard: [[{ text: "📝 Open Notes", web_app: { url } }]] },
      });
    } else {
      const notes = Db.getNotes(uid, 10);
      if (!notes.length) { await ctx.reply("📝 No notes yet."); return; }
      const text = notes.slice(0, 8).map((n: any) => `📌 ${n.title}\n${n.content.slice(0, 80)}...`).join("\n\n");
      await ctx.reply(text);
    }
  });

  bot.command("note", async (ctx) => {
    const uid = ctx.from!.id;
    const text = ctx.match?.trim();
    if (!text) { await ctx.reply("Usage: /note <note text>"); return; }
    Db.addNote(uid, text.slice(0, 50), text, "");
    await ctx.reply("📝 Note saved!");
  });

  // ── /tasks ────────────────────────────────────────────────────────────
  bot.command("tasks", async (ctx) => {
    const uid = ctx.from!.id;
    if (Config.WEBAPP_URL) {
      const token = crypto.createHmac("sha256", Config.BOT_TOKEN).update(String(uid)).digest("hex").slice(0, 16);
      const url = `${Config.WEBAPP_URL}/tasks?uid=${uid}&token=${token}`;
      await ctx.reply("✅ *Tasks*", {
        parse_mode: "Markdown",
        reply_markup: { inline_keyboard: [[{ text: "✅ Open Tasks", web_app: { url } }]] },
      });
    } else {
      const tasks = Db.getTasks(uid);
      if (!tasks.length) { await ctx.reply("✅ No tasks yet."); return; }
      const text = tasks.slice(0, 10).map((t: any) => `${t.status === "done" ? "✅" : "⬜"} ${t.title}`).join("\n");
      await ctx.reply(`*My tasks:*\n\n${text}`, { parse_mode: "Markdown" });
    }
  });

  bot.command("task", async (ctx) => {
    const uid = ctx.from!.id;
    const text = ctx.match?.trim();
    if (!text) { await ctx.reply("Usage: /task <task title>"); return; }
    Db.addTask(uid, text);
    await ctx.reply("✅ Task added!");
  });

  // ── /habits ───────────────────────────────────────────────────────────
  bot.command("habits", async (ctx) => {
    const uid = ctx.from!.id;
    if (Config.WEBAPP_URL) {
      const token = crypto.createHmac("sha256", Config.BOT_TOKEN).update(String(uid)).digest("hex").slice(0, 16);
      const url = `${Config.WEBAPP_URL}/habits?uid=${uid}&token=${token}`;
      await ctx.reply("🎯 *Habits*", {
        parse_mode: "Markdown",
        reply_markup: { inline_keyboard: [[{ text: "🎯 Open Habits", web_app: { url } }]] },
      });
    } else {
      const habits = Db.getHabits(uid);
      if (!habits.length) { await ctx.reply("🎯 No habits yet."); return; }
      const text = habits.map((h: any) => `🎯 ${h.name} · ${h.streak ?? 0}🔥`).join("\n");
      await ctx.reply(`*My habits:*\n\n${text}`, { parse_mode: "Markdown" });
    }
  });

  // ── /memory ───────────────────────────────────────────────────────────
  bot.command("memory", async (ctx) => {
    const uid = ctx.from!.id;
    const mems = Db.getMemories(uid);
    const lm   = Db.getLongMem(uid);
    if (!mems.length && !Object.keys(lm).length) {
      await ctx.reply("🧠 Memory is empty. Just chat with me — I'll remember everything important.");
      return;
    }
    let text = `🧠 *What I know about you:*\n\n`;
    for (const m of mems.slice(0, 15)) text += `• ${m.key}: ${m.value}\n`;
    if (Object.keys(lm).length) {
      text += "\n*Long-term memory:*\n";
      for (const [k, v] of Object.entries(lm)) text += `• ${k}: ${v}\n`;
    }
    await ctx.reply(text, { parse_mode: "Markdown" });
  });

  bot.command("forget", async (ctx) => {
    const uid = ctx.from!.id;
    Db.clearMemory(uid);
    await ctx.reply("🧠 Memory cleared.");
  });

  // ── /status ───────────────────────────────────────────────────────────
  bot.command("status", async (ctx) => {
    const uid   = ctx.from!.id;
    const user  = Db.getUser(uid);
    const agent = getAgentInfo(uid);
    const health = getHealthStatus();
    const rems  = Db.getUserReminders(uid);
    const tasks = Db.getTasks(uid);
    const habits = Db.getHabits(uid);

    let text = `📊 *NEXUM Status*\n\n`;
    text += `👤 ${user?.name ?? "User"} · ${user?.total_msgs ?? 0} messages\n`;
    text += `🧠 AI: ${health.ai ? "✅" : "❌"} · DB: ${health.db ? "✅" : "❌"}\n`;
    text += `💻 PC: ${agent ? `✅ ${agent.name}` : "❌ not connected"}\n`;
    text += `⏰ Reminders: ${rems.length}\n`;
    text += `✅ Tasks: ${tasks.length}\n`;
    text += `🎯 Habits: ${habits.length}\n`;
    text += `⏱ Uptime: ${Math.round(health.uptime / 3600)}h ${Math.round((health.uptime % 3600) / 60)}m`;

    await ctx.reply(text, { parse_mode: "Markdown" });
  });

  // ── /remind ───────────────────────────────────────────────────────────
  bot.command("remind", async (ctx) => {
    const uid  = ctx.from!.id;
    const text = ctx.match?.trim();
    if (!text) { await ctx.reply("Usage: /remind in 30 minutes call mom"); return; }
    const fireAt = parseReminderTime(text);
    if (!fireAt) { await ctx.reply("🤔 Couldn't parse time. Example: /remind in 1 hour meeting"); return; }
    Db.addReminder(uid, ctx.chat!.id, text, fireAt);
    await ctx.reply(`⏰ Reminder set for ${fireAt.toLocaleString("en", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" })}`);
  });

  bot.command("reminders", async (ctx) => {
    const uid  = ctx.from!.id;
    const rems = Db.getUserReminders(uid);
    if (!rems.length) { await ctx.reply("⏰ No active reminders."); return; }
    const lines = rems.map(r =>
      `• ${r.text.slice(0, 40)} — ${new Date(r.fire_at).toLocaleString("en", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}`
    ).join("\n");
    await ctx.reply(`⏰ *Reminders:*\n\n${lines}`, {
      parse_mode: "Markdown",
      reply_markup: {
        inline_keyboard: rems.map(r => [{ text: `❌ ${r.text.slice(0, 30)}`, callback_data: `rem:cancel:${r.id}` }]),
      },
    });
  });

  bot.callbackQuery(/^rem:cancel:(\d+)$/, async (ctx) => {
    await ctx.answerCallbackQuery();
    Db.cancelReminder(parseInt(ctx.match[1]), ctx.from!.id);
    await ctx.editMessageText("✅ Reminder deleted.");
  });

  // ── /search ───────────────────────────────────────────────────────────
  bot.command("search", async (ctx) => {
    const query = ctx.match?.trim();
    if (!query) { await ctx.reply("Usage: /search <query>"); return; }
    await ctx.replyWithChatAction("typing");
    try {
      const result = await webSearch(query);
      if (!result) { await ctx.reply("🔍 No results found."); return; }
      const uid = ctx.from!.id;
      const sys = buildSystemPrompt(uid, ctx.chat!.id, "private", query);
      const resp = await ask([
        { role: "system", content: sys },
        { role: "user", content: `[WEB SEARCH]\n${result}\n\nAnswer: ${query}` },
      ]);
      await send(ctx, resp);
    } catch { await ctx.reply("🔍 Search error. Please try again."); }
  });

  // ── /brief ────────────────────────────────────────────────────────────
  bot.command("brief", async (ctx) => {
    const uid    = ctx.from!.id;
    await ctx.replyWithChatAction("typing");
    const rems   = Db.getUserReminders(uid);
    const tasks  = Db.getTasks(uid).filter((t: any) => t.status !== "done").slice(0, 5);
    const habits = Db.getHabits(uid);
    const accs   = Db.finGetAccounts(uid);
    const bal    = accs.reduce((s: number, a: any) => s + a.balance, 0);

    let text = `☀️ *Daily Digest*\n\n`;
    if (rems.length) {
      text += `⏰ *Reminders (${rems.length}):*\n`;
      text += rems.slice(0, 3).map(r => `• ${r.text.slice(0, 50)}`).join("\n") + "\n\n";
    }
    if (tasks.length) {
      text += `📋 *Tasks (${tasks.length}):*\n`;
      text += tasks.map((t: any) => `• ${t.title}`).join("\n") + "\n\n";
    }
    if (habits.length) text += `🎯 *Habits: ${habits.length}* → /habits\n\n`;
    if (accs.length)   text += `💰 *Balance: ${Math.round(bal).toLocaleString()} UZS*`;
    if (!rems.length && !tasks.length && !habits.length) text += "All clear! Great day 🔥";

    await ctx.reply(text, { parse_mode: "Markdown" });
  });

  bot.command("id", async (ctx) => {
    await ctx.reply(`🆔 Your ID: \`${ctx.from!.id}\``, { parse_mode: "Markdown" });
  });

  // ── ADMIN COMMANDS ────────────────────────────────────────────────────
  bot.command("admin", async (ctx) => {
    if (!isAdmin(ctx.from!.id)) { await ctx.reply("🚫 Access denied."); return; }
    const stats = Db.getStats();
    await ctx.reply(
      `⚙️ *Admin Panel*\n\n` +
      `👥 Users: ${stats.users}\n` +
      `💬 Messages: ${stats.messages}\n` +
      `💾 DB: OK`,
      { parse_mode: "Markdown",
        reply_markup: { inline_keyboard: [
          [{ text: "📊 Stats", callback_data: "admin:stats" }, { text: "📋 Logs", callback_data: "admin:logs" }],
          [{ text: "📢 Broadcast", callback_data: "admin:broadcast" }, { text: "👥 Users", callback_data: "admin:users" }],
        ]},
      }
    );
  });

  bot.callbackQuery(/^admin:(.+)$/, async (ctx) => {
    if (!isAdmin(ctx.from!.id)) { await ctx.answerCallbackQuery("🚫"); return; }
    await ctx.answerCallbackQuery();
    const action = ctx.match[1];

    if (action === "stats") {
      const h = getHealthStatus();
      await ctx.editMessageText(
        `📊 *Stats*\n\nAI: ${h.ai ? "✅" : "❌"} · DB: ${h.db ? "✅" : "❌"} · Bot: ${h.bot ? "✅" : "❌"}\n` +
        `Uptime: ${Math.round(h.uptime / 3600)}h\nChecks: ${h.totalChecks} (${h.uptimePct}% OK)`,
        { parse_mode: "Markdown" }
      );
    } else if (action === "logs") {
      const logs = Db.getRecentErrors(5);
      const text = logs.length
        ? logs.map((l: any) => `[${l.module}] ${l.message.slice(0, 80)}`).join("\n")
        : "No recent errors ✅";
      await ctx.editMessageText(`📋 *Recent errors:*\n\n${text}`, { parse_mode: "Markdown" });
    } else if (action === "users") {
      const top = Db.getTopUsers().slice(0, 10);
      const text = top.map((u: any, i: number) => `${i + 1}. ${u.name || u.uid} — ${u.total_msgs} msg`).join("\n");
      await ctx.editMessageText(`👥 *Top users:*\n\n${text}`, { parse_mode: "Markdown" });
    }
  });

  bot.command("stats", async (ctx) => {
    if (!isAdmin(ctx.from!.id)) return;
    const h = getHealthStatus();
    const stats = Db.getStats();
    await ctx.reply(
      `📊 *NEXUM Stats*\n\n` +
      `👥 Users: ${stats.users}\n💬 Messages: ${stats.messages}\n` +
      `⏱ Uptime: ${Math.round(h.uptime / 3600)}h · ${h.uptimePct}% OK\n` +
      `AI: ${h.ai ? "✅" : "❌"} DB: ${h.db ? "✅" : "❌"}`,
      { parse_mode: "Markdown" }
    );
  });

  bot.command("broadcast", async (ctx) => {
    if (!isAdmin(ctx.from!.id)) return;
    const text = ctx.match?.trim();
    if (!text) { await ctx.reply("Usage: /broadcast <message>"); return; }
    const users = Db.getTopUsers();
    let sent = 0;
    for (const u of users) {
      try {
        await bot.api.sendMessage(u.uid, `📢 ${text}`);
        sent++;
        await new Promise(r => setTimeout(r, 50));
      } catch {}
    }
    await ctx.reply(`✅ Sent: ${sent}/${users.length}`);
  });

  bot.command("logs", async (ctx) => {
    if (!isAdmin(ctx.from!.id)) return;
    const logs = Db.getRecentErrors(10);
    const text = logs.length
      ? logs.map((l: any) => `[${l.module}] ${l.message.slice(0, 100)}`).join("\n\n")
      : "No recent errors ✅";
    await ctx.reply(`📋 *Logs:*\n\n${text}`, { parse_mode: "Markdown" });
  });

  bot.command("users", async (ctx) => {
    if (!isAdmin(ctx.from!.id)) return;
    const top = Db.getTopUsers().slice(0, 20);
    const text = top.map((u: any, i: number) => `${i + 1}. ${u.name || "?"} (${u.uid}) — ${u.total_msgs} msg`).join("\n");
    await ctx.reply(`👥 *Users:*\n\n${text}`, { parse_mode: "Markdown" });
  });

  bot.command("restart", async (ctx) => {
    if (!isAdmin(ctx.from!.id)) { await ctx.reply("🚫 Access denied."); return; }
    silenceAlerts(5); // Don't spam alerts during restart
    await ctx.reply("🔄 Restarting in 2 seconds...");
    log.info(`Restart requested by admin ${ctx.from!.id}`);
    setTimeout(() => process.exit(0), 2000);
  });

  // ── DYNAMIC TOOLS COMMANDS ────────────────────────────────────────────────

  // /tools — list all dynamic tools with details
  bot.command("tools", async (ctx) => {
    const { listDynamicTools } = await import("../tools/tool_registry.js");
    const tools = listDynamicTools();
    if (!tools.length) {
      await ctx.reply(
        "🧰 *Dynamic Tools*\n\nНет созданных тулов.\n\nИспользуй `/newtool <описание>` чтобы создать любой тул!\n\nПримеры:\n• `/newtool курс криптовалют в реальном времени`\n• `/newtool конвертация валют`\n• `/newtool погода в любом городе`",
        { parse_mode: "Markdown" }
      );
      return;
    }
    const lines = tools.map((t: any, i: number) => {
      const pkgs = t.packages?.length ? `📦 ${t.packages.join(", ")}` : "📦 built-in only";
      const test = t.testOutput ? `\n   🧪 ${t.testOutput.slice(0, 80)}` : "";
      return `${i + 1}. *${t.name}* v${t.version}\n   ${t.description}\n   📥 ${t.inputSchema}\n   ${pkgs}${test}`;
    });
    await ctx.reply(
      `🧰 *Dynamic Tools (${tools.length})*\n\n${lines.join("\n\n")}\n\n_Все тулы подключены и готовы._`,
      { parse_mode: "Markdown" }
    );
  });

  // /newtool <description> — create a new tool with live progress updates
  bot.command("newtool", async (ctx) => {
    const uid = ctx.from!.id;
    const requirement = ctx.match?.trim();
    if (!requirement) {
      await ctx.reply(
        "Usage: `/newtool <что должен делать тул>`\n\nПримеры:\n• `/newtool курс BTC и ETH в реальном времени`\n• `/newtool конвертировать валюты`\n• `/newtool парсить заголовки новостей`\n• `/newtool отправить HTTP POST на webhook`",
        { parse_mode: "Markdown" }
      );
      return;
    }
    const chatId = ctx.chat!.id;
    const msg = await ctx.reply(
      "🔨 *Разрабатываю новый тул...*\n\n⏳ Генерирую код через AI...",
      { parse_mode: "Markdown" }
    );
    const update = (text: string) =>
      bot.api.editMessageText(chatId, msg.message_id, text, { parse_mode: "Markdown" }).catch(() => {});

    await update("🔨 *Разрабатываю новый тул...*\n\n✅ AI генерирует код...\n⏳ Устанавливаю пакеты и тестирую...");
    const { generateAndRegisterTool } = await import("../tools/tool_registry.js");
    const result = await generateAndRegisterTool(uid, requirement);
    await update(
      result.success
        ? `✅ *Тул создан и подключён!*\n\n${result.message}\n\n_Nexum теперь умеет это делать автоматически._`
        : `❌ *Не удалось создать тул*\n\n${result.message}\n\n_Попробуй переформулировать задачу._`
    );
  });

  // /deltool <n> — disable a tool (admin)
  bot.command("deltool", async (ctx) => {
    if (!isAdmin(ctx.from!.id)) { await ctx.reply("🚫 Только для админов."); return; }
    const name = ctx.match?.trim();
    if (!name) { await ctx.reply("Usage: /deltool <tool_name>"); return; }
    const { disableTool } = await import("../tools/tool_registry.js");
    const ok = disableTool(name);
    await ctx.reply(ok ? `✅ Тул "${name}" отключён.` : `❌ Тул "${name}" не найден.`);
  });

  // /enabletool <n> — re-enable a disabled tool (admin)
  bot.command("enabletool", async (ctx) => {
    if (!isAdmin(ctx.from!.id)) { await ctx.reply("🚫 Только для админов."); return; }
    const name = ctx.match?.trim();
    if (!name) { await ctx.reply("Usage: /enabletool <tool_name>"); return; }
    const { enableTool } = await import("../tools/tool_registry.js");
    const ok = enableTool(name);
    await ctx.reply(ok ? `✅ Тул "${name}" включён.` : `❌ Тул "${name}" не найден.`);
  });

  // /usetool <n> <input> — directly invoke any dynamic tool
  bot.command("usetool", async (ctx) => {
    const parts = (ctx.match?.trim() ?? "").split(" ");
    if (parts.length < 2) {
      await ctx.reply("Usage: `/usetool <tool_name> <input>`\n\nПример: `/usetool crypto_price BTC`", { parse_mode: "Markdown" });
      return;
    }
    const name  = parts[0]!;
    const input = parts.slice(1).join(" ");
    const { hasDynamicTool, executeDynamicTool } = await import("../tools/tool_registry.js");
    if (!hasDynamicTool(name)) {
      await ctx.reply(`❌ Тул "${name}" не найден. /tools — список доступных.`);
      return;
    }
    const msg = await ctx.reply(`⚙️ Запускаю *${name}*...`, { parse_mode: "Markdown" });
    const result = await executeDynamicTool(name, input);
    const text = `${result.success ? "✅" : "❌"} *${name}*\n\n${result.output.slice(0, 3800)}`;
    await bot.api.editMessageText(ctx.chat!.id, msg.message_id, text, { parse_mode: "Markdown" })
      .catch(() => ctx.reply(text, { parse_mode: "Markdown" }));
  });

  // /toolinfo <n> — full details of a specific tool
  bot.command("toolinfo", async (ctx) => {
    const name = ctx.match?.trim();
    if (!name) { await ctx.reply("Usage: /toolinfo <tool_name>"); return; }
    const { getToolInfo } = await import("../tools/tool_registry.js");
    const t = getToolInfo(name);
    if (!t) { await ctx.reply(`❌ Тул "${name}" не найден.`); return; }
    const created = new Date(t.createdAt).toLocaleString("ru");
    await ctx.reply(
      `🔧 *${t.name}* v${t.version}\n\n📝 ${t.description}\n\n📥 Input: ${t.inputSchema}\n📤 Output: ${t.outputSchema}\n📦 Packages: ${t.packages?.join(", ") || "none"}\n🧪 Test: ${t.testOutput || "—"}\n📅 Created: ${created}\n🟢 Status: ${t.enabled ? "active" : "disabled"}`,
      { parse_mode: "Markdown" }
    );
  });
}
