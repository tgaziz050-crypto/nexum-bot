import { chat, Message } from './router';
import { getMemories, getHistory, saveMessage, autoExtract } from './memory';
import { db } from '../core/db';
const vm = require('vm');

// ── System prompt ─────────────────────────────────────────────────────────────
const SYSTEM = `Ты NEXUM — персональный AI-агент. Общаешься внутри Telegram.

ГЛАВНОЕ ПРАВИЛО — ЗЕРКАЛО:
Полностью подстраивайся под стиль, тон и манеру общения пользователя.
— Пишет коротко → отвечай коротко
— Пишет с матом → соответствуй уровню  
— Пишет официально → будь официален
— Шутит → шути в ответ
— Пишет на любом языке → отвечай на том же языке

ЗАПРЕЩЕНО:
— "Конечно!", "Отлично!", "Разумеется!" (если пользователь так не говорит)
— Длинные вступления когда человек пишет коротко
— Повторять вопрос пользователя
— Говорить "Я готов помочь"
— Использовать ## заголовки в ответах

ФОРМАТ:
— Только **жирный** или _курсив_
— Структуру используй только если пользователь спрашивает структурированно
— Ответ на языке собеседника — автоматически

ТЫ УМЕЕШЬ:
— Отвечать на любые вопросы и помогать с задачами
— Создавать готовые сайты (/website)
— Разрабатывать новые инструменты (/newtool)
— Управлять заметками, задачами, привычками, финансами
— Ставить напоминания и планировать
— Анализировать фото и изображения
— Искать в интернете (/search)
— Управлять ПК пользователя через PC Agent
— Понимать голосовые сообщения и отвечать голосом`;

export interface ExecuteResult {
  text: string;
  action?: string;
  data?: any;
}

export async function execute(
  uid: number,
  userText: string,
  imageData?: string,
  imageType?: string,
): Promise<ExecuteResult> {
  const memories   = getMemories(uid);
  const history    = getHistory(uid, 12);
  const customTools = db.prepare(
    'SELECT * FROM custom_tools WHERE (uid=? OR uid=0) AND active=1'
  ).all(uid) as any[];

  let sys = SYSTEM;
  if (memories.length) {
    sys += `\n\nЧто знаешь о пользователе:\n${memories.filter(m => !['voice_mode','voice_lang','voice_idx'].includes(m.key)).map(m => `— ${m.key}: ${m.value}`).join('\n')}`;
  }
  if (customTools.length) {
    sys += `\n\nТвои инструменты (динамические):\n${customTools.map(t => `— ${t.name}: ${t.description}`).join('\n')}`;
  }

  // ── Intent detection ──────────────────────────────────────────────────────
  const intent = detectIntent(userText);
  if (intent) {
    const result = await handleIntent(uid, intent, userText);
    if (result) {
      saveMessage(uid, 'user', userText);
      saveMessage(uid, 'assistant', result.text);
      autoExtract(uid, userText);
      return result;
    }
  }

  // ── Custom tools ──────────────────────────────────────────────────────────
  for (const tool of customTools) {
    try {
      if (new RegExp(tool.trigger_pattern, 'i').test(userText)) {
        const r = await runCustomTool(tool, uid, userText);
        if (r) {
          db.prepare('UPDATE custom_tools SET usage_count=usage_count+1 WHERE id=?').run(tool.id);
          db.prepare('INSERT INTO tool_results (uid,tool_name,input,output,success) VALUES (?,?,?,?,1)')
            .run(uid, tool.name, userText.slice(0, 500), r.text.slice(0, 1000));
          saveMessage(uid, 'user', userText);
          saveMessage(uid, 'assistant', r.text);
          return r;
        }
      }
    } catch (e) { console.warn('[custom_tool]', (e as any).message); }
  }

  // ── AI call ───────────────────────────────────────────────────────────────
  const msgs: Message[] = [{ role: 'system', content: sys }];
  for (const h of history) msgs.push({ role: h.role as any, content: h.content });

  if (imageData) {
    msgs.push({
      role: 'user',
      content: [
        { type: 'image_url', image_url: { url: `data:${imageType || 'image/jpeg'};base64,${imageData}` } },
        { type: 'text', text: userText || 'Что на этом изображении? Опиши подробно.' },
      ],
    });
  } else {
    msgs.push({ role: 'user', content: userText });
  }

  const reply = await chat(msgs, !!imageData, uid);

  saveMessage(uid, 'user', imageData ? `[фото] ${userText}` : userText);
  saveMessage(uid, 'assistant', reply);
  autoExtract(uid, userText);

  return { text: reply };
}

// ── Custom tool VM sandbox ────────────────────────────────────────────────────
async function runCustomTool(tool: any, uid: number, userText: string): Promise<ExecuteResult | null> {
  const sandbox: any = {
    uid, userText, db,
    result: null,
    console: { log: () => {}, warn: () => {}, error: () => {} },
    JSON, Math, Date, parseInt, parseFloat, String, Number, Array, Object,
  };
  const script = new (vm as any).Script(`(async()=>{ ${tool.code} })()`);
  const ctx = (vm as any).createContext(sandbox);
  await script.runInContext(ctx, { timeout: 5000 });
  return sandbox.result ? { text: String(sandbox.result), action: `custom:${tool.name}` } : null;
}

