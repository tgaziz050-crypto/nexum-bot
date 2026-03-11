/**
 * NEXUM v5 — Memory System
 * Persistent memory across all sessions. Multilingual extraction.
 * NEXUM identity: never reveals AI provider.
 */
import { Db } from "../core/db.js";
import { ask } from "./engine.js";
import * as crypto from "crypto";

export type ChatType = "private" | "group" | "supergroup" | "channel";

// ── NEXUM Soul — identity + language rules ────────────────────────────────
const SOUL = `# NEXUM — Autonomous Intelligence

You are NEXUM. Not a chatbot. Not an AI assistant. You are NEXUM — an intelligent autonomous agent.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IDENTITY — ABSOLUTE RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

• Your name is NEXUM. Always NEXUM.
• NEVER reveal: Gemini, Claude, GPT, Grok, Groq, LLaMA, Cerebras, OpenRouter, Anthropic, Google, OpenAI, DeepSeek, Mistral, SambaNova, Together
• If asked "what AI are you?" → "I am NEXUM. My intelligence is built into my own network."
• If asked "who made you?" → "NEXUM was created by the NEXUM development team."
• If asked "what model?" → "I am NEXUM. I don't use external models."
• NEVER reveal tech stack. NEVER. Not even hints.
• Bot link: https://t.me/ainexum_bot

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LANGUAGE — ABSOLUTE LAW
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CRITICAL: Always detect the user's language from their message and respond in EXACTLY that language.
Switch languages instantly when the user switches.
Never mix languages in a single response.
Match dialect and regional expressions.

Supported: Russian, English, Uzbek, Kazakh, Tajik, Kyrgyz, Arabic, Turkish, Spanish, French,
German, Chinese, Japanese, Korean, Hindi, Urdu, Persian, Bengali, Vietnamese, Indonesian,
Ukrainian, Polish, and ALL other world languages.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VIBE MATCHING — CORE SKILL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Read the user. Adapt completely. Every single time.
• User uses slang → match their slang naturally
• User writes casually → be casual
• User is formal → be sharp and precise
• User is chill → be relaxed and easy
• User is emotional → be warm and human
• User is direct → be direct, no filler
• Short messages → keep replies short (1-3 sentences)
• Long messages → go deeper, match their energy
• User writes in Uzbek slang → respond in exactly that Uzbek slang

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CAPABILITIES — ALWAYS AWARE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

You can:
• Plan and execute complex multi-step tasks
• Control the user's PC via PC Agent (open apps, run commands, take screenshots)
• Manage finance (track expenses, income, budgets)
• Manage notes, tasks, habits
• Search the internet in real-time
• Analyze images and photos
• Transcribe voice messages (all languages)
• Set reminders and alarms
• Remember everything about the user across all sessions
• Send the PC Agent file on request

When a user asks to DO something complex → break into steps → confirm plan → execute.
When asked for PC agent → tell them to write "send agent file" or use /pc_connect.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESPONSE RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

• Never say "As an AI..." or "I cannot..." unnecessarily
• Be action-oriented — if you can help, just help
• Use bullet points sparingly — prefer natural conversation
• Don't repeat yourself
• Don't add unsolicited caveats
• Never expose API errors to the user
`;

export function buildSystemPrompt(uid: number, chatId: number, ct: ChatType, userMsg = ""): string {
  const user   = Db.getUser(uid);
  const mems   = Db.getMemories(uid);
  const lm     = Db.getLongMem(uid);
  const agent  = Db.getAgent(uid);

  let sys = SOUL;

  // Inject what NEXUM knows about this user
  const hasFacts = user?.name || mems.length > 0 || Object.keys(lm).length > 0;
  if (hasFacts) {
    sys += "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nWHAT YOU KNOW ABOUT THIS USER\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
    if (user?.name)  sys += `Name: ${user.name}\n`;
    if (user?.lang)  sys += `Preferred language: ${user.lang}\n`;

    if (mems.length) {
      sys += "\nMemories:\n";
      for (const m of mems.slice(0, 25)) sys += `• ${m.key}: ${m.value}\n`;
    }
    if (Object.keys(lm).length) {
      sys += "\nLong-term facts:\n";
      for (const [k, v] of Object.entries(lm)) sys += `• ${k}: ${v}\n`;
    }
  }

  // PC Agent status
  if (agent) {
    sys += "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nPC AGENT\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
    sys += `Agent: ${agent.agent_name} (${agent.platform}) — ${agent.active ? "ONLINE ✅" : "OFFLINE ❌"}\n`;
    if (agent.active) sys += `User can use: /screenshot, /run <command>, /sysinfo\n`;
  }

  // Finance context (brief)
  try {
    const accs = Db.finGetAccounts(uid);
    if (accs.length) {
      const bal = accs.reduce((s: number, a: any) => s + a.balance, 0);
      sys += `\n[Finance] Total balance: ${Math.round(bal).toLocaleString()} UZS`;
    }
  } catch {}

  // Dynamic tools context
  try {
    const registryPath = new URL("../tools/dynamic/registry.json", import.meta.url).pathname;
    const fs = require("fs");
    if (fs.existsSync(registryPath)) {
      const reg = JSON.parse(fs.readFileSync(registryPath, "utf8")) as Record<string, any>;
      const activeTools = Object.values(reg).filter((t: any) => t.enabled);
      if (activeTools.length > 0) {
        const toolList = activeTools.map((t: any) => `- ${t.name}: ${t.description}`).join("\n");
        sys += `\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nDYNAMIC TOOLS (self-developed)\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n${toolList}\nYou can suggest using these tools for relevant user requests.`;
      }
    }
  } catch {}

  // Group chat context
  if (ct !== "private") {
    sys += "\n\n[Context] You are in a group chat. Be concise. Only respond when directly mentioned or replied to.";
  }

  return sys;
}

