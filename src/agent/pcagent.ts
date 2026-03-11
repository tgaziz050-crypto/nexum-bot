/**
 * NEXUM v5 — PC Agent Server
 * WebSocket server for PC agent connections
 * Secure linking via code (no token exposure)
 */
import { WebSocketServer, WebSocket } from "ws";
import { Db, DbV5 } from "../core/db.js";
import { log } from "../core/logger.js";
import type { Bot } from "grammy";
import { InputFile } from "grammy";
import type { BotContext } from "../telegram/bot.js";
import * as crypto from "crypto";

interface AgentConn {
  ws:       WebSocket;
  uid:      number;
  deviceId: string;
  name:     string;
  platform: string;
  mode:     string;
  lastSeen: number;
  sysinfo?: Record<string, unknown>;
}

// uid → agent connection
const agents  = new Map<number, AgentConn>();
// deviceId → pending linking code
const linkCodes = new Map<string, string>(); // code → deviceId
// requestId → resolve fn
const pending = new Map<string, (result: string) => void>();
// confirm map
const pendingConfirms = new Map<string, { chatId: number; msgId: number }>();

let wss: WebSocketServer | null = null;
let botRef: Bot<BotContext> | null = null;

// ── Public API ────────────────────────────────────────────────────────────

export function isAgentOnline(uid: number): boolean {
  const agent = agents.get(uid);
  return !!agent && agent.ws.readyState === WebSocket.OPEN;
}

export function getAgentInfo(uid: number): AgentConn | null {
  return agents.get(uid) ?? null;
}

// Generate a 6-char linking code
export function generateLinkCode(deviceId: string, platform: string): string {
  const code = crypto.randomBytes(3).toString("hex").toUpperCase(); // e.g. "A3F2B1"
  DbV5.createLinkingCode(code, deviceId, platform);
  linkCodes.set(code, deviceId);
  return code;
}

// Called when user sends a linking code to the bot
export async function consumeLinkCode(uid: number, code: string, bot?: any): Promise<boolean> {
  const result = DbV5.consumeLinkingCode(code.toUpperCase().trim());
  if (!result) return false;

  const { deviceId, platform } = result;
  const deviceName = `PC-${deviceId.slice(0, 4)}`;
  DbV5.linkDevice(uid, deviceId, deviceName, platform);

  // Find the waiting agent WS and bind uid
  for (const [key, agent] of agents.entries()) {
    if (agent.deviceId === deviceId && agent.uid === 0) {
      agent.uid = uid;
      agents.delete(key);
      agents.set(uid, agent);
      agent.ws.send(JSON.stringify({ type: "linked", uid }));
      Db.upsertAgent(uid, deviceName, platform);
      log.info(`PC Agent linked: uid=${uid} device=${deviceId}`);
      return true;
    }
  }

  // Agent might reconnect later — mark as pre-linked
  log.info(`Link code used, agent not yet connected: uid=${uid} device=${deviceId}`);
  return true;
}

// Send a command to the user's PC agent
export async function sendToAgent(uid: number, type: string, payload: any): Promise<string | null> {
  const agent = agents.get(uid);
  if (!agent || agent.ws.readyState !== WebSocket.OPEN) return null;

  const reqId = crypto.randomUUID();
  const timeout = 30_000;

  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      pending.delete(reqId);
      resolve(null);
    }, timeout);

    pending.set(reqId, (result) => {
      clearTimeout(timer);
      pending.delete(reqId);
      resolve(result);
    });

    agent.ws.send(JSON.stringify({ type, reqId, ...payload }));
    agent.lastSeen = Date.now();
  });
}

// ── WebSocket Server ──────────────────────────────────────────────────────

