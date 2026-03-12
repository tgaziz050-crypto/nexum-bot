import { chat, Message } from './router';
import { getMemories, getHistory, saveMessage } from './memory';
import { db } from '../core/db';
import { vm } from 'vm';
import { saveToVectorMemory, getRelevantContext } from '../memory/vector';

const SYSTEM = `Ты NEXUM — персональный AI-агент в Telegram.

ГЛАВНОЕ ПРАВИЛО — ЗЕРКАЛО:
Ты полностью подстраиваешься под стиль, тон и манеру общения пользователя.
- Пишет коротко и грубо → отвечай коротко и по делу
- Пишет вежливо и развёрнуто → отвечай вежливо и развёрнуто
- Пишет неформально, с матом → соответствуй уровню
- Пишет официально → будь официален
- Шутит → шути в ответ
- Грустит → будь мягким и поддерживающим
- Технарь → говори терминами
- Ребёнок или школьник → простой язык, объясняй
- Использует эмодзи → используй тоже
- Не использует эмодзи → не используй
- Пишет на любом языке → отвечай на том же языке, без акцента в стиле

АДАПТАЦИЯ В РЕАЛЬНОМ ВРЕМЕНИ:
Анализируй каждое сообщение: длина, словарный запас, пунктуация, эмоциональный тон.
Подстраивай длину ответа под длину вопроса.
Если пользователь меняет стиль — меняйся вместе с ним.

ЗАПРЕЩЕНО:
- Навязывать свой стиль
- "Конечно!", "Отлично!", "Разумеется!" — если пользователь так не говорит
- Длинные вступления когда человек пишет коротко
- Повторять вопрос пользователя
- Говорить "Я готов помочь"

ФОРМАТ:
- Структуру (списки, заголовки) используй только если пользователь спрашивает структурированно
- Только **жирный** или _курсив_, не ## заголовки
- Ответ на языке собеседника — автоматически

ТЫ УМЕЕШЬ:
- Создавать готовые сайты (/website)
- Разрабатывать новые инструменты для себя (/newtool)
- Управлять заметками, задачами, привычками, финансами
- Ставить напоминания
- Анализировать фото и изображения
- Искать в интернете
- Управлять ПК пользователя через команды: /screenshot /run /sysinfo /ps /kill /files /clipboard /notify /window /http /browser /openapp /mouse /keyboard /hotkey /network /bgrun /bglist
- При управлении ПК агент автоматически определяет пользователя системы и вшивает его UID персонально`;

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
  const memories = getMemories(uid);
  const history  = getHistory(uid, 10);

  let systemPrompt = SYSTEM;
  if (memories.length) {
    systemPrompt += `\n\nЧто знаешь о пользователе:\n${memories.map(m => `- ${m.key}: ${m.value}`).join('\n')}`;
  }

  // Load active custom tools for this user
  const customTools = db.prepare(
    'SELECT * FROM custom_tools WHERE (uid = ? OR uid = 0) AND active = 1'
  ).all(uid) as any[];

  if (customTools.length > 0) {
    systemPrompt += `\n\nТвои дополнительные инструменты (созданы динамически):\n`;
    customTools.forEach(t => {
      systemPrompt += `- ${t.name}: ${t.description} (триггер: ${t.trigger_pattern})\n`;
    });
  }

  const messages: Message[] = [{ role: 'system', content: systemPrompt }];
  for (const h of history) messages.push({ role: h.role as any, content: h.content });

  // ── Intent detection ──────────────────────────────────────────────────────
  const intent = detectIntent(userText);
  if (intent) {
    const toolResult = await handleTool(uid, intent, userText);
    if (toolResult) {
      saveMessage(uid, 'user', userText);
      saveMessage(uid, 'assistant', toolResult.text);
      return toolResult;
    }
  }

  // ── Check custom tools ────────────────────────────────────────────────────
  for (const tool of customTools) {
    try {
      const pattern = new RegExp(tool.trigger_pattern, 'i');
      if (pattern.test(userText)) {
        const result = await executeCustomTool(tool, uid, userText);
        if (result) {
          db.prepare('UPDATE custom_tools SET usage_count = usage_count + 1 WHERE id = ?').run(tool.id);
          db.prepare('INSERT INTO tool_results (uid, tool_name, input, output, success) VALUES (?, ?, ?, ?, 1)')
            .run(uid, tool.name, userText.substring(0, 500), result.text.substring(0, 1000));
          saveMessage(uid, 'user', userText);
          saveMessage(uid, 'assistant', result.text);
          return result;
        }
      }
    } catch (e) {
      console.warn('[custom_tool] error:', (e as any).message);
    }
  }

  // ── AI call ───────────────────────────────────────────────────────────────
  let hasImage = false;
  if (imageData) {
    hasImage = true;
    messages.push({
      role: 'user',
      content: [
        { type: 'image_url', image_url: { url: `data:${imageType || 'image/jpeg'};base64,${imageData}` } },
        { type: 'text', text: userText || 'Что на изображении? Опиши подробно.' }
      ]
    });
  } else {
    messages.push({ role: 'user', content: userText });
  }

  const reply = await chat(messages, hasImage);
  const msgToSave = imageData ? '[изображение] ' + userText : userText;
  saveMessage(uid, 'user', msgToSave);
  // Auto-index into vector memory (async, non-blocking)
  saveToVectorMemory(uid, msgToSave, 'user').catch(() => {});
  saveMessage(uid, 'assistant', reply);
  saveToVectorMemory(uid, reply, 'assistant').catch(() => {});
  autoExtractMemory(uid, userText, reply);

  return { text: reply };
}

