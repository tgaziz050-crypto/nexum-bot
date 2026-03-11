import { Db } from "../core/db.js";
import { ask } from "../ai/engine.js";
import { log } from "../core/logger.js";
import * as crypto from "crypto";

// ── Fast regex extraction (no API call) ──────────────────────────────────
const PATTERNS: { regex: RegExp; cat: string; imp: number }[] = [
  { regex: /меня зовут\s+([А-ЯЁA-Z][а-яёa-z]{1,20})/i,                  cat: "name",       imp: 10 },
  { regex: /my name is\s+([A-Z][a-z]{1,20})/i,                           cat: "name",       imp: 10 },
  { regex: /мне\s+(\d+)\s+лет/i,                                          cat: "age",        imp: 9  },
  { regex: /I(?:'m| am)\s+(\d+)\s+years?\s+old/i,                        cat: "age",        imp: 9  },
  { regex: /(?:работаю|моя работа|я\s+\w+ист)\s+(.{5,50})/i,             cat: "job",        imp: 8  },
  { regex: /(?:мой проект|пишу|разрабатываю)\s+(.{5,60})/i,              cat: "project",    imp: 8  },
  { regex: /(?:использую|мой стек|tech stack)\s+(.{5,80})/i,              cat: "tech",       imp: 7  },
  { regex: /(?:живу|нахожусь|я из)\s+([А-ЯЁa-zA-Z\s]{3,30})/i,          cat: "location",   imp: 7  },
  { regex: /(?:мне нравится|обожаю|люблю)\s+(.{5,60})/i,                 cat: "likes",      imp: 6  },
  { regex: /(?:не нравится|ненавижу|надоело)\s+(.{5,60})/i,              cat: "dislikes",   imp: 6  },
  { regex: /(?:хочу|планирую|цель)\s+(.{5,60})/i,                        cat: "goals",      imp: 7  },
  { regex: /I (?:work at|work for|am a)\s+(.{5,50})/i,                   cat: "job",        imp: 8  },
  { regex: /I (?:live in|am from|based in)\s+(.{5,40})/i,                cat: "location",   imp: 7  },
  { regex: /I (?:love|enjoy|like)\s+(.{5,60})/i,                         cat: "likes",      imp: 6  },
  { regex: /(?:боюсь|страх|тревога)\s+(.{5,60})/i,                       cat: "fears",      imp: 6  },
  { regex: /(?:учусь|студент|универ)\s+(.{5,60})/i,                      cat: "education",  imp: 7  },
  { regex: /(?:мой ник|зови меня|называй меня)\s+(\S{2,30})/i,           cat: "nickname",   imp: 9  },
  { regex: /(?:у меня есть|завёл|купил)\s+(.{5,60})/i,                   cat: "owns",       imp: 5  },
  { regex: /(?:моя семья|жена|муж|дети|дочь|сын)\s+(.{3,60})/i,         cat: "family",     imp: 7  },
];

export function extractFast(uid: number, text: string) {
  for (const { regex, cat, imp } of PATTERNS) {
    const m = regex.exec(text);
    if (m) {
      const fact = m[0].trim().slice(0, 200);
      const key  = `${cat}_${crypto.createHash("md5").update(fact).digest("hex").slice(0, 6)}`;
      Db.remember(uid, key, fact, cat, imp);
      if (imp >= 7) {
        Db.setLongMem(uid, `${cat}_fact`, fact);
      }
    }
  }
}

// ── Deep AI extraction — runs on every message > 30 chars ────────────────
export async function extractDeep(uid: number, text: string) {
  if (text.length < 30) return;
  try {
    const result = await ask([{
      role: "user",
      content: `You are a memory extraction system. Extract ALL personal facts from this message.
Return ONLY a JSON array. No explanation, no markdown, no backticks.
Format: [{"key":"unique_key","value":"exact fact","category":"name|age|job|project|tech|location|likes|dislikes|goals|family|health|education|nickname|owns|fears|personality|habit|event","importance":1-10}]

Rules:
- importance 9-10: name, age, critical personal info
- importance 7-8: job, project, location, family, goals
- importance 5-6: preferences, habits, opinions
- importance 3-4: minor mentions
- Extract up to 5 facts
- If nothing personal return []
- Keys must be short_snake_case

Message: "${text.slice(0, 600)}"`,
    }], "fast");

    let clean = result.replace(/```json|```/g, "").trim();
    const match = clean.match(/\[[\s\S]*\]/);
    if (!match) return;
    const arr = JSON.parse(match[0]) as { key: string; value: string; category: string; importance: number }[];
    if (!Array.isArray(arr)) return;

    for (const item of arr.slice(0, 5)) {
      if (!item.key || !item.value) continue;
      const importance = Math.min(10, Math.max(1, item.importance ?? 5));
      Db.remember(uid, item.key.slice(0, 100), item.value.slice(0, 400), item.category ?? "general", importance);
      if (importance >= 7) {
        Db.setLongMem(uid, item.key, item.value);
      }
      Db.setBankEntry(uid, item.category ?? "general", item.key, item.value, importance * 10);
    }
  } catch (e) {
    log.debug(`extractDeep: ${e}`);
  }
}

// ── AI Summarization — compress old conversations into memory ─────────────
export async function summarizeAndCompress(uid: number, chatId: number) {
  try {
    const count = Db.historyCount(uid, chatId);
    if (count < 60) return;

    const history = Db.getHistoryFull(uid, chatId, 60);
    const toSummarize = history.slice(0, 40);
    if (toSummarize.length < 10) return;

    const convo = toSummarize
      .map(m => `${m.role === "user" ? "User" : "NEXUM"}: ${m.content.slice(0, 300)}`)
      .join("\n");

    const result = await ask([{
      role: "user",
      content: `Analyze this conversation and extract a comprehensive summary.
Return ONLY valid JSON, no other text:
{
  "summary": "2-3 sentence summary of what was discussed",
  "facts": [{"key":"fact_key","value":"personal fact","category":"category","importance":1-10}],
  "decisions": ["important decision or conclusion made"],
  "topics": ["main topic 1", "main topic 2"]
}

Conversation:
${convo}`,
    }], "fast");

    const match = result.match(/\{[\s\S]*\}/);
    if (!match) return;
    const data = JSON.parse(match[0]) as {
      summary: string;
      facts: { key: string; value: string; category: string; importance: number }[];
      decisions: string[];
      topics: string[];
    };

    if (data.summary) {
      const summaryKey = `conv_summary_${Date.now()}`;
      Db.setLongMem(uid, summaryKey, data.summary);
      Db.setBankEntry(uid, "conversation_summary", summaryKey, data.summary, 60);
    }

    if (Array.isArray(data.facts)) {
      for (const f of data.facts.slice(0, 10)) {
        if (!f.key || !f.value) continue;
        const imp = Math.min(10, Math.max(1, f.importance ?? 5));
        Db.remember(uid, f.key, f.value, f.category ?? "general", imp);
        if (imp >= 6) Db.setLongMem(uid, f.key, f.value);
      }
    }

    if (Array.isArray(data.decisions)) {
      for (const d of data.decisions.slice(0, 5)) {
        if (d) Db.setBankEntry(uid, "decision", `dec_${crypto.createHash("md5").update(d).digest("hex").slice(0,6)}`, d, 70);
      }
    }

    Db.deleteOldMessages(uid, chatId, 40);
    log.info(`Summarized ${toSummarize.length} messages for uid=${uid}`);
  } catch (e) {
    log.debug(`summarizeAndCompress: ${e}`);
  }
}

// ── After-turn hook ───────────────────────────────────────────────────────
export async function afterTurn(uid: number, chatId: number, userMsg: string, aiResp: string, isPrivate: boolean) {
  if (!isPrivate) return;
  try {
    extractFast(uid, userMsg);

    if (userMsg.length > 30) {
      await extractDeep(uid, userMsg);
    }

    Db.addDailyLog(uid, `[${new Date().toLocaleTimeString("ru")}] User: ${userMsg.slice(0, 200)} | NEXUM: ${aiResp.slice(0, 100)}`);

    const count = Db.historyCount(uid, chatId);
    if (count >= 60) {
      summarizeAndCompress(uid, chatId).catch(() => {});
    }
  } catch (e) {
    log.debug(`afterTurn: ${e}`);
  }
}
