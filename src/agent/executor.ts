import { chat, Message } from './router.ts';
import { getMemories, getHistory, saveMessage } from './memory.ts';
import { db } from '../core/db.ts';
import { config } from '../core/config.ts';

const SYSTEM = `Ты NEXUM — умный персональный AI-агент в Telegram. Ты помогаешь пользователю управлять задачами, заметками, привычками, финансами, напоминаниями и компьютером.

ВАЖНО: Ты умеешь распознавать намерения и автоматически выполнять действия. Если пользователь просит что-то сделать — ты делаешь это и сообщаешь результат.

Формат ответа: краткий, конкретный, без лишних слов. Используй эмодзи умеренно.
Язык: отвечай на том же языке, на котором пишет пользователь.`;

export interface ExecuteResult {
  text: string;
  action?: string;
  data?: any;
}

export async function execute(
  uid: number,
  userText: string,
  imageData?: string, // base64 image
  imageType?: string, // mime type
): Promise<ExecuteResult> {
  const memories = getMemories(uid);
  const history = getHistory(uid, 8);

  let systemPrompt = SYSTEM;
  if (memories.length) {
    systemPrompt += `\n\nЧто ты знаешь о пользователе:\n${memories.map(m => `- ${m.key}: ${m.value}`).join('\n')}`;
  }

  const messages: Message[] = [{ role: 'system', content: systemPrompt }];

  // Add history
  for (const h of history) {
    messages.push({ role: h.role as any, content: h.content });
  }

  // Build current user message
  let hasImage = false;
  if (imageData) {
    hasImage = true;
    messages.push({
      role: 'user',
      content: [
        { type: 'image_url', image_url: { url: `data:${imageType || 'image/jpeg'};base64,${imageData}` } },
        { type: 'text', text: userText || 'Что на этом изображении? Опиши подробно.' }
      ]
    });
  } else {
    messages.push({ role: 'user', content: userText });
  }

  // Check for tool intents
  const intent = detectIntent(userText);

  if (intent) {
    const toolResult = await handleTool(uid, intent, userText);
    if (toolResult) {
      saveMessage(uid, 'user', userText);
      saveMessage(uid, 'assistant', toolResult.text);
      return toolResult;
    }
  }

  const reply = await chat(messages, hasImage);
  saveMessage(uid, 'user', imageData ? '[изображение] ' + userText : userText);
  saveMessage(uid, 'assistant', reply);

  // Auto-extract memories from conversation
  autoExtractMemory(uid, userText, reply);

  return { text: reply };
}

function detectIntent(text: string): string | null {
  const t = text.toLowerCase();
  if (/напомни|напоминание|remind/i.test(t)) return 'reminder';
  if (/добавь заметку|запиши|note/i.test(t)) return 'note_add';
  if (/задача|задачу|todo|task/i.test(t) && /добавь|создай|поставь/i.test(t)) return 'task_add';
  if (/потратил|потратила|расход|купил|купила|заплатил/i.test(t)) return 'finance_expense';
  if (/получил|доход|зарплата|заработал/i.test(t)) return 'finance_income';
  if (/привычка|habit/i.test(t) && /добавь|создай/i.test(t)) return 'habit_add';
  return null;
}

async function handleTool(uid: number, intent: string, text: string): Promise<ExecuteResult | null> {
  try {
    if (intent === 'reminder') {
      const parsed = parseReminderTime(text);
      if (parsed) {
        const chatId = uid; // Will be set properly by caller
        db.prepare('INSERT INTO reminders (uid, chat_id, text, fire_at) VALUES (?, ?, ?, ?)').run(uid, chatId, parsed.reminderText, parsed.fireAt);
        return { text: `⏰ Напоминание установлено: *${parsed.reminderText}*\n📅 ${formatDate(parsed.fireAt)}`, action: 'reminder' };
      }
    }

    if (intent === 'note_add') {
      const content = text.replace(/добавь заметку|запиши|note:/gi, '').trim();
      if (content.length > 3) {
        db.prepare('INSERT INTO notes (uid, content) VALUES (?, ?)').run(uid, content);
        return { text: `📝 Заметка сохранена:\n_${content}_`, action: 'note' };
      }
    }

    if (intent === 'task_add') {
      const title = text.replace(/добавь задачу|создай задачу|поставь задачу|задача:/gi, '').trim();
      if (title.length > 2) {
        db.prepare('INSERT INTO tasks (uid, title) VALUES (?, ?)').run(uid, title);
        return { text: `✅ Задача создана:\n_${title}_`, action: 'task' };
      }
    }

    if (intent === 'finance_expense') {
      const amountMatch = text.match(/(\d+[\d\s]*)/);
      if (amountMatch) {
        const amount = parseFloat(amountMatch[1].replace(/\s/g, ''));
        const category = detectCategory(text);
        db.prepare('INSERT INTO finance (uid, type, amount, category, note) VALUES (?, ?, ?, ?, ?)').run(uid, 'expense', amount, category, text.substring(0, 100));
        return { text: `💸 Расход записан: *${amount.toLocaleString()}* — ${category}`, action: 'finance' };
      }
    }

    if (intent === 'finance_income') {
      const amountMatch = text.match(/(\d+[\d\s]*)/);
      if (amountMatch) {
        const amount = parseFloat(amountMatch[1].replace(/\s/g, ''));
        db.prepare('INSERT INTO finance (uid, type, amount, category) VALUES (?, ?, ?, ?)').run(uid, 'income', amount, 'Income');
        return { text: `💰 Доход записан: *${amount.toLocaleString()}*`, action: 'finance' };
      }
    }
  } catch (e) {
    console.error('[tool]', e);
  }
  return null;
}

