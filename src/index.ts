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

  // Non-blocking start — Railway healthcheck works immediately
  bot.start({
    onStart: (info) => {
      console.log(`[bot] ✅ NEXUM v12 started as @${info.username}`);
      console.log(`[bot] Admins: ${config.adminIds.join(', ')||'none'}`);
    },
    drop_pending_updates: false,
  }).catch(e => console.error('[bot] fatal:', e));

  console.log('[main] ✅ NEXUM v12 ready');
}

main().catch(e => { console.error('[fatal]', e); process.exit(1); });
