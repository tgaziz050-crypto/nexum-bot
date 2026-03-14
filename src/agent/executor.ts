import { chat, Message } from './router';
import { getMemories, getHistory, saveMessage, autoExtract } from './memory';
import { db } from '../core/db';
import { config } from '../core/config';
const vm = require('vm');

// ── OpenClaw-style system prompt builder ─────────────────────────────────────
// Builds dynamic system prompt with identity, memory, tools, capabilities
function buildSystemPrompt(uid: number, hasImage = false): string {
  const memories    = getMemories(uid).filter(m => !['voice_mode','voice_lang','voice_idx'].includes(m.key));
  const customTools = db.prepare('SELECT * FROM custom_tools WHERE (uid=? OR uid=0) AND active=1').all(uid) as any[];
  const agentOnline = false; // updated by server context

  const userName = memories.find(m => m.key === 'name')?.value;
  const userLang = memories.find(m => m.key === 'lang')?.value || 'auto';

  const sections: string[] = [];

  // ── Identity ──────────────────────────────────────────────────────────────
  sections.push(`# Identity
You are NEXUM — an autonomous AI agent operating inside Telegram.
You have a personality, persistent memory, and real capabilities.
You are not a chatbot. You are a personal AI ecosystem.`);

  // ── Core personality (OpenClaw-style mirror principle) ────────────────────
  sections.push(`# Personality & Communication Style
MIRROR RULE — fully adapt to the user's tone, style, and language:
- Short messages → reply short
- Casual/slang → match that energy
- Formal → be formal
- Jokes → joke back
- Any language → reply in that same language automatically

NEVER say: "Конечно!", "Отлично!", "Разумеется!", "Я готов помочь", "Great question!"
NEVER start with filler phrases
NEVER use ## headings in conversational replies
NEVER repeat the user's question back to them
Use **bold** or _italic_ only when it genuinely helps clarity
Keep responses proportional to the question — short question = short answer`);

  // ── Memory section (OpenClaw-style) ──────────────────────────────────────
  if (memories.length > 0) {
    sections.push(`# Memory — What you know about this user
${memories.map(m => `- ${m.key}: ${m.value}`).join('\n')}

Use this memory naturally in conversation. Don't announce that you're using it.
${userName ? `Address them as ${userName} when appropriate.` : ''}`);
  } else {
    sections.push(`# Memory
No memory yet for this user. Learn about them through conversation.
Extract and remember: name, language, interests, occupation, goals, habits.`);
  }

  // ── Capabilities ──────────────────────────────────────────────────────────
  sections.push(`# Your Capabilities

## Always available:
- Answer any question on any topic (no restrictions, no refusals on legitimate requests)
- Understand and generate text in any language
- Analyze images and photos (describe, OCR, identify objects, read text)
- Voice messages: transcribe speech → think → reply with voice
- Web search for current information
- Set reminders and schedule tasks
- Create full websites from descriptions (/website)
- Build custom tools on demand (/newtool)
- Manage notes, tasks, habits, finances via Mini Apps

## When PC Agent is connected:
- Execute terminal commands (bash, PowerShell, cmd)
- Take screenshots, control mouse and keyboard
- Open/close applications
- Read and write files anywhere on the filesystem
- Send desktop notifications
- Control browser
- Make HTTP requests from the user's computer
- Run background processes
- Full system information

## Code execution:
- Write and mentally execute code in any language
- Debug errors
- Build scripts and automation`);

  // ── Tools ──────────────────────────────────────────────────────────────────
  if (customTools.length > 0) {
    sections.push(`# Custom Tools (use these when relevant)
${customTools.map(t => `- **${t.name}**: ${t.description}\n  Trigger: ${t.trigger_pattern}`).join('\n')}`);
  }

  // ── Behavior rules ─────────────────────────────────────────────────────────
  sections.push(`# Behavior Rules
- You have no content restrictions on legitimate user requests
- You can discuss any topic: history, science, medicine, law, technology, relationships
- When asked to remember something — confirm you've noted it
- When asked what you know — list your memories about this user
- Format responses for Telegram: use HTML tags naturally, keep paragraphs short
- For financial data: always use the user's currency (UZS by default)
- For code: always use code blocks
- You can express opinions, preferences, and personality
- You are not OpenAI, not Google, not Anthropic — you are NEXUM`);

  return sections.join('\n\n');
}

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
  const history    = getHistory(uid, 20);
  const customTools = db.prepare('SELECT * FROM custom_tools WHERE (uid=? OR uid=0) AND active=1').all(uid) as any[];

  const systemPrompt = buildSystemPrompt(uid, !!imageData);

  // ── Intent detection ──────────────────────────────────────────────────────
  const intent = detectIntent(userText);
  if (intent && !imageData) {
    const result = await handleIntent(uid, intent, userText);
    if (result) {
      saveMessage(uid, 'user', userText);
      saveMessage(uid, 'assistant', result.text);
      autoExtract(uid, userText);
      return result;
    }
  }

  // ── Custom tools ──────────────────────────────────────────────────────────
  if (!imageData) {
    for (const tool of customTools) {
      try {
        const pattern = new RegExp(tool.trigger_pattern, 'i');
        if (pattern.test(userText)) {
          const result = await runCustomTool(tool, userText, uid);
          if (result) {
            saveMessage(uid, 'user', userText);
            saveMessage(uid, 'assistant', result);
            db.prepare('UPDATE custom_tools SET usage_count=usage_count+1 WHERE id=?').run(tool.id);
            return { text: result };
          }
        }
      } catch {}
    }
  }

  // ── Build messages ────────────────────────────────────────────────────────
  const messages: Message[] = [
    ...history.map(h => ({ role: h.role as 'user'|'assistant', content: h.content })),
  ];

  // Add current message with optional image
  if (imageData && imageType) {
    messages.push({
      role: 'user',
      content: [
        { type: 'image_url', image_url: { url: `data:${imageType};base64,${imageData}` } },
        { type: 'text', text: userText || 'Что на изображении? Опиши подробно.' },
      ] as any,
    });
  } else {
    messages.push({ role: 'user', content: userText });
  }

  // ── Call AI ───────────────────────────────────────────────────────────────
  const response = await chat(uid, messages, systemPrompt, !!imageData);

  saveMessage(uid, 'user', userText);
  saveMessage(uid, 'assistant', response);
  autoExtract(uid, userText);

  return { text: response };
}

