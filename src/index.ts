import * as dotenv from 'dotenv';
dotenv.config();

import { Bot } from 'grammy';
import { config } from './core/config';
import { setupHandlers } from './telegram/handler';
import { startServer } from './apps/server';
import { startScheduler } from './scheduler/scheduler';
import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

if (!config.botToken) {
  console.error('❌ BOT_TOKEN is not set!');
  process.exit(1);
}

// ── TTS startup check ──────────────────────────────────────────────────────
async function checkTTS() {
  const edgeBin = process.env.EDGE_TTS_PATH || 'edge-tts';
  try {
    const { stdout } = await execAsync(`${edgeBin} --version`, { timeout: 5000 });
    console.log(`[tts] ✅ edge-tts ready: ${stdout.trim()}`);
  } catch {
    // Try python venv path
    try {
      const pyBin = process.env.EDGE_PYTHON_PATH || '/opt/edge-tts-env/bin/python3';
      await execAsync(`${pyBin} -c "import edge_tts; print('edge_tts OK')"`, { timeout: 5000 });
      console.log('[tts] ✅ edge-tts python module ready');
    } catch (e2: any) {
      console.warn('[tts] ⚠️  edge-tts not found — voice replies will fallback to text');
      console.warn('[tts] Install: pip install edge-tts');
    }
  }
}
checkTTS();

const bot = new Bot(config.botToken);

setupHandlers(bot);
const server = startServer(bot);
startScheduler(bot);

bot.catch((err: any) => {
  console.error('[bot error]', err.error);
});

bot.start({
  onStart: (info: any) => {
    console.log(`[nexum] ✅ Bot started: @${info.username}`);
    console.log(`[nexum] Webapp: ${config.webappUrl}`);
  }
});

process.once('SIGINT', () => { bot.stop(); server.close(); });
process.once('SIGTERM', () => { bot.stop(); server.close(); });
