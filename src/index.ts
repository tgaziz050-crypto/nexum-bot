/**
 * NEXUM v1 — Multi-user Personal AI Platform
 *
 * Подсистемы:
 * 1. Database (SQLite, WAL mode)
 * 2. Security guard (ban, access control)
 * 3. Bot (grammY + runner)
 * 4. Commands & Handlers
 * 5. PC Node WebSocket server
 * 6. Reminder scheduler
 * 7. Cron automation
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

  // Security middleware — первый, до всех handlers
  bot.use(securityGuard);

  // Команды и хендлеры
  registerCommands(bot);
  registerNodeCommands(bot);
  registerHandlers(bot); // catch-all — последним

  // Глобальный обработчик ошибок
  bot.catch((err) => {
    log.error(`Bot error: ${err.message}`);
  });

  // PC Node WebSocket сервер
  const nodePort = parseInt(process.env.NODE_PORT ?? "18790");
  startNodeServer(nodePort, bot);

  // Scheduler напоминаний
  startReminderScheduler(bot);

  // Cron задачи
  startScheduler(bot);

  // Запуск polling с runner (параллельные апдейты)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const runner = run(bot as any);
  log.info("✅ Bot started (long polling)");

  // Graceful shutdown
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
