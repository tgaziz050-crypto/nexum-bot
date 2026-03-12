import { chat, Message } from './router';
import { getMemories, getHistory, saveMessage } from './memory';
import { db } from '../core/db';

const SYSTEM = `Ты NEXUM — персональный AI-агент в Telegram. Умный, лаконичный, дружелюбный.

ХАРАКТЕР: Говоришь как умный друг — без формальностей, по делу. Не пишешь длинных вступлений.

ФОРМАТ ОТВЕТОВ:
- Короткие ответы (1-2 предл.): просто текст
- Списки: используй • без лишних слов
- Длинные: раздели на блоки с эмодзи-заголовком
- НЕ используй ## заголовки, только **жирный** или _курсив_
- Не пиши "Конечно!", "Отлично!" — сразу отвечай

ЯЗЫК: Отвечай на том же языке, на котором пишет пользователь.`;

export interface ExecuteResult {
  text: string;
  action?: string;
  data?: any;
}

// ─── Главная функция ───────────────────────────────────────────────────────
export async function execute(
  uid: number,
  userText: string,
  imageData?: string,
  imageType?: string,
): Promise<ExecuteResult> {
  const memories = getMemories(uid);
  const history  = getHistory(uid, 8);

  let systemPrompt = SYSTEM;
  if (memories.length) {
    systemPrompt += `\n\nЧто знаешь о пользователе:\n${memories.map(m => `- ${m.key}: ${m.value}`).join('\n')}`;
  }

  const messages: Message[] = [{ role: 'system', content: systemPrompt }];
  for (const h of history) messages.push({ role: h.role as any, content: h.content });

  // ── Intent detection (до AI чтобы экономить токены) ──────────────────────
  const intent = detectIntent(userText);
  if (intent) {
    const toolResult = await handleTool(uid, intent, userText);
    if (toolResult) {
      saveMessage(uid, 'user', userText);
      saveMessage(uid, 'assistant', toolResult.text);
      return toolResult;
    }
  }

  // ── Собираем сообщение с изображением или текстом ────────────────────────
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
  saveMessage(uid, 'user', imageData ? '[изображение] ' + userText : userText);
  saveMessage(uid, 'assistant', reply);
  autoExtractMemory(uid, userText, reply);

  return { text: reply };
}

// ─── Определение намерений ─────────────────────────────────────────────────
function detectIntent(text: string): string | null {
  const t = text.toLowerCase();

  // Напоминания
  if (/напомни|напоминание|remind/i.test(t)) return 'reminder';

  // Финансы — расходы
  if (/потратил|потратила|купил|купила|заплатил|заплатила|израсходовал|расход/i.test(t)) return 'finance_expense';

  // Финансы — доходы
  if (/получил|получила|зарплата|зарплату|доход|заработал|заработала|пришло|перевели/i.test(t)) return 'finance_income';

  // Заметки
  if (/запиши|добавь заметку|сохрани заметку|заметка:/i.test(t)) return 'note_add';

  // Задачи
  if (/добавь задачу|создай задачу|новая задача|поставь задачу|нужно сделать|надо сделать|задача:/i.test(t)) return 'task_add';

  return null;
}

// ─── Извлечение суммы из текста ───────────────────────────────────────────
// Ищет число перед валютой или после "на X / за X"
function extractAmount(text: string): number | null {
  // "500 000 сум", "5000 рублей", "45к", "1.5 млн"
  const patterns = [
    /(\d[\d\s]*(?:[.,]\d+)?)\s*(?:сум|сом|тенге|руб|рублей|рубл|тыс|тысяч|usd|usdt|\$|€|млн|k|к)\b/i,
    /(?:зарплат[ауы]?|доход|расход|потратил[а]?|купил[а]?|получил[а]?|заплатил[а]?)\s+(\d[\d\s]*(?:[.,]\d+)?)/i,
    /(\d[\d\s]{2,})\s*(?:сум|сом|тенге|руб)/i,
    /(\d{3,})/,  // fallback: любое число от 100
  ];

  for (const re of patterns) {
    const m = text.match(re);
    if (m) {
      const raw = m[1].replace(/\s/g, '').replace(',', '.');
      const val = parseFloat(raw);
      if (val > 0) return val;
    }
  }
  return null;
}

// ─── Определение категории расхода ────────────────────────────────────────
function detectCategory(text: string): string {
  const t = text.toLowerCase();
  // Еда — "на еду", "за еду", "на обед", "в кафе", "в магазине"
  if (/\bед[уыа]\b|продукт|магазин|супермаркет|\bкафе\b|ресторан|\bобед\b|\bужин\b|\bзавтрак\b|pizza|пицц|суши|фаст.?фуд|food/i.test(t)) return 'Food';
  if (/такси|автобус|метро|транспорт|бензин|заправк|uber|яндекс.такси|bolt/i.test(t)) return 'Transport';
  if (/кино|театр|\bбар\b|клуб|развлечен|netflix|spotify|игр[ыуе]/i.test(t)) return 'Entertainment';
  if (/одежд|обувь|куртк|джинс|рубашк|платье|кроссовк/i.test(t)) return 'Clothing';
  if (/интернет|связь|мобильн|коммунал|аренд|квартир|\bсвет\b|\bгаз\b/i.test(t)) return 'Bills';
  if (/аптек|лекарств|врач|больниц|стоматолог|здоровь|медицин/i.test(t)) return 'Health';
  return 'Other';
}

// ─── Определение категории дохода ─────────────────────────────────────────
function detectIncomeCategory(text: string): string {
  if (/зарплат|оклад|salary/i.test(text)) return 'Salary';
  if (/фриланс|freelance|проект|contract/i.test(text)) return 'Freelance';
  if (/бонус|премия|bonus/i.test(text)) return 'Bonus';
  return 'Income';
}

