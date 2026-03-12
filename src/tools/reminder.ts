/**
 * NEXUM — Reminder System
 * Multilingual time parsing: Russian, English, Uzbek, Turkish, Arabic etc.
 * Scheduler sends reminders to user's DM only.
 */
import { Bot } from "grammy";
import { Db } from "../core/db.js";
import { log } from "../core/logger.js";

// ── Multilingual time parser ──────────────────────────────────────────────
export function parseReminderTime(text: string): Date | null {
  const now   = new Date();
  const lower = text.toLowerCase().trim();

  // ── MINUTES ──
  // RU: через N минут/мин | EN: in N min | UZ: N daqiqa | TR: N dakika
  let m = /(?:через|in|oradan|in)\s+(\d+)\s*(?:мин(?:ут)?[аы]?|min(?:utes?)?|daqiqa|dakika)/i.exec(lower);
  if (m) return new Date(now.getTime() + parseInt(m[1]!) * 60_000);

  // ── HOURS ──
  // RU: через N часов | EN: in N hours | UZ: N soat | TR: N saat
  m = /(?:через|in)\s+(\d+)\s*(?:час(?:а|ов)?|h(?:ours?)?|soat|saat)/i.exec(lower);
  if (m) return new Date(now.getTime() + parseInt(m[1]!) * 3_600_000);

  // ── DAYS ──
  // RU: через N дней | EN: in N days | UZ: N kun | TR: N gün
  m = /(?:через|in)\s+(\d+)\s*(?:дн(?:ей|я|ь)|day[s]?|kun|gün)/i.exec(lower);
  if (m) return new Date(now.getTime() + parseInt(m[1]!) * 86_400_000);

  // ── AT TIME: "в HH:MM" | "at HH:MM" | "soat HH:MM" ──
  m = /(?:в|at|soat|saat)\s+(\d{1,2})[:\.](\d{2})/i.exec(lower);
  if (m) {
    const d = new Date(now);
    d.setHours(parseInt(m[1]!), parseInt(m[2]!), 0, 0);
    if (d <= now) d.setDate(d.getDate() + 1);
    return d;
  }

  // ── TOMORROW ──
  // RU: завтра | EN: tomorrow | UZ: ertaga | TR: yarın | AR: غداً
  m = /(?:завтра|tomorrow|ertaga|yarın|غداً?)(?:\s+(?:в|at|soat|saat)\s+(\d{1,2})[:\.](\d{2}))?/i.exec(lower);
  if (m) {
    const d = new Date(now);
    d.setDate(d.getDate() + 1);
    if (m[1]) d.setHours(parseInt(m[1]), parseInt(m[2] ?? "0"), 0, 0);
    else d.setHours(9, 0, 0, 0);
    return d;
  }

  // ── "через полчаса" / "in half an hour" ──
  if (/полчаса|half.?an.?hour/i.test(lower)) {
    return new Date(now.getTime() + 30 * 60_000);
  }

  // ── "вечером" (evening) → 20:00 ──
  if (/вечером|evening|kechqurun/i.test(lower)) {
    const d = new Date(now);
    d.setHours(20, 0, 0, 0);
    if (d <= now) d.setDate(d.getDate() + 1);
    return d;
  }

  // ── "утром" (morning) → 09:00 ──
  if (/утром|morning|ertalab/i.test(lower)) {
    const d = new Date(now);
    d.setHours(9, 0, 0, 0);
    if (d <= now) d.setDate(d.getDate() + 1);
    return d;
  }

  return null;
}

// ── Reminder scheduler (polls every 30s) ─────────────────────────────────
export function startReminderScheduler(bot: Bot) {
  setInterval(async () => {
    try {
      const pending = Db.getPendingReminders();
      for (const rem of pending) {
        try {
          // Send to user's chat (supports both private and group reminders)
          await bot.api.sendMessage(rem.chat_id, `⏰ *Reminder:* ${rem.text}`, { parse_mode: "Markdown" });
        } catch (e) {
          log.debug(`Reminder send ${rem.id}: ${e}`);
        } finally {
          // Handle repeat
          if (rem.repeat === "once" || rem.repeat === "once") {
            Db.markReminderFired(rem.id);
          } else if (rem.repeat === "daily") {
            const next = new Date(new Date(rem.fire_at).getTime() + 86_400_000);
            Db.rescheduleReminder(rem.id, next);
          } else if (rem.repeat === "weekly") {
            const next = new Date(new Date(rem.fire_at).getTime() + 7 * 86_400_000);
            Db.rescheduleReminder(rem.id, next);
          } else {
            Db.markReminderFired(rem.id);
          }
        }
      }
    } catch (e) {
      log.debug(`Reminder scheduler: ${e}`);
    }
  }, 30_000);

  log.info("Reminder scheduler started (30s interval)");
}
