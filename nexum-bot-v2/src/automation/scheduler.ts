import cron from "node-cron";
import { Db } from "../core/db.js";
import { ask } from "../ai/engine.js";
import { log } from "../core/logger.js";

export function startScheduler(bot: any) {
  // Daily digest — 9:00 AM Tashkent (UTC+5 = 4:00 UTC)
  cron.schedule("0 4 * * *", async () => {
    log.info("Daily digest running...");
    try {
      const users = Db.getTopUsers();
      for (const u of users) {
        try {
          const rems = Db.getUserReminders(u.uid);
          const todayRems = rems.filter(r => {
            const d = new Date(r.fire_at);
            const now = new Date();
            return d.toDateString() === now.toDateString();
          });
          if (todayRems.length === 0) continue;
          const text = `☀️ *Доброе утро!*\n\nНапоминания на сегодня:\n` +
            todayRems.map(r => `• ${r.text} — ${new Date(r.fire_at).toLocaleTimeString("ru",{hour:"2-digit",minute:"2-digit"})}`).join("\n");
          await bot.api.sendMessage(u.uid, text, { parse_mode:"Markdown" });
          await new Promise(r => setTimeout(r, 100));
        } catch {}
      }
    } catch(e: any) { log.error(`Digest error: ${e.message}`); }
  });

  // Memory compaction — every 6 hours
  cron.schedule("0 */6 * * *", () => { log.info("Memory compaction tick"); });

  log.info("Scheduler started");
}
