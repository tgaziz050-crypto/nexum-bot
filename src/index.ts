import "./core/config.js";
import { log } from "./core/logger.js";
import { createBot } from "./channels/bot.js";
import { securityGuard } from "./core/guard.js";
import { registerHandlers } from "./channels/handler.js";
import { registerCommands } from "./commands/index.js";
import { registerNodeCommands } from "./commands/node.js";
import { startNodeServer } from "./nodes/pcagent.js";
import { startReminderScheduler } from "./tools/reminder.js";
import { startScheduler } from "./automation/scheduler.js";

async function main() {
  log.info("NEXUM - Starting up");

  const bot = createBot();

  bot.use(securityGuard as any);
  registerCommands(bot as any);
  registerNodeCommands(bot as any);
  registerHandlers(bot as any);

  bot.catch((err: any) => {
    log.error(`Bot error: ${err.message}`);
  });

  const nodePort = parseInt(process.env.NODE_PORT ?? "18790");
  startNodeServer(nodePort, bot as any);
  startReminderScheduler(bot as any);
  startScheduler(bot as any);

  await (bot as any).start({ drop_pending_updates: true });
  log.info("NEXUM online");
}

main().catch((e: any) => {
  log.error(`Fatal: ${e}`);
  process.exit(1);
});
