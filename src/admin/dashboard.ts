/**
 * NEXUM v5 — Admin Dashboard
 * Monitoring, logs, user management
 */
import { Db } from "../core/db.js";
import { getHealthStatus } from "../core/heartbeat.js";
import { log } from "../core/logger.js";

export interface DashboardData {
  users:       number;
  messages:    number;
  uptime:      number;
  uptimePct:   number;
  health:      { ai: boolean; db: boolean; bot: boolean };
  topUsers:    any[];
  recentErrors: any[];
  agentCount:  number;
}

export function getDashboard(): DashboardData {
  const stats  = Db.getStats();
  const health = getHealthStatus();
  const top    = Db.getTopUsers().slice(0, 10);
  const errors = Db.getRecentErrors(5);

  return {
    users:        stats.users,
    messages:     stats.messages,
    uptime:       health.uptime,
    uptimePct:    health.uptimePct,
    health:       { ai: health.ai, db: health.db, bot: health.bot },
    topUsers:     top,
    recentErrors: errors,
    agentCount:   0,
  };
}

export function formatDashboard(d: DashboardData): string {
  const h = `${Math.floor(d.uptime / 3600)}h ${Math.floor((d.uptime % 3600) / 60)}m`;
  return (
    `📊 *NEXUM Dashboard*\n\n` +
    `👥 Users: ${d.users}\n` +
    `💬 Messages: ${d.messages}\n` +
    `⏱ Uptime: ${h} (${d.uptimePct}%)\n` +
    `🤖 AI: ${d.health.ai ? "✅" : "❌"}  DB: ${d.health.db ? "✅" : "❌"}  Bot: ${d.health.bot ? "✅" : "❌"}\n\n` +
    `*Top users:*\n` +
    d.topUsers.slice(0, 5).map((u, i) => `${i + 1}. ${u.name || u.uid} — ${u.total_msgs} msg`).join("\n")
  );
}
