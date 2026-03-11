import type { Bot } from "grammy";
import type { BotContext } from "../channels/bot.js";
import { nodeExec, nodeScreenshot, nodeSysinfo, getNodeStatus, isNodeConnected } from "../nodes/pcagent.js";

export function registerNodeCommands(bot: Bot<BotContext>) {

  // ── /node_connect ──────────────────────────────────────────────────────
  bot.command(["node_connect", "pc_connect"], async (ctx) => {
    const uid = ctx.from!.id;
    await ctx.reply(
      `💻 *Подключение PC Агента*\n\n` +
      `**1. Скачай агент** (из архива проекта): \`nexum_agent.py\`\n\n` +
      `**2. Установи зависимости:**\n\`\`\`\npip install websockets pyautogui pillow psutil\n\`\`\`\n\n` +
      `**3. Задай переменные:**\n\`\`\`\nNEXUM_WS_URL=ws://твой-сервер:18790\nNEXUM_OWNER_ID=${uid}\nNEXUM_MODE=SAFE\n\`\`\`\n\n` +
      `**4. Автозапуск Windows:**\n` +
      `Отредактируй \`install_windows.bat\` и запусти от администратора\n\n` +
      `**5. Автозапуск Linux/Mac:**\n\`\`\`\nsudo python nexum_agent.py --install-service\n\`\`\`\n\n` +
      `После запуска агент пришлёт уведомление сюда.\n\n` +
      `🆔 Твой ID: \`${uid}\``,
      { parse_mode: "Markdown" }
    );
  });

  // ── /node_status ───────────────────────────────────────────────────────
  bot.command(["node_status", "pc_status"], async (ctx) => {
    const uid    = ctx.from!.id;
    const status = getNodeStatus(uid);
    if (status) {
      await ctx.reply(`🖥 *Статус агента:*\n\n${status}`, { parse_mode: "Markdown" });
    } else {
      await ctx.reply("❌ Агент не подключён.\n\n`/node_connect` — инструкция по установке", { parse_mode: "Markdown" });
    }
  });

  // ── /node_run ──────────────────────────────────────────────────────────
  bot.command(["node_run", "pc_run", "run"], async (ctx) => {
    const uid = ctx.from!.id;
    const cmd = ctx.match?.trim();
    if (!cmd) {
      await ctx.reply("Использование: `/run команда`\n\nПримеры:\n`/run dir`\n`/run ls -la`\n`/run ipconfig`", { parse_mode: "Markdown" });
      return;
    }
    if (!isNodeConnected(uid)) {
      await ctx.reply("❌ Агент не подключён. `/node_connect`", { parse_mode: "Markdown" });
      return;
    }

    const m = await ctx.reply(`⚙️ Выполняю: \`${cmd.slice(0, 80)}\`...`, { parse_mode: "Markdown" });
    try {
      const result = await nodeExec(uid, cmd, 60_000);
      const text = result.slice(0, 3800) || "(нет вывода)";
      await ctx.api.editMessageText(
        ctx.chat!.id, m.message_id,
        `💻 \`${cmd.slice(0, 60)}\`\n\n\`\`\`\n${text}\n\`\`\``,
        { parse_mode: "Markdown" }
      );
    } catch (e: unknown) {
      await ctx.api.editMessageText(
        ctx.chat!.id, m.message_id,
        `❌ ${e instanceof Error ? e.message : String(e)}`
      );
    }
  });

  // ── /screenshot ────────────────────────────────────────────────────────
  bot.command(["screenshot", "screen", "ss"], async (ctx) => {
    const uid = ctx.from!.id;
    if (!isNodeConnected(uid)) { await ctx.reply("❌ Агент не подключён."); return; }
    await ctx.reply("📸 Делаю скриншот...");
    try {
      await nodeScreenshot(uid, ctx.chat!.id);
    } catch (e: unknown) {
      await ctx.reply(`❌ ${e instanceof Error ? e.message : String(e)}`);
    }
  });

  // ── /sysinfo ───────────────────────────────────────────────────────────
  bot.command(["sysinfo", "sys", "pc_info"], async (ctx) => {
    const uid = ctx.from!.id;
    if (!isNodeConnected(uid)) { await ctx.reply("❌ Агент не подключён."); return; }
    const m = await ctx.reply("📊 Получаю данные системы...");
    try {
      const info = await nodeSysinfo(uid);
      await ctx.api.editMessageText(ctx.chat!.id, m.message_id, `🖥 *Система:*\n${info}`, { parse_mode: "Markdown" });
    } catch (e) {
      await ctx.api.editMessageText(ctx.chat!.id, m.message_id, `❌ Timeout`);
    }
  });

  // ── /node_disconnect ───────────────────────────────────────────────────
  bot.command(["node_disconnect", "pc_disconnect"], async (ctx) => {
    await ctx.reply("ℹ️ Останови агент на ПК (Ctrl+C или завершением службы). Он отключится автоматически.");
  });
}
