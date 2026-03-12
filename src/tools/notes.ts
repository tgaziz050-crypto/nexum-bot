/**
 * NEXUM — Notes Module
 * Multilingual note creation and management
 */
import type { Bot } from "grammy";
import type { BotContext } from "../telegram/bot.js";
import { Db } from "../core/db.js";
import { log } from "../core/logger.js";

export function tryExtractNote(uid: number, text: string): { saved: boolean } {
  // Multilingual triggers
  const notePattern = /^(?:запиши|сохрани как заметку|note:|заметка:|save note|yozib qo'y|not:)\s+(.+)/i;
  const m = notePattern.exec(text);
  if (!m) return { saved: false };

  const content = m[1]!.trim();
  const title   = content.slice(0, 50);
  Db.addNote(uid, title, content, "");
  return { saved: true };
}

export function registerNoteHandlers(bot: Bot<BotContext>) {
  // /note <text> — add note
  bot.command("note", async (ctx) => {
    const uid  = ctx.from!.id;
    const text = ctx.match?.trim();
    if (!text) {
      await ctx.reply("Usage: `/note <note text>`", { parse_mode: "Markdown" });
      return;
    }
    const id = Db.addNote(uid, text.slice(0, 50), text, "");
    await ctx.reply(`📝 Note saved! /n${id} to view`, { parse_mode: "Markdown" });
  });

  // /n{id} — view note
  bot.hears(/^\/n(\d+)$/, async (ctx) => {
    const uid  = ctx.from!.id;
    const id   = parseInt(ctx.match[1]!);
    const note = Db.getNote(uid, id);
    if (!note) { await ctx.reply("❌ Note not found"); return; }
    await ctx.reply(`📌 *${note.title || "Note"}*\n\n${note.content}`, { parse_mode: "Markdown" });
  });

  // /nd{id} — delete note
  bot.hears(/^\/nd(\d+)$/, async (ctx) => {
    const uid = ctx.from!.id;
    const id  = parseInt(ctx.match[1]!);
    Db.deleteNote(uid, id);
    await ctx.reply("🗑 Note deleted.");
  });

  // Note callback queries
  bot.callbackQuery(/^note:(delete|pin):(\d+)$/, async (ctx) => {
    const uid    = ctx.from.id;
    const action = ctx.match[1];
    const id     = parseInt(ctx.match[2]!);

    if (action === "delete") {
      Db.deleteNote(uid, id);
      await ctx.answerCallbackQuery("🗑 Deleted");
      await ctx.deleteMessage().catch(() => {});
    } else if (action === "pin") {
      Db.pinNote(uid, id, true);
      await ctx.answerCallbackQuery("📌 Pinned!");
    }
  });

  log.info("Note handlers registered");
}
