import { Bot, Context, InputFile } from 'grammy';
import { config } from '../core/config';
import { db, ensureUser } from '../core/db';
import { execute } from '../agent/executor';
import { transcribeVoice } from '../tools/stt';
import { textToSpeech, VOICES, getUserVoicePref, setUserVoicePref } from '../tools/tts';
import { webSearch } from '../tools/search';
import { processNlpAction } from '../agent/nlp_actions';
import { getMemories, clearMemory, clearHistory } from '../agent/memory';
import { chat } from '../agent/router';

// ── Voice mode helpers ────────────────────────────────────────────────────
function getUserVoiceMode(uid: number): string {
  const row = db.prepare("SELECT value FROM memory WHERE uid = ? AND key = 'voice_mode'").get(uid) as any;
  return row?.value || 'auto';
}

function setUserVoiceMode(uid: number, mode: string) {
  db.prepare("INSERT INTO memory (uid, key, value) VALUES (?, 'voice_mode', ?) ON CONFLICT(uid, key) DO UPDATE SET value=excluded.value").run(uid, mode);
}

// ── Safe send — try Markdown first, fallback to plain text ────────────────
async function safeSend(ctx: Context, text: string, extra?: any): Promise<any> {
  try {
    return await ctx.reply(text, { parse_mode: 'Markdown', ...extra });
  } catch (e: any) {
    if (e?.description?.includes('parse') || e?.description?.includes('entity')) {
      return await ctx.reply(text.replace(/[*_`\[\]]/g, ''), extra);
    }
    throw e;
  }
}

async function safeEdit(ctx: Context, chatId: number, msgId: number, text: string, extra?: any): Promise<any> {
  try {
    return await ctx.api.editMessageText(chatId, msgId, text, { parse_mode: 'Markdown', ...extra });
  } catch (e: any) {
    if (e?.description?.includes('parse') || e?.description?.includes('entity')) {
      return await ctx.api.editMessageText(chatId, msgId, text.replace(/[*_`\[\]]/g, ''), extra);
    }
    // Ignore "message is not modified"
    if (!e?.description?.includes('not modified')) throw e;
  }
}

// ── Emoji reactions ───────────────────────────────────────────────────────
function pickReaction(text: string): string {
  const t = text.toLowerCase();
  if (/спасибо|thank|merci|danke|gracias|شكر/i.test(t)) return '🙏';
  if (/люблю|love|amor|liebe/i.test(t)) return '❤';
  if (/помоги|помогите|help/i.test(t)) return '👌';
  if (/привет|hello|hi |hey |salut/i.test(t)) return '👋';
  if (/крутой|отлично|супер|awesome|cool|wow/i.test(t)) return '🔥';
  if (/смешно|хаха|lol|funny|😂/i.test(t)) return '😂';
  if (/грустно|sad|жаль|печально/i.test(t)) return '🥺';
  if (/да|yes|ок|ok\b/i.test(t)) return '👍';
  if (/нет|no\b|не хочу/i.test(t)) return '👎';
  if (/вопрос|почему|зачем|как |what |why /i.test(t)) return '🤔';
  if (/деньги|бабки|финанс|money|cash/i.test(t)) return '💰';
  if (/код|code|программ|github/i.test(t)) return '🖥';
  const pool = ['👍', '🔥', '❤', '⚡', '🎉', '👏', '✨', '💪'];
  return pool[Math.floor(Math.random() * pool.length)];
}

async function reactToMessage(ctx: Context) {
  try {
    const emoji = pickReaction(ctx.message?.text || '');
    await ctx.api.raw.setMessageReaction({
      chat_id: ctx.chat!.id,
      message_id: ctx.message!.message_id,
      reaction: [{ type: 'emoji', emoji }],
    });
  } catch {
    // Reactions not supported silently ignore
  }
}

