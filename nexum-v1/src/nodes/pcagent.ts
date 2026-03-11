import { WebSocketServer, WebSocket } from "ws";
import { Db } from "../core/db.js";
import { log } from "../core/logger.js";
import type { Bot } from "grammy";
import type { BotContext } from "../channels/bot.js";
import { InlineKeyboard } from "grammy";

interface NodeConn {
  ws:        WebSocket;
  uid:       number;
  name:      string;
  platform:  string;
  version:   string;
  mode:      string;
  lastSeen:  number;
  sysinfo?:  Record<string, unknown>;
}

// taskId → messageId (для редактирования сообщения после ответа)
const pendingConfirms = new Map<string, { chatId: number; msgId: number }>();

const nodes   = new Map<number, NodeConn>();
const pending = new Map<string, (result: string) => void>();

let wss: WebSocketServer | null = null;

export function startNodeServer(port: number, bot: Bot<BotContext>) {
  wss = new WebSocketServer({ port });

  wss.on("connection", (ws) => {
    let uid = 0;

    ws.on("message", async (raw) => {
      try {
        const msg = JSON.parse(raw.toString()) as Record<string, unknown>;
        const type = msg.type as string;

        switch (type) {

          // ── Агент регистрируется ──────────────────────────────────────
          case "register": {
            uid = (msg.uid as number) ?? 0;
            if (!uid) { ws.close(); return; }

            nodes.set(uid, {
              ws,
              uid,
              name:     (msg.name as string)     ?? "PC",
              platform: (msg.platform as string) ?? "unknown",
              version:  (msg.version as string)  ?? "?",
              mode:     (msg.mode as string)      ?? "SAFE",
              lastSeen: Date.now(),
              sysinfo:  (msg.sysinfo as Record<string, unknown>) ?? {},
            });

            Db.upsertAgent(uid, (msg.name as string) ?? "PC", (msg.platform as string) ?? "unknown");
            log.info(`Node registered: uid=${uid} name=${msg.name} mode=${msg.mode}`);
            ws.send(JSON.stringify({ type: "registered", ok: true }));

            // Уведомление в Telegram
            try {
              const si = msg.sysinfo as Record<string, unknown> | undefined;
              const siStr = si
                ? `\n📊 CPU: ${si.cpu_percent ?? "?"}% | RAM: ${si.ram_used_gb}/${si.ram_total_gb}GB | Disk free: ${si.disk_free_gb}GB`
                : "";
              await bot.api.sendMessage(
                uid,
                `🖥 *PC Агент подключён*\n` +
                `Устройство: \`${msg.name}\` (${msg.platform})\n` +
                `Режим: \`${msg.mode}\` | v${msg.version}${siStr}\n\n` +
                `Управляй через:\n` +
                `• \`/node_run команда\` — выполнить команду\n` +
                `• \`/screenshot\` — скриншот экрана\n` +
                `• \`/sysinfo\` — статистика системы`,
                { parse_mode: "Markdown" }
              );
            } catch { /* Пользователь не написал боту — ок */ }
            break;
          }

          // ── Heartbeat ─────────────────────────────────────────────────
          case "heartbeat": {
            const node = nodes.get(uid);
            if (node) {
              node.lastSeen = Date.now();
              if (msg.sysinfo) node.sysinfo = msg.sysinfo as Record<string, unknown>;
            }
            ws.send(JSON.stringify({ type: "heartbeat_ok" }));
            break;
          }

          // ── Результат команды ─────────────────────────────────────────
          case "result": {
            const taskId = msg.taskId as string;
            if (taskId && pending.has(taskId)) {
              pending.get(taskId)!(msg.result as string ?? msg.output as string ?? "");
              pending.delete(taskId);
            }
            break;
          }

          // ── Агент запрашивает подтверждение ───────────────────────────
          // (опасная команда в SAFE mode)
          case "confirm_request": {
            const taskId = msg.taskId as string;
            const cmd    = msg.cmd    as string;

            if (!uid || !taskId || !cmd) break;

            const kb = new InlineKeyboard()
              .text("✅ Разрешить", `confirm_yes:${taskId}`)
              .text("❌ Отклонить", `confirm_no:${taskId}`);

            try {
              const sent = await bot.api.sendMessage(
                uid,
                `⚠️ *Агент запрашивает подтверждение*\n\n` +
                `Команда:\n\`\`\`\n${cmd.slice(0, 500)}\n\`\`\`\n\n` +
                `Это действие помечено как *потенциально опасное*.\n` +
                `Разрешить выполнение?`,
                { parse_mode: "Markdown", reply_markup: kb }
              );
              pendingConfirms.set(taskId, { chatId: uid, msgId: sent.message_id });
              log.info(`Confirm request sent: taskId=${taskId}`);
            } catch (e) {
              log.error(`Confirm request send: ${e}`);
              // Если не смогли спросить — отклоняем автоматически
              ws.send(JSON.stringify({ type: "confirm_response", taskId, approved: false }));
            }
            break;
          }

          // ── Скриншот ─────────────────────────────────────────────────
          case "screenshot": {
            const chatId = msg.chatId as number;
            const data   = msg.data   as string;
            if (chatId && data) {
              try {
                const buf = Buffer.from(data, "base64");
                await bot.api.sendPhoto(chatId, { source: buf });
              } catch (e) {
                log.error(`Screenshot send: ${e}`);
              }
            }
            break;
          }

          // ── Sysinfo response ──────────────────────────────────────────
          case "sysinfo_response": {
            const taskId = msg.taskId as string;
            const si     = msg.sysinfo as Record<string, unknown>;
            if (taskId && pending.has(taskId)) {
              const text = si
                ? `📊 CPU: ${si.cpu_percent}% | RAM: ${si.ram_used_gb}/${si.ram_total_gb}GB (${si.ram_percent}%) | Disk free: ${si.disk_free_gb}GB`
                : "Нет данных";
              pending.get(taskId)!(text);
              pending.delete(taskId);
            }
            break;
          }
        }

      } catch (e) {
        log.debug(`Node WS msg error: ${e}`);
      }
    });

    ws.on("close", () => {
      if (uid && nodes.has(uid)) {
        nodes.delete(uid);
        Db.deactivateAgent(uid);
        log.info(`Node disconnected: uid=${uid}`);
        // Уведомить пользователя
        bot.api.sendMessage(uid, "🔴 *PC Агент отключился*", { parse_mode: "Markdown" }).catch(() => {});
      }
    });
  });

  // ── Обработка кнопок подтверждения ──────────────────────────────────
  bot.callbackQuery(/^confirm_(yes|no):(.+)$/, async (ctx) => {
    const match    = ctx.match!;
    const approved = match[1] === "yes";
    const taskId   = match[2]!;
    const uid      = ctx.from.id;

    const node = nodes.get(uid);
    if (!node) {
      await ctx.answerCallbackQuery("❌ Агент отключён");
      return;
    }

    // Отправляем ответ агенту
    node.ws.send(JSON.stringify({ type: "confirm_response", taskId, approved }));

    // Редактируем сообщение
    const info = pendingConfirms.get(taskId);
    if (info) {
      const statusText = approved ? "✅ *Разрешено*" : "❌ *Отклонено*";
      try {
        await ctx.editMessageText(
          `${statusText} — команда выполняется на ПК`,
          { parse_mode: "Markdown" }
        );
      } catch {}
      pendingConfirms.delete(taskId);
    }

    await ctx.answerCallbackQuery(approved ? "✅ Разрешено" : "❌ Отклонено");
    log.info(`Confirm response: taskId=${taskId} approved=${approved} uid=${uid}`);
  });

  // ── Очистка мёртвых нод каждые 5 мин ────────────────────────────────
  setInterval(() => {
    const cutoff = Date.now() - 5 * 60_000;
    for (const [id, node] of nodes) {
      if (node.lastSeen < cutoff) {
        nodes.delete(id);
        Db.deactivateAgent(id);
        log.warn(`Node timeout, removed: uid=${id}`);
      }
    }
  }, 5 * 60_000);

  log.info(`Node server started on ws://0.0.0.0:${port}`);
}

