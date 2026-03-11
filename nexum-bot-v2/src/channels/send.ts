import type { Context } from "grammy";
import { formatForTelegram, smartSplit } from "./format.js";
import { log } from "../core/logger.js";

/**
 * Send formatted AI response. Handles:
 * - Markdown parse errors → fall back to plain text
 * - Long messages → split at paragraph boundaries
 */
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
    } catch {
      // Markdown parse failed → strip and send plain
      try {
        const plain = chunk
          .replace(/\*\*(.+?)\*\*/g, "$1")
          .replace(/__(.+?)__/g,     "$1")
          .replace(/\*(.+?)\*/g,     "$1")
          .replace(/_(.+?)_/g,       "$1")
          .replace(/`{3}[\s\S]*?`{3}/g, (m) => m.replace(/`{3}\w*\n?/g, "").trim())
          .replace(/`(.+?)`/g,       "$1")
          .replace(/^#{1,6}\s+/gm,   "")
          .trim();
        await ctx.reply(plain);
      } catch (e2) {
        log.error(`Send totally failed: ${e2}`);
      }
    }
    // Small delay between chunks to respect Telegram rate limits
    if (chunks.length > 1) await sleep(150);
  }
}

function sleep(ms: number) { return new Promise(r => setTimeout(r, ms)); }
