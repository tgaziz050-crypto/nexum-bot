/**
 * NEXUM — Auto Tool Discovery v2
 *
 * Фоновый цикл который:
 * 1. Анализирует запросы пользователей которые провалились или не имели нужного тула
 * 2. Анализирует сообщения где Nexum ответил "не умею" / "нет тула"
 * 3. Автоматически создаёт и подключает нужный тул
 * 4. Уведомляет админа
 *
 * Запускается: через 5 мин после старта, затем каждые 6 часов.
 * Лимит: не более 2 авто-тулов за один прогон.
 */
import { Db } from "../core/db.js";
import { ask } from "../agent/engine.js";
import { generateAndRegisterTool, listDynamicTools } from "../tools/tool_registry.js";
import { log } from "../core/logger.js";
import { Config } from "./config.js";

let lastRunAt = 0;
let totalAutoCreated = 0;

export async function runAutoToolDiscovery(bot: any) {
  const now = Date.now();
  if (now - lastRunAt < 6 * 60 * 60_000) return;
  lastRunAt = now;

  try {
    log.info("AutoToolDiscovery: starting...");

    const existingTools = listDynamicTools().map(t => t.name);

    // Собираем сигналы о пробелах из разных источников
    const errors = Db.getRecentErrors(50);
    const notImplemented = errors.filter((e: any) =>
      /not.*implement|tool.*not found|no.*handler|not.*support|cannot|unable/i.test(e.message)
    );

    // Последние сообщения от пользователей (ищем паттерны провалов)
    let recentMsgs: any[] = [];
    try { recentMsgs = (Db as any).getRecentMessages?.(100) ?? []; } catch {}

    const failSignals = recentMsgs.filter((m: any) =>
      m.role === "assistant" &&
      /не могу|не умею|нет.*функци|не поддержи|cannot|can't|don't have|не имею|недоступно/i.test(m.content ?? "")
    );

    if (!notImplemented.length && !failSignals.length) {
      log.info("AutoToolDiscovery: no gaps detected, skipping");
      return;
    }

    // Составляем контекст для анализа
    const errorCtx = notImplemented.slice(0, 10)
      .map((e: any) => `[${e.module}] ${e.message.slice(0, 120)}`)
      .join("\n");

    const signalCtx = failSignals.slice(0, 5)
      .map((m: any) => `Bot said: "${(m.content ?? "").slice(0, 150)}"`)
      .join("\n");

    const analysis = await ask([
      {
        role: "system",
        content: `You analyze an AI Telegram bot (NEXUM) to find missing capabilities.
Identify up to 2 tools that should be created to fix real gaps.
Tools must be: practical, implementable in Node.js, not duplicates of existing ones.
Existing tools: ${existingTools.join(", ") || "none"}

Respond ONLY with valid JSON array (max 2 items):
[
  {"requirement": "one sentence: what the tool does and what npm packages to use if needed"},
  ...
]
If no tools needed, respond: []`,
      },
      {
        role: "user",
        content: [
          errorCtx ? `Errors:\n${errorCtx}` : "",
          signalCtx ? `Failure signals:\n${signalCtx}` : "",
        ].filter(Boolean).join("\n\n"),
      },
    ], "analysis");

    let items: { requirement: string }[] = [];
    try {
      const clean = analysis.replace(/```json|```/g, "").trim();
      const idx = clean.indexOf("[");
      items = JSON.parse(idx >= 0 ? clean.slice(idx) : clean);
    } catch {
      log.debug("AutoToolDiscovery: parse failed");
      return;
    }

    if (!Array.isArray(items) || !items.length) {
      log.info("AutoToolDiscovery: no new tools needed");
      return;
    }

    const adminUid = Config.ADMIN_IDS[0] ?? 0;

    for (const item of items.slice(0, 2)) {
      if (!item.requirement) continue;
      log.info(`AutoToolDiscovery: creating tool: "${item.requirement}"`);

      const result = await generateAndRegisterTool(adminUid, item.requirement);
      totalAutoCreated++;

      for (const adminId of Config.ADMIN_IDS) {
        try {
          await bot.api.sendMessage(
            adminId,
            result.success
              ? `🤖 *Auto-Tool Created #${totalAutoCreated}*\n\n${result.message}\n\n_Auto-created based on usage gaps._`
              : `⚠️ *Auto-Tool Failed*\n\n${result.message}`,
            { parse_mode: "Markdown" }
          );
        } catch {}
      }

      // Небольшая пауза между созданием тулов
      await new Promise(r => setTimeout(r, 3000));
    }

  } catch (e: any) {
    log.error(`AutoToolDiscovery: ${e.message}`);
  }
}
