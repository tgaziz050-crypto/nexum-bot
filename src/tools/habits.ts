/**
 * NEXUM — Habits Module
 * Track habits, streaks, AI analysis. Multilingual.
 */
import type { Bot } from "grammy";
import type { BotContext } from "../telegram/bot.js";
import { Db } from "../core/db.js";
import { ask } from "../agent/engine.js";
import { log } from "../core/logger.js";

function streakLabel(n: number): string {
  if (n === 0) return "0";
  if (n < 3)  return `${n} 🌱`;
  if (n < 7)  return `${n} 🔥`;
  if (n < 14) return `${n} 💪`;
  if (n < 30) return `${n} ⚡`;
  return `${n} 🏆`;
}

export function registerHabitHandlers(bot: Bot<BotContext>) {
  // /habits — view all habits (NOTE: commands.ts opens webapp if available)
  // This handles /habits without webapp URL
  bot.command("habits", async (ctx) => {
    const uid    = ctx.from!.id;
    const habits = Db.getHabits(uid);

    if (!habits.length) {
      await ctx.reply(
        "🎯 *No habits yet*\n\nAdd one: `/habit 🏃 Running`\nor: `/habit 💧 Drink water`",
        { parse_mode: "Markdown" }
      );
      return;
    }

    let text = "🎯 *My habits — today:*\n\n";
    const keyboard: any[][] = [];

    for (const h of habits) {
      const done  = Db.isHabitDoneToday(h.id);
      const check = done ? "✅" : "⬜";
      text += `${check} ${h.emoji} *${h.name}* — streak: ${streakLabel(h.streak)}\n`;
      if (!done) {
        keyboard.push([{ text: `${h.emoji} Done: ${h.name}`, callback_data: `habit:done:${h.id}` }]);
      }
    }

    keyboard.push([
      { text: "📊 AI Analysis", callback_data: "habit:analyze" },
      { text: "🗑 Manage", callback_data: "habit:manage" },
    ]);

    await ctx.reply(text, {
      parse_mode: "Markdown",
      reply_markup: { inline_keyboard: keyboard },
    });
  });

  // /habit <emoji> <name> — add habit
  bot.command("habit", async (ctx) => {
    const uid  = ctx.from!.id;
    const text = ctx.match?.trim();
    if (!text) {
      await ctx.reply("Usage: `/habit 🏃 Running`", { parse_mode: "Markdown" });
      return;
    }

    // Extract emoji if present
    const emojiMatch = /^(\p{Emoji})\s+(.+)/u.exec(text);
    let emoji = "✅";
    let name  = text;
    if (emojiMatch) { emoji = emojiMatch[1]!; name = emojiMatch[2]!.trim(); }

    const id = Db.addHabit(uid, name, emoji);
    await ctx.reply(`${emoji} *${name}* added to habits!\n\nUse /habits to track it.`, { parse_mode: "Markdown" });
  });

  // Habit done callback
  bot.callbackQuery(/^habit:done:(\d+)$/, async (ctx) => {
    const uid     = ctx.from.id;
    const habitId = parseInt(ctx.match[1]!);
    const habits  = Db.getHabits(uid);
    const habit   = habits.find((h: any) => h.id === habitId);

    if (!habit) { await ctx.answerCallbackQuery("Not found"); return; }
    if (Db.isHabitDoneToday(habitId)) {
      await ctx.answerCallbackQuery("Already done today! ✅");
      return;
    }

    Db.logHabit(habitId, uid);
    const newStreak = habit.streak + 1;
    await ctx.answerCallbackQuery(`${habit.emoji} Done! Streak: ${streakLabel(newStreak)}`);

    // Refresh the habits list
    const allHabits = Db.getHabits(uid);
    let text = "🎯 *My habits — today:*\n\n";
    const keyboard: any[][] = [];
    for (const h of allHabits) {
      const done  = Db.isHabitDoneToday(h.id);
      const check = done ? "✅" : "⬜";
      text += `${check} ${h.emoji} *${h.name}* — streak: ${streakLabel(h.streak)}\n`;
      if (!done) keyboard.push([{ text: `${h.emoji} Done: ${h.name}`, callback_data: `habit:done:${h.id}` }]);
    }
    keyboard.push([{ text: "📊 AI Analysis", callback_data: "habit:analyze" }]);
    await ctx.editMessageText(text, { parse_mode: "Markdown", reply_markup: { inline_keyboard: keyboard } }).catch(() => {});
  });

  // Habit AI analysis
  bot.callbackQuery("habit:analyze", async (ctx) => {
    await ctx.answerCallbackQuery("Analyzing...");
    const uid    = ctx.from.id;
    const habits = Db.getHabits(uid);
    if (!habits.length) { await ctx.reply("No habits to analyze."); return; }

    const habitData = habits.map((h: any) =>
      `${h.name}: streak=${h.streak}, emoji=${h.emoji}`
    ).join("; ");

    try {
      const analysis = await ask([{
        role: "user",
        content: `Analyze these habits and give a short motivating analysis with tips. User's habits: ${habitData}. Be encouraging, practical, 3-4 sentences.`
      }], "fast");
      await ctx.reply(`📊 *Habit Analysis*\n\n${analysis}`, { parse_mode: "Markdown" });
    } catch { await ctx.reply("📊 Keep going with your habits! Consistency is key 🔥"); }
  });

  // Habit manage (delete)
  bot.callbackQuery("habit:manage", async (ctx) => {
    await ctx.answerCallbackQuery();
    const uid    = ctx.from.id;
    const habits = Db.getHabits(uid);
    if (!habits.length) { await ctx.editMessageText("No habits.").catch(() => {}); return; }
    const keyboard = habits.map((h: any) => [
      { text: `🗑 ${h.emoji} ${h.name}`, callback_data: `habit:del:${h.id}` }
    ]);
    keyboard.push([{ text: "← Back", callback_data: "habit:back" }]);
    await ctx.editMessageText("🗑 *Delete a habit:*", {
      parse_mode: "Markdown",
      reply_markup: { inline_keyboard: keyboard },
    }).catch(() => {});
  });

  bot.callbackQuery(/^habit:del:(\d+)$/, async (ctx) => {
    const uid     = ctx.from.id;
    const habitId = parseInt(ctx.match[1]!);
    Db.deleteHabit(uid, habitId);
    await ctx.answerCallbackQuery("🗑 Deleted");
    await ctx.deleteMessage().catch(() => {});
  });

  bot.callbackQuery("habit:back", async (ctx) => {
    await ctx.answerCallbackQuery();
    const uid    = ctx.from.id;
    const habits = Db.getHabits(uid);
    let text = "🎯 *My habits:*\n\n";
    const keyboard: any[][] = [];
    for (const h of habits) {
      const done  = Db.isHabitDoneToday(h.id);
      const check = done ? "✅" : "⬜";
      text += `${check} ${h.emoji} *${h.name}* — streak: ${streakLabel(h.streak)}\n`;
      if (!done) keyboard.push([{ text: `${h.emoji} Done: ${h.name}`, callback_data: `habit:done:${h.id}` }]);
    }
    await ctx.editMessageText(text, { parse_mode: "Markdown", reply_markup: { inline_keyboard: keyboard } }).catch(() => {});
  });

  log.info("Habit handlers registered");
}

// Send habit reminders to all users with habits
export async function sendHabitReminders(bot: any) {
  try {
    const users = Db.getTopUsers();
    for (const u of users) {
      try {
        const habits = Db.getHabits(u.uid);
        if (!habits.length) continue;
        const pending = habits.filter((h: any) => !Db.isHabitDoneToday(h.id));
        if (!pending.length) continue;
        const names = pending.map((h: any) => `${h.emoji} ${h.name}`).join(", ");
        await bot.api.sendMessage(u.uid,
          `🎯 *Evening habits check-in!*\n\nNot done yet: ${names}\n\nUse /habits to mark them done.`,
          { parse_mode: "Markdown" }
        );
        await new Promise(r => setTimeout(r, 200));
      } catch {}
    }
  } catch (e: any) { log.error(`Habit reminders: ${e.message}`); }
}
