import { Bot, Context, SessionFlavor, session } from "grammy";
import { Config } from "../core/config.js";

export interface SessionData { lang: string; }
export type BotContext = Context & SessionFlavor<SessionData>;
export type ChatType = "private" | "group" | "supergroup" | "channel";

export function createBot(): Bot<BotContext> {
  const bot = new Bot<BotContext>(Config.BOT_TOKEN);
  bot.use(session({ initial: (): SessionData => ({ lang: "ru" }) }));
  return bot;
}
