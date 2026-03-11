/**
 * NEXUM v5 — Main Entry Point
 * Architecture: User → Telegram → Router → Agent Core → Planner → Executor → Tools → PC Agent
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
import { startHeartbeat, silenceAlerts } from "./core/heartbeat.js";
import { runSelfImprovement } from "./core/self_improve.js";
import { loadAllTools } from "./tools/tool_registry.js";
import { runAutoToolDiscovery } from "./core/auto_tools.js";
import { Db } from "./core/db.js";
import { Config } from "./core/config.js";

async function main() {
  log.info(`NEXUM v${Config.VERSION} — Starting`);

  const bot = createBot();
  bot.use(securityGuard as any);

  // Commands (highest priority)
  registerCommands(bot as any);

  // Tool-specific handlers
  registerTaskHandlers(bot as any);
  registerNoteHandlers(bot as any);
  registerHabitHandlers(bot as any);

  // Main AI handler (catch-all)
  registerHandlers(bot as any);

  // Self-improvement approval callbacks — admin DM only
  (bot as any).callbackQuery(/^improve:(approve|reject):(\d+)$/, async (ctx: any) => {
    if (!Config.ADMIN_IDS.includes(ctx.from?.id)) { await ctx.answerCallbackQuery("🚫"); return; }
    await ctx.answerCallbackQuery();
    const action = ctx.match[1];
    const id     = parseInt(ctx.match[2]);
    Db.resolveImprovement(id, action === "approve" ? "approved" : "rejected");
    await ctx.editMessageText(
      action === "approve"
        ? `✅ *Improvement #${id} approved*\nWill be applied on next deploy.`
        : `❌ *Improvement #${id} rejected*`,
      { parse_mode: "Markdown" }
    ).catch(() => {});
  });

  bot.catch((err: any) => {
    log.error(`Bot error: ${err.message}`);
    try { Db.logError("bot", err.message, err.stack ?? ""); } catch {}
  });

  // ── Services ─────────────────────────────────────────────────────────
  log.info(`Starting PC Agent WebSocket on port ${Config.NODE_PORT}`);
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

  // Self-improvement: first run after 10 minutes, then every 6 hours
  setTimeout(() => runSelfImprovement(bot).catch(() => {}), 10 * 60_000);

  // Load all previously created dynamic tools
  log.info("Loading dynamic tools...");
  await loadAllTools();

  // Auto tool discovery: analyze gaps and create tools every 6h
  setTimeout(() => runAutoToolDiscovery(bot).catch(() => {}), 5 * 60_000);
  setInterval(() => runAutoToolDiscovery(bot).catch(() => {}), 6 * 60 * 60_000);

  // Start bot
  silenceAlerts(3); // silence alerts during startup
  await (bot as any).start({ drop_pending_updates: true });

  log.info("NEXUM v5 online ✅");
  log.info(`Bot: @ainexum_bot | WS: :${Config.NODE_PORT} | Web: :${Config.WEBAPP_PORT}`);
}

main().catch((e: any) => {
  log.error(`Fatal startup error: ${e.message}`);
  process.exit(1);
});
