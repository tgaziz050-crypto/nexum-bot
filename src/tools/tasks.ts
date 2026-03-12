/**
 * NEXUM — Tasks Module
 * Multilingual: Russian, English, Uzbek, Turkish, Arabic + more
 */
import type { Bot } from "grammy";
import type { BotContext } from "../telegram/bot.js";
import { Db } from "../core/db.js";
import { log } from "../core/logger.js";

const PRIORITY_ICONS = ["", "🔵", "🟡", "🔴", "⚡"];

export async function parseTaskFromText(text: string): Promise<{
  title: string; project: string; priority: number; dueText: string | null
} | null> {
  const lower = text.toLowerCase();
  // Multilingual task triggers
  if (!/задач|todo|task|сделать|нужно|добав|запиш|vazifa|görev|مهمة|ish/i.test(lower)) return null;

  let title = text
    .replace(/^(?:добавь|запиши|создай|задача|task|todo|нужно|сделать|vazifa qo'sh|görev ekle)\s*/i, "")
    .trim();

  let priority = 2;
  if (/срочно|критично|asap|важно|urgent|shoshilinch|acil|عاجل/i.test(text)) priority = 4;
  else if (/высок|high|muhim/i.test(text)) priority = 3;
  else if (/низк|low|kam/i.test(text)) priority = 1;

  let project = "Inbox";

  return { title: title.slice(0, 200), project, priority, dueText: null };
}

export function registerTaskHandlers(bot: Bot<BotContext>) {
  // /tasks — list tasks (handled in commands.ts for webapp, this is fallback)
  // Note: commands.ts already has /tasks - this handles inline callbacks only

  // /task <text> — add task
  bot.command("task", async (ctx) => {
    const uid  = ctx.from!.id;
    const text = ctx.match?.trim();
    if (!text) {
      await ctx.reply("Usage: `/task <task title>`\nExample: `/task buy groceries`", { parse_mode: "Markdown" });
      return;
    }

    let priority = 2;
    if (/срочно|urgent|!!/i.test(text)) priority = 4;
    else if (/важно|important|!/i.test(text)) priority = 3;

    const id   = Db.addTask(uid, text, "", "Inbox", priority);
    const icon = PRIORITY_ICONS[priority]!;
    await ctx.reply(`${icon} Task added ✅\n\n_${text.slice(0, 100)}_\n\n/t${id} to mark done`, { parse_mode: "Markdown" });
  });

  // /t{id} — mark done
  bot.hears(/^\/t(\d+)$/, async (ctx) => {
    const uid  = ctx.from!.id;
    const id   = parseInt(ctx.match[1]!);
    const task = Db.getTask(uid, id);
    if (!task) { await ctx.reply("❌ Task not found"); return; }
    Db.doneTask(uid, id);
    await ctx.reply(`✅ *Done!*\n\n~~${task.title}~~`, { parse_mode: "Markdown" });
  });

  // /td{id} — delete task
  bot.hears(/^\/td(\d+)$/, async (ctx) => {
    const uid = ctx.from!.id;
    const id  = parseInt(ctx.match[1]!);
    Db.deleteTask(uid, id);
    await ctx.reply("🗑 Task deleted.");
  });

  // Task callback queries
  bot.callbackQuery(/^task:(done|delete):(\d+)$/, async (ctx) => {
    const uid    = ctx.from.id;
    const action = ctx.match[1];
    const id     = parseInt(ctx.match[2]!);

    if (action === "done") {
      const task = Db.getTask(uid, id);
      if (task) {
        Db.doneTask(uid, id);
        await ctx.answerCallbackQuery("✅ Done!");
        await ctx.editMessageText(`✅ ~~${task.title}~~`, { parse_mode: "Markdown" }).catch(() => {});
      }
    } else if (action === "delete") {
      Db.deleteTask(uid, id);
      await ctx.answerCallbackQuery("🗑 Deleted");
      await ctx.deleteMessage().catch(() => {});
    }
  });

  log.info("Task handlers registered");
}

export async function tryExtractAndSaveTask(uid: number, chatId: number, text: string): Promise<string | null> {
  const parsed = await parseTaskFromText(text);
  if (!parsed) return null;
  const id   = Db.addTask(uid, parsed.title, "", parsed.project, parsed.priority);
  const icon = PRIORITY_ICONS[parsed.priority]!;
  return `${icon} Task saved: _${parsed.title}_ (/t${id})`;
}
