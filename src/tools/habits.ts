/**
 * NEXUM — Habits Module
 * Трекер привычек: стрики, статистика, AI-анализ
 */
import type { Bot } from "grammy";
import type { BotContext } from "../channels/bot.js";
import { Db } from "../core/db.js";
import { ask } from "../ai/engine.js";
import { log } from "../core/logger.js";

function streak(n: number): string {
  if (n === 0) return "0";
  if (n < 3) return `${n} 🌱`;
  if (n < 7) return `${n} 🔥`;
  if (n < 14) return `${n} 💪`;
  if (n < 30) return `${n} ⚡`;
  return `${n} 🏆`;
}

export function registerHabitHandlers(bot: Bot<BotContext>) {
  // /habits — view all habits
  bot.command("habits", async (ctx) => {
    const uid = ctx.from!.id;
    const habits = Db.getHabits(uid);

    if (!habits.length) {
      await ctx.reply(
        "🎯 *Привычки пусты*\n\nДобавь: `/habit 🏃 Бег`\nили: `/habit 💧 Пить воду каждый день`",
        { parse_mode: "Markdown" }
      );
      return;
    }

    let text = "🎯 *Мои привычки — сегодня:*\n\n";
    const keyboard: any[][] = [];

    for (const h of habits) {
      const doneToday = Db.isHabitDoneToday(h.id);
      const check = doneToday ? "✅" : "⬜";
      text += `${check} ${h.emoji} *${h.name}* — серия: ${streak(h.streak)}\n`;
      if (!doneToday) {
        keyboard.push([{ text: `${h.emoji} Отметить: ${h.name}`, callback_data: `habit:done:${h.id}` }]);
      }
    }

    keyboard.push([
      { text: "📊 AI Анализ", callback_data: "habit:analyze" },
      { text: "🗑 Удалить", callback_data: "habit:manage" },
    ]);

    await ctx.reply(text, {
      parse_mode: "Markdown",
      reply_markup: { inline_keyboard: keyboard },
    });
  });

  // /habit <name> — add habit
  bot.command("habit", async (ctx) => {
    const uid = ctx.from!.id;
    const text = ctx.match?.trim();
    if (!text) {
      await ctx.reply("Добавь привычку: `/habit 🏃 Бег`\nили `/habit 💧 Пить воду`", { parse_mode: "Markdown" });
      return;
    }

    // Extract emoji if present at start
    const emojiMatch = /^(\p{Emoji})\s*/u.exec(text);
    const emoji = emojiMatch ? emojiMatch[1]! : "✅";
    const name = emojiMatch ? text.slice(emojiMatch[0].length).trim() : text;

    if (!name) { await ctx.reply("Напиши название привычки!"); return; }

    const id = Db.addHabit(uid, name, emoji);
    await ctx.reply(
      `${emoji} *${name}* — добавлено!\n\n🎯 Начни сегодня и не ломай серию!\n\n/habits — все привычки`,
      { parse_mode: "Markdown" }
    );
  });

  // Callback handler
  bot.on("callback_query:data", async (ctx) => {
    const data = ctx.callbackQuery.data;
    if (!data.startsWith("habit:")) return;
    const [, action, idStr] = data.split(":");
    const uid = ctx.from.id;

    if (action === "done") {
      const id = parseInt(idStr!);
      const habits = Db.getHabits(uid);
      const habit = habits.find(h => h.id === id);
      if (!habit) { await ctx.answerCallbackQuery("❌ Не найдено"); return; }

      if (Db.isHabitDoneToday(id)) {
        await ctx.answerCallbackQuery("Уже отмечено сегодня! ✅");
        return;
      }

      Db.logHabit(id, uid);
      const updated = Db.getHabits(uid).find(h => h.id === id);
      await ctx.answerCallbackQuery(`${habit.emoji} Отмечено! Серия: ${updated?.streak ?? 1} 🔥`);

      // Edit the message to update checkmarks
      const allHabits = Db.getHabits(uid);
      let text = "🎯 *Мои привычки — сегодня:*\n\n";
      const keyboard: any[][] = [];
      for (const h of allHabits) {
        const doneToday = Db.isHabitDoneToday(h.id);
        const check = doneToday ? "✅" : "⬜";
        text += `${check} ${h.emoji} *${h.name}* — серия: ${streak(h.streak)}\n`;
        if (!doneToday) keyboard.push([{ text: `${h.emoji} Отметить: ${h.name}`, callback_data: `habit:done:${h.id}` }]);
      }
      keyboard.push([{ text: "📊 AI Анализ", callback_data: "habit:analyze" }]);
      await ctx.editMessageText(text, {
        parse_mode: "Markdown",
        reply_markup: { inline_keyboard: keyboard },
      }).catch(() => {});

    } else if (action === "analyze") {
      await ctx.answerCallbackQuery("⏳ Анализирую...");
      const habits = Db.getHabits(uid);
      if (!habits.length) { await ctx.reply("Нет привычек для анализа."); return; }

      const habitsText = habits.map(h =>
        `${h.emoji} ${h.name}: серия ${h.streak} дней, частота: ${h.frequency}`
      ).join("\n");

      const msgs = [
        { role: "system" as const, content: "Ты коуч по продуктивности. Анализируй привычки и давай конкретные советы. Отвечай на языке пользователя." },
        { role: "user" as const, content: `Мои привычки:\n${habitsText}\n\nДай честный анализ и 3 конкретных совета.` },
      ];
      const result = await ask(msgs, "analysis").catch(() => "Не смог проанализировать.");
      await ctx.reply(`📊 *AI Анализ привычек:*\n\n${result}`, { parse_mode: "Markdown" });

    } else if (action === "manage") {
      const habits = Db.getHabits(uid);
      if (!habits.length) { await ctx.answerCallbackQuery("Нет привычек"); return; }
      await ctx.answerCallbackQuery();
      const keyboard = habits.map(h => [
        { text: `🗑 ${h.emoji} ${h.name}`, callback_data: `habit:delete:${h.id}` }
      ]);
      await ctx.reply("Выбери привычку для удаления:", { reply_markup: { inline_keyboard: keyboard } });

    } else if (action === "delete") {
      const id = parseInt(idStr!);
      Db.deleteHabit(uid, id);
      await ctx.answerCallbackQuery("🗑 Удалено");
      await ctx.deleteMessage().catch(() => {});
    }
  });

  log.info("Habit handlers registered");
}

// Daily habit reminder — called from scheduler
export async function sendHabitReminders(bot: any) {
  try {
    const allUsers = Db.getTopUsers();
    for (const user of allUsers) {
      const habits = Db.getHabits(user.uid);
      const incomplete = habits.filter(h => !Db.isHabitDoneToday(h.id));
      if (!incomplete.length) continue;

      const text = `🎯 *Привычки на сегодня:*\n\n` +
        incomplete.map(h => `⬜ ${h.emoji} ${h.name}`).join("\n") +
        `\n\n/habits — отметить выполненные`;

      await bot.api.sendMessage(user.uid, text, { parse_mode: "Markdown" }).catch(() => {});
      await new Promise(r => setTimeout(r, 100));
    }
  } catch (e: any) {
    log.error(`Habit reminders: ${e.message}`);
  }
}