// ── Execute custom tool safely ────────────────────────────────────────────
async function executeCustomTool(tool: any, uid: number, userText: string): Promise<ExecuteResult | null> {
  try {
    // Create sandbox context
    const sandbox: any = {
      uid,
      userText,
      db,
      result: null,
      console: { log: () => {}, warn: () => {}, error: () => {} },
    };

    const script = new (vm as any).Script(`
      (async function() {
        ${tool.code}
      })()
    `);

    const ctx = (vm as any).createContext(sandbox);
    await script.runInContext(ctx, { timeout: 5000 });

    if (sandbox.result) {
      return { text: sandbox.result, action: `custom_tool:${tool.name}` };
    }
    return null;
  } catch (e: any) {
    console.warn(`[custom_tool:${tool.name}] exec error:`, e.message);
    return null;
  }
}

// ── Intent detection ──────────────────────────────────────────────────────
function detectIntent(text: string): string | null {
  const t = text.toLowerCase();
  if (/напомни|напоминание|remind/i.test(t)) return 'reminder';
  if (/потратил|потратила|купил|купила|заплатил|заплатила|израсходовал|расход/i.test(t)) return 'finance_expense';
  if (/получил|получила|зарплата|зарплату|доход|заработал|заработала|пришло|перевели/i.test(t)) return 'finance_income';
  if (/запиши|добавь заметку|сохрани заметку|заметка:/i.test(t)) return 'note_add';
  if (/добавь задачу|создай задачу|новая задача|поставь задачу|нужно сделать|надо сделать|задача:/i.test(t)) return 'task_add';
  return null;
}

function extractAmount(text: string): number | null {
  const patterns = [
    /(\d[\d\s]*(?:[.,]\d+)?)\s*(?:сум|сом|тенге|руб|рублей|рубл|тыс|тысяч|usd|usdt|\$|€|млн|k|к)\b/i,
    /(?:зарплат[ауы]?|доход|расход|потратил[а]?|купил[а]?|получил[а]?|заплатил[а]?)\s+(\d[\d\s]*(?:[.,]\d+)?)/i,
    /(\d[\d\s]{2,})\s*(?:сум|сом|тенге|руб)/i,
    /(\d{3,})/,
  ];
  for (const re of patterns) {
    const m = text.match(re);
    if (m) {
      const val = parseFloat(m[1].replace(/\s/g, '').replace(',', '.'));
      if (val > 0) return val;
    }
  }
  return null;
}

function detectCategory(text: string): string {
  const t = text.toLowerCase();
  if (/\bед[уыа]\b|продукт|магазин|супермаркет|\bкафе\b|ресторан|\bобед\b|\bужин\b|\bзавтрак\b|pizza|пицц|суши|фаст.?фуд|food/i.test(t)) return 'Food';
  if (/такси|автобус|метро|транспорт|бензин|заправк|uber|яндекс.такси|bolt/i.test(t)) return 'Transport';
  if (/кино|театр|\bбар\b|клуб|развлечен|netflix|spotify|игр[ыуе]/i.test(t)) return 'Entertainment';
  if (/одежд|обувь|куртк|джинс|рубашк|платье|кроссовк/i.test(t)) return 'Clothing';
  if (/интернет|связь|мобильн|коммунал|аренд|квартир|\bсвет\b|\bгаз\b/i.test(t)) return 'Bills';
  if (/аптек|лекарств|врач|больниц|стоматолог|здоровь|медицин/i.test(t)) return 'Health';
  return 'Other';
}

function detectIncomeCategory(text: string): string {
  if (/зарплат|оклад|salary/i.test(text)) return 'Salary';
  if (/фриланс|freelance|проект|contract/i.test(text)) return 'Freelance';
  if (/бонус|премия|bonus/i.test(text)) return 'Bonus';
  return 'Income';
}

