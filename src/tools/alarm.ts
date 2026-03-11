/**
 * NEXUM — Alarm System
 * Будильник с повторными уведомлениями, кнопками подтверждения и отложкой
 */
import type { Bot } from "grammy";
import { Db } from "../core/db.js";
import { log } from "../core/logger.js";

export function parseAlarmTime(text: string): Date | null {
  const now = new Date();
  const lower = text.toLowerCase().trim();

  // "разбуди в HH:MM" / "alarm at HH:MM"
  let m = /(?:в|at|будильник|alarm|разбуди(?:меня)?(?:\s+в)?)\s*(\d{1,2}):(\d{2})/i.exec(lower);
  if (m) {
    const d = new Date(now);
    d.setHours(parseInt(m[1]!), parseInt(m[2]!), 0, 0);
    if (d <= now) d.setDate(d.getDate() + 1);
    return d;
  }

  // "через N минут"
  m = /через\s+(\d+)\s*(?:мин(?:ут)?а?|min)/i.exec(lower);
  if (m) return new Date(now.getTime() + parseInt(m[1]!) * 60_000);

  // "через N часов"
  m = /через\s+(\d+)\s*(?:час(?:а|ов)?|h(?:our)?)/i.exec(lower);
  if (m) return new Date(now.getTime() + parseInt(m[1]!) * 3_600_000);

  // "в HH:MM"
  m = /в\s+(\d{1,2}):(\d{2})/i.exec(lower);
  if (m) {
    const d = new Date(now);
    d.setHours(parseInt(m[1]!), parseInt(m[2]!), 0, 0);
    if (d <= now) d.setDate(d.getDate() + 1);
    return d;
  }

  return null;
}

export function isAlarmRequest(text: string): boolean {
  return /будильник|разбуди|alarm|просн[иу]|wake\s*up/i.test(text);
}

export function startAlarmScheduler(bot: Bot) {
  setInterval(async () => {
    try {
      const pending = Db.getPendingAlarms();
      for (const alarm of pending) {
        try {
          const repeatCount = alarm.repeat_count + 1;
          const isLast = repeatCount >= alarm.max_repeats;

          // Send alarm message with buttons
          const text = isLast
            ? `🚨 *БУДИЛЬНИК!* (последний раз)\n\n⏰ ${alarm.text}\n\n_Не отвечаешь — отключаю._`
            : `🔔 *БУДИЛЬНИК!* (${repeatCount}/${alarm.max_repeats})\n\n⏰ ${alarm.text}`;

          await bot.api.sendMessage(alarm.chat_id, text, {
            parse_mode: "Markdown",
            reply_markup: {
              inline_keyboard: [[
                { text: "✅ Проснулся!", callback_data: `alarm:confirm:${alarm.id}` },
                { text: "⏱ Ещё 5 мин", callback_data: `alarm:snooze:${alarm.id}` },
              ]],
            },
          });

          // Try to send a voice note as "ringing" — send audio alarm via TTS
          try {
            const { tts } = await import("./tts.js");
            const user = Db.getUser(alarm.uid);
            const lang = user?.lang ?? "ru";
            const audioText = lang === "ru"
              ? `Подъём! Вставай! ${alarm.text}`
              : `Wake up! ${alarm.text}`;
            const audio = await tts(audioText, lang);
            if (audio) {
              const { InputFile } = await import("grammy");
              await bot.api.sendVoice(alarm.chat_id, new InputFile(audio, "alarm.mp3"));
            }
          } catch { /* TTS is optional */ }

          // Update alarm state
          const nextFireAt = new Date(Date.now() + alarm.interval_min * 60_000);
          Db.tickAlarm(alarm.id, nextFireAt, isLast);

        } catch (e: any) {
          log.error(`Alarm ${alarm.id}: ${e.message}`);
          Db.tickAlarm(alarm.id, new Date(Date.now() + 60_000), true);
        }
      }
    } catch (e: any) {
      log.error(`Alarm scheduler: ${e.message}`);
    }
  }, 30_000);

  log.info("Alarm scheduler started");
}
