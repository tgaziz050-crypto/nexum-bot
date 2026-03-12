import cron from 'node-cron';
import { db } from '../core/db.ts';
import { Bot } from 'grammy';

export function startScheduler(bot: Bot) {
  // Check reminders every minute
  cron.schedule('* * * * *', async () => {
    const now = new Date().toISOString();
    const due = db.prepare(`
      SELECT * FROM reminders 
      WHERE done = 0 AND fire_at <= ? 
      LIMIT 20
    `).all(now) as any[];

    for (const r of due) {
      try {
        await bot.api.sendMessage(r.chat_id, `⏰ *Напоминание*\n\n${r.text}`, { parse_mode: 'Markdown' });
        db.prepare('UPDATE reminders SET done = 1 WHERE id = ?').run(r.id);
      } catch (e) {
        console.error('[scheduler] reminder error:', e);
        db.prepare('UPDATE reminders SET done = 1 WHERE id = ?').run(r.id);
      }
    }
  });

  console.log('[scheduler] started');
}
