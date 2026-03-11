/**
 * NEXUM — Notes Module
 * Заметки с тегами, поиском и AI-суммаризацией
 */
import type { Bot } from "grammy";
import type { BotContext } from "../channels/bot.js";
import { Db } from "../core/db.js";
import { ask } from "../ai/engine.js";
import { send } from "../channels/send.js";
import { log } from "../core/logger.js";

export function isNoteRequest(text: string): boolean {
  return /(?:запиш[иь]|сохрани|заметка|note down|remember this|запомни это)\s+(?!меня|что)/i.test(text);
}

export function registerNoteHandlers(bot: Bot<BotContext>) {
  // /notes — list notes
  bot.command("notes", async (ctx) => {
    const uid = ctx.from!.id;
    const notes = Db.getNotes(uid, 10);
    if (!notes.length) {
      await ctx.reply(
        "📝 *Заметки пусты*\n\nДобавь: `/note текст заметки`\nили: _\"запиши: встреча в пятницу в 15:00\"_",
        { parse_mode: "Markdown" }
      );
      return;
    }

    let text = "📝 *Мои заметки:*\n\n";
    for (const n of notes) {
      const pin = n.pinned ? "📌 " : "";
      const tags = n.tags ? ` #${n.tags.split(",").join(" #")}` : "";
      const preview = n.content.slice(0, 60) + (n.content.length > 60 ? "…" : "");
      const date = new Date(n.ts).toLocaleDateString("ru", { day: "numeric", month: "short" });
      text += `${pin}*${n.title || preview}*${tags}\n   _${date}_ · /n${n.id}\n\n`;
    }
    text += "🔍 `/nsearch запрос` — поиск";
    await ctx.reply(text, { parse_mode: "Markdown" });
  });

  // /note <text> — add note
  bot.command("note", async (ctx) => {
    const uid = ctx.from!.id;
    const text = ctx.match?.trim();
    if (!text) { await ctx.reply("Напиши: `/note текст заметки`", { parse_mode: "Markdown" }); return; }

    // Auto-extract title (first line or first 40 chars)
    const lines = text.split("\n");
    const title = lines[0]!.slice(0, 40);
    const content = text;

    // Auto-extract tags with #
    const tags = [...text.matchAll(/#(\w+)/g)].map(m => m[1]).join(",");

    const id = Db.addNote(uid, title, content, tags);
    await ctx.reply(
      `📝 Заметка сохранена!\n\n_${title}_\n\n/n${id} — открыть`,
      {
        parse_mode: "Markdown",
        reply_markup: {
          inline_keyboard: [[
            { text: "📌 Закрепить", callback_data: `note:pin:${id}` },
            { text: "🗑 Удалить", callback_data: `note:delete:${id}` },
          ]],
        },
      }
    );
  });

  // /n{id} — view note
  bot.hears(/^\/n(\d+)$/, async (ctx) => {
    const uid = ctx.from!.id;
    const id = parseInt(ctx.match[1]!);
    const note = Db.getNote(uid, id);
    if (!note) { await ctx.reply("❌ Заметка не найдена"); return; }
    const tags = note.tags ? `\n🏷 #${note.tags.split(",").join(" #")}` : "";
    await ctx.reply(
      `📝 *${note.title || "Заметка"}*${tags}\n\n${note.content}`,
      {
        parse_mode: "Markdown",
        reply_markup: {
          inline_keyboard: [[
            { text: note.pinned ? "📌 Открепить" : "📌 Закрепить", callback_data: `note:${note.pinned ? "unpin" : "pin"}:${id}` },
            { text: "✏️ AI суммари", callback_data: `note:summarize:${id}` },
            { text: "🗑 Удалить", callback_data: `note:delete:${id}` },
          ]],
        },
      }
    );
  });

  // /nsearch <query>
  bot.command("nsearch", async (ctx) => {
    const uid = ctx.from!.id;
    const q = ctx.match?.trim();
    if (!q) { await ctx.reply("🔍 Напиши что искать: `/nsearch встреча`", { parse_mode: "Markdown" }); return; }
    const found = Db.searchNotes(uid, q);
    if (!found.length) { await ctx.reply("🔍 Ничего не найдено."); return; }
    let text = `🔍 Найдено ${found.length}:\n\n`;
    for (const n of found) {
      text += `📝 *${n.title || n.content.slice(0, 40)}* · /n${n.id}\n`;
    }
    await ctx.reply(text, { parse_mode: "Markdown" });
  });

  // Inline keyboard handler
  bot.on("callback_query:data", async (ctx) => {
    const data = ctx.callbackQuery.data;
    if (!data.startsWith("note:")) return;
    const [, action, idStr] = data.split(":");
    const id = parseInt(idStr!);
    const uid = ctx.from.id;

    if (action === "pin") {
      Db.pinNote(uid, id, true);
      await ctx.answerCallbackQuery("📌 Закреплено!");
    } else if (action === "unpin") {
      Db.pinNote(uid, id, false);
      await ctx.answerCallbackQuery("📌 Откреплено");
    } else if (action === "delete") {
      Db.deleteNote(uid, id);
      await ctx.answerCallbackQuery("🗑 Удалено");
      await ctx.deleteMessage().catch(() => {});
    } else if (action === "summarize") {
      const note = Db.getNote(uid, id);
      if (!note) { await ctx.answerCallbackQuery("❌ Не найдено"); return; }
      await ctx.answerCallbackQuery("⏳ Обрабатываю...");
      const msgs = [
        { role: "system" as const, content: "Ты помощник. Кратко суммаризируй заметку в 2-3 предложениях на языке оригинала." },
        { role: "user" as const, content: note.content },
      ];
      const summary = await ask(msgs, "fast").catch(() => "Не смог обработать.");
      await ctx.reply(`📋 *Краткое содержание:*\n\n${summary}`, { parse_mode: "Markdown" });
    }
  });

  log.info("Note handlers registered");
}

// Used by message handler to auto-save notes
export function tryExtractNote(uid: number, text: string): { saved: boolean; title: string } | null {
  if (!isNoteRequest(text)) return null;
  const content = text.replace(/^(?:запиш[иь]|сохрани|note down|remember this|запомни это)\s*/i, "").trim();
  if (content.length < 3) return null;
  const title = content.split("\n")[0]!.slice(0, 40);
  Db.addNote(uid, title, content, "");
  return { saved: true, title };
}
