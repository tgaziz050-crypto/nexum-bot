import 'dotenv/config';
import { Bot, session } from 'grammy';
import { config } from './core/config.ts';
import { setupHandlers } from './telegram/handler.ts';
import { startServer } from './apps/server.ts';
import { startScheduler } from './scheduler/scheduler.ts';

if (!config.botToken) {
  console.error('❌ BOT_TOKEN is not set!');
  process.exit(1);
}

const bot = new Bot(config.botToken);

// Setup all handlers
setupHandlers(bot);

// Start HTTP server (mini apps + WS)
const server = startServer(bot);

// Start scheduler (reminders)
startScheduler(bot);

// Error handling
bot.catch((err) => {
  console.error('[bot error]', err.error);
});

// Start bot
bot.start({
  onStart: (info) => {
    console.log(`[nexum] ✅ Bot started: @${info.username}`);
    console.log(`[nexum] Admins: ${config.adminIds.join(', ')}`);
    console.log(`[nexum] Webapp: ${config.webappUrl}`);
  }
});

// Graceful shutdown
process.once('SIGINT', () => { bot.stop(); server.close(); });
process.once('SIGTERM', () => { bot.stop(); server.close(); });
