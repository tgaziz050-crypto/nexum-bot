import { Bot, Context, InputFile } from 'grammy';
import { config } from '../core/config.ts';
import { db, ensureUser } from '../core/db.ts';
import { execute } from '../agent/executor.ts';
import { transcribeVoice } from '../tools/stt.ts';
import { textToSpeech } from '../tools/tts.ts';
import { webSearch } from '../tools/search.ts';
import { getMemories, clearMemory, clearHistory } from '../agent/memory.ts';

// Per-user voice mode cache: uid → 'auto' | 'always' | 'never'
const userVoiceMode = new Map<number, string>();

function getUserVoiceMode(uid: number): string {
  const row = db.prepare("SELECT value FROM memory WHERE uid = ? AND key = 'voice_mode'").get(uid) as any;
  return row?.value || 'auto';
}

function setUserVoiceMode(uid: number, mode: string) {
  db.prepare("INSERT INTO memory (uid, key, value) VALUES (?, 'voice_mode', ?) ON CONFLICT(uid, key) DO UPDATE SET value=excluded.value").run(uid, mode);
  userVoiceMode.set(uid, mode);
}

async function sendVoiceReply(ctx: Context, text: string, uid: number, isVoiceInput: boolean) {
  const mode = getUserVoiceMode(uid);
  const shouldSpeak = mode === 'always' || (mode === 'auto' && isVoiceInput);

  if (!shouldSpeak) {
    await ctx.reply(text, { parse_mode: 'Markdown' });
    return;
  }

  try {
    const tts = await textToSpeech(text);
    const inputFile = new InputFile(tts.buffer, `nexum_voice.${tts.format}`);
    await ctx.replyWithVoice(inputFile);
    // Also send text for reference (collapsed)
    if (text.length > 10) {
      await ctx.reply(`💬 _${text.substring(0, 200)}${text.length > 200 ? '...' : ''}_`, { parse_mode: 'Markdown' });
    }
  } catch (e: any) {
    console.warn('[tts] Failed, falling back to text:', e.message);
    await ctx.reply(text, { parse_mode: 'Markdown' });
  }
}

// Download file helper
async function downloadFile(fileId: string, bot: Bot): Promise<Buffer> {
  const file = await bot.api.getFile(fileId);
  const url = `https://api.telegram.org/file/bot${config.botToken}/${file.file_path}`;
  const r = await fetch(url);
  if (!r.ok) throw new Error(`Download failed: ${r.status}`);
  const ab = await r.arrayBuffer();
  return Buffer.from(ab);
}