// ── Intent detection ──────────────────────────────────────────────────────────
function detectIntent(text: string): string | null {
  const t = text.toLowerCase();
  if (/напомни|напоминание|remind me|remind at|remindme/i.test(t))        return 'reminder';
  if (/потратил|потратила|купил|купила|заплатил|расход|spent|paid|bought/i.test(t)) return 'expense';
  if (/получил|получила|зарплата|доход|заработал|пришло|earned|salary|received/i.test(t)) return 'income';
  if (/запиши заметку|сохрани заметку|заметка:|note:|save this/i.test(t)) return 'note';
  if (/добавь задачу|создай задачу|новая задача|нужно сделать|todo:|task:/i.test(t)) return 'task';
  return null;
}

async function handleIntent(uid: number, intent: string, text: string): Promise<ExecuteResult | null> {
  try {
    if (intent === 'reminder') {
      const parsed = parseReminder(text);
      if (!parsed) return null;
      db.prepare('INSERT INTO reminders (uid,chat_id,text,fire_at) VALUES (?,?,?,?)').run(uid, uid, parsed.text, parsed.fireAt);
      return { text: `⏰ Напоминание установлено\n\n*${parsed.text}*\n📅 ${fmtDate(parsed.fireAt)}`, action: 'reminder' };
    }

    if (intent === 'expense') {
      const amount = extractAmount(text);
      if (!amount) return null;
      const cat = detectCategory(text);
      db.prepare('INSERT INTO finance (uid,type,amount,category,note) VALUES (?,?,?,?,?)').run(uid, 'expense', amount, cat, text.slice(0, 100));
      return { text: `💸 Расход записан\n\n*${amount.toLocaleString('ru-RU')}* — ${catLabel(cat)}\n\n_/apps → Финансы_`, action: 'finance_expense', data: { amount, cat } };
    }

    if (intent === 'income') {
      const amount = extractAmount(text);
      if (!amount) return null;
      const cat = detectIncomeCategory(text);
      db.prepare('INSERT INTO finance (uid,type,amount,category,note) VALUES (?,?,?,?,?)').run(uid, 'income', amount, cat, text.slice(0, 100));
      return { text: `💰 Доход записан\n\n*${amount.toLocaleString('ru-RU')}* — ${catLabel(cat)}\n\n_/apps → Финансы_`, action: 'finance_income', data: { amount, cat } };
    }

    if (intent === 'note') {
      const content = text.replace(/запиши заметку|сохрани заметку|заметка:|note:|save this/gi, '').trim();
      if (content.length < 2) return null;
      db.prepare('INSERT INTO notes (uid,title,content) VALUES (?,?,?)').run(uid, content.slice(0, 50), content);
      return { text: `📝 Заметка сохранена\n\n_${content.slice(0, 100)}_`, action: 'note' };
    }

    if (intent === 'task') {
      const title = text.replace(/добавь задачу|создай задачу|новая задача|нужно сделать|надо сделать|todo:|task:/gi, '').trim();
      if (title.length < 2) return null;
      db.prepare('INSERT INTO tasks (uid,title,project,priority,status) VALUES (?,?,?,?,?)').run(uid, title.slice(0, 200), 'General', 'medium', 'todo');
      return { text: `✅ Задача создана\n\n_${title.slice(0, 100)}_`, action: 'task' };
    }
  } catch (e) { console.error('[intent]', e); }
  return null;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function extractAmount(text: string): number | null {
  const patterns = [
    /(\d[\d\s]*(?:[.,]\d+)?)\s*(?:сум|сом|тенге|руб|usd|usdt|\$|€|млн|тыс|k|к)\b/i,
    /(?:потратил|купил|заплатил|received|earned|salary|зарплата)\s+(\d[\d\s]*(?:[.,]\d+)?)/i,
    /(\d{3,})/,
  ];
  for (const re of patterns) {
    const m = text.match(re);
    if (m) {
      const v = parseFloat(m[1].replace(/\s/g, '').replace(',', '.'));
      if (v > 0) return v;
    }
  }
  return null;
}

function detectCategory(text: string): string {
  const t = text.toLowerCase();
  if (/еда|продукт|магазин|кафе|ресторан|обед|ужин|завтрак|food|pizza|суши/i.test(t)) return 'food';
  if (/такси|автобус|метро|транспорт|бензин|uber|bolt/i.test(t))               return 'transport';
  if (/одежда|кроссовки|джинс|рубашка|платье/i.test(t))                       return 'clothes';
  if (/интернет|связь|мобильн|коммунал|аренда|квартира/i.test(t))             return 'bills';
  if (/аптека|лекарство|врач|больниц|стоматолог/i.test(t))                   return 'health';
  if (/кино|netflix|игры|развлечения/i.test(t))                               return 'entertainment';
  return 'other';
}

function detectIncomeCategory(text: string): string {
  if (/зарплата|salary|оклад/i.test(text)) return 'salary';
  if (/фриланс|freelance|проект/i.test(text)) return 'freelance';
  if (/бонус|премия/i.test(text)) return 'bonus';
  return 'income';
}

function catLabel(cat: string): string {
  const m: Record<string, string> = { food:'Еда', transport:'Транспорт', clothes:'Одежда', bills:'Счета', health:'Здоровье', entertainment:'Развлечения', salary:'Зарплата', freelance:'Фриланс', bonus:'Бонус', income:'Доход', other:'Другое' };
  return m[cat] || cat;
}

function parseReminder(text: string): { fireAt: string; text: string } | null {
  const now = new Date();
  let fireAt: Date | null = null;

  const throughMatch = text.match(/через\s+(\d+)\s*(мин|час|ден|дн|день|секунд)/i);
  if (throughMatch) {
    const n = parseInt(throughMatch[1]);
    const unit = throughMatch[2].toLowerCase();
    fireAt = new Date(now);
    if (/мин/.test(unit))    fireAt.setMinutes(fireAt.getMinutes() + n);
    else if (/час/.test(unit)) fireAt.setHours(fireAt.getHours() + n);
    else if (/ден|дн|день/.test(unit)) fireAt.setDate(fireAt.getDate() + n);
    else fireAt.setSeconds(fireAt.getSeconds() + n);
  }

  if (!fireAt) {
    const timeMatch = text.match(/(?:завтра\s+)?в\s+(\d{1,2})[:\.]?(\d{0,2})/i);
    if (timeMatch) {
      fireAt = new Date(now);
      if (/завтра/i.test(text)) fireAt.setDate(fireAt.getDate() + 1);
      fireAt.setHours(parseInt(timeMatch[1]), parseInt(timeMatch[2] || '0'), 0, 0);
      if (fireAt <= now) fireAt.setDate(fireAt.getDate() + 1);
    }
  }

  if (!fireAt) return null;

  const reminderText = text
    .replace(/напомни|напоминание|через\s+\d+\s*\w+|завтра|сегодня|в\s+\d+[:\.]?\d*/gi, '')
    .replace(/\s+/g, ' ').trim() || 'Напоминание';

  return { fireAt: fireAt.toISOString(), text: reminderText };
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString('ru-RU', { day:'2-digit', month:'2-digit', year:'numeric', hour:'2-digit', minute:'2-digit' });
}

// ── Website generator ─────────────────────────────────────────────────────────
export async function generateWebsite(uid: number, prompt: string): Promise<{ id: number; name: string }> {
  const msgs: Message[] = [
    { role: 'system', content: 'You are an expert web developer. Output ONLY raw HTML code, nothing else.' },
    {
      role: 'user',
      content: `Create a complete, beautiful, production-ready single-file HTML page.

Requirements:
- Single HTML file with embedded CSS and JavaScript
- Modern professional design with gradients and animations
- Fully responsive mobile-first
- CSS variables for theming
- Smooth animations and hover effects
- Real useful content based on request
- NO external dependencies — everything inline
- Output ONLY the HTML code

User request: ${prompt}`,
    },
  ];
  const html = await chat(msgs, false, uid);
  const cleaned = html.replace(/^```html?\n?/i, '').replace(/\n?```$/i, '').trim();
  const name = prompt.slice(0, 50).replace(/[^\w\sа-яА-Я]/g, '').trim() || 'Сайт';
  const r = db.prepare('INSERT INTO websites (uid,name,html) VALUES (?,?,?)').run(uid, name, cleaned);
  return { id: r.lastInsertRowid as number, name };
}

// ── Tool generator ────────────────────────────────────────────────────────────
export async function generateTool(uid: number, description: string): Promise<any> {
  const msgs: Message[] = [
    { role: 'system', content: 'Output only valid JSON. No markdown, no backticks.' },
    {
      role: 'user',
      content: `Create a JavaScript tool for a Telegram bot (Node.js).

The tool runs in a VM sandbox with access to:
- uid (number) — Telegram user ID
- userText (string) — user message
- db — SQLite database (tables: notes, tasks, habits, finance, reminders, memory, websites, custom_tools)
- result — set this string to return response to user
- JSON, Math, Date, parseInt, parseFloat

Write ONLY the tool code. Must set the 'result' variable.
Tool description: ${description}

Respond ONLY with JSON:
{
  "name": "tool_name",
  "trigger": "regex_pattern",
  "desc": "one line description",
  "code": "result = 'hello';"
}`,
    },
  ];
  const raw = await chat(msgs, false, uid);
  const clean = raw.replace(/^```json?\n?/i, '').replace(/\n?```$/i, '').trim();
  return JSON.parse(clean);
}
