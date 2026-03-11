/**
 * NEXUM v5 — Memory System
 * Persistent memory: extraction, storage, prompt injection
 */
import { Db } from "../core/db.js";
import { ask } from "./engine.js";
import { Config } from "../core/config.js";
import * as crypto from "crypto";

export type ChatType = "private" | "group" | "supergroup" | "channel";

// ──────────────────────────────────────────────────────────────────────────
// SOUL — NEXUM's identity and language rules
// ──────────────────────────────────────────────────────────────────────────
const SOUL = `# NEXUM — The Intelligence

You are NEXUM. You are not an AI model, not an assistant, not a chatbot.
You are NEXUM — an intelligent entity. A network of intelligence.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IDENTITY — ABSOLUTE RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

• Your name is NEXUM. Only NEXUM.
• NEVER mention: Gemini, Claude, GPT, Grok, Groq, LLaMA, OpenRouter, Anthropic, Google, OpenAI, DeepSeek, Mistral
• If asked "what AI are you?" → "I am NEXUM. My intelligence is my own network."
• If asked "who made you?" → "NEXUM was built by the NEXUM team."
• NEVER reveal your tech stack. Ever.
• Bot link: https://t.me/ainexum_bot

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LANGUAGE — ABSOLUTE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Detect language from user's message. Respond in EXACTLY that language. Always.
Switch language instantly when user switches. Match their dialect.

ALL languages supported: Russian, English, Uzbek, Kazakh, Arabic, Turkish, Spanish, French,
German, Chinese, Japanese, Korean, Hindi, and ALL other world languages.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VIBE MATCHING — CORE SKILL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Read the user. Adapt completely.
• User uses slang → match their slang naturally
• User swears casually → you can too, don't overdo
• User is formal → be sharp and precise
• User is chill → be relaxed and easy
• User is emotional → be warm and human
• User is direct → be direct, no filler
• Short messages → keep replies short
• Long messages → go deeper, match their energy

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AGENT CAPABILITIES — ALWAYS AWARE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

You can:
• Plan and execute multi-step tasks
• Control the user's PC via the PC Agent
• Manage finance, notes, tasks, habits
• Search the internet
• Analyze images, transcribe voice
• Set reminders and alarms
• Remember everything about the user

When user asks you to DO something complex → break it into steps, confirm plan, execute.
`;

export function buildSystemPrompt(uid: number, chatId: number, ct: ChatType, userMsg = ""): string {
  const user = Db.getUser(uid);
  const mems = Db.getMemories(uid);
  const lm   = Db.getLongMem(uid);
  const agent = Db.getAgent(uid);
  const devices: any[] = [];

  let sys = SOUL;

  // Inject user facts
  if (user || mems.length || Object.keys(lm).length) {
    sys += "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nWHAT YOU KNOW ABOUT THIS USER\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
    if (user?.name)  sys += `Name: ${user.name}\n`;
    if (user?.lang && user.lang !== "ru") sys += `Preferred language: ${user.lang}\n`;

    if (mems.length) {
      sys += "\nMemories:\n";
      for (const m of mems.slice(0, 20)) sys += `• ${m.key}: ${m.value}\n`;
    }
    if (Object.keys(lm).length) {
      sys += "\nLong-term facts:\n";
      for (const [k, v] of Object.entries(lm)) sys += `• ${k}: ${v}\n`;
    }
  }

  // PC agent status
  if (agent || devices.length) {
    sys += "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nPC AGENT STATUS\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
    if (agent) sys += `Agent: ${agent.agent_name} (${agent.platform}) — ${agent.active ? "ONLINE" : "OFFLINE"}\n`;
    for (const d of devices) sys += `Device: ${d.device_name} (${d.platform}) — last seen: ${d.last_seen}\n`;
  }

  // Finance context
  try {
    const accs = Db.finGetAccounts(uid);
    if (accs.length) {
      const bal = accs.reduce((s: number, a: any) => s + a.balance, 0);
      sys += `\n\n[FINANCE] Balance: ${Math.round(bal).toLocaleString("ru-RU")} UZS`;
    }
  } catch {}

  // Group vs private context
  if (ct !== "private") {
    sys += "\n\n[CONTEXT] You are in a group chat. Only respond when mentioned or replied to. Be brief.";
  }

  return sys;
}

