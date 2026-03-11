import type { Bot } from "grammy";
import type { BotContext } from "../channels/bot.js";
import { Db } from "../core/db.js";
import { Config } from "../core/config.js";
import { send } from "../channels/send.js";
import { webSearch } from "../tools/search.js";
import { parseReminderTime } from "../tools/reminder.js";
import { ask } from "../ai/engine.js";
import { buildSystemPrompt } from "../memory/prompt.js";
import { sendFinanceDashboard } from "../finance/finance.js";
import { generateWebAppToken } from "../webapp/server.js";
import { log } from "../core/logger.js";

function isAdmin(uid: number) { return Config.ADMIN_IDS.includes(uid); }

function getKeyboard(uid: number) {
  const rows: any[] = [
    [{ text: "💰 Finance" }, { text: "📊 Статус" }],
    [{ text: "🧠 Память" }, { text: "⏰ Напоминания" }],
    [{ text: "💻 PC Агент" }, { text: "❓ Помощь" }],
  ];
  if (isAdmin(uid)) rows.push([{ text: "⚙️ Админ" }]);
  return { keyboard: rows, resize_keyboard: true };
}

function getMiniAppBtns(uid: number) {
  if (!Config.WEBAPP_URL) return null;
  const token = generateWebAppToken(uid);
  const base = `${Config.WEBAPP_URL}`;
  const q = `?uid=${uid}&token=${token}`;
  return {
    inline_keyboard: [
      [
        { text: "💰 Finance", web_app: { url: base + q } },
        { text: "📝 Notes", web_app: { url: base + "/notes" + q } },
      ],
      [
        { text: "✅ Tasks", web_app: { url: base + "/tasks" + q } },
        { text: "🎯 Habits", web_app: { url: base + "/habits" + q } },
      ],
    ],
  };
}
function getFinanceBtn(uid: number) {
  if (Config.WEBAPP_URL) {
    const token = generateWebAppToken(uid);
    const url = `${Config.WEBAPP_URL}?uid=${uid}&token=${token}`;
    return { inline_keyboard: [[{ text: "💼 Открыть Finance App", web_app: { url } }]] };
  }
  return null;
}

