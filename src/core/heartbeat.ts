/**
 * NEXUM — Heartbeat Monitor
 * Silent health monitoring. Alerts ONLY to admin DM, never to chats.
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
  lastRecoveryAt: 0,
  startTime: Date.now(),
  totalChecks: 0,
  failedChecks: 0,
  silentUntil: 0,
};

let botRef: any = null;

async function checkDB(): Promise<boolean> {
  try { Db.getStats(); return true; }
  catch (e: any) { try { Db.logError("heartbeat", `DB: ${e.message}`); } catch {} return false; }
}

async function checkAI(): Promise<boolean> {
  const cbKeys = Object.entries(process.env).filter(([k]) => /^CB\d+$/.test(k)).map(([,v]) => v!).filter(Boolean);
  const grKeys = Object.entries(process.env).filter(([k]) => /^GR\d+$/.test(k)).map(([,v]) => v!).filter(Boolean);
  const gKeys  = Object.entries(process.env).filter(([k]) => /^G\d+$/.test(k)).map(([,v]) => v!).filter(Boolean);

  // Try fastest providers first
  if (cbKeys[0]) {
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 5000);
      const res = await fetch("https://api.cerebras.ai/v1/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${cbKeys[0]}` },
        body: JSON.stringify({ model: "llama-3.3-70b", max_tokens: 5, messages: [{ role: "user", content: "hi" }] }),
        signal: ctrl.signal,
      });
      clearTimeout(t);
      if (res.ok || res.status === 429 || res.status === 400) return true;
    } catch {}
  }
  if (grKeys[0]) {
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 5000);
      const res = await fetch("https://api.groq.com/openai/v1/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${grKeys[0]}` },
        body: JSON.stringify({ model: "llama-3.1-8b-instant", max_tokens: 5, messages: [{ role: "user", content: "hi" }] }),
        signal: ctrl.signal,
      });
      clearTimeout(t);
      if (res.ok || res.status === 429 || res.status === 400) return true;
    } catch {}
  }
  if (gKeys[0]) {
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 5000);
      const res = await fetch(
        `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${gKeys[0]}`,
        { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ contents: [{ parts: [{ text: "hi" }] }], generationConfig: { maxOutputTokens: 5 } }),
          signal: ctrl.signal }
      );
      clearTimeout(t);
      if (res.ok || res.status === 429 || res.status === 400) return true;
    } catch {}
  }
  // If no keys configured, don't fail
  if (!cbKeys.length && !grKeys.length && !gKeys.length) return true;
  return false;
}

async function checkBot(): Promise<boolean> {
  try { if (!botRef) return true; const me = await botRef.api.getMe(); return !!me?.id; }
  catch { return false; }
}

async function alertAdminDM(text: string) {
  if (!botRef) return;
  for (const adminId of Config.ADMIN_IDS) {
    try { await botRef.api.sendMessage(adminId, text, { parse_mode: "Markdown" }); } catch {}
  }
}

async function runCheck() {
  state.totalChecks++;
  const errors: string[] = [];
  const [dbOk, aiOk, botOk] = await Promise.all([checkDB(), checkAI(), checkBot()]);

  if (!dbOk) errors.push("❌ DB offline");
  if (!aiOk) errors.push("⚠️ AI providers unavailable");
  if (!botOk) errors.push("❌ Telegram API not responding");

  state.status = { bot: botOk, ai: aiOk, db: dbOk, lastCheck: new Date(), errors };

  const now = Date.now();

  if (errors.length > 0) {
    state.failedChecks++;
    state.consecutiveFails++;
    log.warn(`Heartbeat [${state.consecutiveFails} fails]: ${errors.join(", ")}`);

    // Alert admin DM — max once per 10min, only after 3+ consecutive fails
    if (state.consecutiveFails >= 3 && now - state.lastAlertAt > 10 * 60_000 && now > state.silentUntil) {
      state.lastAlertAt = now;
      await alertAdminDM(
        `⚠️ *NEXUM Alert* (${state.consecutiveFails} fails)\n\n${errors.join("\n")}\n` +
        `Time: ${new Date().toLocaleTimeString("ru")}`
      );
    }
    if (state.consecutiveFails === 10) {
      try { Db.logError("heartbeat", `Critical: ${state.consecutiveFails} consecutive fails`); } catch {}
      await alertAdminDM(`🚨 *NEXUM Critical*\n10+ failures. Use /restart if needed.`);
    }
  } else {
    if (state.consecutiveFails >= 3 && now - state.lastRecoveryAt > 15 * 60_000) {
      state.lastRecoveryAt = now;
      await alertAdminDM(`✅ *NEXUM Recovered*\nAll services online.`);
    }
    if (state.consecutiveFails > 0) log.info(`Heartbeat recovered after ${state.consecutiveFails} failures`);
    state.consecutiveFails = 0;
  }
}

export function startHeartbeat(bot: any) {
  botRef = bot;
  setInterval(runCheck, 60_000);
  setTimeout(runCheck, 30_000);
  log.info("Heartbeat started (60s, DM-only alerts)");
}

export function silenceAlerts(minutes = 5) { state.silentUntil = Date.now() + minutes * 60_000; }

export function getHealthStatus() {
  const uptime = Math.round((Date.now() - state.startTime) / 1000);
  const uptimePct = state.totalChecks > 0 ? Math.round(((state.totalChecks - state.failedChecks) / state.totalChecks) * 100) : 100;
  return { ...state.status, uptime, uptimePct, totalChecks: state.totalChecks, failedChecks: state.failedChecks, consecutiveFails: state.consecutiveFails };
}