// ── Voice reply ───────────────────────────────────────────────────────────
async function sendVoiceReply(ctx: Context, text: string, uid: number, isVoiceInput: boolean) {
  const mode = getUserVoiceMode(uid);
  const shouldSpeak = mode === 'always' || (mode === 'auto' && isVoiceInput);

  if (!shouldSpeak) {
    await safeSend(ctx, text);
    return;
  }

  try {
    await ctx.replyWithChatAction('record_voice');
    const speakText = text.replace(/[\u{1F000}-\u{1FFFF}]|[\u{2600}-\u{26FF}]|[\u{2700}-\u{27BF}]|[\u{FE00}-\u{FE0F}]|[\u{1F900}-\u{1F9FF}]/gu, '').replace(/[*_`]/g, '').trim();
    const tts = await textToSpeech(speakText || text, uid);
    const inputFile = new InputFile(tts.buffer, `nexum_voice.${tts.format}`);
    await ctx.replyWithVoice(inputFile);
  } catch (e: any) {
    console.warn('[tts] Failed, fallback to text:', e.message?.slice(0, 100));
    await safeSend(ctx, text);
  }
}

// ── Download file ─────────────────────────────────────────────────────────
async function downloadFile(fileId: string, bot: Bot): Promise<Buffer> {
  const file = await bot.api.getFile(fileId);
  const url = `https://api.telegram.org/file/bot${config.botToken}/${file.file_path}`;
  const r = await fetch(url);
  if (!r.ok) throw new Error(`Download failed: ${r.status}`);
  return Buffer.from(await r.arrayBuffer());
}

// ── Get image as base64 ───────────────────────────────────────────────────
async function getImageBase64(ctx: Context, bot: Bot): Promise<{ data: string; mime: string } | null> {
  let fileId: string | null = null;
  let mime = 'image/jpeg';

  if (ctx.message?.photo) {
    const photos = ctx.message.photo;
    fileId = photos[photos.length - 1].file_id;
  } else if (ctx.message?.document?.mime_type?.startsWith('image/')) {
    fileId = ctx.message.document.file_id;
    mime = ctx.message.document.mime_type;
  } else if (ctx.message?.sticker) {
    fileId = ctx.message.sticker.file_id;
    mime = 'image/webp';
  }

  if (!fileId) return null;
  const buf = await downloadFile(fileId, bot);
  return { data: buf.toString('base64'), mime };
}

// ── Website generator ────────────────────────────────────────────────────
async function generateWebsite(uid: number, prompt: string): Promise<{ id: number; name: string }> {
  const sitePrompt = `You are an expert web developer. Create a complete, beautiful, production-ready HTML page.

Requirements:
- Single HTML file with embedded CSS and JavaScript
- Modern, professional design with gradients and animations
- Fully responsive (mobile-first)
- Use CSS variables for theming
- Include smooth animations and hover effects
- Real, useful content based on the request
- Dark or light theme as appropriate
- NO external dependencies — everything inline
- Output ONLY the HTML code, nothing else

User request: ${prompt}`;

  const messages = [
    { role: 'system' as any, content: 'You are an expert web developer. Output only HTML code.' },
    { role: 'user' as any, content: sitePrompt }
  ];

  const html = await chat(messages, false);
  // Extract HTML if wrapped in code blocks
  const cleaned = html.replace(/^```html?\n?/i, '').replace(/\n?```$/i, '').trim();

  const name = prompt.substring(0, 50).replace(/[^a-zA-Zа-яА-Я0-9\s]/g, '').trim() || 'Мой сайт';
  const result = db.prepare('INSERT INTO websites (uid, name, html) VALUES (?, ?, ?)').run(uid, name, cleaned);
  return { id: result.lastInsertRowid as number, name };
}

// ── New tool generator ────────────────────────────────────────────────────
async function generateTool(uid: number, description: string): Promise<any> {
  const toolPrompt = `You are creating a JavaScript tool for a Telegram bot (Node.js). 

The tool runs in a sandboxed VM context with access to:
- uid (number) — Telegram user ID
- userText (string) — user message
- db — SQLite database with tables: notes, tasks, habits, finance, reminders, memory, websites, custom_tools
- result — set this string to return a response to the user

Write ONLY the tool code (no function wrapper, no async/await wrapper at top level).
The code must set the 'result' variable with the response text.

Tool description: ${description}

Also provide:
- name: short tool name (English, no spaces)
- trigger: regex pattern to detect when to use this tool
- desc: one line description

Respond in JSON format:
{
  "name": "tool_name",
  "trigger": "regex_pattern",
  "desc": "description",
  "code": "// JavaScript code here\\nresult = 'response';"
}`;

  const messages = [
    { role: 'system' as any, content: 'Output only valid JSON.' },
    { role: 'user' as any, content: toolPrompt }
  ];

  const rawResponse = await chat(messages, false);
  const json = rawResponse.replace(/^```json?\n?/i, '').replace(/\n?```$/i, '').trim();
  return JSON.parse(json);
}

export function setupHandlers(bot: Bot) {

  // /start
  bot.command('start', async (ctx) => {
    const uid = ctx.from!.id;
    ensureUser(uid, ctx.from?.username, ctx.from?.first_name);
    await safeSend(ctx,
      `👋 Привет, *${ctx.from?.first_name || 'друг'}*!\n\n` +
      `Я *NEXUM* — твой AI-агент.\n\n` +
      `🤖 Отвечать на любые вопросы\n` +
      `🎙 Понимать голосовые сообщения\n` +
      `📸 Анализировать фото и изображения\n` +
      `🌐 Создавать готовые сайты\n` +
      `🛠 Разрабатывать новые инструменты для себя\n` +
      `📝 Управлять заметками, задачами, привычками\n` +
      `💰 Считать финансы\n` +
      `⏰ Ставить напоминания\n` +
      `💻 Управлять твоим ПК\n\n` +
      `Просто напиши что нужно!`,
      {
        reply_markup: {
          inline_keyboard: [[
            { text: '📱 Mini Apps', web_app: { url: `${config.webappUrl}/hub` } },
            { text: '❓ Помощь', callback_data: 'cmd_help' }
          ]]
        }
      }
    );
  });

  // /help
  bot.command('help', async (ctx) => {
    await safeSend(ctx,
      `*NEXUM — Команды*\n\n` +
      `*Основное*\n` +
      `• Просто пиши — отвечу\n` +
      `• Отправь голосовое — расшифрую + отвечу голосом\n` +
      `• Отправь фото — опишу\n\n` +
      `*Создание*\n` +
      `/website — создать готовый сайт\n` +
      `/newtool — создать новый инструмент\n` +
      `/tools — список моих инструментов\n\n` +
      `*Инструменты*\n` +
      `/notes /tasks /habits /finance\n` +
      `/remind /search /memory /forget /clear\n\n` +
      `*Голос*\n` +
      `/voice — настройка голосового режима\n` +
      `/voices — выбор голоса и языка\n\n` +
      `*PC Agent*\n` +
      `/pc /link /screenshot /run /bgrun /bglist\n/sysinfo /ps /kill /files /clipboard /notify\n/window /http /browser /openapp /mouse /keyboard /hotkey\n/network /agentid\n\n` +
      `*Прочее*\n` +
      `/apps /status`,
      { parse_mode: 'Markdown' }
    );
  });

  // /apps
  bot.command('apps', async (ctx) => {
    await ctx.reply(
      `📱 *NEXUM Mini Apps*`,
      {
        parse_mode: 'Markdown',
        reply_markup: {
          inline_keyboard: [
            [
              { text: '💰 Финансы', web_app: { url: `${config.webappUrl}/finance` } },
              { text: '📝 Заметки', web_app: { url: `${config.webappUrl}/notes` } },
            ],
            [
              { text: '✅ Задачи', web_app: { url: `${config.webappUrl}/tasks` } },
              { text: '🎯 Привычки', web_app: { url: `${config.webappUrl}/habits` } },
            ],
            [
              { text: '🌐 Сайты', web_app: { url: `${config.webappUrl}/sites` } },
              { text: '🛠 Инструменты', web_app: { url: `${config.webappUrl}/tools` } },
            ],
          ]
        }
      }
    );
  });

  // /website — generate a full website like Claude
  bot.command('website', async (ctx) => {
    const uid = ctx.from!.id;
    ensureUser(uid, ctx.from?.username, ctx.from?.first_name);
    const prompt = ctx.match?.trim();

    if (!prompt) {
      await safeSend(ctx,
        `🌐 *Создание сайта*\n\n` +
        `Я создам готовый красивый сайт как Claude!\n\n` +
        `Просто напиши что нужно:\n` +
        `/website лендинг для фитнес-клуба\n` +
        `/website портфолио дизайнера\n` +
        `/website интернет-магазин кофе\n` +
        `/website калькулятор ИМТ`
      );
      return;
    }

    const msg = await ctx.reply('🌐 Создаю сайт...\n_Это займёт 10-20 секунд_', { parse_mode: 'Markdown' });

    try {
      const site = await generateWebsite(uid, prompt);
      const siteUrl = `${config.webappUrl}/site/${site.id}`;

      await safeEdit(ctx, ctx.chat!.id, msg.message_id,
        `✅ *Сайт готов!*\n\n_${site.name}_`,
        {
          reply_markup: {
            inline_keyboard: [
              [{ text: '🌐 Открыть сайт', web_app: { url: siteUrl } }],
              [{ text: '🔗 Поделиться ссылкой', callback_data: `site_share_${site.id}` }],
              [{ text: '✏️ Изменить', callback_data: `site_edit_${site.id}` }],
            ]
          }
        }
      );
    } catch (e: any) {
      console.error('[website]', e);
      await safeEdit(ctx, ctx.chat!.id, msg.message_id, `❌ Ошибка: ${e.message}`);
    }
  });

  // /newtool — self-developing tools
  bot.command('newtool', async (ctx) => {
    const uid = ctx.from!.id;
    ensureUser(uid, ctx.from?.username, ctx.from?.first_name);
    const description = ctx.match?.trim();

    if (!description) {
      const tools = db.prepare('SELECT * FROM custom_tools WHERE (uid = ? OR uid = 0) AND active = 1').all(uid) as any[];
      const toolList = tools.length > 0
        ? tools.map(t => `• *${t.name}* — ${t.description} (использован ${t.usage_count} раз)`).join('\n')
        : '• Инструментов ещё нет';

      await safeSend(ctx,
        `🛠 *Самообучающиеся инструменты NEXUM*\n\n` +
        `Я могу создать любой новый инструмент для себя прямо сейчас!\n\n` +
        `*Примеры:*\n` +
        `/newtool конвертер валют по текущему курсу\n` +
        `/newtool генератор паролей\n` +
        `/newtool калькулятор процентов по кредиту\n` +
        `/newtool переводчик текста\n\n` +
        `*Мои текущие инструменты:*\n${toolList}`
      );
      return;
    }

    const msg = await ctx.reply('🔨 Разрабатываю новый инструмент...', { parse_mode: 'Markdown' });

    try {
      const toolData = await generateTool(uid, description);

      // Save the tool
      const result = db.prepare(
        'INSERT INTO custom_tools (uid, name, description, trigger_pattern, code, active) VALUES (?, ?, ?, ?, ?, 1)'
      ).run(uid, toolData.name, toolData.desc, toolData.trigger, toolData.code);

      await safeEdit(ctx, ctx.chat!.id, msg.message_id,
        `✅ *Инструмент создан и подключён!*\n\n` +
        `🔧 *${toolData.name}*\n` +
        `📝 ${toolData.desc}\n` +
        `🎯 Триггер: \`${toolData.trigger}\`\n\n` +
        `_Теперь я автоматически использую его когда нужно_`,
        {
          reply_markup: {
            inline_keyboard: [
              [{ text: '🧪 Протестировать', callback_data: `test_tool_${result.lastInsertRowid}` }],
              [{ text: '🗑 Удалить', callback_data: `del_tool_${result.lastInsertRowid}` }],
            ]
          }
        }
      );
    } catch (e: any) {
      console.error('[newtool]', e);
      await safeEdit(ctx, ctx.chat!.id, msg.message_id, `❌ Ошибка создания инструмента: ${e.message}`);
    }
  });

  // /tools — list all tools
  bot.command('tools', async (ctx) => {
    const uid = ctx.from!.id;
    const tools = db.prepare('SELECT * FROM custom_tools WHERE (uid = ? OR uid = 0) AND active = 1 ORDER BY usage_count DESC').all(uid) as any[];

    if (!tools.length) {
      await safeSend(ctx, `🛠 *Инструменты*\n\nПока нет. Создай: /newtool описание нового инструмента`);
      return;
    }

    const list = tools.map((t, i) =>
      `${i + 1}. *${t.name}* — ${t.description}\n   🎯 \`${t.trigger_pattern}\` | использован ${t.usage_count}×`
    ).join('\n\n');

    await safeSend(ctx, `🛠 *Мои инструменты (${tools.length})*\n\n${list}`);
  });

  // /voices — select voice
  bot.command('voices', async (ctx) => {
    const uid = ctx.from!.id;
    const pref = getUserVoicePref(uid);

    const langButtons = Object.entries(VOICES)
      .slice(0, 20)
      .map(([lang, data]) => ({
        text: data.name,
        callback_data: `set_voice_${lang}_0`
      }));

    // 2 per row
    const rows: any[] = [];
    for (let i = 0; i < langButtons.length; i += 2) {
      rows.push(langButtons.slice(i, i + 2));
    }
    rows.push([{ text: '🌍 Авто-определение языка', callback_data: 'set_voice_auto_0' }]);

    await ctx.reply(
      `🎙 *Выбор голоса NEXUM*\n\nТекущий: *${pref.lang === 'auto' ? 'Авто' : (VOICES[pref.lang]?.name || pref.lang)}*\n\nВыбери язык:`,
      { parse_mode: 'Markdown', reply_markup: { inline_keyboard: rows } }
    );
  });

  // Handle voice selection callback
  bot.callbackQuery(/^set_voice_(.+)_(\d+)$/, async (ctx) => {
    const lang = ctx.match![1];
    const voiceIdx = parseInt(ctx.match![2]);
    const uid = ctx.from.id;

    setUserVoicePref(uid, lang, voiceIdx);
    await ctx.answerCallbackQuery();

    const langName = lang === 'auto' ? 'Авто-определение' : (VOICES[lang]?.name || lang);
    const voiceName = lang !== 'auto' ? VOICES[lang]?.voices[voiceIdx] || '' : '';

    // Show voice options if language has multiple voices
    if (lang !== 'auto' && VOICES[lang]?.voices.length > 1) {
      const voiceButtons = VOICES[lang].voices.map((v, i) => ({
        text: (i === voiceIdx ? '✅ ' : '') + v.replace(`${lang}-`, '').replace('Neural', ''),
        callback_data: `set_voice_${lang}_${i}`
      }));
      const rows: any[] = [];
      for (let i = 0; i < voiceButtons.length; i += 2) {
        rows.push(voiceButtons.slice(i, i + 2));
      }
      rows.push([{ text: '◀️ Назад к языкам', callback_data: 'voices_back' }]);

      await ctx.editMessageText(
        `🎙 *Голос: ${langName}*\n\nВыбери конкретный голос:`,
        { parse_mode: 'Markdown', reply_markup: { inline_keyboard: rows } }
      );
    } else {
      await ctx.editMessageText(
        `✅ *Голос установлен*\n\n🌍 Язык: ${langName}\n🎤 Голос: ${voiceName || 'авто'}`,
        { parse_mode: 'Markdown' }
      );
    }
  });

  bot.callbackQuery('voices_back', async (ctx) => {
    await ctx.answerCallbackQuery();
    const uid = ctx.from.id;
    const pref = getUserVoicePref(uid);
    const langButtons = Object.entries(VOICES).slice(0, 20).map(([lang, data]) => ({
      text: data.name, callback_data: `set_voice_${lang}_0`
    }));
    const rows: any[] = [];
    for (let i = 0; i < langButtons.length; i += 2) rows.push(langButtons.slice(i, i + 2));
    rows.push([{ text: '🌍 Авто', callback_data: 'set_voice_auto_0' }]);
    await ctx.editMessageText(
      `🎙 *Выбор голоса*\n\nТекущий: *${pref.lang === 'auto' ? 'Авто' : (VOICES[pref.lang]?.name || pref.lang)}*\n\nВыбери язык:`,
      { parse_mode: 'Markdown', reply_markup: { inline_keyboard: rows } }
    );
  });

  // /memory
  bot.command('memory', async (ctx) => {
    const uid = ctx.from!.id;
    const memories = getMemories(uid);
    if (!memories.length) return safeSend(ctx, '🧠 Память пуста. Расскажи мне о себе!');
    const text = memories.filter(m => !['voice_mode'].includes(m.key)).map(m => `• *${m.key}*: ${m.value}`).join('\n');
    await safeSend(ctx, `🧠 *Что я знаю о тебе:*\n\n${text}`);
  });

  // /forget
  bot.command('forget', async (ctx) => {
    clearMemory(ctx.from!.id);
    await ctx.reply('🗑 Память очищена');
  });

  // /clear
  bot.command('clear', async (ctx) => {
    clearHistory(ctx.from!.id);
    await ctx.reply('🗑 История диалога очищена');
  });

  // /notes
  bot.command('notes', async (ctx) => {
    const uid = ctx.from!.id;
    const notes = db.prepare('SELECT * FROM notes WHERE uid = ? ORDER BY pinned DESC, updated_at DESC LIMIT 10').all(uid) as any[];
    if (!notes.length) return ctx.reply('📝 Заметок нет. Просто напиши "запиши..."', {
      reply_markup: { inline_keyboard: [[{ text: '📝 Открыть заметки', web_app: { url: `${config.webappUrl}/notes` } }]] }
    });
    const text = notes.map((n, i) => `${n.pinned ? '📌 ' : ''}*${i + 1}.* ${n.title || n.content.substring(0, 50)}${n.content.length > 50 ? '...' : ''}`).join('\n');
    await safeSend(ctx, `📝 *Заметки:*\n\n${text}`, {
      reply_markup: { inline_keyboard: [[{ text: '📝 Открыть все', web_app: { url: `${config.webappUrl}/notes` } }]] }
    });
  });

  // /tasks
  bot.command('tasks', async (ctx) => {
    const uid = ctx.from!.id;
    const tasks = db.prepare(`SELECT * FROM tasks WHERE uid = ? AND status != 'done' ORDER BY priority DESC, id DESC LIMIT 10`).all(uid) as any[];
    if (!tasks.length) return ctx.reply('✅ Задач нет. Скажи "создай задачу..."', {
      reply_markup: { inline_keyboard: [[{ text: '✅ Открыть задачи', web_app: { url: `${config.webappUrl}/tasks` } }]] }
    });
    const prioEmoji: Record<string, string> = { critical: '🔴', high: '🟠', medium: '🟡', low: '🟢' };
    const text = tasks.map((t, i) => `${prioEmoji[t.priority] || '⚪'} *${i + 1}.* ${t.title}${t.project !== 'General' ? ` _[${t.project}]_` : ''}`).join('\n');
    await safeSend(ctx, `✅ *Активные задачи:*\n\n${text}`, {
      reply_markup: { inline_keyboard: [[{ text: '✅ Открыть все', web_app: { url: `${config.webappUrl}/tasks` } }]] }
    });
  });

  // /habits
  bot.command('habits', async (ctx) => {
    const uid = ctx.from!.id;
    const habits = db.prepare('SELECT * FROM habits WHERE uid = ? ORDER BY streak DESC').all(uid) as any[];
    if (!habits.length) return ctx.reply('🎯 Привычек нет.', {
      reply_markup: { inline_keyboard: [[{ text: '🎯 Добавить привычку', web_app: { url: `${config.webappUrl}/habits` } }]] }
    });
    const today = new Date().toISOString().split('T')[0];
    const text = habits.map(h => `${h.last_done?.startsWith(today) ? '✅' : '⬜'} ${h.emoji} *${h.name}* — 🔥 ${h.streak}`).join('\n');
    await safeSend(ctx, `🎯 *Привычки:*\n\n${text}`, {
      reply_markup: { inline_keyboard: [[{ text: '🎯 Открыть все', web_app: { url: `${config.webappUrl}/habits` } }]] }
    });
  });

  // /finance
  bot.command('finance', async (ctx) => {
    const uid = ctx.from!.id;
    const month = new Date().toISOString().substring(0, 7);
    const stats = db.prepare(`SELECT type, SUM(amount) as total FROM finance WHERE uid = ? AND (created_at >= ? OR created_at IS NULL) GROUP BY type`).all(uid, `${month}-01`) as any[];
    const income = stats.find(s => s.type === 'income')?.total || 0;
    const expense = stats.find(s => s.type === 'expense')?.total || 0;
    const balance = income - expense;
    await safeSend(ctx,
      `💰 *Финансы за ${month}:*\n\n📈 Доходы: *${income.toLocaleString()}*\n📉 Расходы: *${expense.toLocaleString()}*\n💵 Баланс: *${balance >= 0 ? '+' : ''}${balance.toLocaleString()}*`,
      { reply_markup: { inline_keyboard: [[{ text: '💰 Детали', web_app: { url: `${config.webappUrl}/finance` } }]] } }
    );
  });

  // /search
  bot.command('search', async (ctx) => {
    const query = ctx.match?.trim();
    if (!query) return ctx.reply('Укажи запрос: /search что искать');
    const msg = await ctx.reply('🔍 Ищу...');
    try {
      const result = await webSearch(query);
      await safeEdit(ctx, ctx.chat!.id, msg.message_id, result);
    } catch (e: any) {
      await safeEdit(ctx, ctx.chat!.id, msg.message_id, `❌ ${e.message}`);
    }
  });

  // /remind
  bot.command('remind', async (ctx) => {
    const text = ctx.match?.trim();
    if (!text) return ctx.reply('Пример: /remind через 30 минут позвонить');
    const result = await execute(ctx.from!.id, `напомни ${text}`);
    await safeSend(ctx, result.text);
  });

  // /voice
  bot.command('voice', async (ctx) => {
    const uid = ctx.from!.id;
    const arg = ctx.match?.trim().toLowerCase();
    const mode = getUserVoiceMode(uid);
    if (!arg) {
      await ctx.reply(
        `🎙 *Голосовой режим*\n\nТекущий: *${modeLabel(mode)}*\n\nВыбери режим:`,
        {
          parse_mode: 'Markdown',
          reply_markup: {
            inline_keyboard: [
              [{ text: (mode === 'auto' ? '✅ ' : '') + '🔁 Авто — голос на голос', callback_data: 'voice_auto' }],
              [{ text: (mode === 'always' ? '✅ ' : '') + '🔊 Всегда голосом', callback_data: 'voice_always' }],
              [{ text: (mode === 'never' ? '✅ ' : '') + '💬 Только текст', callback_data: 'voice_never' }],
            ]
          }
        }
      );
      return;
    }
    if (['auto', 'always', 'never'].includes(arg)) {
      setUserVoiceMode(uid, arg);
      await ctx.reply(`✅ Режим: *${modeLabel(arg)}*`, { parse_mode: 'Markdown' });
    }
  });

  bot.callbackQuery('voice_auto', async (ctx) => {
    setUserVoiceMode(ctx.from.id, 'auto');
    await ctx.answerCallbackQuery('✅ Авто режим');
    await ctx.editMessageText(`🎙 *Голосовой режим*\n\n✅ *${modeLabel('auto')}*`, { parse_mode: 'Markdown' });
  });
  bot.callbackQuery('voice_always', async (ctx) => {
    setUserVoiceMode(ctx.from.id, 'always');
    await ctx.answerCallbackQuery('✅ Всегда голосом');
    await ctx.editMessageText(`🎙 *Голосовой режим*\n\n✅ *${modeLabel('always')}*`, { parse_mode: 'Markdown' });
  });
  bot.callbackQuery('voice_never', async (ctx) => {
    setUserVoiceMode(ctx.from.id, 'never');
    await ctx.answerCallbackQuery('✅ Только текст');
    await ctx.editMessageText(`🎙 *Голосовой режим*\n\n✅ *${modeLabel('never')}*`, { parse_mode: 'Markdown' });
  });

  // ── Helper: требует онлайн-агента ────────────────────────────────────────
  async function requireAgent(ctx: Context): Promise<boolean> {
    const uid = ctx.from!.id;
    const online = (app as any).isAgentOnline?.(uid);
    if (!online) {
      await safeSend(ctx,
        `💻 *PC Agent офлайн*\n\n` +
        `Запусти агент на своём компьютере:\n` +
        `\`\`\`\npip install websockets pyautogui pillow psutil requests pyperclip\npython nexum_agent.py\n\`\`\`\n` +
        `Затем введи \`/link КОД\``
      );
      return false;
    }
    return true;
  }

  // ── Helper: отправить команду агенту и ответить ───────────────────────────
  async function agentCmd(ctx: Context, msg: object, statusText?: string): Promise<void> {
    if (!await requireAgent(ctx)) return;
    const uid = ctx.from!.id;
    const statusMsg = statusText ? await ctx.reply(statusText) : null;
    try {
      const result = await (app as any).sendToAgent(uid, msg);
      const text = result?.data || result || '(нет ответа)';
      if (statusMsg) {
        await safeEdit(ctx, ctx.chat!.id, statusMsg.message_id, String(text));
      } else {
        await safeSend(ctx, String(text));
      }
    } catch (e: any) {
      const errText = `❌ ${e.message}`;
      if (statusMsg) {
        await safeEdit(ctx, ctx.chat!.id, statusMsg.message_id, errText);
      } else {
        await ctx.reply(errText);
      }
    }
  }

  // /pc — статус агента
  bot.command('pc', async (ctx) => {
    const uid = ctx.from!.id;
    const agent  = db.prepare('SELECT * FROM pc_agents WHERE uid = ?').get(uid) as any;
    const online = (app as any).isAgentOnline?.(uid);
    if (!agent) {
      return safeSend(ctx,
        `💻 *PC Agent не подключён*\n\n` +
        `Установи и запусти агент:\n` +
        `\`\`\`\npip install websockets pyautogui pillow psutil requests pyperclip\npython nexum_agent.py\n\`\`\`\n` +
        `Затем введи \`/link КОД\``
      );
    }
    const lastSeen  = agent.last_seen ? new Date(agent.last_seen).toLocaleString('ru-RU') : 'неизвестно';
    const statusIcon = online ? '🟢 Онлайн' : '🔴 Офлайн';
    await safeSend(ctx,
      `💻 *PC Agent*\n\n` +
      `${statusIcon}\n` +
      `📱 ${agent.device_name || agent.platform || 'неизвестно'}\n` +
      `🕐 Последний раз: ${lastSeen}\n\n` +
      `Команды: /screenshot /run /sysinfo /ps /files /clipboard /notify /window /http /mouse /keyboard /browser /bgrun /bglist`
    );
  });

  // /link — привязка агента к пользователю
  bot.command('link', async (ctx) => {
    const code = ctx.match?.trim().toUpperCase();
    if (!code) return ctx.reply('Укажи код: /link ABCDEF');
    const uid = ctx.from!.id;
    // Пробуем через linkAgent сервера (WebSocket уже живёт)
    const linked = (app as any).linkAgent?.(code, uid);
    if (linked) {
      // Обновляем БД
      const linkReq = db.prepare('SELECT * FROM link_codes WHERE code = ?').get(code) as any;
      db.prepare(
        `INSERT INTO pc_agents (uid, device_id, device_name, platform, last_seen, status)
         VALUES (?, ?, ?, ?, ?, 'online')
         ON CONFLICT(uid) DO UPDATE SET
           device_id=excluded.device_id, device_name=excluded.device_name,
           platform=excluded.platform, last_seen=excluded.last_seen, status='online'`
      ).run(uid, linkReq?.device_id || 'PC', linkReq?.device_id || 'PC',
            linkReq?.platform || 'Unknown', new Date().toISOString());
      db.prepare('DELETE FROM link_codes WHERE code = ?').run(code);
      await ctx.reply(`✅ PC Agent подключён!\n💻 ${linkReq?.platform || 'Unknown'}\n\n` +
        `Твой UID *${uid}* вшит в агент персонально — при следующем запуске привязка будет автоматической.`,
        { parse_mode: 'Markdown' });
    } else {
      const linkReq = db.prepare('SELECT * FROM link_codes WHERE code = ?').get(code) as any;
      if (!linkReq) return ctx.reply('❌ Код не найден или устарел');
      try {
        db.prepare(
          `INSERT INTO pc_agents (uid, device_name, platform, last_seen, status) VALUES (?, ?, ?, ?, 'online')
           ON CONFLICT(uid) DO UPDATE SET device_name=excluded.device_name,
             platform=excluded.platform, last_seen=excluded.last_seen, status='online'`
        ).run(uid, linkReq.device_id || 'PC', linkReq.platform || 'Unknown', new Date().toISOString());
        db.prepare('DELETE FROM link_codes WHERE code = ?').run(code);
        await ctx.reply(`✅ PC Agent привязан!\n💻 ${linkReq.platform || 'Unknown'}`);
      } catch (e: any) {
        await ctx.reply(`❌ Ошибка: ${e.message}`);
      }
    }
  });

  // /screenshot [x1,y1,x2,y2]
  bot.command('screenshot', async (ctx) => {
    if (!await requireAgent(ctx)) return;
    const uid = ctx.from!.id;
    const regionStr = ctx.match?.trim();
    let region: number[] | undefined;
    if (regionStr) {
      region = regionStr.split(',').map(Number);
    }
    const statusMsg = await ctx.reply('📸 Снимаю экран…');
    try {
      const result = await (app as any).sendToAgent(uid, {
        type: 'screenshot', chatId: ctx.chat!.id, region,
      });
      if (result?.data) {
        const buf = Buffer.from(result.data, 'base64');
        await ctx.replyWithPhoto(new InputFile(buf, 'screenshot.png'));
        await ctx.api.deleteMessage(ctx.chat!.id, statusMsg.message_id);
      } else {
        await safeEdit(ctx, ctx.chat!.id, statusMsg.message_id, '❌ Не удалось сделать скриншот');
      }
    } catch (e: any) {
      await safeEdit(ctx, ctx.chat!.id, statusMsg.message_id, `❌ ${e.message}`);
    }
  });

  // /run <команда> — выполнить команду в терминале
  bot.command('run', async (ctx) => {
    const cmd = ctx.match?.trim();
    if (!cmd) return ctx.reply('Укажи команду: /run ls -la');
    await agentCmd(ctx, { type: 'run', command: cmd }, `⚙️ Выполняю: \`${cmd.slice(0,60)}\`…`);
  });

  // /bgrun <команда> — фоновый процесс
  bot.command('bgrun', async (ctx) => {
    const cmd = ctx.match?.trim();
    if (!cmd) return ctx.reply('Укажи команду: /bgrun python server.py');
    await agentCmd(ctx, { type: 'run_background', command: cmd }, `🔄 Запускаю фоново…`);
  });

  // /bglist — список фоновых процессов
  bot.command('bglist', async (ctx) => {
    await agentCmd(ctx, { type: 'bg_list' }, '🔄 Фоновые процессы…');
  });

  // /bgstop <id> — остановить фоновый процесс
  bot.command('bgstop', async (ctx) => {
    const id = ctx.match?.trim();
    if (!id) return ctx.reply('Укажи ID: /bgstop abc123');
    await agentCmd(ctx, { type: 'bg_stop', proc_id: id });
  });

  // /sysinfo — системная информация
  bot.command('sysinfo', async (ctx) => {
    await agentCmd(ctx, { type: 'sysinfo' }, '📊 Собираю информацию о системе…');
  });

  // /ps [limit] — список процессов
  bot.command('ps', async (ctx) => {
    const limit = parseInt(ctx.match?.trim() || '15');
    await agentCmd(ctx, { type: 'processes', limit: isNaN(limit) ? 15 : limit }, '🔍 Получаю процессы…');
  });

  // /kill <pid_или_имя> — убить процесс
  bot.command('kill', async (ctx) => {
    const target = ctx.match?.trim();
    if (!target) return ctx.reply('Укажи PID или имя: /kill chrome');
    await agentCmd(ctx, { type: 'kill_process', input: target });
  });

  // /files <op> <path> [content]
  // Пример: /files list ~/Documents
  //         /files read ~/.bashrc
  //         /files write ~/test.txt hello world
  //         /files delete ~/old.txt
  //         /files search ~/Projects *.ts
  bot.command('files', async (ctx) => {
    const args = (ctx.match?.trim() || '').split(' ');
    const op   = args[0] || 'list';
    const path = args[1] || '~';
    const content = args.slice(2).join(' ');
    await agentCmd(ctx, { type: 'filesystem', op, path, content }, `📁 ${op}: ${path}…`);
  });

  // /clipboard [read|write <text>]
  bot.command('clipboard', async (ctx) => {
    const args = (ctx.match?.trim() || 'read').split(' ');
    const op   = args[0] === 'write' ? 'write' : 'read';
    const text = args.slice(1).join(' ');
    await agentCmd(ctx, { type: 'clipboard', op, text });
  });

  // /notify <title> | <message>
  bot.command('notify', async (ctx) => {
    const input = ctx.match?.trim() || '';
    const [title, ...rest] = input.split('|');
    await agentCmd(ctx,
      { type: 'notify', title: title.trim() || 'NEXUM', message: rest.join('|').trim() || title.trim() }
    );
  });

  // /window [list|focus <name>|close <name>]
  bot.command('window', async (ctx) => {
    const args = (ctx.match?.trim() || 'list').split(' ');
    const op  = args[0];
    const win = args.slice(1).join(' ');
    await agentCmd(ctx, { type: 'window', op, window_id: win }, op === 'list' ? '🪟 Получаю окна…' : undefined);
  });

  // /http <METHOD> <url> [body]
  // Пример: /http GET https://api.github.com
  //         /http POST https://api.example.com/data {"key":"val"}
  bot.command('http', async (ctx) => {
    const args  = (ctx.match?.trim() || '').split(' ');
    const method = args[0]?.toUpperCase() || 'GET';
    const url   = args[1] || '';
    const body  = args.slice(2).join(' ');
    if (!url) return ctx.reply('Укажи URL: /http GET https://api.github.com');
    await agentCmd(ctx, { type: 'http', method, url, body }, `🌐 ${method} ${url.slice(0,50)}…`);
  });

  // /browser <url> — открыть браузер
  bot.command('browser', async (ctx) => {
    const url = ctx.match?.trim();
    if (!url) return ctx.reply('Укажи URL: /browser https://google.com');
    await agentCmd(ctx, { type: 'browser', input: url });
  });

  // /openapp <name> — открыть приложение
  bot.command('openapp', async (ctx) => {
    const name = ctx.match?.trim();
    if (!name) return ctx.reply('Укажи приложение: /openapp Spotify');
    await agentCmd(ctx, { type: 'open_app', input: name });
  });

  // /mouse <action> [x] [y] [text]
  // Пример: /mouse click 500 300
  //         /mouse type hello world
  //         /mouse hotkey ctrl+c
  bot.command('mouse', async (ctx) => {
    const args   = (ctx.match?.trim() || 'position').split(' ');
    const action = args[0];
    const x      = parseInt(args[1] || '0');
    const y      = parseInt(args[2] || '0');
    const text   = args.slice(3).join(' ');
    await agentCmd(ctx, { type: 'mouse', action, x, y, text });
  });

  // /keyboard <text> — набрать текст
  bot.command('keyboard', async (ctx) => {
    const text = ctx.match?.trim();
    if (!text) return ctx.reply('Укажи текст: /keyboard Hello World');
    await agentCmd(ctx, { type: 'keyboard', action: 'type', text });
  });

  // /hotkey <combo> — нажать комбинацию клавиш
  bot.command('hotkey', async (ctx) => {
    const keys = ctx.match?.trim();
    if (!keys) return ctx.reply('Укажи комбинацию: /hotkey ctrl+c');
    await agentCmd(ctx, { type: 'keyboard', action: 'hotkey', text: keys });
  });

  // /network — информация о сети
  bot.command('network', async (ctx) => {
    await agentCmd(ctx, { type: 'network' }, '🌐 Получаю сетевую информацию…');
  });

  // /agentid — показать идентификацию пользователя агента
  bot.command('agentid', async (ctx) => {
    await agentCmd(ctx, { type: 'identity' }, '🆔 Определяю пользователя…');
  });

  // ════════════════════════════════════════════════════════════
  // BROWSER — Chrome CDP automation (OpenClaw-style)
  // ════════════════════════════════════════════════════════════

  // /browse <url> — открыть страницу и получить снапшот
  bot.command('browse', async (ctx) => {
    const url = ctx.match?.trim();
    if (!url) return ctx.reply('Укажи URL: /browse https://google.com');
    const uid = ctx.from!.id;
    const msg = await ctx.reply('🌐 Открываю страницу…');
    try {
      const { navigate, snapshot, screenshotBase64 } = await import('../browser/index');
      await navigate(url);
      const { text: snap } = await snapshot();
      const imgB64 = await screenshotBase64();
      const imgBuf = Buffer.from(imgB64, 'base64');
      await ctx.replyWithPhoto({ source: imgBuf });
      await ctx.api.editMessageText(ctx.chat!.id, msg.message_id,
        `🌐 *${url}*\n\n\`\`\`\n${snap.slice(0, 2000)}\n\`\`\``,
        { parse_mode: 'Markdown' }
      );
    } catch (e: any) {
      await ctx.api.editMessageText(ctx.chat!.id, msg.message_id, `❌ ${e.message}`);
    }
  });

  // /bclick <ref> — кликнуть по элементу (e1, e2, или CSS selector)
  bot.command('bclick', async (ctx) => {
    const ref = ctx.match?.trim();
    if (!ref) return ctx.reply('Укажи ref: /bclick e3  или  /bclick button[type=submit]');
    const msg = await ctx.reply(`🖱 Кликаю [${ref}]…`);
    try {
      const { click } = await import('../browser/index');
      const result = await click(ref);
      await ctx.api.editMessageText(ctx.chat!.id, msg.message_id, result);
    } catch (e: any) {
      await ctx.api.editMessageText(ctx.chat!.id, msg.message_id, `❌ ${e.message}`);
    }
  });

  // /bfill <ref> <text> — заполнить поле
  bot.command('bfill', async (ctx) => {
    const args = ctx.match?.trim() || '';
    const [ref, ...rest] = args.split(' ');
    const text = rest.join(' ');
    if (!ref || !text) return ctx.reply('Пример: /bfill e2 Hello World');
    const msg = await ctx.reply(`⌨️ Заполняю [${ref}]…`);
    try {
      const { fill } = await import('../browser/index');
      const result = await fill(ref, text);
      await ctx.api.editMessageText(ctx.chat!.id, msg.message_id, result);
    } catch (e: any) {
      await ctx.api.editMessageText(ctx.chat!.id, msg.message_id, `❌ ${e.message}`);
    }
  });

  // /bsnap — текущий снапшот страницы
  bot.command('bsnap', async (ctx) => {
    const msg = await ctx.reply('📸 Снапшот…');
    try {
      const { snapshot, screenshotBase64 } = await import('../browser/index');
      const { text } = await snapshot();
      const b64 = await screenshotBase64();
      await ctx.replyWithPhoto({ source: Buffer.from(b64, 'base64') });
      await ctx.api.editMessageText(ctx.chat!.id, msg.message_id,
        `\`\`\`\n${text.slice(0, 3000)}\n\`\`\``, { parse_mode: 'Markdown' }
      );
    } catch (e: any) {
      await ctx.api.editMessageText(ctx.chat!.id, msg.message_id, `❌ ${e.message}`);
    }
  });

  // /beval <js> — выполнить JS на странице
  bot.command('beval', async (ctx) => {
    const js = ctx.match?.trim();
    if (!js) return ctx.reply('Укажи JS: /beval document.title');
    const msg = await ctx.reply('⚡ Выполняю JS…');
    try {
      const { evaluate } = await import('../browser/index');
      const result = await evaluate(js);
      await ctx.api.editMessageText(ctx.chat!.id, msg.message_id,
        `⚡ \`${js}\`\n\n\`\`\`\n${result.slice(0, 2000)}\n\`\`\``, { parse_mode: 'Markdown' }
      );
    } catch (e: any) {
      await ctx.api.editMessageText(ctx.chat!.id, msg.message_id, `❌ ${e.message}`);
    }
  });

  // /bscroll <up|down> [px] — прокрутить страницу
  bot.command('bscroll', async (ctx) => {
    const [dir = 'down', amtStr = '300'] = (ctx.match?.trim() || '').split(' ');
    const msg = await ctx.reply(`📜 Скролю ${dir}…`);
    try {
      const { scroll } = await import('../browser/index');
      const result = await scroll(dir as any, parseInt(amtStr));
      await ctx.api.editMessageText(ctx.chat!.id, msg.message_id, result);
    } catch (e: any) {
      await ctx.api.editMessageText(ctx.chat!.id, msg.message_id, `❌ ${e.message}`);
    }
  });

  // /btext — извлечь текст страницы
  bot.command('btext', async (ctx) => {
    const msg = await ctx.reply('📄 Извлекаю текст…');
    try {
      const { extractText, getUrl } = await import('../browser/index');
      const url = await getUrl();
      const text = await extractText();
      await ctx.api.editMessageText(ctx.chat!.id, msg.message_id,
        `📄 *${url}*\n\n${text.slice(0, 3000)}`, { parse_mode: 'Markdown' }
      );
    } catch (e: any) {
      await ctx.api.editMessageText(ctx.chat!.id, msg.message_id, `❌ ${e.message}`);
    }
  });

  // /gsearch <query> — поиск через браузер Google
  bot.command('gsearch', async (ctx) => {
    const query = ctx.match?.trim();
    if (!query) return ctx.reply('Укажи запрос: /gsearch nodejs tutorial');
    const msg = await ctx.reply('🔍 Ищу в Google…');
    try {
      const { googleSearch } = await import('../browser/index');
      const results = await googleSearch(query);
      await ctx.api.editMessageText(ctx.chat!.id, msg.message_id,
        `🔍 *${query}*\n\n${results.slice(0, 3000)}`, { parse_mode: 'Markdown' }
      );
    } catch (e: any) {
      await ctx.api.editMessageText(ctx.chat!.id, msg.message_id, `❌ ${e.message}`);
    }
  });

  // /btabs — список открытых вкладок
  bot.command('btabs', async (ctx) => {
    try {
      const { getTabs } = await import('../browser/index');
      const tabs = await getTabs();
      if (!tabs.length) return ctx.reply('Нет открытых вкладок. Открой: /browse <url>');
      const lines = tabs.map((t, i) => `${t.active ? '▶' : ' '} [${i}] ${t.title} — ${t.url}`);
      await ctx.reply('🗂 *Вкладки:*\n\n' + lines.join('\n'), { parse_mode: 'Markdown' });
    } catch (e: any) {
      await ctx.reply(`❌ ${e.message}`);
    }
  });

  // ════════════════════════════════════════════════════════════
  // VECTOR MEMORY — семантический поиск (OpenClaw-style)
  // ════════════════════════════════════════════════════════════

  // /vmem <query> — найти похожие разговоры
  bot.command('vmem', async (ctx) => {
    const query = ctx.match?.trim();
    if (!query) return ctx.reply('Укажи запрос: /vmem проект дедлайн');
    const uid = ctx.from!.id;
    const msg = await ctx.reply('🧠 Ищу в памяти…');
    try {
      const { searchVectorMemory } = await import('../memory/vector');
      const results = await searchVectorMemory(uid, query, { k: 5 });
      if (!results.length) {
        await ctx.api.editMessageText(ctx.chat!.id, msg.message_id, '🧠 Ничего похожего не найдено');
        return;
      }
      const lines = results.map((r, i) => {
        const date = new Date(r.createdAt).toLocaleDateString('ru-RU');
        const score = r.score ? ` (${(r.score * 100).toFixed(0)}%)` : '';
        return `${i+1}. [${r.role}, ${date}${score}]\n${r.content.slice(0, 200)}`;
      });
      await ctx.api.editMessageText(ctx.chat!.id, msg.message_id,
        `🧠 *Похожие разговоры для «${query}»:*\n\n${lines.join('\n\n')}`, { parse_mode: 'Markdown' }
      );
    } catch (e: any) {
      await ctx.api.editMessageText(ctx.chat!.id, msg.message_id, `❌ ${e.message}`);
    }
  });

  // /vmemstats — статистика векторной памяти
  bot.command('vmemstats', async (ctx) => {
    const uid = ctx.from!.id;
    try {
      const { getVectorMemoryStats } = await import('../memory/vector');
      const stats = getVectorMemoryStats(uid);
      await ctx.reply(
        `🧠 *Векторная память*\n\n` +
        `📝 Всего записей: ${stats.total}\n` +
        `🔮 С embeddings: ${stats.withEmbeddings}\n` +
        `📊 Покрытие: ${stats.total ? Math.round(stats.withEmbeddings/stats.total*100) : 0}%\n\n` +
        `_Поиск: /vmem <запрос>_`,
        { parse_mode: 'Markdown' }
      );
    } catch (e: any) {
      await ctx.reply(`❌ ${e.message}`);
    }
  });

  // /vmemclear — очистить векторную память
  bot.command('vmemclear', async (ctx) => {
    const uid = ctx.from!.id;
    try {
      const { clearVectorMemory } = await import('../memory/vector');
      clearVectorMemory(uid);
      await ctx.reply('✅ Векторная память очищена');
    } catch (e: any) {
      await ctx.reply(`❌ ${e.message}`);
    }
  });

  // ════════════════════════════════════════════════════════════
  // SUBAGENTS — параллельные AI-задачи (OpenClaw-style)
  // ════════════════════════════════════════════════════════════

  // /agent <task> — запустить субагента
  bot.command('agent', async (ctx) => {
    const task = ctx.match?.trim();
    if (!task) return ctx.reply(
      '🤖 *Субагент — запуск задачи*\n\n' +
      'Примеры:\n' +
      '/agent найди последние новости про AI и напиши краткий дайджест\n' +
      '/agent проверь статус сайта https://google.com\n' +
      '/agent напиши Python скрипт сортировки пузырьком и протестируй',
      { parse_mode: 'Markdown' }
    );
    const uid = ctx.from!.id;
    const msg = await ctx.reply('🤖 Запускаю субагента…');
    try {
      const { spawn, formatRunStatus } = await import('../agents/subagents');
      const run = spawn(task, {
        apiKey: process.env.ANTHROPIC_API_KEY,
        tools: ['exec', 'read_file', 'write_file', 'list_dir', 'http_fetch', 'search_web'],
      });
      await ctx.api.editMessageText(ctx.chat!.id, msg.message_id,
        `🤖 Субагент запущен\nID: \`${run.id}\`\n\n_Задача: ${task.slice(0, 100)}_\n\nПроверь: /agentlist или /agentwait ${run.id}`,
        { parse_mode: 'Markdown' }
      );
    } catch (e: any) {
      await ctx.api.editMessageText(ctx.chat!.id, msg.message_id, `❌ ${e.message}`);
    }
  });

  // /agentmany <task1> | <task2> | <task3> — параллельные задачи
  bot.command('agentmany', async (ctx) => {
    const input = ctx.match?.trim();
    if (!input) return ctx.reply('Пример: /agentmany задача 1 | задача 2 | задача 3');
    const tasks = input.split('|').map(t => t.trim()).filter(Boolean);
    if (tasks.length < 2) return ctx.reply('Нужно минимум 2 задачи разделённые |');
    const msg = await ctx.reply(`🚀 Запускаю ${tasks.length} субагентов параллельно…`);
    try {
      const { spawnMany, formatRunStatus } = await import('../agents/subagents');
      const runs = await spawnMany(tasks, {
        apiKey: process.env.ANTHROPIC_API_KEY,
        tools: ['exec', 'http_fetch', 'search_web'],
        timeout: 60000,
      }, (id, status, result) => {
        // Progress updates
        ctx.api.editMessageText(ctx.chat!.id, msg.message_id,
          `🚀 Прогресс: ${id} → ${status}`
        ).catch(() => {});
      });
      const summary = runs.map((r, i) =>
        `${i+1}. [${r.id}] ${r.status === 'done' ? '✅' : '❌'} ${r.task.slice(0, 50)}\n${(r.result || r.error || '').slice(0, 200)}`
      ).join('\n\n');
      await ctx.api.editMessageText(ctx.chat!.id, msg.message_id,
        `✅ *Результаты ${runs.length} субагентов:*\n\n${summary.slice(0, 3000)}`,
        { parse_mode: 'Markdown' }
      );
    } catch (e: any) {
      await ctx.api.editMessageText(ctx.chat!.id, msg.message_id, `❌ ${e.message}`);
    }
  });

  // /agentwait <id> — дождаться результата субагента
  bot.command('agentwait', async (ctx) => {
    const id = ctx.match?.trim();
    if (!id) return ctx.reply('Укажи ID: /agentwait abc123');
    const msg = await ctx.reply(`⏳ Жду субагента ${id}…`);
    try {
      const { waitForRun, formatRunStatus } = await import('../agents/subagents');
      const run = await waitForRun(id, 120000);
      await ctx.api.editMessageText(ctx.chat!.id, msg.message_id,
        formatRunStatus(run), { parse_mode: 'Markdown' }
      );
    } catch (e: any) {
      await ctx.api.editMessageText(ctx.chat!.id, msg.message_id, `❌ ${e.message}`);
    }
  });

  // /agentlist — список всех субагентов
  bot.command('agentlist', async (ctx) => {
    try {
      const { getAllRuns, formatRunStatus } = await import('../agents/subagents');
      const runs = getAllRuns();
      if (!runs.length) return ctx.reply('Нет активных субагентов. Запусти: /agent <задача>');
      const text = runs.slice(0, 10).map(formatRunStatus).join('\n─────────\n');
      await ctx.reply(`🤖 *Субагенты:*\n\n${text.slice(0, 4000)}`, { parse_mode: 'Markdown' });
    } catch (e: any) {
      await ctx.reply(`❌ ${e.message}`);
    }
  });

  // /agentcancel <id> — отменить субагента
  bot.command('agentcancel', async (ctx) => {
    const id = ctx.match?.trim();
    if (!id) return ctx.reply('Укажи ID: /agentcancel abc123');
    try {
      const { cancel } = await import('../agents/subagents');
      const ok = cancel(id);
      await ctx.reply(ok ? `✅ Субагент ${id} отменён` : `❌ Субагент ${id} не найден`);
    } catch (e: any) {
      await ctx.reply(`❌ ${e.message}`);
    }
  });

  // /status — общая статистика бота
  bot.command('status', async (ctx) => {
    const uid        = ctx.from!.id;
    const totalUsers = (db.prepare('SELECT COUNT(*) as c FROM users').get() as any).c;
    const totalNotes = (db.prepare('SELECT COUNT(*) as c FROM notes').get() as any).c;
    const totalTasks = (db.prepare('SELECT COUNT(*) as c FROM tasks').get() as any).c;
    const totalTools = (db.prepare('SELECT COUNT(*) as c FROM custom_tools WHERE active=1').get() as any).c;
    const totalSites = (db.prepare('SELECT COUNT(*) as c FROM websites').get() as any).c;
    const agentOnline = (app as any).isAgentOnline?.(uid);
    await safeSend(ctx,
      `📊 *NEXUM*\n\n` +
      `👥 Пользователей: ${totalUsers}\n` +
      `📝 Заметок: ${totalNotes}\n` +
      `✅ Задач: ${totalTasks}\n` +
      `🛠 Инструментов: ${totalTools}\n` +
      `🌐 Сайтов: ${totalSites}\n` +
      `🤖 AI: активен\n` +
      `💻 PC Agent: ${agentOnline ? '🟢 онлайн' : '🔴 офлайн'}`
    );
  });

  // Callback queries
  bot.callbackQuery('cmd_help', async (ctx) => {
    await ctx.answerCallbackQuery();
    await safeSend(ctx, `*Команды NEXUM*\n\n/notes /tasks /habits /finance\n/website /newtool /tools\n/voice /voices /remind /search\n/memory /forget /clear /apps /status`);
  });

  bot.callbackQuery(/^site_share_(\d+)$/, async (ctx) => {
    const siteId = ctx.match![1];
    await ctx.answerCallbackQuery();
    const siteUrl = `${config.webappUrl}/site/${siteId}`;
    await safeSend(ctx, `🔗 Ссылка на сайт:\n${siteUrl}`);
  });

  bot.callbackQuery(/^site_edit_(\d+)$/, async (ctx) => {
    await ctx.answerCallbackQuery();
    await ctx.reply('Напиши что изменить: /website [описание изменений]');
  });

  bot.callbackQuery(/^del_tool_(\d+)$/, async (ctx) => {
    const toolId = ctx.match![1];
    db.prepare('UPDATE custom_tools SET active = 0 WHERE id = ?').run(parseInt(toolId));
    await ctx.answerCallbackQuery('🗑 Инструмент удалён');
    await ctx.editMessageText('🗑 Инструмент удалён');
  });

  bot.callbackQuery(/^test_tool_(\d+)$/, async (ctx) => {
    const toolId = ctx.match![1];
    const tool = db.prepare('SELECT * FROM custom_tools WHERE id = ?').get(parseInt(toolId)) as any;
    await ctx.answerCallbackQuery();
    if (tool) {
      await safeSend(ctx, `🧪 Тест инструмента *${tool.name}*\n\nТриггер-паттерн: \`${tool.trigger_pattern}\`\n\nНапиши мне сообщение содержащее этот паттерн.`);
    }
  });

  // Handle photos
  bot.on('message:photo', async (ctx) => {
    const uid = ctx.from!.id;
    ensureUser(uid, ctx.from?.username, ctx.from?.first_name);
    const caption = ctx.message.caption || '';
    const statusMsg = await ctx.reply('👁 Анализирую изображение...');

    try {
      const imgData = await getImageBase64(ctx, bot);
      if (!imgData) throw new Error('Не удалось загрузить изображение');
      const result = await execute(uid, caption || 'Что на этом изображении? Опиши подробно.', imgData.data, imgData.mime);
      await safeEdit(ctx, ctx.chat!.id, statusMsg.message_id, `📸 *Анализ:*\n\n${result.text}`);
    } catch (e: any) {
      console.error('[photo handler]', e);
      await safeEdit(ctx, ctx.chat!.id, statusMsg.message_id, `❌ Ошибка: ${e.message}`);
    }
  });

  // Handle documents
  bot.on('message:document', async (ctx) => {
    const uid = ctx.from!.id;
    ensureUser(uid, ctx.from?.username, ctx.from?.first_name);
    const mime = ctx.message.document?.mime_type || '';
    if (mime.startsWith('image/')) {
      const statusMsg = await ctx.reply('👁 Анализирую изображение...');
      try {
        const imgData = await getImageBase64(ctx, bot);
        if (!imgData) throw new Error('Не удалось загрузить');
        const caption = ctx.message.caption || 'Что на этом изображении?';
        const result = await execute(uid, caption, imgData.data, imgData.mime);
        await safeEdit(ctx, ctx.chat!.id, statusMsg.message_id, `📸 *Анализ:*\n\n${result.text}`);
      } catch (e: any) {
        await safeEdit(ctx, ctx.chat!.id, statusMsg.message_id, `❌ ${e.message}`);
      }
      return;
    }
    await safeSend(ctx, `📎 Получил файл: *${ctx.message.document.file_name || 'файл'}*\n_Скоро добавлю поддержку документов_`);
  });

  // Handle stickers
  bot.on('message:sticker', async (ctx) => {
    const pool = ['😄', '👍', '🔥', '💯', '✨', '🤩', '😎'];
    await ctx.reply(pool[Math.floor(Math.random() * pool.length)]);
  });

  // Handle voice messages
  bot.on('message:voice', async (ctx) => {
    const uid = ctx.from!.id;
    ensureUser(uid, ctx.from?.username, ctx.from?.first_name);

    const statusMsg = await ctx.reply('🎙 Слушаю...');

    try {
      const buf = await downloadFile(ctx.message.voice.file_id, bot);
      const transcript = await transcribeVoice(buf, 'voice.ogg');

      await safeEdit(ctx, ctx.chat!.id, statusMsg.message_id,
        `🎙 _${transcript}_\n\n⏳ Думаю...`);

      const result = await execute(uid, transcript);
      const mode = getUserVoiceMode(uid);

      if (mode !== 'never') {
        await ctx.api.deleteMessage(ctx.chat!.id, statusMsg.message_id).catch(() => {});
        try {
          await ctx.replyWithChatAction('record_voice');
          const tts = await textToSpeech(result.text, uid);
          await ctx.replyWithVoice(new InputFile(tts.buffer, `nexum.${tts.format}`), {
            caption: `_${transcript.substring(0, 100)}${transcript.length > 100 ? '...' : ''}_`,
            parse_mode: 'Markdown',
          });
        } catch (ttsErr: any) {
          console.warn('[tts] fallback:', ttsErr.message);
          await safeEdit(ctx, ctx.chat!.id, statusMsg.message_id, `🎙 _${transcript}_\n\n${result.text}`);
        }
      } else {
        await safeEdit(ctx, ctx.chat!.id, statusMsg.message_id, `🎙 _${transcript}_\n\n${result.text}`);
      }
    } catch (e: any) {
      console.error('[voice]', e);
      await safeEdit(ctx, ctx.chat!.id, statusMsg.message_id, `❌ ${e.message}`).catch(() => ctx.reply(`❌ ${e.message}`));
    }
  });

  // Handle audio
  bot.on('message:audio', async (ctx) => {
    const uid = ctx.from!.id;
    ensureUser(uid, ctx.from?.username, ctx.from?.first_name);
    const statusMsg = await ctx.reply('🎵 Обрабатываю аудио...');
    try {
      const buf = await downloadFile(ctx.message.audio.file_id, bot);
      const transcript = await transcribeVoice(buf, 'audio.mp3');
      await safeEdit(ctx, ctx.chat!.id, statusMsg.message_id, `🎵 _${transcript}_\n\n⏳ Думаю...`);
      const result = await execute(uid, transcript);
      await safeEdit(ctx, ctx.chat!.id, statusMsg.message_id, `🎵 _${transcript}_\n\n${result.text}`);
    } catch (e: any) {
      await safeEdit(ctx, ctx.chat!.id, statusMsg.message_id, `❌ ${e.message}`);
    }
  });

  // Main text handler
  bot.on('message:text', async (ctx) => {
    const uid = ctx.from!.id;
    ensureUser(uid, ctx.from?.username, ctx.from?.first_name);

    const text = ctx.message.text;
    if (text.startsWith('/')) return;

    // React to message
    const mode = getUserVoiceMode(uid);
    await ctx.replyWithChatAction(mode === 'always' ? 'record_voice' : 'typing');

    try {
      // ── NLP Auto-action: check if message should auto-update Mini Apps ──
      const nlpResult = await processNlpAction(uid, text);
      if (nlpResult.handled && nlpResult.summary) {
        // Still pass to AI for conversational response but prepend context
        const result = await execute(uid, text + `\n[Система: автоматически выполнено действие: ${nlpResult.summary}]`);
        await sendVoiceReply(ctx, nlpResult.summary + '\n\n' + result.text, uid, false);
      } else {
        const result = await execute(uid, text);
        await sendVoiceReply(ctx, result.text, uid, false);
      }
    } catch (e: any) {
      console.error('[text handler]', e);
      await ctx.reply(`❌ ${e.message}`);
    }
  });
}

function modeLabel(mode: string): string {
  return { auto: 'Авто (голос → голос)', always: 'Всегда голосом', never: 'Только текст' }[mode] || mode;
}