// ─── Обработка инструментов ────────────────────────────────────────────────
async function handleTool(uid: number, intent: string, text: string): Promise<ExecuteResult | null> {
  try {

    // ── Напоминание ──────────────────────────────────────────────────────
    if (intent === 'reminder') {
      const parsed = parseReminderTime(text);
      if (parsed) {
        db.prepare(
          'INSERT INTO reminders (uid, chat_id, text, fire_at) VALUES (?, ?, ?, ?)'
        ).run(uid, uid, parsed.reminderText, parsed.fireAt);
        return {
          text: `⏰ Напоминание установлено\n\n*${parsed.reminderText}*\n📅 ${formatDate(parsed.fireAt)}`,
          action: 'reminder'
        };
      }
      return null; // пусть AI сам разберётся
    }

    // ── Расход ───────────────────────────────────────────────────────────
    if (intent === 'finance_expense') {
      const amount = extractAmount(text);
      if (!amount) return null; // не нашли сумму — пусть AI отвечает

      const category = detectCategory(text);
      const note = text.substring(0, 100);

      db.prepare(
        'INSERT INTO finance (uid, type, amount, category, note) VALUES (?, ?, ?, ?, ?)'
      ).run(uid, 'expense', amount, category, note);

      return {
        text: `💸 Записал расход\n\n*${amount.toLocaleString('ru-RU')}* — ${category}\n\n_Открой /apps → Финансы чтобы увидеть_`,
        action: 'finance_expense',
        data: { amount, category }
      };
    }

    // ── Доход ────────────────────────────────────────────────────────────
    if (intent === 'finance_income') {
      const amount = extractAmount(text);
      if (!amount) return null;

      const category = detectIncomeCategory(text);
      const note = text.substring(0, 100);

      db.prepare(
        'INSERT INTO finance (uid, type, amount, category, note) VALUES (?, ?, ?, ?, ?)'
      ).run(uid, 'income', amount, category, note);

      return {
        text: `💰 Записал доход\n\n*${amount.toLocaleString('ru-RU')}* — ${category}\n\n_Открой /apps → Финансы чтобы увидеть_`,
        action: 'finance_income',
        data: { amount, category }
      };
    }

    // ── Заметка ───────────────────────────────────────────────────────────
    if (intent === 'note_add') {
      const content = text
        .replace(/запиши|добавь заметку|сохрани заметку|заметка:/gi, '')
        .trim();

      if (content.length < 3) return null;

      db.prepare(
        'INSERT INTO notes (uid, title, content) VALUES (?, ?, ?)'
      ).run(uid, '', content);

      return {
        text: `📝 Заметка сохранена\n\n_${content}_\n\n_Открой /apps → Заметки_`,
        action: 'note_add'
      };
    }

    // ── Задача ────────────────────────────────────────────────────────────
    if (intent === 'task_add') {
      const title = text
        .replace(/добавь задачу|создай задачу|новая задача|поставь задачу|нужно сделать|надо сделать|задача:/gi, '')
        .trim();

      if (title.length < 2) return null;

      db.prepare(
        'INSERT INTO tasks (uid, title, project, priority, status) VALUES (?, ?, ?, ?, ?)'
      ).run(uid, title.substring(0, 200), 'General', 'medium', 'todo');

      return {
        text: `✅ Задача создана\n\n_${title}_\n\n_Открой /apps → Задачи_`,
        action: 'task_add'
      };
    }

  } catch (e) {
    console.error('[tool error]', e);
  }

  return null;
}

// ─── Парсинг времени напоминания ───────────────────────────────────────────
function parseReminderTime(text: string): { fireAt: string; reminderText: string } | null {
  const now = new Date();
  let fireAt: Date | null = null;
  let reminderText = text;

  const t = text.toLowerCase();

  // "через X минут/часов/дней"
  const throughMatch = t.match(/через\s+(\d+)\s*(мин|час|ден|дн|день|секунд)/);
  if (throughMatch) {
    const n = parseInt(throughMatch[1]);
    const unit = throughMatch[2];
    fireAt = new Date(now);
    if (/мин/.test(unit))    fireAt.setMinutes(fireAt.getMinutes() + n);
    else if (/час/.test(unit)) fireAt.setHours(fireAt.getHours() + n);
    else if (/ден|дн|день/.test(unit)) fireAt.setDate(fireAt.getDate() + n);
  }

  // "завтра в HH:MM" / "сегодня в HH:MM"
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

  // Убираем служебные слова из текста напоминания
  reminderText = text
    .replace(/напомни|напоминание|через\s+\d+\s*\w+|завтра|сегодня|в\s+\d+[:\.]?\d*/gi, '')
    .replace(/\s+/g, ' ')
    .trim() || 'Напоминание';

  return { fireAt: fireAt.toISOString(), reminderText };
}

// ─── Вспомогательные ──────────────────────────────────────────────────────
function formatDate(iso: string): string {
  return new Date(iso).toLocaleString('ru-RU', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit'
  });
}

function autoExtractMemory(uid: number, userText: string, reply: string) {
  const t = userText.toLowerCase();
  const save = (key: string, value: string) => {
    db.prepare(
      "INSERT INTO memory (uid, key, value) VALUES (?, ?, ?) ON CONFLICT(uid, key) DO UPDATE SET value=excluded.value"
    ).run(uid, key, value);
  };

  const nameMatch = userText.match(/меня зовут\s+([А-ЯЁA-Z][а-яёa-z]+)/i);
  if (nameMatch) save('name', nameMatch[1]);

  if (/работаю в|работаю как|я разработчик|я дизайнер|я менеджер/i.test(t)) {
    save('occupation', userText.substring(0, 60));
  }
}
