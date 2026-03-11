/**
 * NEXUM — Tasks Module
 * Управление задачами: создание, статус, приоритеты
 */
import type { Bot } from "grammy";
import type { BotContext } from "../telegram/bot.js";
import { Db } from "../core/db.js";
import { ask } from "../agent/engine.js";
import { send } from "../telegram/send.js";
import { log } from "../core/logger.js";

const PRIORITY_ICONS = ["", "🔵", "🟡", "🔴", "⚡"];
const PRIORITY_NAMES = ["", "низкий", "средний", "высокий", "критический"];

export async function parseTaskFromText(text: string): Promise<{
  title: string; project: string; priority: number; dueText: string | null
} | null> {
  const lower = text.toLowerCase();
  if (!/задач|todo|task|сделать|нужно|добав[ьи]|запиш[иь]|напомн/i.test(lower)) return null;

  // Quick parse
  let title = text
    .replace(/^(?:добавь|запиши|создай|новая|задача|task|todo|нужно|сделать)\s*/i, "")
    .trim();

  let priority = 2;
  if (/срочно|критично|asap|важно/i.test(text)) priority = 4;
  else if (/высок/i.test(text)) priority = 3;
  else if (/низк/i.test(text)) priority = 1;

  let project = "Inbox";
  const projMatch = /(?:проект|project|в|for)\s+"?([a-zA-Zа-яёА-ЯЁ0-9\s]+)"?/i.exec(text);
  if (projMatch) project = projMatch[1]!.trim();

  let dueText: string | null = null;
  const dueMatch = /(?:до|к|by|deadline)\s+([\w\s:]+)/i.exec(text);
  if (dueMatch) dueText = dueMatch[1]!.trim();

  return { title: title.slice(0, 200), project, priority, dueText };
}

export function registerTaskHandlers(bot: Bot<BotContext>) {
  // /tasks — list tasks
  bot.command("tasks", async (ctx) => {
    const uid = ctx.from!.id;
    const tasks = Db.getTasks(uid);
    if (!tasks.length) {
      await ctx.reply(
        "📋 *Задачи пусты*\n\nДобавь: `/task купить молоко`\nили просто напиши: _\"добавь задачу позвонить врачу\"_",
        { parse_mode: "Markdown" }
      );
      return;
    }

    // Group by project
    const byProject: Record<string, any[]> = {};
    for (const t of tasks) {
      if (!byProject[t.project]) byProject[t.project] = [];
      byProject[t.project]!.push(t);
    }

    let text = "📋 *Мои задачи:*\n\n";
    for (const [proj, items] of Object.entries(byProject)) {
      text += `📁 *${proj}*\n`;
      for (const t of items) {
        const icon = PRIORITY_ICONS[t.priority] ?? "⚪";
        const due = t.due_at ? ` · 📅 ${new Date(t.due_at).toLocaleDateString("ru")}` : "";
        text += `${icon} ${t.title}${due} /t${t.id}\n`;
      }
      text += "\n";
    }
    text += "_/t{id} — завершить, /td{id} — удалить_";
    await ctx.reply(text, { parse_mode: "Markdown" });
  });

  // /task <text> — add task
  bot.command("task", async (ctx) => {
    const uid = ctx.from!.id;
    const text = ctx.match?.trim();
    if (!text) { await ctx.reply("Напиши задачу: `/task купить молоко`", { parse_mode: "Markdown" }); return; }

    let priority = 2;
    if (/срочно|!!/i.test(text)) priority = 4;
    else if (/важно|!/i.test(text)) priority = 3;

    const id = Db.addTask(uid, text, "", "Inbox", priority);
    const icon = PRIORITY_ICONS[priority]!;
    await ctx.reply(`${icon} Задача добавлена ✅\n\n_${text}_\n\n/t${id} — завершить`, { parse_mode: "Markdown" });
  });

  // /t{id} — mark done
  bot.hears(/^\/t(\d+)$/, async (ctx) => {
    const uid = ctx.from!.id;
    const id = parseInt(ctx.match[1]!);
    const task = Db.getTask(uid, id);
    if (!task) { await ctx.reply("❌ Задача не найдена"); return; }
    Db.doneTask(uid, id);
    await ctx.reply(`✅ *Выполнено!*\n\n~~${task.title}~~`, { parse_mode: "Markdown" });
  });

  // /td{id} — delete task
  bot.hears(/^\/td(\d+)$/, async (ctx) => {
    const uid = ctx.from!.id;
    const id = parseInt(ctx.match[1]!);
    Db.deleteTask(uid, id);
    await ctx.reply("🗑 Задача удалена.");
  });

  // Inline keyboard handler for task actions
  bot.on("callback_query:data", async (ctx) => {
    const data = ctx.callbackQuery.data;
    if (!data.startsWith("task:")) return;
    const [, action, idStr] = data.split(":");
    const id = parseInt(idStr!);
    const uid = ctx.from.id;

    if (action === "done") {
      const task = Db.getTask(uid, id);
      if (task) {
        Db.doneTask(uid, id);
        await ctx.answerCallbackQuery("✅ Выполнено!");
        await ctx.editMessageText(`✅ ~~${task.title}~~`, { parse_mode: "Markdown" });
      }
    } else if (action === "delete") {
      Db.deleteTask(uid, id);
      await ctx.answerCallbackQuery("🗑 Удалено");
      await ctx.deleteMessage().catch(() => {});
    }
  });

  log.info("Task handlers registered");
}

// AI-powered task extraction used by handler.ts
export async function tryExtractAndSaveTask(uid: number, chatId: number, text: string): Promise<string | null> {
  const parsed = await parseTaskFromText(text);
  if (!parsed) return null;
  const id = Db.addTask(uid, parsed.title, "", parsed.project, parsed.priority);
  const icon = PRIORITY_ICONS[parsed.priority]!;
  return `${icon} Записал в задачи: _${parsed.title}_ (/t${id})`;
}
