import { Db } from "../core/db.js";
import { ask } from "../ai/engine.js";
import { log } from "../core/logger.js";
import * as crypto from "crypto";

// ── Fast regex extraction (no API call) ──────────────────────────────────
const PATTERNS: { regex: RegExp; cat: string; imp: number }[] = [
  { regex: /меня зовут\s+([А-ЯЁA-Z][а-яёa-z]{1,20})/i,                 cat: "name",       imp: 10 },
  { regex: /my name is\s+([A-Z][a-z]{1,20})/i,                          cat: "name",       imp: 10 },
  { regex: /мне\s+(\d+)\s+лет/i,                                        cat: "age",        imp: 9  },
  { regex: /(?:работаю|моя работа|я\s+\w+ист)\s+(.{5,50})/i,            cat: "job",        imp: 8  },
  { regex: /(?:мой проект|пишу|разрабатываю)\s+(.{5,60})/i,             cat: "project",    imp: 8  },
  { regex: /(?:использую|мой стек|tech stack)\s+(.{5,80})/i,             cat: "tech",       imp: 7  },
  { regex: /(?:живу|нахожусь|я из)\s+([А-ЯЁa-zA-Z\s]{3,30})/i,         cat: "location",   imp: 7  },
  { regex: /(?:мне нравится|обожаю|люблю)\s+(.{5,60})/i,                cat: "likes",      imp: 6  },
  { regex: /(?:не нравится|ненавижу|надоело)\s+(.{5,60})/i,             cat: "dislikes",   imp: 6  },
  { regex: /(?:хочу|планирую|цель)\s+(.{5,60})/i,                       cat: "goals",      imp: 7  },
  { regex: /I (?:work at|work for|am a)\s+(.{5,50})/i,                  cat: "job",        imp: 8  },
  { regex: /I (?:live in|am from|based in)\s+(.{5,40})/i,               cat: "location",   imp: 7  },
  { regex: /I (?:love|enjoy|like)\s+(.{5,60})/i,                        cat: "likes",      imp: 6  },
];

export function extractFast(uid: number, text: string) {
  for (const { regex, cat, imp } of PATTERNS) {
    const m = regex.exec(text);
    if (m) {
      const fact = m[0].trim().slice(0, 200);
      const key  = `${cat}_${crypto.createHash("md5").update(fact).digest("hex").slice(0, 6)}`;
      Db.remember(uid, key, fact, cat, imp);
      if (imp >= 8) {
        Db.setLongMem(uid, `fact_${key}`, fact);
      }
    }
  }
}

// ── Deep AI extraction (for longer messages) ─────────────────────────────
export async function extractDeep(uid: number, text: string) {
  if (text.length < 50) return;
  try {
    const result = await ask([{
      role: "user",
      content: `Extract personal facts from this message. Return JSON array only, no other text.
Format: [{"key":"short_key","value":"fact","category":"name|job|project|tech|location|preference|goal|age","importance":1-10}]
Only extract clear, factual personal info. Max 3 items. Return [] if nothing important.

Message: "${text.slice(0, 400)}"`,
    }], "fast");

    const clean = result.replace(/```json|```/g, "").trim();
    const arr = JSON.parse(clean) as { key: string; value: string; category: string; importance: number }[];
    if (!Array.isArray(arr)) return;

    for (const item of arr.slice(0, 3)) {
      if (!item.key || !item.value) continue;
      Db.remember(uid, item.key.slice(0, 100), item.value.slice(0, 300), item.category ?? "general", item.importance ?? 5);
      if ((item.importance ?? 0) >= 8) {
        Db.setLongMem(uid, item.key, item.value);
      }
      Db.setBankEntry(uid, item.category ?? "general", item.key, item.value, (item.importance ?? 5) * 10);
    }
  } catch {
    // Silent — extraction is best-effort
  }
}

// ── After-turn hook (runs in background) ─────────────────────────────────
export async function afterTurn(uid: number, userMsg: string, aiResp: string, isPrivate: boolean) {
  if (!isPrivate) return;
  try {
    extractFast(uid, userMsg);
    if (userMsg.length > 50) {
      await extractDeep(uid, userMsg);
    }
    Db.addDailyLog(uid, `[${new Date().toLocaleTimeString("ru")}] User: ${userMsg.slice(0, 150)}`);
  } catch (e) {
    log.debug(`afterTurn: ${e}`);
  }
}