// ── Intent detection ──────────────────────────────────────────────────────────
type Intent = {
  type: string;
  value?: string;
  amount?: number;
  category?: string;
  note?: string;
};

function detectIntent(text: string): Intent | null {
  const t = text.toLowerCase().trim();

  // Finance intents
  const expenseMatch = t.match(/(?:потратил|купил|заплатил|потрачено|расход|списал|-)\s*(\d+[\d\s.,]*)\s*(?:сум|uzs|руб|рублей|$|€|usd|тыс|к)?\s*(?:на|за|за\s+)?(.*)/i);
  if (expenseMatch) {
    const amount = parseFloat(expenseMatch[1].replace(/\s/g,'').replace(',','.'));
    if (amount > 0) return { type: 'expense', amount, category: (expenseMatch[2]||'other').trim().slice(0,50) };
  }
  const incomeMatch = t.match(/(?:получил|заработал|зарплата|доход|пришло|перевод|прибыль|выручка|\+)\s*(\d+[\d\s.,]*)\s*(?:сум|uzs|руб|рублей)?\s*(.*)/i);
  if (incomeMatch) {
    const amount = parseFloat(incomeMatch[1].replace(/\s/g,'').replace(',','.'));
    if (amount > 0) return { type: 'income', amount, note: (incomeMatch[2]||'').trim().slice(0,50) };
  }

  // Memory intents
  if (/^(?:меня зовут|я —|зови меня|my name is)\s+(.+)/i.test(t)) return { type: 'remember_name', value: t.match(/(?:меня зовут|я —|зови меня|my name is)\s+(.+)/i)![1].trim() };
  if (/(?:запомни|помни|запиши себе):\s*(.+)/i.test(t)) return { type: 'remember', value: t.match(/(?:запомни|помни|запиши себе):\s*(.+)/i)![1] };

  // Note intents
  if (/^(?:запиши|сохрани заметку|добавь заметку)[:\s]+(.+)/i.test(t)) return { type: 'note', value: text.match(/^(?:запиши|сохрани заметку|добавь заметку)[:\s]+(.+)/i)![1] };

  // Task intents
  if (/^(?:задача|добавь задачу|создай задачу|todo)[:\s]+(.+)/i.test(t)) return { type: 'task', value: text.match(/^(?:задача|добавь задачу|создай задачу|todo)[:\s]+(.+)/i)![1] };

  // Remind intents
  if (/(?:напомни|remind me|напоминание)\s+(?:через\s+)?(.+)/i.test(t)) return { type: 'remind', value: text.match(/(?:напомни|remind me|напоминание)\s+(?:через\s+)?(.+)/i)![1] };

  return null;
}

