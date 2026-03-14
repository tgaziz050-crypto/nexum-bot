// NEXUM Status Reaction Controller — adapted from OpenClaw architecture
// Manages lifecycle of status reactions (queued → thinking → done/error)

import type { Bot } from 'grammy';
import {
  STATUS_REACTIONS,
  NEXUM_SUPPORTED_REACTIONS,
  pickStatusReaction,
  pickContextReaction,
  isSupportedReaction,
} from './format';

export type StatusReactionState = 'queued' | 'thinking' | 'tool' | 'coding' | 'web' | 'done' | 'error' | 'voice' | 'image' | 'memory';

export interface ReactionController {
  /** Set reaction showing current status */
  setStatus(status: StatusReactionState): Promise<void>;
  /** Remove all reactions */
  remove(): Promise<void>;
  /** Set reaction based on message content */
  setContextual(text: string): Promise<void>;
}

export function createReactionController(params: {
  bot: Bot;
  chatId: number;
  messageId: number;
  enabled?: boolean;
}): ReactionController {
  const { bot, chatId, messageId } = params;
  const enabled = params.enabled !== false;
  let currentEmoji: string | null = null;

  async function setReaction(emoji: string): Promise<void> {
    if (!enabled) return;
    if (!isSupportedReaction(emoji)) return;
    if (currentEmoji === emoji) return;
    try {
      await (bot.api.raw as any).setMessageReaction({
        chat_id: chatId,
        message_id: messageId,
        reaction: [{ type: 'emoji', emoji }],
        is_big: false,
      });
      currentEmoji = emoji;
    } catch {
      // Silently ignore — reactions may be disabled in group
    }
  }

  async function removeReaction(): Promise<void> {
    if (!enabled || !currentEmoji) return;
    try {
      await (bot.api.raw as any).setMessageReaction({
        chat_id: chatId,
        message_id: messageId,
        reaction: [],
      });
      currentEmoji = null;
    } catch {
      // Silently ignore
    }
  }

  return {
    async setStatus(status: StatusReactionState) {
      const emoji = pickStatusReaction(status);
      await setReaction(emoji);
    },
    async remove() {
      await removeReaction();
    },
    async setContextual(text: string) {
      const emoji = pickContextReaction(text);
      await setReaction(emoji);
    },
  };
}

// ── Reaction rate limiter (human-like: ~40% of messages) ─────────────────────
export function shouldReact(probability = 0.40): boolean {
  return Math.random() < probability;
}
