import 'dotenv/config';
import { Bot } from 'grammy';
import { config } from './core/config';
import { setupHandlers } from './telegram/handler';
import { startServer } from './apps/server';
import { startScheduler } from './scheduler/scheduler';

process.on('uncaughtException',  (e) => console.error('[uncaughtException]', e));
process.on('unhandledRejection', (e) => console.error('[unhandledRejection]', e));

async function main() {
  if (!config.botToken) throw new Error('BOT_TOKEN is required');
  if (!config.webappUrl) console.warn('[warn] WEBAPP_URL not set — Mini Apps will not work');

  const bot = new Bot(config.botToken);
  const app = startServer(bot);

  setupHandlers(bot, app);
  startScheduler(bot);

  // Non-blocking start — HTTP server responds to healthcheck immediately
  bot.start({
    onStart: () => {
      console.log('[bot] ✅ NEXUM v11 started');
      console.log(`[bot] Admin IDs: ${config.adminIds.join(', ') || 'none'}`);
      console.log(`[bot] Public bot: ${config.publicBot}`);
    },
    drop_pending_updates: false,
  }).catch(e => console.error('[bot] error', e));

  console.log('[main] ✅ NEXUM initialized');
}

main().catch(e => { console.error('[fatal]', e); process.exit(1); });
