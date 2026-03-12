/**
 * NEXUM — Cron Scheduler
 * Daily digest, habit reminders, self-improvement cycles
 * All times in UTC. Server is on Railway (UTC).
 */
import cron from "node-cron";
import { Db } from "../core/db.js";
import { ask } from "../agent/engine.js";
import { log } from "../core/logger.js";
import { sendHabitReminders } from "../tools/habits.js";

export function startScheduler(bot: any) {

  // ── Daily morning digest — 4:00 UTC = 9:00 Tashkent ───────────────────
  cron.schedule("0 4 * * *", async () => {
    log.info("Daily digest running...");
    try {
      const users = Db.getTopUsers();
      for (const u of users) {
        try {
          const rems   = Db.getUserReminders(u.uid);
          const tasks  = Db.getTasks(u.uid).filter((t: any) => t.status !== "done");
          const habits = Db.getHabits(u.uid);
          const alarms = Db.getUserAlarms(u.uid);

          if (!rems.length && !tasks.length && !habits.length && !alarms.length) continue;

          let text = `☀️ *Good morning!*\n\n`;

          const todayRems = rems.filter(r => {
            const d = new Date(r.fire_at);
            const now = new Date();
            return d.toDateString() === now.toDateString();
          });

          if (todayRems.length) {
            text += `⏰ *Today's reminders (${todayRems.length}):*\n`;
            text += todayRems.map(r =>
              `• ${r.text.slice(0, 50)}`
            ).join("\n") + "\n\n";
          }

          if (alarms.length) {
            text += `🔔 *Alarms:*\n`;
            text += alarms.slice(0, 3).map((a: any) =>
              `• ${a.text.slice(0, 40)}`
            ).join("\n") + "\n\n";
          }

          const urgentTasks = tasks.filter((t: any) => t.priority >= 3).slice(0, 3);
          if (urgentTasks.length) {
            text += `📋 *Priority tasks:*\n`;
            text += urgentTasks.map((t: any) => `• ${t.title}`).join("\n") + "\n\n";
          }

          if (habits.length) {
            text += `🎯 *Habits today:* ${habits.length} → /habits`;
          }

          await bot.api.sendMessage(u.uid, text, { parse_mode: "Markdown" });
          await new Promise(r => setTimeout(r, 150));
        } catch {}
      }
    } catch (e: any) { log.error(`Digest error: ${e.message}`); }
  });

  // ── Habit evening reminders — 15:00 UTC = 20:00 Tashkent ──────────────
  cron.schedule("0 15 * * *", async () => {
    log.info("Habit reminders running...");
    await sendHabitReminders(bot).catch(() => {});
  });

  // ── Memory compaction — every 12 hours ─────────────────────────────────
  cron.schedule("0 6,18 * * *", () => {
    log.debug("Memory compaction tick");
    // Trim old conversation history for all users (keep last 200 per chat)
    try {
      const users = Db.getTopUsers();
      for (const u of users) {
        try {
          const count = Db.historyCount(u.uid, u.uid);
          if (count > 200) {
            Db.deleteOldMessages(u.uid, u.uid, count - 200);
          }
        } catch {}
      }
    } catch {}
  });

  log.info("Scheduler started (daily digest 9AM Tashkent, habits 8PM Tashkent)");
}