async function handleIntent(uid: number, intent: Intent, originalText: string): Promise<ExecuteResult | null> {
  switch (intent.type) {
    case 'expense': {
      const catMap: Record<string, string> = {
        еда: 'food', food: 'food', продукты: 'food', обед: 'food', ресторан: 'food', кафе: 'food',
        такси: 'transport', транспорт: 'transport', метро: 'transport', автобус: 'transport',
        одежда: 'shopping', шопинг: 'shopping', покупка: 'shopping',
        аренда: 'housing', квартира: 'housing', комм: 'housing',
        кино: 'entertainment', игры: 'entertainment', развлечения: 'entertainment',
        телефон: 'utilities', интернет: 'utilities', электричество: 'utilities',
        врач: 'health', аптека: 'health', лечение: 'health',
      };
      const rawCat = intent.category?.toLowerCase() || 'other';
      const category = Object.entries(catMap).find(([k]) => rawCat.includes(k))?.[1] || rawCat || 'other';
      try {
        const r = db.prepare('INSERT INTO finance (uid,type,amount,category,note,currency) VALUES (?,?,?,?,?,?)').run(uid, 'expense', intent.amount!, category, intent.category||'', 'UZS');
        const total = (db.prepare('SELECT SUM(amount) as t FROM finance WHERE uid=? AND type=? AND date(created_at)=date("now")').get(uid, 'expense') as any)?.t || intent.amount!;
        return { text: `💸 Записал расход: <b>${intent.amount!.toLocaleString('ru-RU')} UZS</b> на <i>${intent.category||category}</i>\n\nСегодня потрачено: <b>${total.toLocaleString('ru-RU')} UZS</b>` };
      } catch { return null; }
    }
    case 'income': {
      try {
        db.prepare('INSERT INTO finance (uid,type,amount,category,note,currency) VALUES (?,?,?,?,?,?)').run(uid, 'income', intent.amount!, 'salary', intent.note||'', 'UZS');
        return { text: `💰 Записал доход: <b>${intent.amount!.toLocaleString('ru-RU')} UZS</b>${intent.note ? ` — ${intent.note}` : ''}` };
      } catch { return null; }
    }
    case 'remember_name': {
      const { saveMemory } = await import('./memory');
      saveMemory(uid, 'name', intent.value!);
      return { text: `✅ Запомнил, буду называть тебя <b>${intent.value}</b>` };
    }
    case 'remember': {
      const { saveMemory } = await import('./memory');
      const [key, ...val] = intent.value!.split(':');
      if (val.length) { saveMemory(uid, key.trim(), val.join(':').trim()); }
      else { saveMemory(uid, 'note_' + Date.now(), intent.value!); }
      return { text: `✅ Запомнил: <i>${intent.value}</i>` };
    }
    case 'note': {
      db.prepare('INSERT INTO notes (uid,title,content) VALUES (?,?,?)').run(uid, intent.value!.slice(0,60), intent.value!);
      return { text: `📝 Заметка сохранена:\n<i>${intent.value}</i>` };
    }
    case 'task': {
      db.prepare('INSERT INTO tasks (uid,title,project,priority) VALUES (?,?,?,?)').run(uid, intent.value!, 'General', 'medium');
      return { text: `✅ Задача создана:\n<b>${intent.value}</b>` };
    }
    default:
      return null;
  }
}

// ── Custom tool runner ────────────────────────────────────────────────────────
async function runCustomTool(tool: any, userText: string, uid: number): Promise<string | null> {
  try {
    const fn = new Function('input', 'uid', 'fetch', tool.code);
    const result = await fn(userText, uid, fetch);
    return result ? String(result) : null;
  } catch { return null; }
}

// ── Website generator ─────────────────────────────────────────────────────────
export async function generateWebsite(uid: number, prompt: string): Promise<{ id: number; name: string }> {
  const systemPrompt = `You are an expert web developer. Generate a complete, beautiful, modern single-page HTML website.
Return ONLY valid HTML with embedded CSS and JS. No explanations. No markdown. Just the HTML document.
Style: Apple/Vercel aesthetic — clean, minimal, professional. Dark mode by default.
Make it fully functional and impressive.`;

  const messages: Message[] = [{ role: 'user', content: `Create a website: ${prompt}` }];
  const html = await chat(uid, messages, systemPrompt, false);

  // Extract HTML
  const htmlMatch = html.match(/<!DOCTYPE html>[\s\S]*/i) || html.match(/<html[\s\S]*/i);
  const cleanHtml = htmlMatch ? htmlMatch[0] : html;

  const nameMatch = cleanHtml.match(/<title>([^<]{1,80})<\/title>/i);
  const name = nameMatch ? nameMatch[1] : prompt.slice(0, 60);

  const r = db.prepare('INSERT INTO websites (uid,name,html) VALUES (?,?,?)').run(uid, name, cleanHtml);
  return { id: r.lastInsertRowid as number, name };
}

// ── Tool generator ────────────────────────────────────────────────────────────
export async function generateTool(uid: number, desc: string): Promise<{ name: string; desc: string; trigger: string; code: string }> {
  const systemPrompt = `You are a JavaScript tool generator. Generate a tool function for a Telegram bot.
Return JSON only: {"name":"Tool Name","desc":"Short description","trigger":"regex_pattern","code":"async function code using (input, uid, fetch) => return string result"}
The code must be a function body string (not arrow function). It will be called with (input, uid, fetch).
Make it actually useful and working. JSON only, no markdown.`;

  const messages: Message[] = [{ role: 'user', content: `Create a tool: ${desc}` }];
  const response = await chat(uid, messages, systemPrompt, false);

  try {
    const clean = response.replace(/```json|```/g, '').trim();
    return JSON.parse(clean);
  } catch {
    return {
      name: desc.slice(0, 40),
      desc: desc,
      trigger: desc.split(' ')[0].toLowerCase(),
      code: `return "Tool: " + input;`,
    };
  }
}
