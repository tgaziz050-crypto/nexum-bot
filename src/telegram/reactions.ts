/**
 * NEXUM — Smart Reactions
 * Sets actual Telegram emoji reactions ON the user's message.
 * NOT sent as text. Adaptive frequency — not on every message.
 */
import { Bot } from "grammy";
import { ask } from "../agent/engine.js";
import { log } from "../core/logger.js";

// All standard Telegram reactions (emoji only, no custom stickers)
const ALL_REACTIONS = [
  "👍","👎","❤","🔥","🥰","👏","😁","🤔","🤯","😱","🤬","😢","🎉","🤩","🤮","💩",
  "🙏","👌","🕊","🤡","🥱","🥴","😍","🐳","❤‍🔥","🌚","🌭","💯","🤣","⚡","🍌","🏆",
  "💔","🤨","😐","🍓","🍾","💋","🖕","😈","😴","😭","🤓","👻","👨‍💻","👀","🎃","🙈",
  "😇","😂","🤝","✍","🤗","🫡","🎅","🎄","☃","💅","🤪","🗿","🆒","💘","🙉","🦄",
  "😘","💊","🙊","😎","👾","🤷","🤷‍♀","🤷‍♂","😡",
];

// Per-chat cooldown state
const lastReactionTime = new Map<number, number>();
const reactionHistory  = new Map<number, string[]>();
const msgReactionCount = new Map<number, number>(); // messages since last reaction

// Cooldown: minimum 30 seconds between reactions per chat
const COOLDOWN_MS = 30_000;
// Skip every N messages (react to roughly 1 in 5)
const REACT_EVERY_N = 5;

export async function setReaction(bot: Bot, chatId: number, messageId: number, emoji: string, isBig = false) {
  try {
    await (bot.api as any).setMessageReaction({
      chat_id: chatId,
      message_id: messageId,
      reaction: [{ type: "emoji", emoji }],
      is_big: isBig,
    });
  } catch {
    // Silently ignore — reactions may not be supported in all chat types
  }
}

export async function clearReaction(bot: Bot, chatId: number, messageId: number) {
  try {
    await (bot.api as any).setMessageReaction({ chat_id: chatId, message_id: messageId, reaction: [] });
  } catch {}
}

/**
 * Smart react — places emoji reaction on user's message.
 * Rate-limited, not on every message, adapts to message content.
 */
export async function smartReact(bot: Bot, chatId: number, messageId: number, userText: string): Promise<void> {
  const now = Date.now();

  // Cooldown check
  const last = lastReactionTime.get(chatId) ?? 0;
  if (now - last < COOLDOWN_MS) return;

  // Count-based throttle — only react to ~1 in 5 messages
  const count = (msgReactionCount.get(chatId) ?? 0) + 1;
  msgReactionCount.set(chatId, count);
  if (count % REACT_EVERY_N !== 0) return;

  const history = reactionHistory.get(chatId) ?? [];

  try {
    const prompt = `Choose ONE Telegram emoji reaction for this message.
Available: ${ALL_REACTIONS.join(" ")}
Recent (avoid repeating): ${history.slice(-3).join(" ") || "none"}
Message: "${userText.slice(0, 200)}"
Rules:
- Reply with ONLY the emoji (e.g. 👍)
- Reply SKIP if message is plain/neutral
- Match emotion: happy→🔥😁, sad→😢, funny→😂🤣, impressive→🤯💯, question→🤔
Single emoji or SKIP:`;

    const result = await ask([{ role: "user", content: prompt }], "fast");
    const emoji = result.trim().split(/\s/)[0] ?? "";

    if (!emoji || emoji === "SKIP" || emoji === "NONE" || !ALL_REACTIONS.includes(emoji)) return;

    const isBig = /!!!|wow|невероятно|amazing|incredible|обалдеть/i.test(userText);

    await setReaction(bot, chatId, messageId, emoji, isBig);
    lastReactionTime.set(chatId, now);
    reactionHistory.set(chatId, [...history, emoji].slice(-5));
  } catch (e) {
    log.debug(`smartReact: ${e}`);
  }
}