export function registerCommands(bot: Bot<BotContext>) {

  bot.command("start", async (ctx) => {
    const uid  = ctx.from!.id;
    const name = ctx.from!.first_name ?? "";
    Db.ensureUser(uid, name, ctx.from!.username ?? "");
    Db.finEnsureDefaults(uid);
    const kb = getMiniAppBtns(uid);
    await ctx.reply(
      `👋 Привет${name ? `, ${name}` : ""}! Я **NEXUM**.\n\n` +
      `🧠 Помню всё о тебе\n🌐 Ищу в интернете\n🎤 Понимаю голос\n👁 Анализирую фото\n` +
      `💰 Веду твои финансы\n📝 Заметки · ✅ Задачи · 🎯 Привычки\n⏰ Напоминания · 💻 PC Агент\n\n` +
      `Просто пиши — я всё понимаю!`,
      { parse_mode: "Markdown", reply_markup: getKeyboard(uid) }
    );
    if (kb) {
      await ctx.reply("📱 *Мини-приложения NEXUM:*", { parse_mode: "Markdown", reply_markup: kb });
    }
  });

  bot.command("help", async (ctx) => {
    await ctx.reply(
      `📖 **NEXUM — Команды:**\n\n` +
      `**Основные:**\n` +
      `/start — старт\n/new — новая сессия\n/memory — память\n/forget — очистить\n` +
      `/status — статус\n/id — твой ID\n/brief — дайджест дня\n\n` +
      `**Финансы:**\n` +
      `/finance — обзор финансов\n/history — история транзакций\n/accounts — счета\n/budgets — бюджеты\n/finai — AI анализ\n/spent — расходы\n/income — доходы\n\n` +
      `**Инструменты:**\n` +
      `/search — поиск в сети\n/remind — напоминание\n/reminders — список\n\n` +
      `**PC Агент:**\n` +
      `/node_connect — подключить ПК\n/screenshot — скриншот\n/run — команда\n/sysinfo — инфо`,
      { parse_mode: "Markdown" }
    );
  });

  bot.command(["new", "reset", "clear"], async (ctx) => {
    Db.clearHistory(ctx.from!.id, ctx.chat!.id);
    await ctx.reply("🔄 Начинаем заново!");
  });

  // ── FINANCE ──────────────────────────────────────────────────────────
  bot.command("finance", async (ctx) => {
    const uid = ctx.from!.id;
    Db.ensureUser(uid, ctx.from!.first_name ?? "", ctx.from!.username ?? "");
    Db.finEnsureDefaults(uid);
    const kb = getFinanceBtn(uid);
    if (kb) {
      await ctx.reply("💼 *NEXUM Finance*\n\nОткрой приложение:", { parse_mode: "Markdown", reply_markup: kb });
    } else {
      await sendFinanceDashboard(bot, ctx.chat!.id, uid);
    }
  });

  bot.hears("💰 Finance", async (ctx) => {
    const uid = ctx.from!.id;
    Db.ensureUser(uid, ctx.from!.first_name ?? "", ctx.from!.username ?? "");
    Db.finEnsureDefaults(uid);
    const kb = getFinanceBtn(uid);
    if (kb) {
      await ctx.reply("💼 *NEXUM Finance*\n\nОткрой приложение:", { parse_mode: "Markdown", reply_markup: kb });
    } else {
      await sendFinanceDashboard(bot, ctx.chat!.id, uid);
    }
  });

  bot.command("history", async (ctx) => {
    const uid = ctx.from!.id;
    const txs = Db.finGetTxs(uid, 15);
    if (!txs.length) { await ctx.reply("📋 История пуста."); return; }
    const fmt = (n: number) => Math.round(n).toLocaleString("ru-RU") + " UZS";
    let text = `📋 *Последние транзакции:*\n━━━━━━━━━━━━━━━━━━━━\n\n`;
    for (const tx of txs) {
      const icon = tx.type==="income"?"🟢":tx.type==="transfer"?"🔵":"🔴";
      const sign = tx.type==="income"?"+":tx.type==="transfer"?"⟷":"-";
      const date = new Date(tx.ts).toLocaleDateString("ru",{day:"numeric",month:"short"});
      text += `${icon} ${sign}${fmt(tx.amount)}\n   ${tx.category}${tx.note?" · "+tx.note:""} · _${date}_\n\n`;
    }
    await ctx.reply(text, { parse_mode:"Markdown" });
  });

  bot.command("accounts", async (ctx) => {
    const uid = ctx.from!.id;
    const accs = Db.finGetAccounts(uid);
    const fmt = (n: number, cur = "UZS") => Math.round(n).toLocaleString("ru-RU") + " " + cur;
    let text = `🏦 *Мои счета:*\n━━━━━━━━━━━━━━━━━━━━\n\n`;
    for (const a of accs) text += `${a.icon} *${a.name}*\n   ${fmt(a.balance, a.currency)}\n\n`;
    const total = accs.reduce((s: number, a: any) => s + a.balance, 0);
    text += `━━━━━━━━━━━━━━━━━━━━\n💰 *Итого: ${fmt(total)}*`;
    await ctx.reply(text, { parse_mode:"Markdown" });
  });

  bot.command("budgets", async (ctx) => {
    const uid = ctx.from!.id;
    const from = new Date(new Date().getFullYear(), new Date().getMonth(), 1);
    const budgets = Db.finGetBudgets(uid);
    const cats = Db.finGetByCategory(uid, from);
    const fmt = (n: number) => Math.round(n).toLocaleString("ru-RU") + " UZS";
    let text = `🎯 *Бюджеты на месяц:*\n━━━━━━━━━━━━━━━━━━━━\n\n`;
    if (!budgets.length) {
      text += `Бюджеты не установлены.\n\nНапиши: _"установи бюджет на еду 500000"_`;
    } else {
      for (const b of budgets) {
        const spent = cats.find((c: any) => c.category === b.category)?.total ?? 0;
        const pct = Math.round((spent / b.amount) * 100);
        const bar = Math.min(Math.round(pct / 10), 10);
        const color = pct > 100 ? "🔴" : pct > 75 ? "🟡" : "🟢";
        text += `${color} *${b.category}*\n   ${fmt(spent)} / ${fmt(b.amount)} (${pct}%)\n   ${"▓".repeat(bar)}${"░".repeat(10 - bar)}\n\n`;
      }
    }
    await ctx.reply(text, { parse_mode:"Markdown" });
  });

  bot.command("finai", async (ctx) => {
    const uid = ctx.from!.id;
    await ctx.replyWithChatAction("typing");
    const now = new Date();
    const from = new Date(now.getFullYear(), now.getMonth(), 1);
    const accs = Db.finGetAccounts(uid);
    const { income, expense } = Db.finGetTotalByPeriod(uid, from, now);
    const cats = Db.finGetByCategory(uid, from);
    const bal = accs.reduce((s: number, a: any) => s + a.balance, 0);
    const fmt = (n: number) => Math.round(n).toLocaleString("ru-RU") + " UZS";
    const finData = `Баланс: ${fmt(bal)} | Доходы: ${fmt(income)} | Расходы: ${fmt(expense)} | Категории: ${cats.map((c: any) => `${c.category}:${fmt(c.total)}`).join(", ")}`;
    const sys = buildSystemPrompt(uid, ctx.chat!.id, "private");
    const msgs = [
      { role:"system" as const, content: sys + `\n\n[FINANCE]\n${finData}` },
      { role:"user" as const, content:"Проанализируй мои финансы. Дай конкретные советы. Честно и по делу." },
    ];
    const r = await ask(msgs, "analysis");
    await send(ctx, r);
  });

  bot.command("spent", async (ctx) => {
    const uid = ctx.from!.id;
    const now = new Date();
    const from = new Date(now.getFullYear(), now.getMonth(), 1);
    const { expense } = Db.finGetTotalByPeriod(uid, from, now);
    const cats = Db.finGetByCategory(uid, from);
    let text = `💸 *Расходы за месяц: ${Math.round(expense).toLocaleString("ru-RU")} UZS*\n\n`;
    for (const c of cats.slice(0, 10)) text += `• ${c.category}: ${Math.round(c.total).toLocaleString("ru-RU")}\n`;
    await ctx.reply(text, { parse_mode: "Markdown" });
  });

  // ── MEMORY ───────────────────────────────────────────────────────────
  bot.command(["memory", "mem"], async (ctx) => {
    const uid  = ctx.from!.id;
    const mems = Db.getMemories(uid);
    const lm   = Db.getLongMem(uid);
    if (!mems.length && !Object.keys(lm).length) { await ctx.reply("🧠 Память пуста."); return; }
    let text = "";
    if (mems.length) text += `**Факты:**\n` + mems.slice(0,15).map(m=>`• ${m.value}`).join("\n");
    if (Object.keys(lm).length) text += `\n\n**Долгая память:**\n` + Object.entries(lm).slice(0,10).map(([k,v])=>`• ${k}: ${v}`).join("\n");
    await ctx.reply(text, { parse_mode: "Markdown" });
  });

  bot.hears("🧠 Память", async (ctx) => {
    const uid = ctx.from!.id;
    const mems = Db.getMemories(uid);
    if (!mems.length) { await ctx.reply("🧠 Память пуста."); return; }
    await ctx.reply(mems.slice(0,15).map(m=>`• ${m.value}`).join("\n"));
  });

  bot.command(["forget", "clear_memory"], async (ctx) => {
    const uid = ctx.from!.id;
    Db.clearMemories(uid); Db.clearLongMem(uid);
    await ctx.reply("🗑 Память очищена.");
  });

  // ── STATUS ───────────────────────────────────────────────────────────
  bot.command("status", async (ctx) => {
    const uid  = ctx.from!.id;
    const user = Db.getUser(uid);
    const agent = Db.getAgent(uid);
    const rems = Db.getUserReminders(uid);
    const alarms = Db.getUserAlarms(uid);
    const mems = Db.getMemories(uid);
    const accs = Db.finGetAccounts(uid);
    const tasks = Db.getTasks(uid);
    const habits = Db.getHabits(uid);
    const bal  = accs.reduce((s, a) => s + a.balance, 0);

    let text = `📊 *NEXUM Status*\n\n`;
    text += `👤 ${user?.name || "—"} · 💬 ${user?.total_msgs || 0} сообщений\n`;
    text += `🧠 Фактов: ${mems.length} · ⏰ Напоминаний: ${rems.length}\n`;
    text += `🔔 Будильников: ${alarms.length} · 📋 Задач: ${tasks.length}\n`;
    text += `🎯 Привычек: ${habits.length} · 💰 Баланс: ${Math.round(bal).toLocaleString("ru-RU")} UZS\n`;
    text += `💻 PC Агент: ${agent ? `✅ ${agent.agent_name}` : "❌ не подключён"}\n`;
    text += `🎤 Голос: ${user?.voice_mode ? "✅ вкл" : "❌ выкл"}`;
    await ctx.reply(text, { parse_mode: "Markdown" });
  });

  bot.hears("📊 Статус", async (ctx) => {
    ctx.message = ctx.message;
    const uid  = ctx.from!.id;
    const user = Db.getUser(uid);
    const rems = Db.getUserReminders(uid);
    const mems = Db.getMemories(uid);
    const accs = Db.finGetAccounts(uid);
    const bal  = accs.reduce((s, a) => s + a.balance, 0);
    let text = `📊 *Status*\n👤 ${user?.name || "—"} · ${user?.total_msgs || 0} msg\n`;
    text += `🧠 ${mems.length} фактов · ⏰ ${rems.length} напоминаний\n`;
    text += `💰 ${Math.round(bal).toLocaleString("ru-RU")} UZS`;
    await ctx.reply(text, { parse_mode: "Markdown" });
  });
  bot.hears("⚙️ Админ", async (ctx) => {
    const uid = ctx.from!.id;
    if (!isAdmin(uid)) { await ctx.reply("❌"); return; }
    const stats = Db.getStats();
    const top   = Db.getTopUsers().slice(0, 5);
    let text = `⚙️ *Admin Panel*\n\n👥 Юзеров: ${stats.users}\n💬 Сообщений: ${stats.messages}\n\n*Топ:*\n`;
    text += top.map(u => `• ${u.name || u.username || u.uid}: ${u.total_msgs} msg`).join("\n");
    await ctx.reply(text, { parse_mode: "Markdown" });
  });

  // ── REMINDERS ────────────────────────────────────────────────────────
  bot.command("remind", async (ctx) => {
    const uid    = ctx.from!.id;
    const chatId = ctx.chat!.id;
    const text   = ctx.match?.trim();
    if (!text) { await ctx.reply("📝 Напиши что напомнить: `/remind в 15:00 позвонить Джону`", { parse_mode:"Markdown" }); return; }
    const date = parseReminderTime(text);
    if (!date) { await ctx.reply("❓ Не понял время. Попробуй: 'через 30 минут', 'завтра в 10', 'в 15:30'"); return; }
    Db.addReminder(uid, chatId, text, date);
    const ts = date.toLocaleString("ru", { timeZone:"Asia/Tashkent", dateStyle:"short", timeStyle:"short" });
    await ctx.reply(`✅ Напомню: **${text}**\n🕐 В ${ts}`, { parse_mode:"Markdown" });
  });

  bot.command("reminders", async (ctx) => {
    const rems = Db.getUserReminders(ctx.from!.id);
    if (!rems.length) { await ctx.reply("⏰ Нет активных напоминаний."); return; }
    const kb = { inline_keyboard: rems.map(r => [{ text: `❌ ${r.text.slice(0,30)}`, callback_data:`rem:cancel:${r.id}` }]) };
    const lines = rems.map(r => {
      const t = new Date(r.fire_at).toLocaleString("ru",{dateStyle:"short",timeStyle:"short"});
      return `⏰ ${r.text} — _${t}_`;
    }).join("\n");
    await ctx.reply(lines, { parse_mode:"Markdown", reply_markup:kb });
  });

  bot.hears("⏰ Напоминания", async (ctx) => {
    const rems = Db.getUserReminders(ctx.from!.id);
    if (!rems.length) { await ctx.reply("Нет активных напоминаний."); return; }
    await ctx.reply(rems.map(r=>{ const t=new Date(r.fire_at).toLocaleString("ru",{dateStyle:"short",timeStyle:"short"}); return `⏰ ${r.text} — ${t}`; }).join("\n"));
  });

  // ── SEARCH ───────────────────────────────────────────────────────────
  bot.command("search", async (ctx) => {
    const q = ctx.match?.trim();
    if (!q) { await ctx.reply("🔍 Что ищем?"); return; }
    await ctx.replyWithChatAction("typing");
    const results = await webSearch(q);
    await send(ctx, results || "Ничего не нашёл.");
  });

  // ── BRIEF ────────────────────────────────────────────────────────────
  bot.command("brief", async (ctx) => {
    const uid = ctx.from!.id;
    await ctx.replyWithChatAction("typing");
    const sys  = buildSystemPrompt(uid, ctx.chat!.id, "private");
    const msgs = [
      { role:"system" as const, content: sys },
      { role:"user" as const, content:"Сделай краткий дайджест дня: погода в Ташкенте, курс USD/UZS, мои напоминания на сегодня, краткий совет дня. Коротко и по делу." },
    ];
    const r = await ask(msgs, "analysis");
    await send(ctx, r);
  });

  // ── ADMIN ────────────────────────────────────────────────────────────
  bot.command("admin", async (ctx) => {
    if (!isAdmin(ctx.from!.id)) { await ctx.reply("❌"); return; }
    const stats = Db.getStats();
    const top   = Db.getTopUsers().slice(0, 5);
    let text = `⚙️ *Admin Panel*\n\n👥 Юзеров: ${stats.users}\n💬 Сообщений: ${stats.messages}\n\n*Топ:*\n`;
    text += top.map(u => `• ${u.name || u.username || u.uid}: ${u.total_msgs} msg`).join("\n");
    await ctx.reply(text, {
      parse_mode: "Markdown",
      reply_markup: {
        inline_keyboard: [
          [{ text: "🩺 Health", callback_data: "admin:health" }, { text: "📋 Логи", callback_data: "admin:logs" }],
          [{ text: "📊 Метрики", callback_data: "admin:metrics" }, { text: "🤖 Улучшения", callback_data: "admin:improvements" }],
        ],
      },
    });
  });

  bot.command("health", async (ctx) => {
    if (!isAdmin(ctx.from!.id)) { await ctx.reply("❌"); return; }
    const { getHealthStatus } = await import("../core/heartbeat.js");
    const h = getHealthStatus();
    const upH = Math.floor(h.uptime / 3600);
    const upM = Math.floor((h.uptime % 3600) / 60);
    await ctx.reply(
      `🩺 *NEXUM Health*\n\n` +
      `🤖 Bot: ${h.bot ? "✅" : "❌"}\n` +
      `🧠 AI: ${h.ai ? "✅" : "⚠️"}\n` +
      `💾 DB: ${h.db ? "✅" : "❌"}\n\n` +
      `⏱ Uptime: ${upH}h ${upM}m\n` +
      `📈 Аптайм: ${h.uptimePct}%\n` +
      `🔁 Проверок: ${h.totalChecks} (сбоев: ${h.failedChecks})\n` +
      (h.errors.length ? `\n⚠️ Активные ошибки:\n${h.errors.join("\n")}` : "\n✅ Ошибок нет"),
      { parse_mode: "Markdown" }
    );
  });

  bot.command("logs", async (ctx) => {
    if (!isAdmin(ctx.from!.id)) { await ctx.reply("❌"); return; }
    const errors = Db.getRecentErrors(20);
    if (!errors.length) { await ctx.reply("✅ Ошибок нет."); return; }
    let text = `📋 *Последние ошибки (${errors.length}):*\n\n`;
    for (const e of errors.slice(0, 15)) {
      const time = new Date(e.ts).toLocaleTimeString("ru");
      text += `[${time}] \`${e.module || "?"}\`: ${e.message.slice(0, 80)}\n`;
    }
    await ctx.reply(text, { parse_mode: "Markdown" });
  });

  bot.command("broadcast", async (ctx) => {
    if (!isAdmin(ctx.from!.id)) return;
    const msg = ctx.match?.trim();
    if (!msg) { await ctx.reply("Напиши сообщение после /broadcast"); return; }
    const users = Db.getTopUsers();
    let sent = 0;
    for (const u of users) {
      try { await (bot.api as any).sendMessage(u.uid, msg); sent++; } catch {}
      await new Promise(r => setTimeout(r, 50));
    }
    await ctx.reply(`✅ Отправлено ${sent}/${users.length}`);
  });

  bot.command("id", async (ctx) => { await ctx.reply(`🆔 \`${ctx.from!.id}\``, { parse_mode: "Markdown" }); });

  bot.hears("❓ Помощь", async (ctx) => {
    await ctx.reply(
      `📖 *NEXUM — Полный список:*\n\n` +
      `*Основные:*\n/start /new /memory /forget /status /brief\n\n` +
      `*Финансы:*\n/finance /history /accounts /budgets /finai /spent\n\n` +
      `*Задачи:* /tasks /task\n` +
      `*Заметки:* /notes /note /nsearch\n` +
      `*Привычки:* /habits /habit\n` +
      `*Напоминания:* /remind /reminders\n` +
      `*Будильник:* "разбуди в 7:00" или "будильник в 8:30"\n\n` +
      `*Инструменты:*\n/search /id\n\n` +
      `*PC Агент:*\n/node_connect /screenshot /run /sysinfo`,
      { parse_mode: "Markdown" }
    );
  });

  // ── UNIFIED CALLBACK QUERY HANDLER ─────────────────────────────────
  bot.on("callback_query:data", async (ctx) => {
    const data = ctx.callbackQuery.data;

    // Alarm callbacks
    if (data.startsWith("alarm:")) {
      const [, action, idStr] = data.split(":");
      const id = parseInt(idStr!);
      const uid = ctx.from.id;
      if (action === "confirm") {
        Db.confirmAlarm(id);
        await ctx.answerCallbackQuery("✅ Хорошего дня!");
        await ctx.editMessageText(
          `✅ *Встал!* Отличное начало дня! 💪\n\nБудильник отключён.`,
          { parse_mode: "Markdown" }
        );
      } else if (action === "snooze") {
        Db.snoozeAlarm(id);
        await ctx.answerCallbackQuery("⏱ Ещё 5 минут...");
        await ctx.editMessageText(
          `😴 *Ещё 5 минут...*\n\nЗвоню снова через 5 минут!`,
          { parse_mode: "Markdown" }
        );
      }
      return;
    }

    // Reminder callbacks
    if (data.startsWith("rem:")) {
      const [, action, id] = data.split(":");
      if (action === "cancel") { Db.cancelReminder(+id!, ctx.from.id); await ctx.answerCallbackQuery("✅ Отменено"); }
      return;
    }

    // Admin callbacks
    if (data.startsWith("admin:")) {
      if (!isAdmin(ctx.from.id)) { await ctx.answerCallbackQuery("❌"); return; }
      const action = data.split(":")[1];

      if (action === "health") {
        const { getHealthStatus } = await import("../core/heartbeat.js");
        const h = getHealthStatus();
        const upH = Math.floor(h.uptime / 3600);
        const upM = Math.floor((h.uptime % 3600) / 60);
        await ctx.answerCallbackQuery();
        await ctx.reply(
          `🩺 *Health Check*\n\n🤖 ${h.bot ? "✅" : "❌"} Bot  🧠 ${h.ai ? "✅" : "⚠️"} AI  💾 ${h.db ? "✅" : "❌"} DB\n` +
          `⏱ ${upH}h ${upM}m uptime · ${h.uptimePct}% аптайм`,
          { parse_mode: "Markdown" }
        );
      } else if (action === "logs") {
        const errors = Db.getRecentErrors(10);
        await ctx.answerCallbackQuery();
        if (!errors.length) { await ctx.reply("✅ Ошибок нет."); return; }
        let text = `📋 *Ошибки:*\n\n`;
        for (const e of errors) {
          text += `\`${e.module}\`: ${e.message.slice(0, 60)}\n`;
        }
        await ctx.reply(text, { parse_mode: "Markdown" });
      } else if (action === "metrics") {
        const stats = Db.getStats();
        const users = Db.getTopUsers().slice(0, 5);
        await ctx.answerCallbackQuery();
        await ctx.reply(
          `📊 *Метрики:*\n\n👥 ${stats.users} юзеров · 💬 ${stats.messages} сообщений\n\n*Топ активных:*\n` +
          users.map(u => `• ${u.name || u.uid}: ${u.total_msgs}`).join("\n"),
          { parse_mode: "Markdown" }
        );
      } else if (action === "improvements") {
        const pending = Db.getPendingImprovements();
        await ctx.answerCallbackQuery();
        if (!pending.length) { await ctx.reply("Нет pending улучшений."); return; }
        for (const p of pending) {
          await ctx.reply(
            `🤖 *Предложение #${p.id}*\n\n${p.proposal}`,
            {
              parse_mode: "Markdown",
              reply_markup: {
                inline_keyboard: [[
                  { text: "✅ Применить", callback_data: `improve:approve:${p.id}` },
                  { text: "❌ Отклонить", callback_data: `improve:reject:${p.id}` },
                ]],
              },
            }
          );
        }
      }
      return;
    }

    // Improvement callbacks
    if (data.startsWith("improve:")) {
      if (!isAdmin(ctx.from.id)) { await ctx.answerCallbackQuery("❌"); return; }
      const [, action, idStr] = data.split(":");
      const id = parseInt(idStr!);
      if (action === "approve") {
        Db.resolveImprovement(id, "approved", "");
        await ctx.answerCallbackQuery("✅ Принято к разработке!");
        await ctx.editMessageText(`✅ Предложение #${id} принято.\n\n_Добавлено в очередь разработки._`, { parse_mode: "Markdown" });
      } else if (action === "reject") {
        Db.resolveImprovement(id, "rejected", "");
        await ctx.answerCallbackQuery("❌ Отклонено");
        await ctx.editMessageText(`❌ Предложение #${id} отклонено.`, { parse_mode: "Markdown" });
      }
      return;
    }
  });

  log.info("Commands registered");
}
