/**
 * NEXUM v1 — Security Guard
 *
 * Middleware который:
 * 1. Блокирует забаненных пользователей
 * 2. Блокирует доступ если PUBLIC_BOT=false и uid не в ADMIN_IDS
 * 3. Гарантирует что ctx.from.id всегда присутствует
 */

import type { BotContext } from "../telegram/bot.js";
import { Config } from "./config.js";
import { Db } from "./db.js";
import { log } from "./logger.js";
import type { NextFunction } from "grammy";

export async function securityGuard(ctx: BotContext, next: NextFunction): Promise<void> {
  const uid = ctx.from?.id;

  // Без uid — игнорируем (каналы и т.д.)
  if (!uid) { await next(); return; }

  // Бан
  if (Db.isBanned(uid)) {
    log.warn(`Blocked banned user: ${uid}`);
    return;
  }

  // Закрытый бот
  if (!Config.PUBLIC_BOT && !Config.ADMIN_IDS.includes(uid)) {
    await ctx.reply("🔒 Этот бот работает в закрытом режиме.");
    return;
  }

  await next();
}
