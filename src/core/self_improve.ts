/**
 * NEXUM — Self-Improvement Cycle
 * AI analyzes errors and sends improvement proposals ONLY to admin DM.
 * Not to any chat. Never spams. Max once per 6 hours.
 */
import { Db } from "../core/db.js";
import { ask } from "../agent/engine.js";
import { Config } from "./config.js";
import { log } from "./logger.js";

let lastRunAt = 0;

export async function runSelfImprovement(bot: any) {
  const now = Date.now();
  // Cooldown: min 6 hours between runs
  if (now - lastRunAt < 6 * 60 * 60_000) return;
  lastRunAt = now;

  try {
    log.info("Self-improvement cycle starting...");

    const errors  = Db.getRecentErrors(50);
    const stats   = Db.getStats();
    const pending = Db.getPendingImprovements();

    // Don't create more proposals if 2+ are already pending
    if (pending.length >= 2) {
      log.info("Self-improvement: pending proposals exist, skipping");
      return;
    }

    // Only run if there are actual errors to analyze
    if (!errors.length) {
      log.info("Self-improvement: no errors, skipping");
      return;
    }

    // Group errors by module
    const errorGroups: Record<string, { count: number; msgs: string[] }> = {};
    for (const e of errors) {
      const mod = e.module || "unknown";
      if (!errorGroups[mod]) errorGroups[mod] = { count: 0, msgs: [] };
      errorGroups[mod].count++;
      if (errorGroups[mod].msgs.length < 3) errorGroups[mod].msgs.push(e.message);
    }

    const errorSummary = Object.entries(errorGroups)
      .map(([mod, d]) => `[${mod}] ×${d.count}: ${d.msgs.join(" | ")}`)
      .join("\n");

    const proposal = await ask([
      {
        role: "system",
        content: `You are a senior TypeScript/Node.js engineer reviewing NEXUM bot errors.
NEXUM is a Telegram AI agent bot (TypeScript + grammy + better-sqlite3).
Analyze the errors and propose 2-3 SPECIFIC code fixes.
Format each fix as:
PROBLEM: [what breaks]
FIX: [exact code change or approach]
PRIORITY: high/medium/low`,
      },
      {
        role: "user",
        content: `Stats: ${stats.users} users, ${stats.messages} messages\n\nRecent errors:\n${errorSummary}\n\nPropose fixes:`,
      },
    ], "analysis");

    const id = Db.addImprovement(proposal, JSON.stringify({ users: stats.users, errorCount: errors.length }));
    log.info(`Self-improvement proposal #${id} created`);

    // Send ONLY to admin DM — never to any chat
    for (const adminId of Config.ADMIN_IDS) {
      try {
        await bot.api.sendMessage(
          adminId,
          `🤖 *NEXUM Self-Improvement #${id}*\n\n${proposal.slice(0, 3000)}\n\n_Errors analyzed: ${errors.length}_`,
          {
            parse_mode: "Markdown",
            reply_markup: {
              inline_keyboard: [[
                { text: "✅ Apply", callback_data: `improve:approve:${id}` },
                { text: "❌ Reject", callback_data: `improve:reject:${id}` },
              ]],
            },
          }
        );
      } catch (e: any) {
        log.error(`Self-improve admin notify ${adminId}: ${e.message}`);
      }
    }
  } catch (e: any) {
    log.error(`Self-improvement: ${e.message}`);
  }
}
