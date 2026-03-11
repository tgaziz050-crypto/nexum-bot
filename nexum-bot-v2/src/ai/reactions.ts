import { Bot } from "grammy";
import { ask } from "./engine.js";
import { log } from "../core/logger.js";

// All 70+ Telegram reactions available
const ALL_REACTIONS = [
  "👍","👎","❤","🔥","🥰","👏","😁","🤔","🤯","😱","🤬","😢","🎉","🤩","🤮","💩",
  "🙏","👌","🕊","🤡","🥱","🥴","😍","🐳","❤‍🔥","🌚","🌭","💯","🤣","⚡","🍌","🏆",
  "💔","🤨","😐","🍓","🍾","💋","🖕","😈","😴","😭","🤓","👻","👨‍💻","👀","🎃","🙈",
  "😇","😂","🤝","✍","🤗","🫡","🎅","🎄","☃","💅","🤪","🗿","🆒","💘","🙉","🦄",
  "😘","💊","🙊","😎","👾","🤷","🤷‍♀","🤷‍♂","😡",
];

// Cooldown: 20s per chat
const lastReactionTime = new Map<number, number>();
// Track last 3 reactions per chat to avoid repetition
const reactionHistory  = new Map<number, string[]>();

// Patterns that trigger an ACK reaction (👀) while bot is "thinking"
const ACK_PATTERNS = [
  /сделай|напиши|создай|придумай|помоги|найди|переведи|объясни/i,
  /make|write|create|find|explain|translate|generate|build/i,
  /дай|покажи|расскажи|нарисуй|сгенерируй/i,
];

export function shouldAck(text: string): boolean {
  return ACK_PATTERNS.some(p => p.test(text));
}

export async function setReaction(bot: Bot, chatId: number, messageId: number, emoji: string, isBig = false) {
  try {
    await (bot.api as unknown as {
      setMessageReaction: (p: { chat_id: number; message_id: number; reaction: unknown[]; is_big: boolean }) => Promise<void>
    }).setMessageReaction({
      chat_id:    chatId,
      message_id: messageId,
      reaction:   [{ type: "emoji", emoji }],
      is_big:     isBig,
    });
  } catch {
    // Reactions fail silently (old bots, no permission, etc.)
  }
}

export async function clearReaction(bot: Bot, chatId: number, messageId: number) {
  try {
    await (bot.api as unknown as {
      setMessageReaction: (p: { chat_id: number; message_id: number; reaction: unknown[] }) => Promise<void>
    }).setMessageReaction({
      chat_id:    chatId,
      message_id: messageId,
      reaction:   [],
    });
  } catch {}
}

export async function smartReact(bot: Bot, chatId: number, messageId: number, userText: string) {
  // Cooldown check
  const now   = Date.now();
  const last  = lastReactionTime.get(chatId) ?? 0;
  if (now - last < 20_000) return;

  const history = reactionHistory.get(chatId) ?? [];

  try {
    const prompt = `You are choosing a Telegram emoji reaction to a message. 
Available reactions: ${ALL_REACTIONS.join(" ")}
Recent reactions used (don't repeat last 3): ${history.slice(-3).join(" ") || "none"}

User message: "${userText.slice(0, 200)}"

Rules:
- Reply with ONLY the single emoji that best matches the message's emotion/topic
- Reply NONE if the message is neutral/plain and no reaction fits
- Don't repeat recently used reactions
- Match the energy: happy → 😁🔥, sad → 😢, funny → 😂🤣, impressive → 🤯💯

Your answer (single emoji or NONE):`;

    const result = await ask([{ role: "user", content: prompt }], "fast");
    const emoji  = result.trim().split(/\s/)[0] ?? "";

    if (!emoji || emoji === "NONE" || !ALL_REACTIONS.includes(emoji)) return;

    // Detect is_big (3+ exclamation marks, or hype words)
    const isBig = /!!!|невероятно|amazing|incredible|обалдеть|охуеть/i.test(userText);

    await setReaction(bot, chatId, messageId, emoji, isBig);
    lastReactionTime.set(chatId, now);

    const updated = [...history, emoji].slice(-5);
    reactionHistory.set(chatId, updated);
  } catch (e) {
    log.debug(`smartReact: ${e}`);
  }
}
