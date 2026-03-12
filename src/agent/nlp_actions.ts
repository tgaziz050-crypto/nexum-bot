/**
 * NLP Actions — auto-detects intent from user message
 * and executes Mini App actions (finance, tasks, notes, habits)
 * Returns { handled: true, summary } if action was taken
 */
import { db } from '../core/db';

interface ActionResult {
  handled: boolean;
  summary?: string;
  action?: string;
}

// ── Finance patterns ──────────────────────────────────────────────────────
const EXPENSE_PATTERNS = [
  /потрат[иыла]+\s+(.+?)\s+на\s+(.+)/i,
  /купил[аи]?\s+(.+?)\s+за\s+(.+)/i,
  /заплатил[аи]?\s+(.+?)\s+за\s+(.+)/i,
  /потрат[иыла]+\s+([\d,. ]+)\s*(uzs|сум|usd|eur|rub|\$|€|£)?/i,
  /spent\s+([\d,.]+)\s*(uzs|usd|eur|rub|\$|€|£)?\s*(?:on\s+(.+))?/i,
  /bought\s+(.+?)\s+for\s+([\d,.]+)/i,
  /paid\s+([\d,.]+)\s+for\s+(.+)/i,
  /xarajat\s+([\d,.]+)/i,
  /сарфладим?\s+([\d,.]+)/i,
];

const INCOME_PATTERNS = [
  /получил[аи]?\s+([\d,.]+)\s*(uzs|сум|usd|eur|rub|\$|€|£)?/i,
  /заработал[аи]?\s+([\d,.]+)/i,
  /пришло\s+([\d,.]+)/i,
  /received\s+([\d,.]+)/i,
  /earned\s+([\d,.]+)/i,
  /salary\s+([\d,.]+)/i,
  /зарплата\s+([\d,.]+)/i,
  /даромад\s+([\d,.]+)/i,
];

const CATEGORY_KEYWORDS: Record<string, string> = {
  еда: 'food', кафе: 'food', ресторан: 'food', обед: 'food', ужин: 'food', завтрак: 'food',
  продукты: 'food', grocery: 'food', food: 'food', cafe: 'food', restaurant: 'food',
  такси: 'trans', метро: 'trans', автобус: 'trans', транспорт: 'trans', taxi: 'trans', uber: 'trans',
  магазин: 'shop', одежда: 'shop', покупка: 'shop', shopping: 'shop', clothes: 'shop',
  жильё: 'home', аренда: 'home', квартира: 'home', rent: 'home', housing: 'home',
  телефон: 'pc', интернет: 'pc', связь: 'pc', internet: 'pc', phone: 'pc',
  кино: 'ent', развлечения: 'ent', игры: 'ent', entertainment: 'ent', games: 'ent',
  зарплата: 'salary', salary: 'salary', работа: 'salary', freelance: 'free', фриланс: 'free',
  здоровье: 'med', аптека: 'med', врач: 'med', health: 'med', medicine: 'med',
  обучение: 'edu', курсы: 'edu', образование: 'edu', education: 'edu',
  авто: 'car', машина: 'car', бензин: 'car', car: 'car', petrol: 'car',
  инвестиции: 'inv', invest: 'inv', акции: 'inv',
};

function detectCategory(text: string): string {
  const lower = text.toLowerCase();
  for (const [kw, cat] of Object.entries(CATEGORY_KEYWORDS)) {
    if (lower.includes(kw)) return cat;
  }
  return 'other';
}

function parseAmount(str: string): number {
  return parseFloat(str.replace(/[, ]/g, '').replace(/[^0-9.]/g, '')) || 0;
}

// ── Task patterns ────────────────────────────────────────────────────────
const TASK_PATTERNS = [
  /(?:добавь|создай|запиши)\s+задачу[:\s]+(.+)/i,
  /(?:нужно|надо)\s+(.+)/i,
  /(?:add|create)\s+task[:\s]+(.+)/i,
  /(?:todo|to do)[:\s]+(.+)/i,
  /vazifa\s*:\s*(.+)/i,
];

