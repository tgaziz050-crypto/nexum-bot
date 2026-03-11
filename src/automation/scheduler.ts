import cron from "node-cron";
import { Db } from "../core/db.js";
import { ask } from "../ai/engine.js";
import { log } from "../core/logger.js";
import { sendHabitReminders } from "../tools/habits.js";
import { runSelfImprovement } from "../core/self_improve.js";

export function startScheduler(bot: any) {
  // Daily digest — 9:00 AM Tashkent (UTC+5 = 4:00 UTC)
  cron.schedule("0 4 * * *", async () => {
    log.info("Daily digest running...");
    try {
      const users = Db.getTopUsers();
      for (const u of users) {
        try {
          const rems = Db.getUserReminders(u.uid);
          const alarms = Db.getUserAlarms(u.uid);
          const tasks = Db.getTasks(u.uid);
          const habits = Db.getHabits(u.uid);

          const todayRems = rems.filter(r => {
            const d = new Date(r.fire_at);
            const now = new Date();
            return d.toDateString() === now.toDateString();
          });

          if (!todayRems.length && !alarms.length && !tasks.length && !habits.length) continue;

          let text = `☀️ *Доброе утро!*\n\n`;

          if (todayRems.length) {
            text += `⏰ *Напоминания на сегодня:*\n`;
            text += todayRems.map(r =>
              `• ${r.text} — ${new Date(r.fire_at).toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" })}`
            ).join("\n") + "\n\n";
          }

          if (alarms.length) {
            text += `🔔 *Будильники:*\n`;
            text += alarms.map(a =>
              `• ${a.text} — ${new Date(a.fire_at).toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" })}`
            ).join("\n") + "\n\n";
          }

          const urgentTasks = tasks.filter(t => t.priority >= 3).slice(0, 3);
          if (urgentTasks.length) {
            text += `📋 *Важные задачи:*\n`;
            text += urgentTasks.map(t => `• ${t.title}`).join("\n") + "\n\n";
          }

          if (habits.length) {
            text += `🎯 *Привычки сегодня:* /habits`;
          }

          await bot.api.sendMessage(u.uid, text, { parse_mode: "Markdown" });
          await new Promise(r => setTimeout(r, 100));
        } catch {}
      }
    } catch (e: any) { log.error(`Digest error: ${e.message}`); }
  });

  // Habit reminders — 8:00 PM Tashkent (15:00 UTC)
  cron.schedule("0 15 * * *", async () => {
    log.info("Habit reminders running...");
    await sendHabitReminders(bot);
  });

  // Self-improvement cycle — every 6 hours
  cron.schedule("0 */6 * * *", async () => {
    log.info("Self-improvement cycle tick");
    await runSelfImprovement(bot);
  });

  // Memory compaction — every 6 hours (offset by 3h)
  cron.schedule("0 3,9,15,21 * * *", () => {
    log.info("Memory compaction tick");
  });

  log.info("Scheduler started");
}
