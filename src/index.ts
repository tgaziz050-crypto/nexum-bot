import "./core/config.js";
import { log } from "./core/logger.js";
import { createBot } from "./channels/bot.js";
import { securityGuard } from "./core/guard.js";
import { registerHandlers } from "./channels/handler.js";
import { registerCommands } from "./commands/index.js";
import { registerNodeCommands } from "./commands/node.js";
import { registerFinanceHandlers } from "./finance/finance.js";
import { registerTaskHandlers } from "./tools/tasks.js";
import { registerNoteHandlers } from "./tools/notes.js";
import { registerHabitHandlers } from "./tools/habits.js";
import { startNodeServer } from "./nodes/pcagent.js";
import { startReminderScheduler } from "./tools/reminder.js";
import { startAlarmScheduler } from "./tools/alarm.js";
import { startScheduler } from "./automation/scheduler.js";
import { startWebAppServer } from "./webapp/server.js";
import { startHeartbeat } from "./core/heartbeat.js";
import { Db } from "./core/db.js";
import { Config } from "./core/config.js";

async function main() {
  log.info("NEXUM v3 — Starting up");
  const bot = createBot();
  bot.use(securityGuard as any);

  // Register all handlers in order
  registerCommands(bot as any);
  registerNodeCommands(bot as any);
  registerFinanceHandlers(bot as any);
  registerTaskHandlers(bot as any);
  registerNoteHandlers(bot as any);
  registerHabitHandlers(bot as any);
  registerHandlers(bot as any);

  bot.catch((err: any) => {
    log.error(`Bot error: ${err.message}`);
    try { Db.logError("bot", err.message, err.stack ?? ""); } catch {}
  });

  // Start services
  const nodePort = parseInt(process.env.NODE_PORT ?? "18790");
  startNodeServer(nodePort, bot as any);
  startReminderScheduler(bot as any);
  startAlarmScheduler(bot as any);
  startScheduler(bot as any);
  startWebAppServer(Config.WEBAPP_PORT);
  startHeartbeat(bot as any);

  await (bot as any).start({ drop_pending_updates: true });
  log.info("NEXUM v3 online ✅");
}

main().catch((e: any) => { log.error(`Fatal: ${e}`); process.exit(1); });
