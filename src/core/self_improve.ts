/**
 * NEXUM — Self-Improvement Cycle
 * AI анализирует ошибки и предлагает улучшения администратору
 */
import { Db } from "../core/db.js";
import { ask } from "../agent/engine.js";
import { Config } from "./config.js";
import { log } from "./logger.js";

export async function runSelfImprovement(bot: any) {
  try {
    log.info("Self-improvement cycle starting...");

    // Gather metrics
    const errors = Db.getRecentErrors(50);
    const stats = Db.getStats();
    const pending = Db.getPendingImprovements();

    // Don't spam — max 1 proposal per 6h
    if (pending.length >= 2) {
      log.info("Self-improvement: pending proposals exist, skipping");
      return;
    }

    if (!errors.length) {
      log.info("Self-improvement: no errors to analyze");
      return;
    }

    // Group errors by module
    const errorGroups: Record<string, { count: number; messages: string[] }> = {};
    for (const e of errors) {
      const mod = e.module || "unknown";
      if (!errorGroups[mod]) errorGroups[mod] = { count: 0, messages: [] };
      errorGroups[mod].count++;
      if (errorGroups[mod].messages.length < 3) errorGroups[mod].messages.push(e.message);
    }

    const errorSummary = Object.entries(errorGroups)
      .map(([mod, d]) => `[${mod}] ${d.count} ошибок: ${d.messages.join(" | ")}`)
      .join("\n");

    const metrics = JSON.stringify({
      totalUsers: stats.users,
      totalMessages: stats.messages,
      recentErrors: errors.length,
      errorsByModule: Object.fromEntries(
        Object.entries(errorGroups).map(([k, v]) => [k, v.count])
      ),
    });

    // AI analysis
    const msgs = [
      {
        role: "system" as const,
        content: `Ты инженер по оптимизации AI-бота NEXUM (Telegram бот на TypeScript + grammy + better-sqlite3).
Твоя задача: проанализировать ошибки и предложить КОНКРЕТНЫЕ улучшения кода.
Отвечай в формате:
ПРОБЛЕМА: [описание]
РЕШЕНИЕ: [конкретное техническое решение]
ПРИОРИТЕТ: [высокий/средний/низкий]
Предложи максимум 3 улучшения. Будь конкретен.`,
      },
      {
        role: "user" as const,
        content: `Метрики:\nПользователей: ${stats.users}, Сообщений: ${stats.messages}\n\nОшибки за последние часы:\n${errorSummary}\n\nЧто улучшить?`,
      },
    ];

    const proposal = await ask(msgs, "analysis");
    const id = Db.addImprovement(proposal, metrics);

    log.info(`Self-improvement proposal #${id} created`);

    // Send to all admins
    for (const adminId of Config.ADMIN_IDS) {
      try {
        await bot.api.sendMessage(
          adminId,
          `🤖 *NEXUM Self-Improvement #${id}*\n\n${proposal}\n\n` +
          `📊 _Ошибок проанализировано: ${errors.length}_`,
          {
            parse_mode: "Markdown",
            reply_markup: {
              inline_keyboard: [[
                { text: "✅ Применить", callback_data: `improve:approve:${id}` },
                { text: "❌ Отклонить", callback_data: `improve:reject:${id}` },
              ]],
            },
          }
        );
      } catch (e: any) {
        log.error(`Self-improvement notify admin ${adminId}: ${e.message}`);
      }
    }
  } catch (e: any) {
    log.error(`Self-improvement cycle: ${e.message}`);
  }
}
