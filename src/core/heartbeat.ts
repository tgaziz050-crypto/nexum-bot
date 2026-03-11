/**
 * NEXUM — Heartbeat Monitor
 * Следит за здоровьем бота, AI провайдеров, БД и шедулера
 */
import { Db } from "./db.js";
import { log } from "./logger.js";
import { Config } from "./config.js";

interface HealthStatus {
  bot: boolean;
  ai: boolean;
  db: boolean;
  lastCheck: Date;
  errors: string[];
}

const state = {
  status: { bot: true, ai: true, db: true, lastCheck: new Date(), errors: [] } as HealthStatus,
  consecutiveFails: 0,
  lastAlertAt: 0,
  startTime: Date.now(),
  totalChecks: 0,
  failedChecks: 0,
};

let botRef: any = null;

async function checkDB(): Promise<boolean> {
  try {
    Db.getStats();
    return true;
  } catch (e: any) {
    Db.logError("heartbeat", `DB check failed: ${e.message}`);
    return false;
  }
}

async function checkAI(): Promise<boolean> {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    // Ping with a tiny fast request
    const keys = Object.entries(process.env)
      .filter(([k]) => k.startsWith("CB") && k.length <= 4)
      .map(([, v]) => v)
      .filter(Boolean);
    if (!keys.length) return true; // no key = skip check

    const res = await fetch("https://api.cerebras.ai/v1/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${keys[0]}` },
      body: JSON.stringify({
        model: "llama-3.3-70b",
        max_tokens: 5,
        messages: [{ role: "user", content: "hi" }],
      }),
      signal: controller.signal,
    });
    clearTimeout(timeout);
    return res.ok || res.status === 429; // 429 = rate limit = service alive
  } catch {
    return false;
  }
}

async function checkBot(): Promise<boolean> {
  try {
    if (!botRef) return true;
    const me = await botRef.api.getMe();
    return !!me?.id;
  } catch {
    return false;
  }
}

async function runCheck() {
  state.totalChecks++;
  const errors: string[] = [];

  const [dbOk, aiOk, botOk] = await Promise.all([checkDB(), checkAI(), checkBot()]);

  if (!dbOk) errors.push("❌ БД недоступна");
  if (!aiOk) errors.push("⚠️ AI провайдер недоступен");
  if (!botOk) errors.push("❌ Telegram Bot API не отвечает");

  state.status = {
    bot: botOk,
    ai: aiOk,
    db: dbOk,
    lastCheck: new Date(),
    errors,
  };

  if (errors.length > 0) {
    state.failedChecks++;
    state.consecutiveFails++;
    log.warn(`Heartbeat [${state.consecutiveFails} fails]: ${errors.join(", ")}`);

    // Alert admins (rate limited: max 1 alert per 5 min)
    const now = Date.now();
    if (state.consecutiveFails >= 2 && now - state.lastAlertAt > 5 * 60_000) {
      state.lastAlertAt = now;
      for (const adminId of Config.ADMIN_IDS) {
        try {
          await botRef?.api.sendMessage(adminId,
            `⚠️ *NEXUM ALERT*\n\n${errors.join("\n")}\n\n` +
            `Сбоев подряд: ${state.consecutiveFails}\n` +
            `Время: ${new Date().toLocaleTimeString("ru")}`,
            { parse_mode: "Markdown" }
          );
        } catch {}
      }
    }

    // Critical: 5+ consecutive fails
    if (state.consecutiveFails >= 5) {
      log.error("CRITICAL: 5+ consecutive heartbeat failures");
      Db.logError("heartbeat", `Critical: ${state.consecutiveFails} consecutive fails`);
    }
  } else {
    if (state.consecutiveFails > 0) {
      log.info(`Heartbeat recovered after ${state.consecutiveFails} failures`);
      // Notify admin on recovery
      for (const adminId of Config.ADMIN_IDS) {
        try {
          await botRef?.api.sendMessage(adminId,
            `✅ *NEXUM восстановлен*\n\nВсе сервисы работают нормально.`,
            { parse_mode: "Markdown" }
          );
        } catch {}
      }
    }
    state.consecutiveFails = 0;
  }
}

export function startHeartbeat(bot: any) {
  botRef = bot;
  // Check every 30 seconds
  setInterval(runCheck, 30_000);
  // First check after 10s
  setTimeout(runCheck, 10_000);
  log.info("Heartbeat monitor started (30s interval)");
}

export function getHealthStatus() {
  const uptime = Math.round((Date.now() - state.startTime) / 1000);
  const uptimePct = state.totalChecks > 0
    ? Math.round(((state.totalChecks - state.failedChecks) / state.totalChecks) * 100)
    : 100;
  return {
    ...state.status,
    uptime,
    uptimePct,
    totalChecks: state.totalChecks,
    failedChecks: state.failedChecks,
    consecutiveFails: state.consecutiveFails,
  };
}