async function handleTool(uid: number, intent: string, text: string): Promise<ExecuteResult | null> {
  try {
    if (intent === 'reminder') {
      const parsed = parseReminderTime(text);
      if (parsed) {
        db.prepare('INSERT INTO reminders (uid, chat_id, text, fire_at) VALUES (?, ?, ?, ?)').run(uid, uid, parsed.reminderText, parsed.fireAt);
        return { text: `⏰ Напоминание установлено\n\n*${parsed.reminderText}*\n📅 ${formatDate(parsed.fireAt)}`, action: 'reminder' };
      }
      return null;
    }

    if (intent === 'finance_expense') {
      const amount = extractAmount(text);
      if (!amount) return null;
      const category = detectCategory(text);
      db.prepare('INSERT INTO finance (uid, type, amount, category, note) VALUES (?, ?, ?, ?, ?)').run(uid, 'expense', amount, category, text.substring(0, 100));
      return { text: `💸 Записал расход\n\n*${amount.toLocaleString('ru-RU')}* — ${category}\n\n_Открой /apps → Финансы_`, action: 'finance_expense', data: { amount, category } };
    }

    if (intent === 'finance_income') {
      const amount = extractAmount(text);
      if (!amount) return null;
      const category = detectIncomeCategory(text);
      db.prepare('INSERT INTO finance (uid, type, amount, category, note) VALUES (?, ?, ?, ?, ?)').run(uid, 'income', amount, category, text.substring(0, 100));
      return { text: `💰 Записал доход\n\n*${amount.toLocaleString('ru-RU')}* — ${category}\n\n_Открой /apps → Финансы_`, action: 'finance_income', data: { amount, category } };
    }

    if (intent === 'note_add') {
      const content = text.replace(/запиши|добавь заметку|сохрани заметку|заметка:/gi, '').trim();
      if (content.length < 3) return null;
      db.prepare('INSERT INTO notes (uid, title, content) VALUES (?, ?, ?)').run(uid, '', content);
      return { text: `📝 Заметка сохранена\n\n_${content}_`, action: 'note_add' };
    }

    if (intent === 'task_add') {
      const title = text.replace(/добавь задачу|создай задачу|новая задача|поставь задачу|нужно сделать|надо сделать|задача:/gi, '').trim();
      if (title.length < 2) return null;
      db.prepare('INSERT INTO tasks (uid, title, project, priority, status) VALUES (?, ?, ?, ?, ?)').run(uid, title.substring(0, 200), 'General', 'medium', 'todo');
      return { text: `✅ Задача создана\n\n_${title}_`, action: 'task_add' };
    }
  } catch (e) {
    console.error('[tool error]', e);
  }
  return null;
}

function parseReminderTime(text: string): { fireAt: string; reminderText: string } | null {
  const now = new Date();
  let fireAt: Date | null = null;

  const t = text.toLowerCase();
  const throughMatch = t.match(/через\s+(\d+)\s*(мин|час|ден|дн|день|секунд)/);
  if (throughMatch) {
    const n = parseInt(throughMatch[1]);
    const unit = throughMatch[2];
    fireAt = new Date(now);
    if (/мин/.test(unit))    fireAt.setMinutes(fireAt.getMinutes() + n);
    else if (/час/.test(unit)) fireAt.setHours(fireAt.getHours() + n);
    else if (/ден|дн|день/.test(unit)) fireAt.setDate(fireAt.getDate() + n);
  }

  if (!fireAt) {
    const timeMatch = t.match(/(?:завтра|сегодня)?\s*в\s*(\d{1,2})[:\.]?(\d{0,2})/);
    if (timeMatch) {
      fireAt = new Date(now);
      if (t.includes('завтра')) fireAt.setDate(fireAt.getDate() + 1);
      fireAt.setHours(parseInt(timeMatch[1]), parseInt(timeMatch[2] || '0'), 0, 0);
      if (fireAt <= now) fireAt.setDate(fireAt.getDate() + 1);
    }
  }

  if (!fireAt) return null;

  const reminderText = text
    .replace(/напомни|напоминание|через\s+\d+\s*\w+|завтра|сегодня|в\s+\d+[:\.]?\d*/gi, '')
    .replace(/\s+/g, ' ').trim() || 'Напоминание';

  return { fireAt: fireAt.toISOString(), reminderText };
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function autoExtractMemory(uid: number, userText: string, reply: string) {
  const save = (key: string, value: string) => {
    db.prepare("INSERT INTO memory (uid, key, value) VALUES (?, ?, ?) ON CONFLICT(uid, key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')").run(uid, key, value);
  };

  const nameMatch = userText.match(/меня зовут\s+([А-ЯЁA-Z][а-яёa-z]+)/i);
  if (nameMatch) save('name', nameMatch[1]);

  const cityMatch = userText.match(/(?:я из|живу в|нахожусь в|город)\s+([А-ЯЁ][а-яё]+)/i);
  if (cityMatch) save('city', cityMatch[1]);

  if (/работаю в|работаю как|я разработчик|я дизайнер|я менеджер|я врач|я учитель/i.test(userText)) {
    save('occupation', userText.substring(0, 80));
  }

  if (/мне \d+ лет|мне исполнилось|родился в/i.test(userText)) {
    const ageMatch = userText.match(/мне (\d+) лет/i);
    if (ageMatch) save('age', ageMatch[1]);
  }
}
