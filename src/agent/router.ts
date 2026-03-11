/**
 * NEXUM v5 — Message Router
 * Detects intent and routes to correct handler
 */

export type Intent =
  | "finance"
  | "note"
  | "task"
  | "habit"
  | "reminder"
  | "alarm"
  | "search"
  | "pc_command"
  | "link_code"
  | "plan"
  | "general";

interface RouteResult {
  intent: Intent;
  confidence: number;
  extracted?: string;
}

// Pattern-based fast intent detection
const ROUTES: { intent: Intent; patterns: RegExp[]; confidence: number }[] = [
  {
    intent: "finance",
    patterns: [
      /потратил|купил|заплатил|расход|трата|оплатил|paid|spent|bought/i,
      /получил зарплат|доход|income|salary|earned/i,
      /перевёл|перевел|transfer/i,
    ],
    confidence: 0.9,
  },
  {
    intent: "note",
    patterns: [
      /запиши|сохрани|запомни|note|save this|записать/i,
      /заметка|добавь в заметки|create note/i,
    ],
    confidence: 0.85,
  },
  {
    intent: "task",
    patterns: [
      /задача|добавь задачу|create task|todo|нужно сделать|нужно выполнить/i,
      /поставь задачу|напомни что нужно/i,
    ],
    confidence: 0.85,
  },
  {
    intent: "reminder",
    patterns: [
      /напомни|reminder|remind me|через \d+|в \d+:\d+|завтра в|сегодня в/i,
      /не забудь напомнить|set reminder/i,
    ],
    confidence: 0.9,
  },
  {
    intent: "alarm",
    patterns: [
      /разбуди|будильник|wake me|alarm|поставь будильник/i,
    ],
    confidence: 0.95,
  },
  {
    intent: "search",
    patterns: [
      /найди в интернете|погугли|поищи|search for|look up|what is the latest/i,
      /курс доллара сегодня|новости|current price/i,
    ],
    confidence: 0.8,
  },
  {
    intent: "link_code",
    patterns: [
      /^[A-Fa-f0-9]{6}$/,
      /^\/link\s+[A-Fa-f0-9]{6}$/i,
    ],
    confidence: 0.99,
  },
  {
    intent: "plan",
    patterns: [
      /скачай|загрузи|download.*и.*сохрани/i,
      /сделай план|составь план|пошагово|step by step/i,
      /автоматизируй|automate/i,
      /открой.*потом.*закрой/i,
    ],
    confidence: 0.75,
  },
  {
    intent: "pc_command",
    patterns: [
      /на моём компе|на пк|на компьютере|execute on pc|на моём ноуте/i,
      /открой программу|запусти программу|open app on my/i,
    ],
    confidence: 0.85,
  },
];

export function detectIntent(text: string): RouteResult {
  const trimmed = text.trim();

  // Check link code format first
  const linkMatch = /^([A-Fa-f0-9]{6})$/.test(trimmed) || /^\/link\s+([A-Fa-f0-9]{6})$/i.test(trimmed);
  if (linkMatch) return { intent: "link_code", confidence: 0.99 };

  let best: RouteResult = { intent: "general", confidence: 0 };

  for (const route of ROUTES) {
    for (const pattern of route.patterns) {
      if (pattern.test(trimmed)) {
        if (route.confidence > best.confidence) {
          best = { intent: route.intent, confidence: route.confidence };
        }
      }
    }
  }

  return best.confidence > 0.6 ? best : { intent: "general", confidence: 1 };
}

export function extractLinkCode(text: string): string | null {
  const m1 = text.match(/^([A-Fa-f0-9]{6})$/);
  if (m1) return m1[1].toUpperCase();
  const m2 = text.match(/\/link\s+([A-Fa-f0-9]{6})/i);
  if (m2) return m2[1].toUpperCase();
  return null;
}