// ── Note patterns ────────────────────────────────────────────────────────
const NOTE_PATTERNS = [
  /(?:запиши|сохрани|заметка)[:\s]+(.+)/i,
  /(?:note|save this)[:\s]+(.+)/i,
  /eslatma[:\s]+(.+)/i,
];

// ── Habit patterns ────────────────────────────────────────────────────────
const HABIT_CHECK_PATTERNS = [
  /(?:отметь|сделал[аи]?|выполнил[аи]?)\s+привычку?\s+(.+)/i,
  /(?:did|completed|done)\s+(.+)\s+today/i,
  /привычка\s+(.+)\s+выполнена/i,
];

export async function processNlpAction(uid: number, text: string): Promise<ActionResult> {
  // ── Check expense ──────────────────────────────────────────────────────
  for (const pat of EXPENSE_PATTERNS) {
    const m = text.match(pat);
    if (m) {
      // Try to extract amount
      let amount = 0;
      let note = text;
      // Find first number in text
      const numMatch = text.match(/([\d][\d,. ]*)/);
      if (numMatch) amount = parseAmount(numMatch[1]);
      if (amount > 0) {
        const category = detectCategory(text);
        // Get first account or null
        const acct = db.prepare('SELECT id FROM accounts WHERE uid = ? ORDER BY id LIMIT 1').get(uid) as any;
        db.prepare('INSERT INTO finance (uid, type, amount, category, note, account_id) VALUES (?, ?, ?, ?, ?, ?)').run(uid, 'expense', amount, category, text.substring(0, 200), acct?.id || null);
        if (acct?.id) db.prepare('UPDATE accounts SET balance = balance - ? WHERE id = ?').run(amount, acct.id);
        return {
          handled: true,
          action: 'finance_expense',
          summary: `💸 Записал расход: ${amount.toLocaleString()} на "${text.substring(0, 60)}"`
        };
      }
    }
  }

  // ── Check income ──────────────────────────────────────────────────────
  for (const pat of INCOME_PATTERNS) {
    const m = text.match(pat);
    if (m) {
      const numMatch = text.match(/([\d][\d,. ]*)/);
      const amount = numMatch ? parseAmount(numMatch[1]) : 0;
      if (amount > 0) {
        const category = detectCategory(text);
        const acct = db.prepare('SELECT id FROM accounts WHERE uid = ? ORDER BY id LIMIT 1').get(uid) as any;
        db.prepare('INSERT INTO finance (uid, type, amount, category, note, account_id) VALUES (?, ?, ?, ?, ?, ?)').run(uid, 'income', amount, category, text.substring(0, 200), acct?.id || null);
        if (acct?.id) db.prepare('UPDATE accounts SET balance = balance + ? WHERE id = ?').run(amount, acct.id);
        return {
          handled: true,
          action: 'finance_income',
          summary: `💰 Записал доход: ${amount.toLocaleString()}`
        };
      }
    }
  }

  // ── Check task creation ───────────────────────────────────────────────
  for (const pat of TASK_PATTERNS) {
    const m = text.match(pat);
    if (m && m[1]) {
      const title = m[1].trim().substring(0, 200);
      db.prepare('INSERT INTO tasks (uid, title, project, priority) VALUES (?, ?, ?, ?)').run(uid, title, 'General', 'medium');
      return { handled: true, action: 'task_created', summary: `✅ Задача добавлена: "${title}"` };
    }
  }

  // ── Check note creation ───────────────────────────────────────────────
  for (const pat of NOTE_PATTERNS) {
    const m = text.match(pat);
    if (m && m[1]) {
      const content = m[1].trim().substring(0, 2000);
      db.prepare('INSERT INTO notes (uid, title, content) VALUES (?, ?, ?)').run(uid, content.substring(0, 50), content);
      return { handled: true, action: 'note_created', summary: `📝 Заметка сохранена` };
    }
  }

  return { handled: false };
}
