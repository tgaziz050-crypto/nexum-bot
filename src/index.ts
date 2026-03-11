/**
 * NEXUM v1 — Multi-user Personal AI Platform
 */

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
import { run } from "@grammyjs/runner";

async function main() {
  log.info("═══════════════════════════════════════════");
  log.info("  NEXUM v1 — Starting up");
  log.info("═══════════════════════════════════════════");

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

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const runner = run(bot as any);
  log.info("Bot started (long polling)");

  const stop = async () => {
    log.info("Shutting down...");
    await runner.stop();
    process.exit(0);
  };
  process.on("SIGINT",  stop);
  process.on("SIGTERM", stop);
}

main().catch((e) => {
  log.error(`Fatal: ${e}`);
  process.exit(1);
});
