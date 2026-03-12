/**
 * NEXUM v5 — Message Router
 * Multilingual intent detection — Russian, English, Uzbek, Turkish, Arabic, and more
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
  | "voice_mode"
  | "general";

interface RouteResult {
  intent: Intent;
  confidence: number;
  extracted?: string;
}

const ROUTES: { intent: Intent; patterns: RegExp[]; confidence: number }[] = [
  {
    intent: "finance",
    patterns: [
      // RU
      /потратил|купил|заплатил|расход|трата|оплатил|получил зарплату|доход|перевёл|перевел/i,
      // EN
      /paid|spent|bought|expense|income|salary|earned|transfer|transaction/i,
      // UZ
      /xarajat|sotib oldim|to'ladim|maosh|daromad|pul/i,
      // TR
      /harcadım|satın aldım|ödedim|gelir|maaş|masraf/i,
    ],
    confidence: 0.9,
  },
  {
    intent: "note",
    patterns: [
      // RU
      /запиши|сохрани|запомни|заметка|добавь в заметки/i,
      // EN
      /note|save this|remember this|write down|create note/i,
      // UZ
      /eslab qol|yozib qo'y|qeyd/i,
      // TR
      /not al|kaydet|hatırla/i,
    ],
    confidence: 0.85,
  },
  {
    intent: "task",
    patterns: [
      // RU
      /задача|добавь задачу|нужно сделать|поставь задачу|нужно выполнить/i,
      // EN
      /task|todo|need to|add task|create task/i,
      // UZ
      /vazifa|ish|qilish kerak/i,
      // TR
      /görev|yapılacak|ekle/i,
    ],
    confidence: 0.85,
  },
  {
    intent: "reminder",
    patterns: [
      // RU
      /напомни|напоминание|через \d+|в \d+:\d+|завтра в|сегодня в/i,
      // EN
      /remind|reminder|in \d+ min|at \d+:\d+|tomorrow at/i,
      // UZ
      /eslatib qo'y|eslatma|soat/i,
      // TR
      /hatırlat|hatırlatıcı|saat \d/i,
      // AR
      /ذكرني|تذكير/,
    ],
    confidence: 0.9,
  },
  {
    intent: "alarm",
    patterns: [
      // RU
      /будильник|разбуди|поставь будильник|сигнал/i,
      // EN
      /alarm|wake me|set alarm/i,
      // UZ
      /uyg'ot|budilnik|signal/i,
      // TR
      /alarm|uyandır/i,
    ],
    confidence: 0.9,
  },
  {
    intent: "search",
    patterns: [
      // RU
      /найди|поищи|загугли|поиск|ищи|что такое|кто такой|когда был/i,
      // EN
      /search|find|google|look up|what is|who is|when was/i,
      // UZ
      /qidir|izla|top/i,
      // TR
      /ara|bul|google/i,
      // AR
      /ابحث|جد|ما هو/,
    ],
    confidence: 0.85,
  },
  {
    intent: "pc_command",
    patterns: [
      // RU
      /открой|запусти|скриншот|скрин|включи|выключи|моего компьютера|на компе|агент/i,
      // EN
      /open app|launch|screenshot|screen|my computer|on my pc|pc agent/i,
      // UZ
      /oч|ish|kompyuter|skrinshot/i,
    ],
    confidence: 0.85,
  },
  {
    intent: "habit",
    patterns: [
      // RU
      /привычка|трекер|отметить|стрик|серия|каждый день|ежедневно/i,
      // EN
      /habit|streak|track|daily/i,
      // UZ
      /odat|kunlik/i,
      // TR
      /alışkanlık|günlük/i,
    ],
    confidence: 0.8,
  },
  {
    intent: "voice_mode",
    patterns: [
      /(?:включи|вкл|turn on|enable)\s+(?:голос|voice)/i,
      /(?:выключи|выкл|turn off|disable)\s+(?:голос|voice)/i,
      /(?:отвечай|reply|respond)\s+(?:голосом|by voice|with voice)/i,
    ],
    confidence: 0.95,
  },
];

// Linking code: exactly 6 uppercase hex-like chars
const LINK_CODE_RE = /\b([A-F0-9]{6})\b/i;

export function detectIntent(text: string): RouteResult {
  // Check for linking code
  if (LINK_CODE_RE.test(text.trim()) && text.trim().length <= 10) {
    return { intent: "link_code", confidence: 0.99 };
  }

  let best: RouteResult = { intent: "general", confidence: 0 };

  for (const route of ROUTES) {
    if (route.patterns.some(p => p.test(text))) {
      if (route.confidence > best.confidence) {
        best = { intent: route.intent, confidence: route.confidence };
      }
    }
  }

  return best;
}

export function extractLinkCode(text: string): string | null {
  const m = LINK_CODE_RE.exec(text.trim());
  return m ? m[1]!.toUpperCase() : null;
}
