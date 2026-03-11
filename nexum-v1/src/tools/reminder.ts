import { Bot } from "grammy";
import { Db } from "../core/db.js";
import { log } from "../core/logger.js";

// ── Time parser ───────────────────────────────────────────────────────────
export function parseReminderTime(text: string): Date | null {
  const now  = new Date();
  const lower = text.toLowerCase().trim();

  // "через N мин/минут/минуты"
  let m = /через\s+(\d+)\s*(?:мин(?:ут)?а?|min(?:utes?)?)/i.exec(lower);
  if (m) return new Date(now.getTime() + parseInt(m[1]!) * 60_000);

  // "through N hours / через N час"
  m = /через\s+(\d+)\s*(?:час(?:а|ов)?|h(?:ours?)?)/i.exec(lower);
  if (m) return new Date(now.getTime() + parseInt(m[1]!) * 3_600_000);

  // "через N дней / через N дня"
  m = /через\s+(\d+)\s*(?:дн(?:ей|я)|day)/i.exec(lower);
  if (m) return new Date(now.getTime() + parseInt(m[1]!) * 86_400_000);

  // "в HH:MM" or "at HH:MM"
  m = /(?:в|at)\s+(\d{1,2}):(\d{2})/i.exec(lower);
  if (m) {
    const d = new Date(now);
    d.setHours(parseInt(m[1]!), parseInt(m[2]!), 0, 0);
    if (d <= now) d.setDate(d.getDate() + 1);
    return d;
  }

  // "завтра в HH:MM" / "tomorrow at HH:MM"
  m = /(?:завтра|tomorrow)(?:\s+(?:в|at)\s+(\d{1,2}):(\d{2}))?/i.exec(lower);
  if (m) {
    const d = new Date(now);
    d.setDate(d.getDate() + 1);
    if (m[1]) d.setHours(parseInt(m[1]), parseInt(m[2] ?? "0"), 0, 0);
    return d;
  }

  // "in N min/minutes"
  m = /in\s+(\d+)\s*(?:min(?:utes?)?)/i.exec(lower);
  if (m) return new Date(now.getTime() + parseInt(m[1]!) * 60_000);

  // "in N hours"
  m = /in\s+(\d+)\s*(?:h(?:ours?)?)/i.exec(lower);
  if (m) return new Date(now.getTime() + parseInt(m[1]!) * 3_600_000);

  return null;
}

// ── Reminder scheduler (polls every 30s) ─────────────────────────────────
export function startReminderScheduler(bot: Bot) {
  setInterval(async () => {
    try {
      const pending = Db.getPendingReminders();
      for (const rem of pending) {
        try {
          await bot.api.sendMessage(rem.chat_id, `⏰ **Напоминание:** ${rem.text}`, { parse_mode: "Markdown" });
        } catch (e) {
          log.error(`Reminder send ${rem.id}: ${e}`);
        } finally {
          Db.markReminderFired(rem.id);
        }
      }
    } catch (e) {
      log.error(`Reminder scheduler: ${e}`);
    }
  }, 30_000);

  log.info("Reminder scheduler started (30s interval)");
}
