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
  log.info("NEXUM — Starting up");

  const bot = createBot();

  bot.use(securityGuard);
  registerCommands(bot);
  registerNodeCommands(bot);
  registerHandlers(bot);

  bot.catch((err) => {
    log.error(`Bot error: ${err.message}`);
  });

  const nodePort = parseInt(process.env.NODE_PORT ?? "18790");
  startNodeServer(nodePort, bot);
  startReminderScheduler(bot);
  startScheduler(bot);

  await bot.start({
    onStart: () => log.info("NEXUM online"),
    drop_pending_updates: true,
  });
}

main().catch((e) => {
  log.error(`Fatal: ${e}`);
  process.exit(1);
});
