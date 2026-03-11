/**
 * NEXUM v5 — Monitoring
 * System-level health tracking
 */
import { log } from "../core/logger.js";
import { getHealthStatus } from "../core/heartbeat.js";
import { Db } from "../core/db.js";

export interface Alert {
  level:   "warn" | "error" | "critical";
  module:  string;
  message: string;
  ts:      Date;
}

const alerts: Alert[] = [];

export function addAlert(level: Alert["level"], module: string, message: string) {
  alerts.unshift({ level, module, message, ts: new Date() });
  if (alerts.length > 100) alerts.pop();
  log[level === "critical" ? "error" : level](`[MONITOR] ${module}: ${message}`);
}

export function getAlerts(limit = 10): Alert[] {
  return alerts.slice(0, limit);
}

export function getSystemReport(): string {
  const h = getHealthStatus();
  const recent = alerts.slice(0, 5);
  const lines = [
    `🔍 *System Monitor*\n`,
    `AI: ${h.ai ? "✅" : "❌"} | DB: ${h.db ? "✅" : "❌"} | Bot: ${h.bot ? "✅" : "❌"}`,
    `Checks: ${h.totalChecks} total, ${h.failedChecks} failed`,
    `Consecutive fails: ${h.consecutiveFails}`,
  ];
  if (recent.length) {
    lines.push(`\n*Recent alerts:*`);
    for (const a of recent) {
      const icon = a.level === "critical" ? "🔴" : a.level === "error" ? "🟠" : "🟡";
      lines.push(`${icon} [${a.module}] ${a.message}`);
    }
  }
  return lines.join("\n");
}
