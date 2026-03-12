/**
 * NEXUM — Send formatted AI response to Telegram
 * Handles Markdown parse errors, long message splits, rate limits
 */
import type { Context } from "grammy";
import { formatForTelegram, smartSplit, stripMarkdown } from "./format.js";
import { log } from "../core/logger.js";

export async function send(ctx: Context, text: string): Promise<void> {
  const formatted = formatForTelegram(text);
  const chunks    = smartSplit(formatted);

  for (const chunk of chunks) {
    if (!chunk.trim()) continue;
    try {
      await ctx.reply(chunk, {
        parse_mode: "Markdown",
        link_preview_options: { is_disabled: true },
      });
    } catch (markdownErr: any) {
      // Telegram rejected Markdown — send as plain text
      try {
        const plain = stripMarkdown(chunk);
        await ctx.reply(plain, { link_preview_options: { is_disabled: true } });
      } catch (e2) {
        log.error(`Send totally failed: ${e2}`);
      }
    }
    if (chunks.length > 1) await sleep(200);
  }
}

/** Send a message by chat_id (for schedulers, not in ctx context) */
export async function sendToChatId(bot: any, chatId: number, text: string): Promise<void> {
  const formatted = formatForTelegram(text);
  const chunks    = smartSplit(formatted);

  for (const chunk of chunks) {
    if (!chunk.trim()) continue;
    try {
      await bot.api.sendMessage(chatId, chunk, {
        parse_mode: "Markdown",
        link_preview_options: { is_disabled: true },
      });
    } catch {
      try {
        await bot.api.sendMessage(chatId, stripMarkdown(chunk));
      } catch {}
    }
    if (chunks.length > 1) await sleep(200);
  }
}

function sleep(ms: number) { return new Promise(r => setTimeout(r, ms)); }