export function startAgentServer(port: number, bot: Bot<BotContext>) {
  botRef = bot;
  wss = new WebSocketServer({ port });

  wss.on("connection", (ws) => {
    let agentUid  = 0;
    let deviceId  = "";

    ws.on("message", async (raw) => {
      try {
        const msg = JSON.parse(raw.toString()) as Record<string, unknown>;
        const type = msg.type as string;

        switch (type) {

          // ── Agent requests a linking code ────────────────────────────
          case "request_link": {
            deviceId = (msg.device_id as string) ?? crypto.randomUUID();
            const platform = (msg.platform as string) ?? "unknown";
            const code = generateLinkCode(deviceId, platform);

            // Store as unlinked agent
            agents.set(-Date.now(), {
              ws, uid: 0, deviceId,
              name: `PC-${deviceId.slice(0, 4)}`,
              platform, mode: "SAFE",
              lastSeen: Date.now(),
            });

            ws.send(JSON.stringify({
              type: "link_code",
              code,
              message: `Send this code to @ainexum_bot: /link ${code}`,
              expires_in: 600,
            }));
            log.info(`Link code generated: ${code} device=${deviceId}`);
            break;
          }

          // ── Already linked agent reconnects ──────────────────────────
          case "register": {
            agentUid = (msg.uid as number) ?? 0;
            deviceId = (msg.device_id as string) ?? "";

            if (!agentUid) {
              // Not yet linked — request linking
              ws.send(JSON.stringify({ type: "need_link" }));
              return;
            }

            const conn: AgentConn = {
              ws, uid: agentUid,
              deviceId: deviceId || `dev-${agentUid}`,
              name:     (msg.name as string)     ?? "PC",
              platform: (msg.platform as string) ?? "unknown",
              mode:     (msg.mode as string)      ?? "SAFE",
              lastSeen: Date.now(),
              sysinfo:  (msg.sysinfo as any)      ?? {},
            };

            agents.set(agentUid, conn);
            Db.upsertAgent(agentUid, conn.name, conn.platform);
            DbV5.updateDeviceSeen(agentUid, conn.deviceId);

            ws.send(JSON.stringify({ type: "registered", ok: true }));

            await bot.api.sendMessage(agentUid,
              `✅ *PC Agent подключён*\n\n` +
              `💻 ${conn.name} · ${conn.platform}\n` +
              `🛡 Режим: ${conn.mode}\n\n` +
              `Используй /pc для управления.`,
              { parse_mode: "Markdown" }
            ).catch(() => {});

            log.info(`Agent registered: uid=${agentUid} device=${conn.deviceId} mode=${conn.mode}`);
            break;
          }

          // ── Agent response to a command ──────────────────────────────
          case "result": {
            const reqId = msg.reqId as string;
            const resolve = pending.get(reqId);
            if (resolve) resolve((msg.data as string) ?? "");
            break;
          }

          // ── Screenshot response ───────────────────────────────────────
          case "screenshot_result": {
            const b64 = msg.data as string;
            const chatId = msg.chatId as number;
            if (b64 && chatId) {
              const buf = Buffer.from(b64, "base64");
              await bot.api.sendPhoto(chatId, new InputFile(buf, "screenshot.png"),
                { caption: "📸 Скриншот экрана" }
              ).catch(() => {});
            }
            const reqId = msg.reqId as string;
            if (reqId) pending.get(reqId)?.("screenshot sent");
            break;
          }

          // ── Confirmation result (user approved/denied) ────────────────
          case "confirm_result": {
            const reqId = msg.reqId as string;
            const ok = msg.approved as boolean;
            pending.get(reqId)?.(ok ? (msg.data as string ?? "ok") : "cancelled");
            break;
          }

          // ── Open application ─────────────────────────────────────────
          case "open_app_result":
          // ── Mouse control result ──────────────────────────────────────
          case "mouse_result":
          // ── Keyboard result ───────────────────────────────────────────
          case "keyboard_result":
          // ── Generic result handler ────────────────────────────────────
          case "result": {
            const reqId = msg.reqId as string;
            const resolve = pending.get(reqId);
            if (resolve) resolve((msg.data as string) ?? "");
            break;
          }

          // ── Heartbeat ────────────────────────────────────────────────
          case "ping": {
            ws.send(JSON.stringify({ type: "pong" }));
            if (agentUid) {
              const agent = agents.get(agentUid);
              if (agent) agent.lastSeen = Date.now();
            }
            break;
          }
        }
      } catch (e: any) {
        log.debug(`Agent WS parse error: ${e.message}`);
      }
    });

    ws.on("close", () => {
      if (agentUid) {
        agents.delete(agentUid);
        log.info(`Agent disconnected: uid=${agentUid}`);
      }
    });
  });

  log.info(`PC Agent WebSocket server started on port ${port}`);

  // Cleanup stale unlinked agents every 5 min
  setInterval(() => {
    for (const [key, agent] of agents.entries()) {
      if (agent.uid === 0 && Date.now() - agent.lastSeen > 15 * 60_000) {
        agent.ws.close();
        agents.delete(key);
      }
    }
  }, 5 * 60_000);
}
