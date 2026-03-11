import cron from "node-cron";
import { Db } from "../core/db.js";
import { ask } from "../ai/engine.js";
import { log } from "../core/logger.js";
import type { Bot } from "grammy";
import type { BotContext } from "../channels/bot.js";

export function startScheduler(bot: Bot<BotContext>) {

  // ── Daily digest — 9:00 AM every day ──────────────────────────────────
  cron.schedule("0 9 * * *", async () => {
    log.info("Daily digest: sending...");
    // Would iterate active users and send daily brief
    // For now just log
    log.info("Daily digest: done");
  });

  // ── Memory compaction — every 6 hours ─────────────────────────────────
  cron.schedule("0 */6 * * *", async () => {
    log.info("Memory compaction: running...");
    // Could compact old conversation history here
  });

  log.info("Scheduler started");
}
