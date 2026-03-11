/**
 * NEXUM v5 — Commands
 * All Telegram commands with PC agent linking and agent controls
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

export function registerCommands(bot: Bot<BotContext>) {
  setTimeout(() => setupMenuButton(bot), 3000);

  // ── /start ───────────────────────────────────────────────────────────
  bot.command("start", async (ctx) => {
    const uid  = ctx.from!.id;
    const name = ctx.from!.first_name ?? "";
    Db.ensureUser(uid, name, ctx.from!.username ?? "");
    Db.finEnsureDefaults(uid);

    await ctx.reply(
      `👋 Привет${name ? `, ${name}` : ""}! Я **NEXUM** — автономный ИИ-агент.\n\n` +
      `🧠 Помню всё о тебе\n` +
      `🌐 Ищу в интернете в реальном времени\n` +
      `🎤 Понимаю голос и кружки\n` +
      `👁 Анализирую фото\n` +
      `💰 Финансы · 📝 Заметки · ✅ Задачи · 🎯 Привычки\n` +
      `⏰ Напоминания · 🔔 Будильники\n` +
      `💻 PC Агент — управляю твоим компьютером\n` +
      `🗺 Планирую и выполняю сложные задачи\n\n` +
      `Просто пиши — я всё понимаю!\n` +
      `📱 Приложения — кнопка *Apps* внизу слева`,
      {
        parse_mode: "Markdown",
        reply_markup: { remove_keyboard: true },
      }
    );

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
      await ctx.reply("⚙️ WEBAPP_URL не настроен. Добавь в Railway Variables.");
      return;
    }
    const kb = getMiniAppBtns(uid);
    if (kb) await ctx.reply("📱 *NEXUM Apps:*", { parse_mode: "Markdown", reply_markup: kb });
  });

  // ── /help ────────────────────────────────────────────────────────────
  bot.command("help", async (ctx) => {
    await ctx.reply(
      `📖 *NEXUM v${Config.VERSION} — Команды:*\n\n` +
      `*Основные:*\n` +
      `/start — приветствие\n` +
      `/apps — все мини-приложения\n` +
      `/new — новая беседа\n` +
      `/memory — моя память\n` +
      `/forget — очистить память\n` +
      `/status — мой статус\n` +
      `/brief — дайджест дня\n\n` +
      `*Финансы:*\n` +
      `/finance · /history · /accounts · /budgets · /finai\n\n` +
      `*Задачи и заметки:*\n` +
      `/tasks · /task текст\n` +
      `/notes · /note текст\n` +
      `/habits\n\n` +
      `*Инструменты:*\n` +
      `/remind текст — напоминание\n` +
      `/reminders — список\n` +
      `/search запрос\n\n` +
      `*PC Агент:*\n` +
      `/pc — статус агента\n` +
      `/pc_connect — инструкция подключения\n` +
      `/link КОД — привязать устройство\n` +
      `/screenshot — скриншот экрана\n` +
      `/run команда — выполнить на ПК\n` +
      `/sysinfo — информация о системе`,
      { parse_mode: "Markdown" }
    );
  });

  // ── /new ─────────────────────────────────────────────────────────────
  bot.command(["new", "reset", "clear"], async (ctx) => {
    Db.clearHistory(ctx.from!.id, ctx.chat!.id);
    await ctx.reply("🔄 Начинаем заново!");
  });

  // ── /link CODE — device linking ──────────────────────────────────────
  bot.command("link", async (ctx) => {
    const uid  = ctx.from!.id;
    const code = ctx.match?.trim().toUpperCase();
    if (!code) {
      await ctx.reply(
        `🔗 *Привязка PC Агента*\n\n` +
        `1. Запусти агент на компьютере\n` +
        `2. Агент покажет 6-символьный код\n` +
        `3. Отправь код сюда: \`/link ABCDEF\``,
        { parse_mode: "Markdown" }
      );
      return;
    }

    const { consumeLinkCode } = await import("../agent/pcagent.js");
    const ok = await consumeLinkCode(uid, code);
    if (ok) {
      await ctx.reply(
        `✅ *Устройство привязано!*\n\n` +
        `PC Agent подключён к аккаунту.\n` +
        `Используй /pc для управления.`,
        { parse_mode: "Markdown" }
      );
    } else {
      await ctx.reply("❌ Неверный или просроченный код. Запусти агент заново.");
    }
  });

  // ── /pc — PC agent status and control ────────────────────────────────
  bot.command("pc", async (ctx) => {
    const uid = ctx.from!.id;
    const online = isAgentOnline(uid);
    const agent = getAgentInfo(uid);
    const devices = DbV5.getLinkedDevices(uid);

    let text = `💻 *PC Агент*\n\n`;
    if (online && agent) {
      text += `🟢 *Онлайн*\n`;
      text += `📟 ${agent.name} (${agent.platform})\n`;
      text += `🛡 Режим: ${agent.mode}\n\n`;
      text += `Команды:\n/screenshot · /sysinfo · /run команда`;
    } else if (devices.length) {
      text += `🔴 *Устройство не в сети*\n\n`;
      for (const d of devices) {
        text += `📟 ${d.device_name} (${d.platform})\n`;
        text += `   Последний раз: ${new Date(d.last_seen).toLocaleString("ru")}\n`;
      }
      text += `\nЗапусти агент на компьютере.`;
    } else {
      text += `❌ *Не подключён*\n\n` +
        `Используй /pc_connect для инструкции подключения.`;
    }

    await ctx.reply(text, { parse_mode: "Markdown" });
  });

  // ── /pc_connect ───────────────────────────────────────────────────────
  bot.command("pc_connect", async (ctx) => {
    await ctx.reply(
      `💻 *Подключение PC Агента*\n\n` +
      `1️⃣ Установи Python 3.8+\n\n` +
      `2️⃣ Установи зависимости:\n` +
      `\`\`\`\npip install websockets pyautogui pillow psutil\n\`\`\`\n\n` +
      `3️⃣ Скачай агент:\n` +
      `\`\`\`\npython nexum_agent.py\n\`\`\`\n\n` +
      `4️⃣ Агент покажет 6-буквенный код\n\n` +
      `5️⃣ Отправь сюда: \`/link ABCDEF\`\n\n` +
      `*Агент скачать:* напиши мне "скачай агент" и я пришлю файл`,
      { parse_mode: "Markdown" }
    );
  });

  // ── /screenshot ──────────────────────────────────────────────────────
  bot.command("screenshot", async (ctx) => {
    const uid = ctx.from!.id;
    if (!isAgentOnline(uid)) {
      await ctx.reply("❌ PC Agent не в сети. Запусти агент на компьютере.");
      return;
    }
    await ctx.reply("📸 Делаю скриншот...");
    await sendToAgent(uid, "screenshot", { chatId: ctx.chat!.id });
  });

  // ── /run ─────────────────────────────────────────────────────────────
  bot.command("run", async (ctx) => {
    const uid = ctx.from!.id;
    const cmd = ctx.match?.trim();
    if (!cmd) { await ctx.reply("Использование: /run команда"); return; }
    if (!isAgentOnline(uid)) {
      await ctx.reply("❌ PC Agent не в сети.");
      return;
    }

    // Sensitive check
    const dangerous = /rm\s+-rf|format|del\s+\/|shutdown|mkfs|dd\s+if/i.test(cmd);
    if (dangerous) {
      await ctx.reply(
        `⚠️ *Опасная команда*\n\n\`${cmd}\`\n\nВыполнить?`,
        {
          parse_mode: "Markdown",
          reply_markup: {
            inline_keyboard: [[
              { text: "✅ Да, выполнить", callback_data: `pc_run_confirm:${cmd}` },
              { text: "❌ Отмена", callback_data: "pc_run_cancel" },
            ]],
          },
        }
      );
      return;
    }

    const msg = await ctx.reply(`⚙️ Выполняю: \`${cmd}\``, { parse_mode: "Markdown" });
    const result = await sendToAgent(uid, "run", { command: cmd });
    await ctx.api.editMessageText(ctx.chat!.id, msg.message_id,
      `✅ \`${cmd}\`\n\n\`\`\`\n${(result ?? "No output").slice(0, 2000)}\n\`\`\``,
      { parse_mode: "Markdown" }
    ).catch(() => {});
  });

  bot.callbackQuery("pc_run_cancel", async (ctx) => {
    await ctx.answerCallbackQuery();
    await ctx.editMessageText("❌ Команда отменена.");
  });

  bot.callbackQuery(/^pc_run_confirm:(.+)$/, async (ctx) => {
    await ctx.answerCallbackQuery();
    const uid = ctx.from!.id;
    const cmd = ctx.match[1];
    await ctx.editMessageText(`⚙️ Выполняю: \`${cmd}\``, { parse_mode: "Markdown" });
    const result = await sendToAgent(uid, "run", { command: cmd });
    await ctx.editMessageText(
      `✅ \`${cmd}\`\n\n\`\`\`\n${(result ?? "No output").slice(0, 2000)}\n\`\`\``,
      { parse_mode: "Markdown" }
    ).catch(() => {});
  });

  // ── /sysinfo ─────────────────────────────────────────────────────────
  bot.command("sysinfo", async (ctx) => {
    const uid = ctx.from!.id;
    if (!isAgentOnline(uid)) {
      await ctx.reply("❌ PC Agent не в сети.");
      return;
    }
    const info = await sendToAgent(uid, "sysinfo", {});
    await ctx.reply(info ? `💻 *Система:*\n\`\`\`\n${info.slice(0, 1500)}\n\`\`\`` : "❌ Нет данных.", { parse_mode: "Markdown" });
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
        reply_markup: { inline_keyboard: [[{ text: "💰 Открыть Finance", web_app: { url } }]] },
      });
    } else {
      await sendFinanceDashboard(bot as any, ctx.chat!.id, uid);
    }
  });

  // Import remaining commands from old file (finance subs, notes, tasks, habits, reminders, search, memory, status, admin)
  // ── /history ─────────────────────────────────────────────────────────
  bot.command("history", async (ctx) => {
    const uid = ctx.from!.id;
    const txs = Db.finGetTxs(uid, 15);
    if (!txs.length) { await ctx.reply("📋 История пуста."); return; }
    const fmt = (n: number) => Math.round(n).toLocaleString("ru-RU") + " UZS";
    let text = `📋 *Последние транзакции:*\n━━━━━━━━━━━━━━━━\n\n`;
    for (const tx of txs) {
      const icon = tx.type === "income" ? "🟢" : tx.type === "transfer" ? "🔵" : "🔴";
      const sign = tx.type === "income" ? "+" : tx.type === "transfer" ? "⟷" : "-";
      const date = new Date(tx.ts).toLocaleDateString("ru", { day: "numeric", month: "short" });
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
        reply_markup: { inline_keyboard: [[{ text: "📝 Открыть Notes", web_app: { url } }]] },
      });
    } else {
      const notes = Db.getNotes(uid, 10);
      if (!notes.length) { await ctx.reply("📝 Заметок нет."); return; }
      const text = notes.slice(0, 8).map((n: any) => `📌 ${n.title}\n${n.content.slice(0, 80)}...`).join("\n\n");
      await ctx.reply(text);
    }
  });

  // ── /note text ────────────────────────────────────────────────────────
  bot.command("note", async (ctx) => {
    const uid = ctx.from!.id;
    const text = ctx.match?.trim();
    if (!text) { await ctx.reply("Использование: /note текст заметки"); return; }
    Db.addNote(uid, text.slice(0, 50), text, "");
    await ctx.reply("📝 Заметка сохранена!");
  });

  // ── /tasks ────────────────────────────────────────────────────────────
  bot.command("tasks", async (ctx) => {
    const uid = ctx.from!.id;
    if (Config.WEBAPP_URL) {
      const token = crypto.createHmac("sha256", Config.BOT_TOKEN).update(String(uid)).digest("hex").slice(0, 16);
      const url = `${Config.WEBAPP_URL}/tasks?uid=${uid}&token=${token}`;
      await ctx.reply("✅ *Tasks*", {
        parse_mode: "Markdown",
        reply_markup: { inline_keyboard: [[{ text: "✅ Открыть Tasks", web_app: { url } }]] },
      });
    } else {
      const tasks = Db.getTasks(uid);
      if (!tasks.length) { await ctx.reply("✅ Задач нет."); return; }
      const text = tasks.slice(0, 10).map((t: any) => `${t.status === "done" ? "✅" : "⬜"} ${t.title}`).join("\n");
      await ctx.reply(`*Мои задачи:*\n\n${text}`, { parse_mode: "Markdown" });
    }
  });

  // ── /task text ────────────────────────────────────────────────────────
  bot.command("task", async (ctx) => {
    const uid = ctx.from!.id;
    const text = ctx.match?.trim();
    if (!text) { await ctx.reply("Использование: /task название задачи"); return; }
    Db.addTask(uid, text);
    await ctx.reply("✅ Задача добавлена!");
  });

  // ── /habits ───────────────────────────────────────────────────────────
  bot.command("habits", async (ctx) => {
    const uid = ctx.from!.id;
    if (Config.WEBAPP_URL) {
      const token = crypto.createHmac("sha256", Config.BOT_TOKEN).update(String(uid)).digest("hex").slice(0, 16);
      const url = `${Config.WEBAPP_URL}/habits?uid=${uid}&token=${token}`;
      await ctx.reply("🎯 *Habits*", {
        parse_mode: "Markdown",
        reply_markup: { inline_keyboard: [[{ text: "🎯 Открыть Habits", web_app: { url } }]] },
      });
    } else {
      const habits = Db.getHabits(uid);
      if (!habits.length) { await ctx.reply("🎯 Привычек нет."); return; }
      const text = habits.map((h: any) => `🎯 ${h.name} · ${h.streak ?? 0}🔥`).join("\n");
      await ctx.reply(`*Мои привычки:*\n\n${text}`, { parse_mode: "Markdown" });
    }
  });

  // ── /memory ───────────────────────────────────────────────────────────
  bot.command("memory", async (ctx) => {
    const uid = ctx.from!.id;
    const mems = Db.getMemories(uid);
    const lm = Db.getLongMem(uid);
    if (!mems.length && !Object.keys(lm).length) {
      await ctx.reply("🧠 Память пуста. Просто общайся со мной — я запомню всё важное.");
      return;
    }
    let text = `🧠 *Что я знаю о тебе:*\n\n`;
    for (const m of mems.slice(0, 15)) text += `• ${m.key}: ${m.value}\n`;
    if (Object.keys(lm).length) {
      text += "\n*Долгосрочная память:*\n";
      for (const [k, v] of Object.entries(lm)) text += `• ${k}: ${v}\n`;
    }
    await ctx.reply(text, { parse_mode: "Markdown" });
  });

  // ── /forget ───────────────────────────────────────────────────────────
  bot.command("forget", async (ctx) => {
    const uid = ctx.from!.id;
    Db.clearMemory(uid);
    await ctx.reply("🧠 Память очищена.");
  });

  // ── /status ───────────────────────────────────────────────────────────
  bot.command("status", async (ctx) => {
    const uid = ctx.from!.id;
    const user = Db.getUser(uid);
    const agent = getAgentInfo(uid);
    const health = getHealthStatus();
    const rems = Db.getUserReminders(uid);
    const tasks = Db.getTasks(uid);
    const habits = Db.getHabits(uid);

    let text = `📊 *Статус NEXUM*\n\n`;
    text += `👤 ${user?.name ?? "Пользователь"} · ${user?.total_msgs ?? 0} сообщений\n`;
    text += `🧠 AI: ${health.ai ? "✅" : "❌"} · БД: ${health.db ? "✅" : "❌"}\n`;
    text += `💻 PC: ${agent ? `✅ ${agent.name}` : "❌ не подключён"}\n`;
    text += `⏰ Напоминаний: ${rems.length}\n`;
    text += `✅ Задач: ${tasks.length}\n`;
    text += `🎯 Привычек: ${habits.length}\n`;
    text += `⏱ Аптайм: ${Math.round(health.uptime / 3600)}ч ${Math.round((health.uptime % 3600) / 60)}м`;

    await ctx.reply(text, { parse_mode: "Markdown" });
  });

  // ── /remind ───────────────────────────────────────────────────────────
  bot.command("remind", async (ctx) => {
    const uid = ctx.from!.id;
    const text = ctx.match?.trim();
    if (!text) { await ctx.reply("Использование: /remind через 30 минут позвонить маме"); return; }
    const fireAt = parseReminderTime(text);
    if (!fireAt) { await ctx.reply("🤔 Не понял время. Пример: /remind через 1 час встреча"); return; }
    Db.addReminder(uid, ctx.chat!.id, text, fireAt);
    await ctx.reply(`⏰ Напоминание установлено на ${fireAt.toLocaleString("ru", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" })}`);
  });

  // ── /reminders ────────────────────────────────────────────────────────
  bot.command("reminders", async (ctx) => {
    const uid = ctx.from!.id;
    const rems = Db.getUserReminders(uid);
    if (!rems.length) { await ctx.reply("⏰ Нет активных напоминаний."); return; }
    const lines = rems.map(r =>
      `• ${r.text.slice(0, 40)} — ${new Date(r.fire_at).toLocaleString("ru", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}`
    ).join("\n");
    await ctx.reply(`⏰ *Напоминания:*\n\n${lines}`, {
      parse_mode: "Markdown",
      reply_markup: {
        inline_keyboard: rems.map(r => [{ text: `❌ ${r.text.slice(0, 30)}`, callback_data: `rem:cancel:${r.id}` }]),
      },
    });
  });

  bot.callbackQuery(/^rem:cancel:(\d+)$/, async (ctx) => {
    await ctx.answerCallbackQuery();
    const uid_rem = ctx.from!.id;
    Db.cancelReminder(parseInt(ctx.match[1]), uid_rem);
    await ctx.editMessageText("✅ Напоминание удалено.");
  });

  // ── /search ───────────────────────────────────────────────────────────
  bot.command("search", async (ctx) => {
    const query = ctx.match?.trim();
    if (!query) { await ctx.reply("Использование: /search запрос"); return; }
    await ctx.replyWithChatAction("typing");
    try {
      const result = await webSearch(query);
      if (!result) { await ctx.reply("🔍 Ничего не найдено."); return; }
      const uid = ctx.from!.id;
      const sys = buildSystemPrompt(uid, ctx.chat!.id, "private", query);
      const resp = await ask([
        { role: "system", content: sys },
        { role: "user", content: `[WEB SEARCH]\n${result}\n\nОтветь на вопрос: ${query}` },
      ]);
      await send(ctx, resp);
    } catch { await ctx.reply("🔍 Ошибка поиска. Проверь SERPER_KEY1 или BRAVE_KEY1."); }
  });

  // ── /brief ────────────────────────────────────────────────────────────
  bot.command("brief", async (ctx) => {
    const uid = ctx.from!.id;
    await ctx.replyWithChatAction("typing");
    const rems   = Db.getUserReminders(uid);
    const tasks  = Db.getTasks(uid).filter((t: any) => t.status !== "done").slice(0, 5);
    const habits = Db.getHabits(uid);
    const accs   = Db.finGetAccounts(uid);
    const bal    = accs.reduce((s: number, a: any) => s + a.balance, 0);

    let text = `☀️ *Дайджест дня*\n\n`;
    if (rems.length) {
      text += `⏰ *Напоминания (${rems.length}):*\n`;
      text += rems.slice(0, 3).map(r => `• ${r.text.slice(0, 50)}`).join("\n") + "\n\n";
    }
    if (tasks.length) {
      text += `📋 *Задачи (${tasks.length}):*\n`;
      text += tasks.map((t: any) => `• ${t.title}`).join("\n") + "\n\n";
    }
    if (habits.length) {
      text += `🎯 *Привычки: ${habits.length}* → /habits\n\n`;
    }
    if (accs.length) {
      text += `💰 *Баланс: ${Math.round(bal).toLocaleString("ru-RU")} UZS*`;
    }

    if (!rems.length && !tasks.length && !habits.length) {
      text += "Всё чисто! Хороший день 🔥";
    }

    await ctx.reply(text, { parse_mode: "Markdown" });
  });

  // ── /id ──────────────────────────────────────────────────────────────
  bot.command("id", async (ctx) => {
    await ctx.reply(`🆔 Твой ID: \`${ctx.from!.id}\``, { parse_mode: "Markdown" });
  });

  // ── ADMIN COMMANDS ────────────────────────────────────────────────────
  bot.command("admin", async (ctx) => {
    if (!isAdmin(ctx.from!.id)) { await ctx.reply("🚫 Нет доступа."); return; }
    const stats = Db.getStats();
    await ctx.reply(
      `⚙️ *Admin Panel*\n\n` +
      `👥 Юзеров: ${stats.users}\n` +
      `💬 Сообщений: ${stats.messages}\n` +
      `💾 БД: OK`,
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
        : "No recent errors";
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
    if (!text) { await ctx.reply("Использование: /broadcast текст сообщения"); return; }
    const users = Db.getTopUsers();
    let sent = 0;
    for (const u of users) {
      try {
        await bot.api.sendMessage(u.uid, `📢 ${text}`);
        sent++;
        await new Promise(r => setTimeout(r, 50));
      } catch {}
    }
    await ctx.reply(`✅ Отправлено: ${sent}/${users.length}`);
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

  // ── /restart ────────────────────────────────────────────────────────────
  bot.command("restart", async (ctx) => {
    if (!isAdmin(ctx.from!.id)) { await ctx.reply("🚫 Нет доступа."); return; }
    await ctx.reply("🔄 Перезапуск через 2 секунды...");
    log.info(`Restart requested by admin ${ctx.from!.id}`);
    setTimeout(() => process.exit(0), 2000);
  });
}