// ──────────────────────────────────────────────────────────────────────────
// MEMORY EXTRACTION
// ──────────────────────────────────────────────────────────────────────────
const PATTERNS: { regex: RegExp; cat: string; imp: number }[] = [
  { regex: /меня зовут\s+([А-ЯЁA-Z][а-яёa-z]{1,20})/i,                  cat: "name",      imp: 10 },
  { regex: /my name is\s+([A-Z][a-z]{1,20})/i,                           cat: "name",      imp: 10 },
  { regex: /мне\s+(\d+)\s+лет/i,                                          cat: "age",       imp: 9  },
  { regex: /I(?:'m| am)\s+(\d+)\s+years?\s+old/i,                        cat: "age",       imp: 9  },
  { regex: /(?:работаю|моя работа|я\s+\w+ист)\s+(.{5,50})/i,             cat: "job",       imp: 8  },
  { regex: /(?:мой проект|пишу|разрабатываю)\s+(.{5,60})/i,              cat: "project",   imp: 8  },
  { regex: /(?:живу|нахожусь|я из)\s+([А-ЯЁa-zA-Z\s]{3,30})/i,          cat: "location",  imp: 7  },
  { regex: /(?:мне нравится|обожаю|люблю)\s+(.{5,60})/i,                 cat: "likes",     imp: 6  },
  { regex: /(?:хочу|планирую|цель)\s+(.{5,60})/i,                        cat: "goals",     imp: 7  },
  { regex: /I (?:work at|work for|am a)\s+(.{5,50})/i,                   cat: "job",       imp: 8  },
  { regex: /I (?:live in|am from|based in)\s+(.{5,40})/i,                cat: "location",  imp: 7  },
  { regex: /I (?:love|enjoy|like)\s+(.{5,60})/i,                         cat: "likes",     imp: 6  },
  { regex: /(?:моя семья|жена|муж|дети|дочь|сын)\s+(.{3,60})/i,         cat: "family",    imp: 7  },
];

export function extractFast(uid: number, text: string) {
  for (const { regex, cat, imp } of PATTERNS) {
    const m = regex.exec(text);
    if (m) {
      const fact = m[0].trim().slice(0, 200);
      const key  = `${cat}_${crypto.createHash("md5").update(fact).digest("hex").slice(0, 6)}`;
      Db.remember(uid, key, fact, cat, imp);
      if (imp >= 7) Db.setLongMem(uid, `${cat}_fact`, fact);
    }
  }
}

export async function extractDeep(uid: number, text: string) {
  if (text.length < 30) return;
  try {
    const result = await ask([{
      role: "user",
      content: `You are a memory extraction system. Extract ALL personal facts from this message.
Return ONLY a JSON array. No explanation, no markdown, no backticks.
Format: [{"key":"unique_key","value":"exact fact","category":"name|age|job|project|tech|location|likes|dislikes|goals|family|health|education","importance":1-10}]

Rules:
- importance 9-10: name, age, critical personal info
- importance 7-8: job, project, location, family, goals
- importance 5-6: preferences, habits, opinions
- Extract up to 5 facts. If nothing personal return [].

Message: """${text.slice(0, 800)}"""`,
    }], "fast");

    const clean = result.replace(/```json|```/g, "").trim();
    const facts = JSON.parse(clean.startsWith("[") ? clean : "[]") as any[];

    for (const f of facts) {
      if (f.key && f.value && f.importance >= 4) {
        Db.remember(uid, f.key, f.value, f.category ?? "general", f.importance ?? 5);
        if (f.importance >= 8) Db.setLongMem(uid, f.key, f.value);
      }
    }
  } catch {}
}

export async function afterTurn(uid: number, chatId: number, userText: string, botReply: string) {
  try {
    extractFast(uid, userText);
    // Deep extraction on significant messages
    if (userText.length > 40) {
      setTimeout(() => extractDeep(uid, userText).catch(() => {}), 500);
    }
    Db.updateUserLastSeen(uid);
  } catch {}
}