function parseReminderTime(text: string): { fireAt: string; reminderText: string } | null {
  const now = new Date();
  let fireAt: Date | null = null;
  let reminderText = text;

  const throughMatch = text.match(/через\s+(\d+)\s*(минут|час|день|мин)/i);
  const tomorrowMatch = text.match(/завтра\s+в?\s*(\d{1,2})[:\s]?(\d{0,2})/i);
  const todayMatch   = text.match(/сегодня\s+в?\s*(\d{1,2})[:\s]?(\d{0,2})/i);
  const timeMatch    = text.match(/в\s+(\d{1,2})[:\s]?(\d{0,2})/i);
  const minutesMatch = text.match(/(\d+)\s*(минут|мин)/i);
  const hoursMatch   = text.match(/(\d+)\s*час/i);

  if (throughMatch) {
    const n = parseInt(throughMatch[1]);
    const unit = throughMatch[2].toLowerCase();
    fireAt = new Date(now);
    if (unit.startsWith('мин')) fireAt.setMinutes(fireAt.getMinutes() + n);
    else if (unit.startsWith('час')) fireAt.setHours(fireAt.getHours() + n);
    else if (unit.startsWith('ден') || unit.startsWith('дн')) fireAt.setDate(fireAt.getDate() + n);
  } else if (tomorrowMatch) {
    fireAt = new Date(now);
    fireAt.setDate(fireAt.getDate() + 1);
    fireAt.setHours(parseInt(tomorrowMatch[1]), parseInt(tomorrowMatch[2] || '0'), 0, 0);
  } else if (todayMatch) {
    fireAt = new Date(now);
    fireAt.setHours(parseInt(todayMatch[1]), parseInt(todayMatch[2] || '0'), 0, 0);
  } else if (timeMatch) {
    fireAt = new Date(now);
    fireAt.setHours(parseInt(timeMatch[1]), parseInt(timeMatch[2] || '0'), 0, 0);
    if (fireAt <= now) fireAt.setDate(fireAt.getDate() + 1);
  }

  if (!fireAt) return null;

  // Extract reminder text
  reminderText = text
    .replace(/напомни(ть)?(\s+мне)?/gi, '')
    .replace(/через\s+\d+\s*(минут|час|день|мин)/gi, '')
    .replace(/завтра\s+в?\s*\d{1,2}[:\s]?\d{0,2}/gi, '')
    .replace(/сегодня\s+в?\s*\d{1,2}[:\s]?\d{0,2}/gi, '')
    .replace(/в\s+\d{1,2}[:\s]?\d{0,2}/gi, '')
    .trim() || 'Напоминание';

  return { fireAt: fireAt.toISOString(), reminderText };
}

function detectCategory(text: string): string {
  const t = text.toLowerCase();
  if (/еда|кафе|ресторан|обед|ужин|продукт|магазин/i.test(t)) return 'Food';
  if (/такси|убер|транспорт|автобус|метро|бензин/i.test(t)) return 'Transport';
  if (/одежда|кроссовки|обувь/i.test(t)) return 'Clothing';
  if (/кино|кофе|развлечение|игра/i.test(t)) return 'Entertainment';
  if (/коммунал|интернет|телефон|подписка/i.test(t)) return 'Bills';
  if (/аптека|врач|лекарство|здоровье/i.test(t)) return 'Health';
  return 'Other';
}

function formatDate(isoDate: string): string {
  return new Date(isoDate).toLocaleString('ru-RU', { 
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit'
  });
}

function autoExtractMemory(uid: number, userText: string, reply: string) {
  const nameMatch = userText.match(/меня зовут\s+([А-Яа-яA-Za-z]+)/i);
  if (nameMatch) {
    db.prepare(`INSERT INTO memory (uid, key, value) VALUES (?, 'name', ?) ON CONFLICT(uid, key) DO UPDATE SET value=excluded.value`).run(uid, nameMatch[1]);
  }
}