// Get image as base64 from photo/document
async function getImageBase64(ctx: Context, bot: Bot): Promise<{ data: string; mime: string } | null> {
  let fileId: string | null = null;
  let mime = 'image/jpeg';

  if (ctx.message?.photo) {
    const photos = ctx.message.photo;
    fileId = photos[photos.length - 1].file_id; // largest
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

export function setupHandlers(bot: Bot) {
  // /start
  bot.command('start', async (ctx) => {
    const uid = ctx.from!.id;
    ensureUser(uid, ctx.from?.username, ctx.from?.first_name);

    await ctx.reply(
      `👋 Привет, *${ctx.from?.first_name || 'друг'}*!\n\n` +
      `Я *NEXUM* — твой персональный AI-агент. Я умею:\n\n` +
      `🤖 Отвечать на любые вопросы\n` +
      `🎙 Понимать голосовые сообщения\n` +
      `📸 Анализировать фото и изображения\n` +
      `📝 Управлять заметками\n` +
      `✅ Вести задачи и проекты\n` +
      `🎯 Трекать привычки\n` +
      `💰 Считать финансы\n` +
      `⏰ Ставить напоминания\n` +
      `💻 Управлять твоим ПК\n\n` +
      `Просто напиши что тебе нужно!`,
      {
        parse_mode: 'Markdown',
        reply_markup: {
          inline_keyboard: [[
            { text: '📱 Mini Apps', web_app: { url: `${config.webappUrl}/hub` } },
            { text: '❓ Команды', callback_data: 'cmd_help' }
          ]]
        }
      }
    );
  });

  // /help
  bot.command('help', async (ctx) => {
    await ctx.reply(
      `*Команды NEXUM*\n\n` +
      `*AI & Общение*\n` +
      `• Просто пиши — я отвечу\n` +
      `• Отправь голосовое — расшифрую и отвечу\n` +
      `• Отправь фото — опишу что на нём\n\n` +
      `*Инструменты*\n` +
      `/notes — заметки\n` +
      `/tasks — задачи\n` +
      `/habits — привычки\n` +
      `/finance — финансы\n` +
      `/remind [текст] — напоминание\n` +
      `/search [запрос] — поиск в интернете\n\n` +
      `*Память*\n` +
      `/memory — что я знаю о тебе\n` +
      `/forget — очистить память\n` +
      `/clear — очистить историю чата\n\n` +
      `*PC Agent*\n` +
      `/pc — статус агента\n` +
      `/link [код] — привязать ПК\n` +
      `/screenshot — скриншот\n` +
      `/run [команда] — выполнить в терминале\n\n` +
      `*Приложения*\n` +
      `/apps — открыть Mini Apps`,
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
              { text: '🌐 Все Apps', web_app: { url: `${config.webappUrl}/hub` } },
            ]
          ]
        }
      }
    );
  });

  // /memory
  bot.command('memory', async (ctx) => {
    const uid = ctx.from!.id;
    const mems = getMemories(uid);
    if (!mems.length) return ctx.reply('Память пуста — пообщайся со мной больше!');
    const text = mems.map(m => `• *${m.key}*: ${m.value}`).join('\n');
    await ctx.reply(`🧠 *Что я знаю о тебе:*\n\n${text}`, { parse_mode: 'Markdown' });
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
    if (!notes.length) return ctx.reply('📝 Заметок нет. Просто напиши "запиши..." или открой Mini App.', {
      reply_markup: { inline_keyboard: [[{ text: '📝 Открыть заметки', web_app: { url: `${config.webappUrl}/notes` } }]] }
    });

    const text = notes.map((n, i) =>
      `${n.pinned ? '📌 ' : ''}*${i + 1}.* ${n.title || n.content.substring(0, 50)}${n.content.length > 50 ? '...' : ''}`
    ).join('\n');

    await ctx.reply(`📝 *Твои заметки:*\n\n${text}`, {
      parse_mode: 'Markdown',
      reply_markup: { inline_keyboard: [[{ text: '📝 Открыть все', web_app: { url: `${config.webappUrl}/notes` } }]] }
    });
  });

  // /tasks
  bot.command('tasks', async (ctx) => {
    const uid = ctx.from!.id;
    const tasks = db.prepare(`SELECT * FROM tasks WHERE uid = ? AND status != 'done' ORDER BY priority DESC, created_at DESC LIMIT 10`).all(uid) as any[];
    if (!tasks.length) return ctx.reply('✅ Задач нет. Скажи "создай задачу..." или открой Mini App.', {
      reply_markup: { inline_keyboard: [[{ text: '✅ Открыть задачи', web_app: { url: `${config.webappUrl}/tasks` } }]] }
    });

    const prioEmoji: Record<string, string> = { critical: '🔴', high: '🟠', medium: '🟡', low: '🟢' };
    const text = tasks.map((t, i) =>
      `${prioEmoji[t.priority] || '⚪'} *${i + 1}.* ${t.title}${t.project !== 'General' ? ` _[${t.project}]_` : ''}`
    ).join('\n');

    await ctx.reply(`✅ *Активные задачи:*\n\n${text}`, {
      parse_mode: 'Markdown',
      reply_markup: { inline_keyboard: [[{ text: '✅ Открыть все', web_app: { url: `${config.webappUrl}/tasks` } }]] }
    });
  });

  // /habits
  bot.command('habits', async (ctx) => {
    const uid = ctx.from!.id;
    const habits = db.prepare('SELECT * FROM habits WHERE uid = ? ORDER BY streak DESC').all(uid) as any[];
    if (!habits.length) return ctx.reply('🎯 Привычек нет. Открой Mini App чтобы добавить.', {
      reply_markup: { inline_keyboard: [[{ text: '🎯 Открыть привычки', web_app: { url: `${config.webappUrl}/habits` } }]] }
    });

    const today = new Date().toISOString().split('T')[0];
    const text = habits.map(h => {
      const done = h.last_done?.startsWith(today);
      return `${done ? '✅' : '⬜'} ${h.emoji} *${h.name}* — 🔥 ${h.streak} дн.`;
    }).join('\n');

    await ctx.reply(`🎯 *Привычки:*\n\n${text}`, {
      parse_mode: 'Markdown',
      reply_markup: { inline_keyboard: [[{ text: '🎯 Открыть все', web_app: { url: `${config.webappUrl}/habits` } }]] }
    });
  });

  // /finance
  bot.command('finance', async (ctx) => {
    const uid = ctx.from!.id;
    const month = new Date().toISOString().substring(0, 7);
    const stats = db.prepare(`
      SELECT type, SUM(amount) as total FROM finance 
      WHERE uid = ? AND created_at >= ? 
      GROUP BY type
    `).all(uid, `${month}-01`) as any[];

    const income  = stats.find(s => s.type === 'income')?.total || 0;
    const expense = stats.find(s => s.type === 'expense')?.total || 0;
    const balance = income - expense;

    await ctx.reply(
      `💰 *Финансы за ${month}:*\n\n` +
      `📈 Доходы: *${income.toLocaleString()}*\n` +
      `📉 Расходы: *${expense.toLocaleString()}*\n` +
      `💵 Баланс: *${balance >= 0 ? '+' : ''}${balance.toLocaleString()}*`,
      {
        parse_mode: 'Markdown',
        reply_markup: { inline_keyboard: [[{ text: '💰 Открыть финансы', web_app: { url: `${config.webappUrl}/finance` } }]] }
      }
    );
  });

  // /search
  bot.command('search', async (ctx) => {
    const query = ctx.match?.trim();
    if (!query) return ctx.reply('Укажи поисковый запрос: /search что искать');
    const msg = await ctx.reply('🔍 Ищу...');
    try {
      const result = await webSearch(query);
      await ctx.api.editMessageText(ctx.chat.id, msg.message_id, result, { parse_mode: 'Markdown' });
    } catch (e: any) {
      await ctx.api.editMessageText(ctx.chat.id, msg.message_id, `❌ Ошибка: ${e.message}`);
    }
  });

  // /remind
  bot.command('remind', async (ctx) => {
    const text = ctx.match?.trim();
    if (!text) return ctx.reply('Пример: /remind через 30 минут позвонить маме');
    const result = await execute(ctx.from!.id, `напомни ${text}`);
    await ctx.reply(result.text, { parse_mode: 'Markdown' });
  });

  // /pc
  bot.command('pc', async (ctx) => {
    const uid = ctx.from!.id;
    const agent = db.prepare('SELECT * FROM pc_agents WHERE uid = ?').get(uid) as any;
    if (!agent) {
      return ctx.reply(
        '💻 *PC Agent не подключён*\n\n' +
        'Запусти агент на своём компьютере:\n' +
        '```\npip install websockets pyautogui pillow psutil\npython nexum_agent.py\n```\n' +
        'Затем введи `/link КОД` который покажет агент.',
        { parse_mode: 'Markdown' }
      );
    }
    const lastSeen = agent.last_seen ? new Date(agent.last_seen).toLocaleString('ru-RU') : 'неизвестно';
    await ctx.reply(
      `💻 *PC Agent*\n\n` +
      `📱 Устройство: ${agent.platform || 'неизвестно'}\n` +
      `🕐 Последнее соединение: ${lastSeen}`,
      { parse_mode: 'Markdown' }
    );
  });

  // /link
  bot.command('link', async (ctx) => {
    const code = ctx.match?.trim().toUpperCase();
    if (!code) return ctx.reply('Укажи код: /link ABCDEF');

    const linkReq = db.prepare('SELECT * FROM link_codes WHERE code = ?').get(code) as any;
    if (!linkReq) return ctx.reply('❌ Код не найден. Убедись что агент запущен.');

    const uid = ctx.from!.id;
    db.prepare('INSERT INTO pc_agents (uid, device_id, platform, last_seen) VALUES (?, ?, ?, ?) ON CONFLICT(uid) DO UPDATE SET device_id=excluded.device_id, platform=excluded.platform, last_seen=excluded.last_seen')
      .run(uid, linkReq.device_id, linkReq.platform, new Date().toISOString());
    db.prepare('DELETE FROM link_codes WHERE code = ?').run(code);

    await ctx.reply(`✅ PC Agent подключён!\n💻 ${linkReq.platform || 'Unknown'}`);
  });

  // /screenshot
  bot.command('screenshot', async (ctx) => {
    const uid = ctx.from!.id;
    const agent = db.prepare('SELECT * FROM pc_agents WHERE uid = ?').get(uid) as any;
    if (!agent?.ws_id) return ctx.reply('❌ PC Agent не подключён. Используй /pc для инструкций.');
    await ctx.reply('📸 Запрос отправлен агенту...');
  });

  // /run
  bot.command('run', async (ctx) => {
    const cmd = ctx.match?.trim();
    if (!cmd) return ctx.reply('Укажи команду: /run ls -la');
    const uid = ctx.from!.id;
    const agent = db.prepare('SELECT * FROM pc_agents WHERE uid = ?').get(uid) as any;
    if (!agent?.ws_id) return ctx.reply('❌ PC Agent не подключён.');
    await ctx.reply(`⚙️ Выполняю: \`${cmd}\``, { parse_mode: 'Markdown' });
  });

  // /status
  bot.command('status', async (ctx) => {
    const isAdmin = config.adminIds.includes(ctx.from!.id);
    const totalUsers = (db.prepare('SELECT COUNT(*) as c FROM users').get() as any).c;
    const totalNotes = (db.prepare('SELECT COUNT(*) as c FROM notes').get() as any).c;
    const totalTasks = (db.prepare('SELECT COUNT(*) as c FROM tasks').get() as any).c;

    await ctx.reply(
      `📊 *NEXUM Status*\n\n` +
      `👥 Пользователей: ${totalUsers}\n` +
      `📝 Заметок: ${totalNotes}\n` +
      `✅ Задач: ${totalTasks}\n` +
      `🤖 AI: активен\n` +
      `⚙️ Версия: 6.0.0`,
      { parse_mode: 'Markdown' }
    );
  });

  // /voice — manage voice mode
  bot.command('voice', async (ctx) => {
    const uid = ctx.from!.id;
    const arg = ctx.match?.trim().toLowerCase();
    const mode = getUserVoiceMode(uid);

    if (!arg) {
      await ctx.reply(
        `🎙 *Голосовой режим NEXUM*\n\nТекущий: *${modeLabel(mode)}*\n\n` +
        `Я умею отвечать голосом как ChatGPT!\n` +
        `Поддерживаю 50+ языков без акцента.\n\nВыбери режим:`,
        {
          parse_mode: 'Markdown',
          reply_markup: {
            inline_keyboard: [
              [{ text: (mode==='auto'?'✅ ':'') + '🔁 Авто — голос на голос',   callback_data: 'voice_auto' }],
              [{ text: (mode==='always'?'✅ ':'') + '🔊 Всегда отвечать голосом', callback_data: 'voice_always' }],
              [{ text: (mode==='never'?'✅ ':'') + '💬 Только текст',             callback_data: 'voice_never' }],
            ]
          }
        }
      );
      return;
    }
    if (['auto','always','never'].includes(arg)) {
      setUserVoiceMode(uid, arg);
      await ctx.reply(`✅ Режим: *${modeLabel(arg)}*`, { parse_mode: 'Markdown' });
    }
  });

  bot.callbackQuery('voice_auto', async (ctx) => {
    setUserVoiceMode(ctx.from.id, 'auto');
    await ctx.answerCallbackQuery();
    await ctx.editMessageText(`🎙 *Голосовой режим*\n\n✅ *${modeLabel('auto')}*\n\n${modeDesc('auto')}`, { parse_mode: 'Markdown' });
  });
  bot.callbackQuery('voice_always', async (ctx) => {
    setUserVoiceMode(ctx.from.id, 'always');
    await ctx.answerCallbackQuery();
    await ctx.editMessageText(`🎙 *Голосовой режим*\n\n✅ *${modeLabel('always')}*\n\n${modeDesc('always')}`, { parse_mode: 'Markdown' });
  });
  bot.callbackQuery('voice_never', async (ctx) => {
    setUserVoiceMode(ctx.from.id, 'never');
    await ctx.answerCallbackQuery();
    await ctx.editMessageText(`🎙 *Голосовой режим*\n\n✅ *${modeLabel('never')}*\n\n${modeDesc('never')}`, { parse_mode: 'Markdown' });
  });

  // Callback queries
  bot.callbackQuery('cmd_help', async (ctx) => {
    await ctx.answerCallbackQuery();
    await ctx.reply(
      `*Команды NEXUM*\n\n/notes /tasks /habits /finance\n/remind /search /memory /forget\n/pc /link /screenshot /apps`,
      { parse_mode: 'Markdown' }
    );
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

      await ctx.api.editMessageText(ctx.chat.id, statusMsg.message_id,
        `📸 *Анализ изображения:*\n\n${result.text}`,
        { parse_mode: 'Markdown' }
      );
    } catch (e: any) {
      console.error('[photo handler]', e);
      await ctx.api.editMessageText(ctx.chat.id, statusMsg.message_id, `❌ Ошибка анализа: ${e.message}`);
    }
  });

  // Handle documents (including images sent as files)
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
        await ctx.api.editMessageText(ctx.chat.id, statusMsg.message_id,
          `📸 *Анализ изображения:*\n\n${result.text}`, { parse_mode: 'Markdown' });
      } catch (e: any) {
        await ctx.api.editMessageText(ctx.chat.id, statusMsg.message_id, `❌ Ошибка: ${e.message}`);
      }
      return;
    }

    await ctx.reply(`📎 Получил файл: *${ctx.message.document.file_name || 'файл'}*\n_Обработка документов скоро появится_`, { parse_mode: 'Markdown' });
  });

  // Handle stickers
  bot.on('message:sticker', async (ctx) => {
    const responses = ['😄', '👍', '🔥', '💯', '✨'];
    await ctx.reply(responses[Math.floor(Math.random() * responses.length)]);
  });

  // Handle video/video notes
  bot.on([':video', ':video_note'], async (ctx) => {
    await ctx.reply('🎥 Видео получено. Пока я не умею анализировать видео, но могу помочь с чем-то другим!');
  });

  // Handle voice messages — full voice conversation (like ChatGPT)
  bot.on('message:voice', async (ctx) => {
    const uid = ctx.from!.id;
    ensureUser(uid, ctx.from?.username, ctx.from?.first_name);

    const statusMsg = await ctx.reply('🎙 Слушаю...');

    try {
      // 1. STT — transcribe
      const buf = await downloadFile(ctx.message.voice.file_id, bot);
      const transcript = await transcribeVoice(buf, 'voice.ogg');

      await ctx.api.editMessageText(ctx.chat.id, statusMsg.message_id,
        `🎙 _${transcript}_\n\n⏳ Думаю...`, { parse_mode: 'Markdown' });

      // 2. AI — generate reply
      const result = await execute(uid, transcript);

      // 3. TTS — synthesize and send voice
      const mode = getUserVoiceMode(uid);
      if (mode !== 'never') {
        // Delete status, send voice + text
        await ctx.api.deleteMessage(ctx.chat.id, statusMsg.message_id).catch(() => {});
        try {
          await ctx.replyWithChatAction('record_voice');
          const tts = await textToSpeech(result.text);
          const inputFile = new InputFile(tts.buffer, `nexum.${tts.format}`);
          await ctx.replyWithVoice(inputFile, {
            caption: `_${transcript.substring(0, 100)}${transcript.length > 100 ? '...' : ''}_`,
            parse_mode: 'Markdown',
          });
        } catch (ttsErr: any) {
          console.warn('[tts] fallback to text:', ttsErr.message);
          await ctx.reply(result.text, { parse_mode: 'Markdown' });
        }
      } else {
        await ctx.api.editMessageText(ctx.chat.id, statusMsg.message_id,
          `🎙 _${transcript}_\n\n${result.text}`, { parse_mode: 'Markdown' });
      }
    } catch (e: any) {
      console.error('[voice]', e);
      await ctx.api.editMessageText(ctx.chat.id, statusMsg.message_id,
        `❌ Ошибка: ${e.message}`).catch(() => ctx.reply(`❌ ${e.message}`));
    }
  });

  // Handle audio files
  bot.on('message:audio', async (ctx) => {
    const uid = ctx.from!.id;
    ensureUser(uid, ctx.from?.username, ctx.from?.first_name);
    const statusMsg = await ctx.reply('🎵 Обрабатываю аудио...');
    try {
      const buf = await downloadFile(ctx.message.audio.file_id, bot);
      const transcript = await transcribeVoice(buf, 'audio.mp3');
      await ctx.api.editMessageText(ctx.chat.id, statusMsg.message_id,
        `🎵 _${transcript}_\n\n⏳ Думаю...`, { parse_mode: 'Markdown' });
      const result = await execute(uid, transcript);
      await ctx.api.editMessageText(ctx.chat.id, statusMsg.message_id,
        `🎵 _${transcript}_\n\n${result.text}`, { parse_mode: 'Markdown' });
    } catch (e: any) {
      await ctx.api.editMessageText(ctx.chat.id, statusMsg.message_id, `❌ Ошибка: ${e.message}`);
    }
  });

  // Handle text messages (main handler — must be last)
  bot.on('message:text', async (ctx) => {
    const uid = ctx.from!.id;
    ensureUser(uid, ctx.from?.username, ctx.from?.first_name);

    const text = ctx.message.text;
    if (text.startsWith('/')) return; // skip unknown commands

    const mode = getUserVoiceMode(uid);
    await ctx.replyWithChatAction(mode === 'always' ? 'record_voice' : 'typing');

    try {
      const result = await execute(uid, text);
      await sendVoiceReply(ctx, result.text, uid, false);
    } catch (e: any) {
      console.error('[text handler]', e);
      await ctx.reply(`❌ Ошибка: ${e.message}`);
    }
  });
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function modeLabel(mode: string): string {
  return { auto: 'Авто (голос → голос)', always: 'Всегда голосом', never: 'Только текст' }[mode] || mode;
}

function modeDesc(mode: string): string {
  return {
    auto: 'Отправляешь голосовое — получаешь голосовой ответ. Текст → текст.',
    always: 'Я всегда отвечаю голосовыми сообщениями, на любой запрос.',
    never: 'Только текстовые ответы. TTS отключён.',
  }[mode] || '';
}
