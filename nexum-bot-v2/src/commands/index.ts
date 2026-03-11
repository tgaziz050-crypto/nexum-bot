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
import { log } from "../core/logger.js";

function isAdmin(uid: number) { return Config.ADMIN_IDS.includes(uid); }

export function registerCommands(bot: Bot<BotContext>) {

  bot.command("start", async (ctx) => {
    const uid  = ctx.from!.id;
    const name = ctx.from!.first_name ?? "";
    Db.ensureUser(uid, name, ctx.from!.username ?? "");
    Db.finEnsureDefaults(uid);
    await ctx.reply(
      `👋 Привет${name ? `, ${name}` : ""}! Я **NEXUM**.\n\n` +
      `🧠 Помню всё о тебе\n🌐 Ищу в интернете\n🎤 Понимаю голос\n👁 Анализирую фото\n` +
      `💰 Веду твои финансы\n⏰ Ставлю напоминания\n💻 Управляю ПК\n\n` +
      `Просто пиши — я всё понимаю!`,
      {
        parse_mode: "Markdown",
        reply_markup: {
          keyboard: [
            [{ text: "💰 Finance" }, { text: "📊 Статус" }],
            [{ text: "🧠 Память" }, { text: "⏰ Напоминания" }],
            [{ text: "💻 PC Агент" }, { text: "❓ Помощь" }],
          ],
          resize_keyboard: true,
        },
      }
    );
  });

  bot.command("help", async (ctx) => {
    await ctx.reply(
      `📖 **NEXUM — Команды:**\n\n` +
      `**Основные:**\n` +
      `/start — старт\n/new — новая сессия\n/memory — память\n/forget — очистить\n` +
      `/status — статус\n/id — твой ID\n/brief — дайджест дня\n\n` +
      `**Финансы:**\n` +
      `/finance — Finance App\n/spent — расходы\n/income — доходы\n\n` +
      `**Инструменты:**\n` +
      `/search — поиск\n/remind — напоминание\n/reminders — список\n\n` +
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
    await sendFinanceDashboard(bot, ctx.chat!.id, uid);
  });

  bot.hears("💰 Finance", async (ctx) => {
    const uid = ctx.from!.id;
    Db.ensureUser(uid, ctx.from!.first_name ?? "", ctx.from!.username ?? "");
    await sendFinanceDashboard(bot, ctx.chat!.id, uid);
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
    const mems = Db.getMemories(uid);
    const accs = Db.finGetAccounts(uid);
    const bal  = accs.reduce((s,a)=>s+a.balance,0);

    let text = `📊 **NEXUM Status**\n\n`;
    text += `👤 ${user?.name || "—"} | 💬 ${user?.total_msgs || 0} сообщений\n`;
    text += `🧠 Фактов: ${mems.length} | ⏰ Напоминаний: ${rems.length}\n`;
    text += `💰 Баланс: ${Math.round(bal).toLocaleString("ru-RU")} UZS\n`;
    text += `💻 PC Агент: ${agent ? `✅ ${agent.agent_name}` : "❌ не подключён"}\n`;
    text += `🎤 Голос: ${user?.voice_mode ? "✅ вкл" : "❌ выкл"}`;
    await ctx.reply(text, { parse_mode: "Markdown" });
  });

  bot.hears("📊 Статус", async (ctx) => { await ctx.reply(`/status`); });

  // ── REMINDERS ────────────────────────────────────────────────────────
  bot.command("remind", async (ctx) => {
    const uid    = ctx.from!.id;
    const chatId = ctx.chat!.id;
    const text   = ctx.match?.trim();
    if (!text) { await ctx.reply("📝 Напиши что напомнить: `/remind в 15:00 позвонить Джону`", { parse_mode:"Markdown" }); return; }
    const { date, text: remText } = await parseReminderTime(text);
    if (!date) { await ctx.reply("❓ Не понял время. Попробуй: 'через 30 минут', 'завтра в 10', 'в 15:30'"); return; }
    Db.addReminder(uid, chatId, remText, date);
    const ts = date.toLocaleString("ru", { timeZone:"Asia/Tashkent", dateStyle:"short", timeStyle:"short" });
    await ctx.reply(`✅ Напомню: **${remText}**\n🕐 В ${ts}`, { parse_mode:"Markdown" });
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

  bot.on("callback_query:data", async (ctx) => {
    const data = ctx.callbackQuery.data;
    if (!data.startsWith("rem:")) return;
    const [,action,id] = data.split(":");
    if (action==="cancel") { Db.cancelReminder(+id!, ctx.from.id); await ctx.answerCallbackQuery("✅ Отменено"); }
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
    const top   = Db.getTopUsers().slice(0,5);
    let text = `⚙️ **Admin Panel**\n\n👥 Юзеров: ${stats.users}\n💬 Сообщений: ${stats.messages}\n\n**Топ:**\n`;
    text += top.map(u=>`• ${u.name||u.username||u.uid}: ${u.total_msgs} msg`).join("\n");
    await ctx.reply(text, { parse_mode:"Markdown" });
  });

  bot.command("broadcast", async (ctx) => {
    if (!isAdmin(ctx.from!.id)) return;
    const msg = ctx.match?.trim();
    if (!msg) { await ctx.reply("Напиши сообщение после /broadcast"); return; }
    const users = Db.getTopUsers();
    let sent = 0;
    for (const u of users) {
      try { await (bot.api as any).sendMessage(u.uid, msg); sent++; } catch {}
      await new Promise(r=>setTimeout(r,50));
    }
    await ctx.reply(`✅ Отправлено ${sent}/${users.length}`);
  });

  bot.command("id", async (ctx) => { await ctx.reply(`🆔 \`${ctx.from!.id}\``, { parse_mode:"Markdown" }); });

  bot.hears("❓ Помощь", async (ctx) => {
    await ctx.reply("Напиши /help для списка команд, или просто задай вопрос!");
  });

  log.info("Commands registered");
}