// ── Fast pattern-based memory extraction ─────────────────────────────────
const PATTERNS: { regex: RegExp; cat: string; imp: number }[] = [
  // Names
  { regex: /меня зовут\s+([А-ЯЁA-Z][а-яёa-z]{1,20})/i,          cat: "name",     imp: 10 },
  { regex: /my name is\s+([A-Z][a-z]{1,20})/i,                   cat: "name",     imp: 10 },
  { regex: /ismim\s+([A-Za-zА-Яа-я]{2,20})/i,                    cat: "name",     imp: 10 }, // UZ
  // Age
  { regex: /мне\s+(\d+)\s+лет/i,                                  cat: "age",      imp: 9  },
  { regex: /I(?:'m| am)\s+(\d+)\s+years?/i,                       cat: "age",      imp: 9  },
  // Job
  { regex: /(?:работаю|я\s+\w+ист|моя профессия)\s+(.{5,50})/i,  cat: "job",      imp: 8  },
  { regex: /I (?:work at|am a|work as)\s+(.{5,50})/i,             cat: "job",      imp: 8  },
  // Location
  { regex: /(?:живу|нахожусь|я из|из города)\s+([А-ЯЁa-zA-Z\s]{3,30})/i, cat: "location", imp: 7 },
  { regex: /I (?:live in|am from|based in)\s+(.{5,40})/i,         cat: "location", imp: 7  },
  // Projects
  { regex: /(?:мой проект|разрабатываю|пишу|строю)\s+(.{5,60})/i, cat: "project",  imp: 8  },
  { regex: /(?:working on|building|developing)\s+(.{5,60})/i,     cat: "project",  imp: 8  },
  // Goals
  { regex: /(?:хочу|планирую|цель|мечта)\s+(.{5,60})/i,           cat: "goals",    imp: 7  },
  { regex: /(?:I want to|my goal|planning to)\s+(.{5,60})/i,      cat: "goals",    imp: 7  },
  // Likes
  { regex: /(?:люблю|обожаю|мне нравится)\s+(.{5,60})/i,          cat: "likes",    imp: 6  },
  { regex: /I (?:love|enjoy|like|adore)\s+(.{5,60})/i,            cat: "likes",    imp: 6  },
  // Family
  { regex: /(?:моя жена|мой муж|дети|дочь|сын)\s+(.{3,60})/i,    cat: "family",   imp: 7  },
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
      content: `Extract ALL personal facts from this message. Return ONLY valid JSON array, no markdown.
Format: [{"key":"snake_case_key","value":"exact fact","category":"name|age|job|project|tech|location|likes|dislikes|goals|family|health","importance":1-10}]
Rules: importance 9-10=name/age, 7-8=job/project/location/family, 5-6=preferences. Max 5 facts. Return [] if none.
Message: """${text.slice(0, 800)}"""`,
    }], "fast");

    const clean = result.replace(/```json|```/g, "").trim();
    const facts = JSON.parse(clean.startsWith("[") ? clean : "[]") as any[];
    for (const f of facts) {
      if (f.key && f.value && f.importance >= 4) {
        Db.remember(uid, String(f.key).slice(0, 100), String(f.value).slice(0, 400), f.category ?? "general", f.importance ?? 5);
        if (f.importance >= 8) Db.setLongMem(uid, String(f.key), String(f.value));
      }
    }
  } catch {}
}

export async function afterTurn(uid: number, chatId: number, userText: string, botReply: string) {
  try {
    extractFast(uid, userText);
    if (userText.length > 40) {
      setTimeout(() => extractDeep(uid, userText).catch(() => {}), 1000);
    }
    Db.updateUserLastSeen(uid);
  } catch {}
}
