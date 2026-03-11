/**
 * NEXUM v5 — Main Entry Point
 * Autonomous AI Agent Platform
 *
 * Architecture:
 * User → Telegram → Gateway → Router → Agent Core → Planner → Executor → Tools → PC Agent
 */
import "./core/config.js";
import { log } from "./core/logger.js";
import { createBot } from "./telegram/bot.js";
import { securityGuard } from "./core/guard.js";
import { registerHandlers } from "./telegram/handler.js";
import { registerCommands } from "./telegram/commands.js";
import { registerTaskHandlers } from "./tools/tasks.js";
import { registerNoteHandlers } from "./tools/notes.js";
import { registerHabitHandlers } from "./tools/habits.js";
import { startAgentServer } from "./agent/pcagent.js";
import { startReminderScheduler } from "./tools/reminder.js";
import { startAlarmScheduler } from "./tools/alarm.js";
import { startScheduler } from "./scheduler/scheduler.js";
import { startWebAppServer } from "./apps/server.js";
import { startHeartbeat } from "./core/heartbeat.js";
import { Db } from "./core/db.js";
import { Config } from "./core/config.js";

async function main() {
  log.info(`NEXUM v${Config.VERSION} — Starting up`);
  log.info("Architecture: User → Telegram → Router → Agent Core → Planner → Executor → Tools → PC");

  const bot = createBot();
  bot.use(securityGuard as any);

  // Register command handlers first (higher priority)
  registerCommands(bot as any);

  // Register tool handlers (auto-detection from text)
  registerTaskHandlers(bot as any);
  registerNoteHandlers(bot as any);
  registerHabitHandlers(bot as any);

  // Register main AI handler last (catch-all)
  registerHandlers(bot as any);

  bot.catch((err: any) => {
    log.error(`Bot error: ${err.message}`);
    try { Db.logError("bot", err.message, err.stack ?? ""); } catch {}
  });

  // Start services
  log.info(`Starting PC Agent WebSocket server on port ${Config.NODE_PORT}`);
  startAgentServer(Config.NODE_PORT, bot as any);

  log.info("Starting reminder scheduler");
  startReminderScheduler(bot as any);

  log.info("Starting alarm scheduler");
  startAlarmScheduler(bot as any);

  log.info("Starting cron scheduler");
  startScheduler(bot as any);

  log.info(`Starting web app server on port ${Config.WEBAPP_PORT}`);
  startWebAppServer(Config.WEBAPP_PORT);

  log.info("Starting heartbeat monitor");
  startHeartbeat(bot as any);

  await (bot as any).start({ drop_pending_updates: true });
  log.info("NEXUM v5 online ✅");
  log.info(`Bot: @ainexum_bot | PC Agent: ws://localhost:${Config.NODE_PORT} | Web: http://localhost:${Config.WEBAPP_PORT}`);
}

main().catch((e: any) => {
  log.error(`Fatal: ${e}`);
  process.exit(1);
});
