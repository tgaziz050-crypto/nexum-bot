import type { Bot } from "grammy";
import type { BotContext } from "../channels/bot.js";
import { Db } from "../core/db.js";
import { Config } from "../core/config.js";
import { send } from "../channels/send.js";
import { webSearch } from "../tools/search.js";
import { parseReminderTime } from "../tools/reminder.js";
import { ask } from "../ai/engine.js";
import { buildSystemPrompt } from "../memory/prompt.js";
import { log } from "../core/logger.js";

function isAdmin(uid: number): boolean {
  return Config.ADMIN_IDS.includes(uid);
}

export function registerCommands(bot: Bot<BotContext>) {

  // ── /start ─────────────────────────────────────────────────────────
  bot.command("start", async (ctx) => {
    const uid  = ctx.from!.id;
    const name = ctx.from!.first_name ?? "";
    Db.ensureUser(uid, name, ctx.from!.username ?? "");
    await ctx.reply(
      `👋 Привет${name ? `, ${name}` : ""}! Я **NEXUM** — твой личный AI.\n\n` +
      `🧠 Помню всё о тебе\n` +
      `🌐 Ищу в интернете\n` +
      `🎤 Понимаю и отвечаю голосом\n` +
      `👁 Анализирую фото\n` +
      `⏰ Ставлю напоминания\n` +
      `💻 Управляю твоим компьютером\n\n` +
      `Просто пиши — я всё понимаю!`,
      { parse_mode: "Markdown" }
    );
  });

  // ── /help ──────────────────────────────────────────────────────────
  bot.command("help", async (ctx) => {
    await ctx.reply(
      `📖 **Команды NEXUM v1:**\n\n` +
      `/start — приветствие\n` +
      `/new — новая сессия\n` +
      `/memory — посмотреть память\n` +
      `/forget — очистить память\n` +
      `/search [запрос] — поиск\n` +
      `/remind [текст] — напоминание\n` +
      `/reminders — список напоминаний\n` +
      `/status — статус бота\n` +
      `/id — твой Telegram ID\n` +
      `/brief — дайджест дня\n\n` +
      `**PC Агент:**\n` +
      `/node_connect — подключить ПК\n` +
      `/run [команда] — выполнить команду\n` +
      `/screenshot — скриншот экрана\n` +
      `/sysinfo — статистика системы`,
      { parse_mode: "Markdown" }
    );
  });

  // ── /new /reset ────────────────────────────────────────────────────
  bot.command(["new", "reset", "clear"], async (ctx) => {
    const uid    = ctx.from!.id;
    const chatId = ctx.chat!.id;
    Db.clearHistory(uid, chatId);
    await ctx.reply("🔄 История очищена. Начинаем заново!");
  });

  // ── /memory ────────────────────────────────────────────────────────
  bot.command(["memory", "mem"], async (ctx) => {
    const uid  = ctx.from!.id;
    const mems = Db.getMemories(uid);
    const lm   = Db.getLongMem(uid);
    if (!mems.length && !Object.keys(lm).length) {
      await ctx.reply("🧠 Память пуста. Расскажи о себе!");
      return;
    }
    const lines = [
      mems.length
        ? `**Факты (${mems.length}):**\n` + mems.slice(0, 15).map(m => `• [${m.category}] ${m.value}`).join("\n")
        : "",
      Object.keys(lm).length
        ? `\n**Долгосрочная память:**\n` + Object.entries(lm).slice(0, 10).map(([k, v]) => `• ${k}: ${v}`).join("\n")
        : "",
    ].filter(Boolean);
    await send(ctx, lines.join("\n"));
  });

  // ── /forget ────────────────────────────────────────────────────────
  bot.command("forget", async (ctx) => {
    const uid = ctx.from!.id;
    Db.clearMemories(uid);
    Db.clearLongMem(uid);
    await ctx.reply("🗑 Память очищена полностью.");
  });

  // ── /search ────────────────────────────────────────────────────────
  bot.command("search", async (ctx) => {
    const uid    = ctx.from!.id;
    const chatId = ctx.chat!.id;
    const query  = ctx.match?.trim();
    if (!query) { await ctx.reply("🔍 Напиши: `/search запрос`", { parse_mode: "Markdown" }); return; }
    await ctx.replyWithChatAction("typing");
    const results = await webSearch(query);
    if (!results) { await ctx.reply("😕 Ничего не нашёл."); return; }
    const sys    = buildSystemPrompt(uid, chatId, "private");
    const answer = await ask([
      { role: "system", content: sys },
      { role: "user", content: `Web results for "${query}":\n\n${results}\n\nAnswer based on these results. Use user's language.` },
    ]);
    await send(ctx, answer);
  });

  // ── /remind ────────────────────────────────────────────────────────
  bot.command(["remind", "reminder"], async (ctx) => {
    const uid    = ctx.from!.id;
    const chatId = ctx.chat!.id;
    const text   = ctx.match?.trim();
    if (!text) {
      await ctx.reply(
        "⏰ **Напоминания:**\n\n" +
        "`/remind позвонить маме через 30 мин`\n" +
        "`/remind встреча через 2 часа`\n" +
        "`/remind проверить почту в 15:00`\n" +
        "`/remind купить молоко завтра`",
        { parse_mode: "Markdown" }
      );
      return;
    }
    const fireAt = parseReminderTime(text);
    if (!fireAt) {
      await ctx.reply("❌ Не понял время. Укажи: `через 30 мин`, `в 15:00`, `завтра в 9:00`", { parse_mode: "Markdown" });
      return;
    }
    const remText = text.replace(/через .+|в \d+:\d+|завтра.*|in .+|at \d+:\d+/i, "").trim() || text;
    Db.addReminder(uid, chatId, remText, fireAt);
    const timeStr = fireAt.toLocaleString("ru", { timeZone: "Asia/Tashkent", dateStyle: "short", timeStyle: "short" });
    await ctx.reply(`✅ Напомню: **${remText}**\n🕐 В ${timeStr}`, { parse_mode: "Markdown" });
  });

  // ── /reminders ─────────────────────────────────────────────────────
  bot.command("reminders", async (ctx) => {
    const uid  = ctx.from!.id;
    const rems = Db.getUserReminders(uid);
    if (!rems.length) { await ctx.reply("⏰ Нет активных напоминаний."); return; }
    const lines = rems.map((r, i) => {
      const t = new Date(r.fire_at).toLocaleString("ru", { dateStyle: "short", timeStyle: "short" });
      return `${i + 1}. ${r.text} — **${t}** (ID: ${r.id})`;
    });
    await ctx.reply(`⏰ **Напоминания:**\n\n${lines.join("\n")}\n\nОтменить: \`/remind_cancel ID\``, { parse_mode: "Markdown" });
  });

  bot.command("remind_cancel", async (ctx) => {
    const uid = ctx.from!.id;
    const id  = parseInt(ctx.match?.trim() ?? "");
    if (!id) { await ctx.reply("Напиши: `/remind_cancel ID`", { parse_mode: "Markdown" }); return; }
    Db.cancelReminder(id, uid);
    await ctx.reply(`✅ Напоминание #${id} отменено.`);
  });

  // ── /status ────────────────────────────────────────────────────────
  bot.command("status", async (ctx) => {
    const uid    = ctx.from!.id;
    const chatId = ctx.chat!.id;
    const user   = Db.getUser(uid);
    const mems   = Db.getMemories(uid);
    const hist   = Db.historyCount(uid, chatId);
    const rems   = Db.getUserReminders(uid);

    const providers = [
      Config.CEREBRAS_KEYS.length   ? `✅ Cerebras (${Config.CEREBRAS_KEYS.length})` : null,
      Config.GROQ_KEYS.length       ? `✅ Groq (${Config.GROQ_KEYS.length})` : null,
      Config.GEMINI_KEYS.length     ? `✅ Gemini (${Config.GEMINI_KEYS.length})` : null,
      Config.DEEPSEEK_KEYS.length   ? `✅ DeepSeek (${Config.DEEPSEEK_KEYS.length})` : null,
      Config.OPENROUTER_KEYS.length ? `✅ OpenRouter (${Config.OPENROUTER_KEYS.length})` : null,
      Config.CLAUDE_KEYS.length     ? `✅ Claude (${Config.CLAUDE_KEYS.length})` : null,
    ].filter(Boolean);

    await ctx.reply(
      `📊 **NEXUM v1**\n\n` +
      `👤 ${user?.name || "Аноним"} | Сообщений: ${user?.total_msgs ?? 0}\n` +
      `🧠 Фактов в памяти: ${mems.length}\n` +
      `💬 В истории: ${hist}\n` +
      `⏰ Напоминаний: ${rems.length}\n\n` +
      `**AI провайдеры:**\n${providers.join("\n") || "❌ Нет ключей"}`,
      { parse_mode: "Markdown" }
    );
  });

  // ── /id ────────────────────────────────────────────────────────────
  bot.command(["id", "myid"], async (ctx) => {
    await ctx.reply(
      `🆔 **Telegram ID:** \`${ctx.from!.id}\`\n💬 **Chat ID:** \`${ctx.chat!.id}\``,
      { parse_mode: "Markdown" }
    );
  });

  // ── /brief ─────────────────────────────────────────────────────────
  bot.command(["brief", "digest"], async (ctx) => {
    const uid  = ctx.from!.id;
    const logs = Db.getDailyLogs(uid, 1);
    if (!logs.length) { await ctx.reply("📅 Сегодня пока ничего."); return; }
    await ctx.replyWithChatAction("typing");
    const answer = await ask([{
      role: "user",
      content: `Daily summary in 3-5 bullets, in user's language:\n${logs.slice(-20).join("\n")}`,
    }]);
    await send(ctx, `📅 **Дайджест:**\n\n${answer}`);
  });

  // ══════════════════════════════════════════════════════════════════
  // ADMIN КОМАНДЫ — только для ADMIN_IDS
  // ══════════════════════════════════════════════════════════════════

  // ── /admin ─────────────────────────────────────────────────────────
  bot.command("admin", async (ctx) => {
    if (!isAdmin(ctx.from!.id)) return;
    const stats = Db.getStats();
    await ctx.reply(
      `🔧 **Admin Panel — NEXUM v1**\n\n` +
      `👥 Пользователей: ${stats.users}\n` +
      `💬 Сообщений всего: ${stats.messages}\n\n` +
      `**Команды:**\n` +
      `/admin_users — топ пользователей\n` +
      `/admin_ban [uid] — забанить\n` +
      `/admin_unban [uid] — разбанить\n` +
      `/admin_broadcast [текст] — рассылка`,
      { parse_mode: "Markdown" }
    );
  });

  // ── /admin_users ───────────────────────────────────────────────────
  bot.command("admin_users", async (ctx) => {
    if (!isAdmin(ctx.from!.id)) return;
    const users = Db.getTopUsers();
    const lines = users.map((u, i) =>
      `${i + 1}. ${u.name || "?"} (@${u.username || "?"}) — ${u.total_msgs} сообщ. | ID: \`${u.uid}\``
    );
    await ctx.reply(`👥 **Топ пользователей:**\n\n${lines.join("\n")}`, { parse_mode: "Markdown" });
  });

  // ── /admin_ban ─────────────────────────────────────────────────────
  bot.command("admin_ban", async (ctx) => {
    if (!isAdmin(ctx.from!.id)) return;
    const uid = parseInt(ctx.match?.trim() ?? "");
    if (!uid) { await ctx.reply("Укажи ID: `/admin_ban 123456`", { parse_mode: "Markdown" }); return; }
    if (isAdmin(uid)) { await ctx.reply("❌ Нельзя забанить администратора."); return; }
    Db.banUser(uid);
    await ctx.reply(`✅ Пользователь ${uid} заблокирован.`);
    log.warn(`Admin ban: uid=${uid} by admin=${ctx.from!.id}`);
  });

  // ── /admin_unban ───────────────────────────────────────────────────
  bot.command("admin_unban", async (ctx) => {
    if (!isAdmin(ctx.from!.id)) return;
    const uid = parseInt(ctx.match?.trim() ?? "");
    if (!uid) { await ctx.reply("Укажи ID: `/admin_unban 123456`", { parse_mode: "Markdown" }); return; }
    Db.unbanUser(uid);
    await ctx.reply(`✅ Пользователь ${uid} разблокирован.`);
  });

  // ── /admin_broadcast ───────────────────────────────────────────────
  bot.command("admin_broadcast", async (ctx) => {
    if (!isAdmin(ctx.from!.id)) return;
    const text = ctx.match?.trim();
    if (!text) { await ctx.reply("Укажи текст: `/admin_broadcast Привет всем!`", { parse_mode: "Markdown" }); return; }
    const users = Db.getTopUsers();
    let sent = 0, failed = 0;
    for (const u of users) {
      try {
        await bot.api.sendMessage(u.uid, `📢 ${text}`);
        sent++;
        await new Promise(r => setTimeout(r, 50)); // Rate limit
      } catch { failed++; }
    }
    await ctx.reply(`📢 Рассылка завершена: ✅ ${sent} / ❌ ${failed}`);
  });

  log.info("Commands registered");
}
