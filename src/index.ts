import 'dotenv/config';
import { Bot } from 'grammy';
import { config } from './core/config';
import { setupHandlers } from './telegram/handler';
import { startServer } from './apps/server';
import { startScheduler } from './scheduler/scheduler';

process.on('uncaughtException', (e) => console.error('[uncaughtException]', e));
process.on('unhandledRejection', (e) => console.error('[unhandledRejection]', e));

async function main() {
  if (!config.botToken) throw new Error('BOT_TOKEN is required');
  if (!config.webappUrl) console.warn('[warn] WEBAPP_URL not set — Mini Apps buttons will not work');

  const bot = new Bot(config.botToken);
  const server = startServer(bot);
  setupHandlers(bot);
  startScheduler(bot);

  bot.start({
    onStart: () => console.log('[bot] ✅ NEXUM v10 started'),
    drop_pending_updates: false,
  });
}

main().catch(e => { console.error('[fatal]', e); process.exit(1); });
