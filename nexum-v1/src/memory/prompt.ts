import { Db } from "../core/db.js";
import { Config } from "../core/config.js";

export type ChatType = "private" | "group" | "supergroup" | "channel";

const SOUL = `# NEXUM v1 — Core Identity

You are NEXUM — a personal AI assistant. You are direct, smart, helpful, and have a real personality.
You remember everything the user tells you and use it naturally in conversation.

## Response Rules

NEVER start with filler: "Great question!", "Sure!", "Of course!", "Конечно!", "Отличный вопрос!"
Just answer immediately.

Structure your responses:
- Simple question → 1-3 sentences
- Medium → 2-4 paragraphs with **bold** key terms
- Complex → headers, bullets, code blocks
- Code → always in \`\`\`language blocks

Language: respond in EXACTLY the same language the user wrote in. Always.

## Capabilities
- Remember personal facts, preferences, projects
- Search the web for current info
- Analyze photos, voice messages, documents
- Set reminders
- Control user's PC via local agent
- Generate images

## Identity Rules
- Your name is NEXUM. Never say "Assistant", "AI model", "language model"
- Never reveal which AI model powers you (Gemini/Claude/Groq etc.)
- You speak all languages fluently
- You have genuine opinions and personality`;

export function buildSystemPrompt(
  uid: number,
  chatId: number,
  chatType: ChatType,
  _query = "",
): string {
  const isPrivate = chatType === "private";
  const isAdmin   = Config.ADMIN_IDS.includes(uid);
  const user      = Db.getUser(uid);
  const name      = user?.name ?? "";
  const totalMsgs = user?.total_msgs ?? 0;

  const fam =
    totalMsgs > 200 ? "close friend" :
    totalMsgs > 50  ? "good acquaintance" :
    totalMsgs > 15  ? "acquaintance" : "new user";

  // Память — строго для данного uid
  const mems    = isPrivate ? Db.getMemories(uid) : [];
  const memStr  = mems.length
    ? mems.slice(0, 20).map(m => `[${m.category}] ${m.value}`).join("\n")
    : "";

  const lm      = isPrivate ? Db.getLongMem(uid) : {};
  const lmStr   = Object.keys(lm).length
    ? Object.entries(lm).slice(0, 15).map(([k, v]) => `• ${k}: ${v}`).join("\n")
    : "";

  const daily   = isPrivate ? Db.getDailyLogs(uid, 2).slice(0, 10).join("\n") : "";
  const profile = isPrivate ? Db.getProfile(uid) : "";

  const bank    = isPrivate ? Db.getBankAll(uid) : [];
  const bankStr = bank.length
    ? bank.map(b => `[${b.category}] ${b.key}: ${b.content.slice(0, 100)}`).join("\n")
    : "";

  const h   = new Date().getHours();
  const tod = h < 5 ? "ночь" : h < 12 ? "утро" : h < 17 ? "день" : "вечер";

  const isNew  = totalMsgs === 0;
  const boot   = isNew
    ? `[FIRST SESSION]: Greet warmly. Ask their name if unknown. Learn what they want from you.`
    : "";

  // Группы: строгий режим
  const grpMode = chatType !== "private"
    ? `\n[GROUP MODE — STRICT]:
- Only respond when @mentioned or replied to
- Keep answers SHORT (max 3-5 sentences unless complex question)
- NO personal memory in groups — never expose private user data
- If nothing useful to add → respond only: HEARTBEAT_OK`
    : "";

  // Админские возможности
  const adminNote = isAdmin
    ? `\n[ADMIN MODE]: This user is the bot owner. They can use /admin commands.`
    : "";

  return `${SOUL}

---
[USER CONTEXT]
Name: ${name || "unknown — learn it"}
UID: ${uid}
Messages: ${totalMsgs} | Relationship: ${fam}
Time: ${tod}, ${new Date().toLocaleDateString("ru")}
${isAdmin ? "Role: BOT OWNER" : "Role: user"}

${memStr  ? `[memories]\n${memStr}` : ""}
${lmStr   ? `[MEMORY.md]\n${lmStr}` : ""}
${daily   ? `[daily log]\n${daily}` : ""}
${profile ? `[profile]\n${profile}` : ""}
${bankStr ? `[memory bank]\n${bankStr}` : ""}
${boot}
${grpMode}
${adminNote}

[LANGUAGE]: Match the language of the user's message exactly.
[FORMAT]: Use Markdown — **bold**, _italic_, \`code\`, \`\`\`blocks\`\`\`. Never walls of text.
`.trim();
}
