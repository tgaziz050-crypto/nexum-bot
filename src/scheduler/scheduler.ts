import cron from 'node-cron';
import { db } from '../core/db';
import { Bot } from 'grammy';

export function startScheduler(bot: Bot) {
  // Check reminders every minute
  cron.schedule('* * * * *', async () => {
    const now = new Date().toISOString();
    const due = db.prepare(`
      SELECT * FROM reminders WHERE done=0 AND fire_at <= ? LIMIT 20
    `).all(now) as any[];

    for (const r of due) {
      try {
        await bot.api.sendMessage(r.chat_id, `⏰ *Напоминание*\n\n${r.text}`, { parse_mode: 'Markdown' });
      } catch (e) {
        console.error('[scheduler] send error:', e);
      }
      // Mark done (or schedule next if repeat)
      if (r.repeat && r.repeat !== 'none') {
        const next = calcNext(r.fire_at, r.repeat);
        if (next) {
          db.prepare('UPDATE reminders SET fire_at=?, done=0 WHERE id=?').run(next, r.id);
          continue;
        }
      }
      db.prepare('UPDATE reminders SET done=1 WHERE id=?').run(r.id);
    }
  });

  console.log('[scheduler] ✅ started');
}

function calcNext(fireAt: string, repeat: string): string | null {
  const d = new Date(fireAt);
  if (repeat === 'daily')   { d.setDate(d.getDate() + 1);   return d.toISOString(); }
  if (repeat === 'weekly')  { d.setDate(d.getDate() + 7);   return d.toISOString(); }
  if (repeat === 'monthly') { d.setMonth(d.getMonth() + 1); return d.toISOString(); }
  return null;
}