// ── API для команд ───────────────────────────────────────────────────────
export async function nodeExec(uid: number, cmd: string, timeout = 30_000): Promise<string> {
  const node = nodes.get(uid);
  if (!node) throw new Error("Агент не подключён. Запусти nexum_agent.py на ПК.");

  return new Promise((resolve, reject) => {
    const taskId = `task_${Date.now()}_${Math.random().toString(36).slice(2)}`;
    const tid = setTimeout(() => {
      pending.delete(taskId);
      reject(new Error("Timeout: агент не ответил за 30 секунд"));
    }, timeout);

    pending.set(taskId, (result) => {
      clearTimeout(tid);
      resolve(result);
    });

    node.ws.send(JSON.stringify({ type: "exec", taskId, cmd }));
  });
}

export async function nodeSysinfo(uid: number): Promise<string> {
  const node = nodes.get(uid);
  if (!node) throw new Error("Агент не подключён.");

  return new Promise((resolve, reject) => {
    const taskId = `sysinfo_${Date.now()}`;
    const tid = setTimeout(() => {
      pending.delete(taskId);
      reject(new Error("Timeout"));
    }, 10_000);

    pending.set(taskId, (result) => {
      clearTimeout(tid);
      resolve(result);
    });

    node.ws.send(JSON.stringify({ type: "sysinfo", taskId }));
  });
}

export async function nodeScreenshot(uid: number, chatId: number): Promise<void> {
  const node = nodes.get(uid);
  if (!node) throw new Error("Агент не подключён.");
  node.ws.send(JSON.stringify({ type: "screenshot", chatId }));
}

export function getNodeStatus(uid: number): string | null {
  const node = nodes.get(uid);
  if (!node) return null;
  const ago  = Math.floor((Date.now() - node.lastSeen) / 1000);
  const icon = ago < 60 ? "🟢" : ago < 120 ? "🟡" : "🔴";
  const si   = node.sysinfo;
  const siStr = si
    ? ` | CPU: ${si["cpu_percent"]}% RAM: ${si["ram_percent"]}%`
    : "";
  return `${icon} *${node.name}* (${node.platform}) | Mode: \`${node.mode}\` | ${ago < 60 ? "только что" : `${Math.floor(ago / 60)} мин назад`}${siStr}`;
}

export function isNodeConnected(uid: number): boolean {
  return nodes.has(uid);
}
