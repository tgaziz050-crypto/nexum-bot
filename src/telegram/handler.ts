import { Bot, Context, InputFile } from 'grammy';
import { config } from '../core/config';
import { db, ensureUser, setUserApiKey } from '../core/db';
import { execute, generateWebsite, generateTool } from '../agent/executor';
import { transcribeVoice } from '../tools/stt';
import { textToSpeech, VOICES, getUserVoicePref, setUserVoicePref, detectLang } from '../tools/tts';
import { webSearch } from '../tools/search';
import { getMemories, clearMemory, clearHistory } from '../agent/memory';

// ── Voice mode ────────────────────────────────────────────────────────────────
function getVoiceMode(uid: number): string {
  const r = db.prepare("SELECT value FROM memory WHERE uid=? AND key='voice_mode'").get(uid) as any;
  return r?.value || 'auto';
}
function setVoiceMode(uid: number, mode: string) {
  db.prepare("INSERT INTO memory (uid,key,value) VALUES (?,'voice_mode',?) ON CONFLICT(uid,key) DO UPDATE SET value=excluded.value").run(uid, mode);
}
function modeLabel(m: string): string {
  return { auto: 'Авто (голос → голос)', always: 'Всегда голосом', never: 'Только текст' }[m] || m;
}

// ── Reaction picker ───────────────────────────────────────────────────────────
function pickReaction(text: string): string {
  const t = text.toLowerCase();
  if (/спасибо|thank|merci|danke|gracias|شكر/i.test(t)) return '🙏';
  if (/люблю|love|amor|liebe/i.test(t))                  return '❤';
  if (/помоги|help/i.test(t))                            return '👌';
  if (/привет|hello|hi |hey |salut/i.test(t))            return '👋';
  if (/круто|отлично|супер|awesome|cool|wow/i.test(t))   return '🔥';
  if (/смешно|хаха|lol|funny/i.test(t))                  return '😂';
  if (/грустно|sad|жаль/i.test(t))                       return '🥺';
  if (/деньги|финанс|money|cash/i.test(t))               return '💰';
  if (/код|code|программ/i.test(t))                      return '🖥';
  const pool = ['👍','🔥','❤','⚡','🎉','👏','✨','💪','🤙'];
  return pool[Math.floor(Math.random() * pool.length)];
}

async function react(ctx: Context) {
  try {
    // React only ~40% of the time (human-like)
    if (Math.random() > 0.4) return;
    const emoji = pickReaction(ctx.message?.text || '');
    await ctx.api.raw.setMessageReaction({
      chat_id: ctx.chat!.id,
      message_id: ctx.message!.message_id,
      reaction: [{ type: 'emoji', emoji }],
    });
  } catch { /* silently ignore */ }
}

// ── Safe send helpers ─────────────────────────────────────────────────────────
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

async function safeEdit(ctx: Context, chatId: number, msgId: number, text: string, extra?: any) {
  try {
    return await ctx.api.editMessageText(chatId, msgId, text, { parse_mode: 'Markdown', ...extra });
  } catch (e: any) {
    if (!e?.description?.includes('not modified')) {
      // Try plain text
      try { return await ctx.api.editMessageText(chatId, msgId, text.replace(/[*_`\[\]]/g, ''), extra); }
      catch { /* ignore */ }
    }
  }
}

// ── Download file from Telegram ───────────────────────────────────────────────
async function downloadFile(fileId: string, bot: Bot): Promise<Buffer> {
  const file = await bot.api.getFile(fileId);
  const url  = `https://api.telegram.org/file/bot${config.botToken}/${file.file_path}`;
  const r    = await fetch(url);
  if (!r.ok) throw new Error(`Download failed: ${r.status}`);
  return Buffer.from(await r.arrayBuffer());
}

// ── Get image as base64 ───────────────────────────────────────────────────────
async function getImageB64(ctx: Context, bot: Bot): Promise<{ data: string; mime: string } | null> {
  let fileId: string | null = null;
  let mime = 'image/jpeg';
  if (ctx.message?.photo) {
    const photos = ctx.message.photo;
    fileId = photos[photos.length - 1].file_id;
  } else if (ctx.message?.document?.mime_type?.startsWith('image/')) {
    fileId = ctx.message.document.file_id;
    mime   = ctx.message.document.mime_type;
  } else if (ctx.message?.sticker) {
    fileId = ctx.message.sticker.file_id;
    mime   = 'image/webp';
  }
  if (!fileId) return null;
  const buf = await downloadFile(fileId, bot);
  return { data: buf.toString('base64'), mime };
}

// ── Voice reply dispatcher ─────────────────────────────────────────────────────
async function voiceReply(ctx: Context, text: string, uid: number, isVoice: boolean) {
  const mode = getVoiceMode(uid);
  const speak = mode === 'always' || (mode === 'auto' && isVoice);
  if (!speak) { await safeSend(ctx, text); return; }
  try {
    await ctx.replyWithChatAction('record_voice');
    const tts = await textToSpeech(text, uid);
    await ctx.replyWithVoice(new InputFile(tts.buffer, `nexum.${tts.format}`));
  } catch (e: any) {
    console.warn('[tts] fallback to text:', e.message?.slice(0, 80));
    await safeSend(ctx, text);
  }
}

// ── Check if admin ────────────────────────────────────────────────────────────
function isAdmin(uid: number): boolean {
  return config.adminIds.includes(uid);
}

// ── Require PC Agent online ───────────────────────────────────────────────────
async function requireAgent(ctx: Context, app: any): Promise<boolean> {
  const uid    = ctx.from!.id;
  const online = app.isAgentOnline?.(uid);
  if (!online) {
    await safeSend(ctx,
      `💻 *PC Agent офлайн*\n\nЗапусти агент на компьютере:\n\`\`\`\npip install websockets pyautogui pillow psutil requests pyperclip\npython nexum_agent.py\n\`\`\`\nЗатем: \`/link КОД\``
    );
    return false;
  }
  return true;
}

async function agentCmd(ctx: Context, app: any, msg: object, statusText?: string) {
  if (!await requireAgent(ctx, app)) return;
  const uid     = ctx.from!.id;
  const statusMsg = statusText ? await ctx.reply(statusText) : null;
  try {
    const result = await app.sendToAgent(uid, msg);
    const text   = result?.data || result || '(нет ответа)';
    if (statusMsg) await safeEdit(ctx, ctx.chat!.id, statusMsg.message_id, String(text));
    else await safeSend(ctx, String(text));
  } catch (e: any) {
    const err = `❌ ${e.message}`;
    if (statusMsg) await safeEdit(ctx, ctx.chat!.id, statusMsg.message_id, err);
    else await ctx.reply(err);
  }
}

// ═════════════════════════════════════════════════════════════════════════════
// SETUP HANDLERS
// ═════════════════════════════════════════════════════════════════════════════
export function setupHandlers(bot: Bot, app: any) {

  // /start ──────────────────────────────────────────────────────────────────
  bot.command('start', async (ctx) => {
    const uid = ctx.from!.id;
    ensureUser(uid, ctx.from?.username, ctx.from?.first_name);
    const name = ctx.from?.first_name || 'друг';
    await safeSend(ctx,
      `👋 Привет, *${name}*!\n\nЯ *NEXUM* — твой автономный AI-агент.\n\n` +
      `🤖 Отвечаю на любые вопросы\n` +
      `🎙 Понимаю голосовые сообщения\n` +
      `📸 Анализирую фото и изображения\n` +
      `🌐 Создаю готовые сайты\n` +
      `🛠 Разрабатываю новые инструменты\n` +
      `📝 Управляю заметками, задачами, привычками\n` +
      `💰 Считаю финансы\n` +
      `⏰ Ставлю напоминания\n` +
      `💻 Управляю твоим ПК\n\n` +
      `Просто напиши что нужно!`,
      {
        reply_markup: {
          inline_keyboard: [[
            config.webappUrl ? { text: '📱 Mini Apps', web_app: { url: `${config.webappUrl}/hub` } } : { text: '❓ Помощь', callback_data: 'cmd_help' },
            { text: '❓ Помощь', callback_data: 'cmd_help' },
          ]]
        }
      }
    );
  });

  // /help ───────────────────────────────────────────────────────────────────
  bot.command('help', async (ctx) => {
    await safeSend(ctx,
      `*NEXUM — Команды*\n\n` +
      `*Основное*\n• Просто пиши — отвечу\n• Голосовое — расшифрую + отвечу\n• Фото — опишу\n\n` +
      `*Создание*\n/website — создать сайт\n/newtool — создать инструмент\n/tools — мои инструменты\n\n` +
      `*Mini Apps*\n/apps — открыть приложения\n/notes /tasks /habits /finance\n\n` +
      `*Утилиты*\n/remind /search /memory /forget /clear\n/voice /voices /status\n\n` +
      `*PC Agent*\n/pc /link /screenshot /run /bgrun /bglist\n/sysinfo /ps /kill /files /clipboard\n/notify /window /http /browser /openapp\n/mouse /keyboard /hotkey /network\n\n` +
      `*Настройки*\n/setkey — добавить свой API ключ\n/mykeys — мои ключи`
    );
  });

  // /apps ───────────────────────────────────────────────────────────────────
  bot.command('apps', async (ctx) => {
    if (!config.webappUrl) return ctx.reply('WEBAPP_URL не настроен');
    await ctx.reply('📱 *NEXUM Mini Apps*', {
      parse_mode: 'Markdown',
      reply_markup: {
        inline_keyboard: [
          [{ text: '💰 Финансы', web_app: { url: `${config.webappUrl}/finance` } }, { text: '📝 Заметки', web_app: { url: `${config.webappUrl}/notes` } }],
          [{ text: '✅ Задачи',  web_app: { url: `${config.webappUrl}/tasks` } },   { text: '🎯 Привычки', web_app: { url: `${config.webappUrl}/habits` } }],
          [{ text: '🌐 Сайты',  web_app: { url: `${config.webappUrl}/sites` } },    { text: '🛠 Инструменты', web_app: { url: `${config.webappUrl}/tools-app` } }],
        ]
      }
    });
  });

  // /status ─────────────────────────────────────────────────────────────────
  bot.command('status', async (ctx) => {
    const uid  = ctx.from!.id;
    const totalUsers  = (db.prepare('SELECT COUNT(*) as c FROM users').get() as any).c;
    const totalNotes  = (db.prepare('SELECT COUNT(*) as c FROM notes').get() as any).c;
    const totalTasks  = (db.prepare('SELECT COUNT(*) as c FROM tasks').get() as any).c;
    const totalTools  = (db.prepare('SELECT COUNT(*) as c FROM custom_tools WHERE active=1').get() as any).c;
    const totalSites  = (db.prepare('SELECT COUNT(*) as c FROM websites').get() as any).c;
    const agentOnline = app.isAgentOnline?.(uid);
    const uptime = process.uptime();
    const hrs = Math.floor(uptime / 3600), mins = Math.floor((uptime % 3600) / 60);
    await safeSend(ctx,
      `📊 *NEXUM v11*\n\n` +
      `👥 Пользователей: ${totalUsers}\n📝 Заметок: ${totalNotes}\n✅ Задач: ${totalTasks}\n` +
      `🛠 Инструментов: ${totalTools}\n🌐 Сайтов: ${totalSites}\n` +
      `🤖 AI: активен\n💻 PC Agent: ${agentOnline ? '🟢 онлайн' : '🔴 офлайн'}\n⏱ Uptime: ${hrs}h ${mins}m`
    );
  });

  // /website ─────────────────────────────────────────────────────────────────
  bot.command('website', async (ctx) => {
    const uid    = ctx.from!.id;
    const prompt = ctx.match?.trim();
    ensureUser(uid, ctx.from?.username, ctx.from?.first_name);
    if (!prompt) {
      return safeSend(ctx,
        `🌐 *Создание сайта*\n\nПример:\n/website лендинг для фитнес-клуба\n/website портфолио разработчика\n/website калькулятор ИМТ`
      );
    }
    const msg = await ctx.reply('🌐 Создаю сайт... _10–20 сек_', { parse_mode: 'Markdown' });
    try {
      const site    = await generateWebsite(uid, prompt);
      const siteUrl = `${config.webappUrl}/site/${site.id}`;
      await safeEdit(ctx, ctx.chat!.id, msg.message_id, `✅ *Сайт готов!*\n\n_${site.name}_`, {
        reply_markup: {
          inline_keyboard: [
            [{ text: '🌐 Открыть', web_app: { url: siteUrl } }],
            [{ text: '🔗 Ссылка',  callback_data: `site_link_${site.id}` }],
          ]
        }
      });
    } catch (e: any) {
      await safeEdit(ctx, ctx.chat!.id, msg.message_id, `❌ ${e.message}`);
    }
  });

  // /newtool ─────────────────────────────────────────────────────────────────
  bot.command('newtool', async (ctx) => {
    const uid  = ctx.from!.id;
    const desc = ctx.match?.trim();
    ensureUser(uid, ctx.from?.username, ctx.from?.first_name);
    if (!desc) {
      const tools = db.prepare('SELECT * FROM custom_tools WHERE (uid=? OR uid=0) AND active=1').all(uid) as any[];
      const list  = tools.length ? tools.map(t => `• *${t.name}* — ${t.description} (×${t.usage_count})`).join('\n') : '• Пока нет';
      return safeSend(ctx, `🛠 *Самообучающиеся инструменты*\n\n/newtool конвертер валют\n/newtool генератор паролей\n/newtool калькулятор кредита\n\n*Текущие:*\n${list}`);
    }
    const msg = await ctx.reply('🔨 Создаю инструмент...');
    try {
      const toolData = await generateTool(uid, desc);
      const r = db.prepare('INSERT INTO custom_tools (uid,name,description,trigger_pattern,code,active) VALUES (?,?,?,?,?,1)')
        .run(uid, toolData.name, toolData.desc, toolData.trigger, toolData.code);
      await safeEdit(ctx, ctx.chat!.id, msg.message_id,
        `✅ *Инструмент создан!*\n\n🔧 *${toolData.name}*\n📝 ${toolData.desc}\n🎯 Триггер: \`${toolData.trigger}\`\n\n_Теперь буду использовать его автоматически_`,
        {
          reply_markup: {
            inline_keyboard: [
              [{ text: '🧪 Тест',  callback_data: `test_tool_${r.lastInsertRowid}` }],
              [{ text: '🗑 Удалить', callback_data: `del_tool_${r.lastInsertRowid}` }],
            ]
          }
        }
      );
    } catch (e: any) {
      await safeEdit(ctx, ctx.chat!.id, msg.message_id, `❌ ${e.message}`);
    }
  });

  // /tools ───────────────────────────────────────────────────────────────────
  bot.command('tools', async (ctx) => {
    const uid   = ctx.from!.id;
    const tools = db.prepare('SELECT * FROM custom_tools WHERE (uid=? OR uid=0) AND active=1 ORDER BY usage_count DESC').all(uid) as any[];
    if (!tools.length) return safeSend(ctx, `🛠 *Инструменты*\n\nПока нет. Создай: /newtool описание`);
    const list = tools.map((t, i) =>
      `${i+1}. *${t.name}* — ${t.description}\n   \`${t.trigger_pattern}\` · ×${t.usage_count}`
    ).join('\n\n');
    await safeSend(ctx, `🛠 *Инструменты (${tools.length})*\n\n${list}`);
  });

  // /notes ───────────────────────────────────────────────────────────────────
  bot.command('notes', async (ctx) => {
    const uid   = ctx.from!.id;
    const notes = db.prepare('SELECT * FROM notes WHERE uid=? ORDER BY pinned DESC, updated_at DESC LIMIT 10').all(uid) as any[];
    if (!notes.length) return ctx.reply('📝 Заметок нет. Просто напиши "запиши..."', {
      reply_markup: config.webappUrl ? { inline_keyboard: [[{ text: '📝 Открыть', web_app: { url: `${config.webappUrl}/notes` } }]] } : undefined
    });
    const text = notes.map((n, i) => `${n.pinned ? '📌 ' : ''}*${i+1}.* ${(n.title || n.content).slice(0, 50)}${(n.title || n.content).length > 50 ? '...' : ''}`).join('\n');
    await safeSend(ctx, `📝 *Заметки:*\n\n${text}`, {
      reply_markup: config.webappUrl ? { inline_keyboard: [[{ text: '📝 Все', web_app: { url: `${config.webappUrl}/notes` } }]] } : undefined
    });
  });

  // /tasks ───────────────────────────────────────────────────────────────────
  bot.command('tasks', async (ctx) => {
    const uid   = ctx.from!.id;
    const tasks = db.prepare(`SELECT * FROM tasks WHERE uid=? AND status!='done' ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, id DESC LIMIT 10`).all(uid) as any[];
    if (!tasks.length) return ctx.reply('✅ Задач нет. Скажи "создай задачу..."', {
      reply_markup: config.webappUrl ? { inline_keyboard: [[{ text: '✅ Открыть', web_app: { url: `${config.webappUrl}/tasks` } }]] } : undefined
    });
    const emoji: Record<string,string> = { critical:'🔴', high:'🟠', medium:'🟡', low:'🟢' };
    const text = tasks.map((t, i) => `${emoji[t.priority]||'⚪'} *${i+1}.* ${t.title}${t.project!=='General' ? ` _[${t.project}]_` : ''}`).join('\n');
    await safeSend(ctx, `✅ *Задачи:*\n\n${text}`, {
      reply_markup: config.webappUrl ? { inline_keyboard: [[{ text: '✅ Все', web_app: { url: `${config.webappUrl}/tasks` } }]] } : undefined
    });
  });

  // /habits ──────────────────────────────────────────────────────────────────
  bot.command('habits', async (ctx) => {
    const uid    = ctx.from!.id;
    const habits = db.prepare('SELECT * FROM habits WHERE uid=? ORDER BY streak DESC').all(uid) as any[];
    if (!habits.length) return ctx.reply('🎯 Привычек нет.', {
      reply_markup: config.webappUrl ? { inline_keyboard: [[{ text: '🎯 Добавить', web_app: { url: `${config.webappUrl}/habits` } }]] } : undefined
    });
    const today = new Date().toISOString().split('T')[0];
    const text  = habits.map(h => `${h.last_done?.startsWith(today) ? '✅' : '⬜'} ${h.emoji} *${h.name}* — 🔥${h.streak}`).join('\n');
    await safeSend(ctx, `🎯 *Привычки:*\n\n${text}`, {
      reply_markup: config.webappUrl ? { inline_keyboard: [[{ text: '🎯 Все', web_app: { url: `${config.webappUrl}/habits` } }]] } : undefined
    });
  });

  // /finance ─────────────────────────────────────────────────────────────────
  bot.command('finance', async (ctx) => {
    const uid   = ctx.from!.id;
    const month = new Date().toISOString().slice(0, 7);
    const stats = db.prepare(`SELECT type, SUM(amount) as total FROM finance WHERE uid=? AND created_at >= ? GROUP BY type`).all(uid, `${month}-01`) as any[];
    const income  = stats.find(s => s.type === 'income')?.total  || 0;
    const expense = stats.find(s => s.type === 'expense')?.total || 0;
    const bal     = income - expense;
    await safeSend(ctx,
      `💰 *Финансы (${month}):*\n\n📈 Доходы: *${income.toLocaleString('ru-RU')}*\n📉 Расходы: *${expense.toLocaleString('ru-RU')}*\n💵 Баланс: *${bal >= 0 ? '+' : ''}${bal.toLocaleString('ru-RU')}*`,
      { reply_markup: config.webappUrl ? { inline_keyboard: [[{ text: '💰 Детали', web_app: { url: `${config.webappUrl}/finance` } }]] } : undefined }
    );
  });

  // /search ──────────────────────────────────────────────────────────────────
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

  // /remind ──────────────────────────────────────────────────────────────────
  bot.command('remind', async (ctx) => {
    const text = ctx.match?.trim();
    if (!text) return ctx.reply('Пример: /remind через 30 минут позвонить маме');
    const result = await execute(ctx.from!.id, `напомни ${text}`);
    await safeSend(ctx, result.text);
  });

  // /memory ──────────────────────────────────────────────────────────────────
  bot.command('memory', async (ctx) => {
    const uid = ctx.from!.id;
    const mem = getMemories(uid).filter(m => !['voice_mode','voice_lang','voice_idx'].includes(m.key));
    if (!mem.length) return safeSend(ctx, '🧠 Память пуста. Расскажи мне о себе!');
    const text = mem.map(m => `• *${m.key}*: ${m.value}`).join('\n');
    await safeSend(ctx, `🧠 *Что я знаю о тебе:*\n\n${text}`);
  });

  // /forget / /clear ─────────────────────────────────────────────────────────
  bot.command('forget', async (ctx) => { clearMemory(ctx.from!.id); await ctx.reply('🗑 Память очищена'); });
  bot.command('clear',  async (ctx) => { clearHistory(ctx.from!.id); await ctx.reply('🗑 История очищена'); });

  // /voice / /voices ─────────────────────────────────────────────────────────
  bot.command('voice', async (ctx) => {
    const uid  = ctx.from!.id;
    const mode = getVoiceMode(uid);
    const arg  = ctx.match?.trim().toLowerCase();
    if (arg && ['auto','always','never'].includes(arg)) {
      setVoiceMode(uid, arg);
      return ctx.reply(`✅ Голосовой режим: *${modeLabel(arg)}*`, { parse_mode: 'Markdown' });
    }
    await ctx.reply(`🎙 *Голосовой режим*\n\nТекущий: *${modeLabel(mode)}*`, {
      parse_mode: 'Markdown',
      reply_markup: {
        inline_keyboard: [
          [{ text: (mode==='auto'   ?'✅ ':'')+'🔁 Авто',      callback_data: 'voice_auto' }],
          [{ text: (mode==='always' ?'✅ ':'')+'🔊 Всегда',    callback_data: 'voice_always' }],
          [{ text: (mode==='never'  ?'✅ ':'')+'💬 Только текст', callback_data: 'voice_never' }],
        ]
      }
    });
  });

  bot.callbackQuery('voice_auto',   async (ctx) => { setVoiceMode(ctx.from.id,'auto');   await ctx.answerCallbackQuery(); await ctx.editMessageText(`🎙 Режим: *${modeLabel('auto')}*`,   { parse_mode:'Markdown' }); });
  bot.callbackQuery('voice_always', async (ctx) => { setVoiceMode(ctx.from.id,'always'); await ctx.answerCallbackQuery(); await ctx.editMessageText(`🎙 Режим: *${modeLabel('always')}*`, { parse_mode:'Markdown' }); });
  bot.callbackQuery('voice_never',  async (ctx) => { setVoiceMode(ctx.from.id,'never');  await ctx.answerCallbackQuery(); await ctx.editMessageText(`🎙 Режим: *${modeLabel('never')}*`,  { parse_mode:'Markdown' }); });

  bot.command('voices', async (ctx) => {
    const uid  = ctx.from!.id;
    const pref = getUserVoicePref(uid);
    const btns = Object.entries(VOICES).slice(0, 20).map(([lang, d]) => ({ text: d.name, callback_data: `set_voice_${lang}_0` }));
    const rows: any[] = [];
    for (let i = 0; i < btns.length; i += 2) rows.push(btns.slice(i, i + 2));
    rows.push([{ text: '🌍 Авто', callback_data: 'set_voice_auto_0' }]);
    await ctx.reply(`🎙 *Выбор голоса*\n\nТекущий: *${pref.lang === 'auto' ? 'Авто' : (VOICES[pref.lang]?.name || pref.lang)}*`, {
      parse_mode: 'Markdown', reply_markup: { inline_keyboard: rows }
    });
  });

  bot.callbackQuery(/^set_voice_(.+)_(\d+)$/, async (ctx) => {
    const lang = ctx.match![1], idx = parseInt(ctx.match![2]);
    setUserVoicePref(ctx.from.id, lang, idx);
    await ctx.answerCallbackQuery();
    const name = lang === 'auto' ? 'Авто' : (VOICES[lang]?.name || lang);
    await ctx.editMessageText(`✅ Голос: *${name}*`, { parse_mode: 'Markdown' });
  });

  // /setkey — user API keys ───────────────────────────────────────────────────
  bot.command('setkey', async (ctx) => {
    const args = ctx.match?.trim().split(' ');
    if (!args || args.length < 2) {
      return safeSend(ctx,
        `🔑 *Добавить API ключ*\n\n/setkey groq sk-...\n/setkey gemini AI...\n/setkey openrouter sk-...\n/setkey deepseek sk-...\n/setkey claude sk-ant-...\n/setkey cerebras csk-...\n\n_Провайдер с твоим ключом будет использоваться первым_`
      );
    }
    const [provider, key] = args;
    const allowed = ['groq','gemini','openrouter','deepseek','claude','cerebras','together'];
    if (!allowed.includes(provider.toLowerCase())) return ctx.reply(`❌ Неизвестный провайдер. Доступны: ${allowed.join(', ')}`);
    setUserApiKey(ctx.from!.id, provider.toLowerCase(), key);
    await ctx.reply(`✅ Ключ для *${provider}* сохранён`, { parse_mode: 'Markdown' });
  });

  bot.command('mykeys', async (ctx) => {
    const uid  = ctx.from!.id;
    const keys = db.prepare('SELECT provider, api_key FROM user_api_keys WHERE uid=?').all(uid) as any[];
    if (!keys.length) return safeSend(ctx, '🔑 Нет своих ключей. Добавь: /setkey провайдер ключ');
    const list = keys.map(k => `• *${k.provider}*: \`${k.api_key.slice(0,8)}...\``).join('\n');
    await safeSend(ctx, `🔑 *Твои API ключи:*\n\n${list}\n\nУдалить: /delkey провайдер`);
  });

  bot.command('delkey', async (ctx) => {
    const provider = ctx.match?.trim();
    if (!provider) return ctx.reply('Укажи провайдер: /delkey groq');
    db.prepare('DELETE FROM user_api_keys WHERE uid=? AND provider=?').run(ctx.from!.id, provider);
    await ctx.reply(`✅ Ключ *${provider}* удалён`, { parse_mode: 'Markdown' });
  });

  // ── PC Agent commands ──────────────────────────────────────────────────────

  bot.command('pc', async (ctx) => {
    const uid    = ctx.from!.id;
    const agent  = db.prepare('SELECT * FROM pc_agents WHERE uid=?').get(uid) as any;
    const online = app.isAgentOnline?.(uid);
    if (!agent) {
      return safeSend(ctx,
        `💻 *PC Agent не подключён*\n\n\`\`\`\npip install websockets pyautogui pillow psutil requests pyperclip\npython nexum_agent.py\n\`\`\`\nЗатем: \`/link КОД\``
      );
    }
    const lastSeen = agent.last_seen ? new Date(agent.last_seen).toLocaleString('ru-RU') : 'неизвестно';
    await safeSend(ctx,
      `💻 *PC Agent*\n\n${online ? '🟢 Онлайн' : '🔴 Офлайн'}\n` +
      `📱 ${agent.device_name || agent.platform || 'неизвестно'}\n` +
      `🕐 Последний раз: ${lastSeen}\n\n` +
      `Команды: /screenshot /run /sysinfo /ps /kill\n/files /clipboard /notify /window /http\n/mouse /keyboard /hotkey /network /bgrun /bglist`
    );
  });

  bot.command('link', async (ctx) => {
    const code = ctx.match?.trim().toUpperCase();
    if (!code) return ctx.reply('Укажи код: /link ABCDEF');
    const uid    = ctx.from!.id;
    const linked = app.linkAgent?.(code, uid);
    if (linked) {
      const lr = db.prepare('SELECT * FROM link_codes WHERE code=?').get(code) as any;
      db.prepare(`INSERT INTO pc_agents (uid,device_id,device_name,platform,last_seen,status) VALUES (?,?,?,?,?,'online')
        ON CONFLICT(uid) DO UPDATE SET device_id=excluded.device_id,device_name=excluded.device_name,platform=excluded.platform,last_seen=excluded.last_seen,status='online'`)
        .run(uid, lr?.device_id || 'PC', lr?.device_id || 'PC', lr?.platform || 'Unknown', new Date().toISOString());
      db.prepare('DELETE FROM link_codes WHERE code=?').run(code);
      await ctx.reply(`✅ PC Agent подключён!\n💻 ${lr?.platform || 'Unknown'}\n\nПри следующем запуске привязка будет автоматической.`, { parse_mode: 'Markdown' });
    } else {
      const lr = db.prepare('SELECT * FROM link_codes WHERE code=?').get(code) as any;
      if (!lr) return ctx.reply('❌ Код не найден или устарел');
      db.prepare(`INSERT INTO pc_agents (uid,device_name,platform,last_seen,status) VALUES (?,?,?,?,'online')
        ON CONFLICT(uid) DO UPDATE SET device_name=excluded.device_name,platform=excluded.platform,last_seen=excluded.last_seen,status='online'`)
        .run(uid, lr.device_id || 'PC', lr.platform || 'Unknown', new Date().toISOString());
      db.prepare('DELETE FROM link_codes WHERE code=?').run(code);
      await ctx.reply(`✅ PC Agent привязан!\n💻 ${lr.platform || 'Unknown'}`);
    }
  });

  bot.command('screenshot', async (ctx) => {
    if (!await requireAgent(ctx, app)) return;
    const uid    = ctx.from!.id;
    const region = ctx.match?.trim()?.split(',').map(Number);
    const statusMsg = await ctx.reply('📸 Снимаю экран...');
    try {
      const result = await app.sendToAgent(uid, { type: 'screenshot', chatId: ctx.chat!.id, region: region?.length === 4 ? region : undefined });
      if (result?.data) {
        await ctx.replyWithPhoto(new InputFile(Buffer.from(result.data, 'base64'), 'screenshot.png'));
        await ctx.api.deleteMessage(ctx.chat!.id, statusMsg.message_id).catch(() => {});
      } else {
        await safeEdit(ctx, ctx.chat!.id, statusMsg.message_id, '❌ Не удалось сделать скриншот');
      }
    } catch (e: any) {
      await safeEdit(ctx, ctx.chat!.id, statusMsg.message_id, `❌ ${e.message}`);
    }
  });

  bot.command('run',     async (ctx) => { const c = ctx.match?.trim(); if (!c) return ctx.reply('Укажи команду: /run ls'); await agentCmd(ctx, app, { type:'run', command:c }, `⚙️ \`${c?.slice(0,50)}\`...`); });
  bot.command('bgrun',   async (ctx) => { const c = ctx.match?.trim(); if (!c) return ctx.reply('Укажи команду'); await agentCmd(ctx, app, { type:'run_background', command:c }, '🔄 Запускаю фоново...'); });
  bot.command('bglist',  async (ctx) => { await agentCmd(ctx, app, { type:'bg_list' }); });
  bot.command('bgstop',  async (ctx) => { const id = ctx.match?.trim(); if (!id) return ctx.reply('Укажи ID'); await agentCmd(ctx, app, { type:'bg_stop', proc_id:id }); });
  bot.command('sysinfo', async (ctx) => { await agentCmd(ctx, app, { type:'sysinfo' }, '📊 Собираю...'); });
  bot.command('ps',      async (ctx) => { const l = parseInt(ctx.match?.trim()||'15'); await agentCmd(ctx, app, { type:'processes', limit: isNaN(l)?15:l }, '🔍 Процессы...'); });
  bot.command('kill',    async (ctx) => { const t = ctx.match?.trim(); if (!t) return ctx.reply('Укажи PID или имя'); await agentCmd(ctx, app, { type:'kill_process', input:t }); });
  bot.command('network', async (ctx) => { await agentCmd(ctx, app, { type:'network' }, '🌐 Сеть...'); });

  bot.command('files', async (ctx) => {
    const args = (ctx.match?.trim() || '').split(' ');
    await agentCmd(ctx, app, { type:'filesystem', op:args[0]||'list', path:args[1]||'~', content:args.slice(2).join(' ') }, `📁 ${args[0]||'list'}...`);
  });

  bot.command('clipboard', async (ctx) => {
    const args = (ctx.match?.trim() || 'read').split(' ');
    await agentCmd(ctx, app, { type:'clipboard', op:args[0]==='write'?'write':'read', text:args.slice(1).join(' ') });
  });

  bot.command('notify', async (ctx) => {
    const [title, ...rest] = (ctx.match?.trim() || '').split('|');
    await agentCmd(ctx, app, { type:'notify', title:title.trim()||'NEXUM', message:rest.join('|').trim()||title.trim() });
  });

  bot.command('window', async (ctx) => {
    const args = (ctx.match?.trim() || 'list').split(' ');
    await agentCmd(ctx, app, { type:'window', op:args[0], window_id:args.slice(1).join(' ') }, args[0]==='list'?'🪟 Окна...':undefined);
  });

  bot.command('http', async (ctx) => {
    const args = (ctx.match?.trim() || '').split(' ');
    const method = args[0]?.toUpperCase() || 'GET';
    const url    = args[1] || '';
    if (!url) return ctx.reply('Укажи URL: /http GET https://api.github.com');
    await agentCmd(ctx, app, { type:'http', method, url, body:args.slice(2).join(' ') }, `🌐 ${method} ${url.slice(0,40)}...`);
  });

  bot.command('browser',  async (ctx) => { const u = ctx.match?.trim(); if (!u) return ctx.reply('Укажи URL'); await agentCmd(ctx, app, { type:'browser', input:u }); });
  bot.command('openapp',  async (ctx) => { const n = ctx.match?.trim(); if (!n) return ctx.reply('Укажи приложение'); await agentCmd(ctx, app, { type:'open_app', input:n }); });

  bot.command('mouse', async (ctx) => {
    const a = (ctx.match?.trim() || 'position').split(' ');
    await agentCmd(ctx, app, { type:'mouse', action:a[0], x:parseInt(a[1]||'0'), y:parseInt(a[2]||'0'), text:a.slice(3).join(' ') });
  });

  bot.command('keyboard', async (ctx) => { const t = ctx.match?.trim(); if (!t) return ctx.reply('Укажи текст'); await agentCmd(ctx, app, { type:'keyboard', action:'type', text:t }); });
  bot.command('hotkey',   async (ctx) => { const k = ctx.match?.trim(); if (!k) return ctx.reply('Укажи комбо: ctrl+c'); await agentCmd(ctx, app, { type:'keyboard', action:'hotkey', text:k }); });

  // ── Admin commands ─────────────────────────────────────────────────────────
  bot.command('admin', async (ctx) => {
    if (!isAdmin(ctx.from!.id)) return ctx.reply('❌ Нет доступа');
    const users = (db.prepare('SELECT COUNT(*) as c FROM users').get() as any).c;
    const msgs  = (db.prepare('SELECT COUNT(*) as c FROM conversations').get() as any).c;
    await safeSend(ctx,
      `🔐 *Admin Panel*\n\n👥 Users: ${users}\n💬 Messages: ${msgs}\n\n` +
      `/stats /logs /users /broadcast`
    );
  });

  bot.command('users', async (ctx) => {
    if (!isAdmin(ctx.from!.id)) return ctx.reply('❌ Нет доступа');
    const users = db.prepare('SELECT uid, username, first_name, created_at FROM users ORDER BY created_at DESC LIMIT 20').all() as any[];
    const text  = users.map(u => `• \`${u.uid}\` ${u.first_name || ''} @${u.username || '—'}`).join('\n');
    await safeSend(ctx, `👥 *Пользователи (${users.length}):*\n\n${text}`);
  });

  bot.command('broadcast', async (ctx) => {
    if (!isAdmin(ctx.from!.id)) return ctx.reply('❌ Нет доступа');
    const text = ctx.match?.trim();
    if (!text) return ctx.reply('Укажи текст: /broadcast Сообщение');
    const users = db.prepare('SELECT uid FROM users').all() as any[];
    let sent = 0, failed = 0;
    for (const u of users) {
      try { await bot.api.sendMessage(u.uid, text); sent++; }
      catch { failed++; }
    }
    await ctx.reply(`✅ Отправлено: ${sent} | Ошибок: ${failed}`);
  });

  // ── Callback queries ───────────────────────────────────────────────────────
  bot.callbackQuery('cmd_help', async (ctx) => {
    await ctx.answerCallbackQuery();
    await safeSend(ctx, `*NEXUM — Команды*\n\n/notes /tasks /habits /finance\n/website /newtool /tools\n/voice /remind /search\n/memory /forget /clear\n/apps /status /setkey`);
  });

  bot.callbackQuery(/^site_link_(\d+)$/, async (ctx) => {
    const id  = ctx.match![1];
    const url = `${config.webappUrl}/site/${id}`;
    await ctx.answerCallbackQuery();
    await safeSend(ctx, `🔗 ${url}`);
  });

  bot.callbackQuery(/^del_tool_(\d+)$/, async (ctx) => {
    db.prepare('UPDATE custom_tools SET active=0 WHERE id=?').run(parseInt(ctx.match![1]));
    await ctx.answerCallbackQuery('🗑 Удалён');
    await ctx.editMessageText('🗑 Инструмент удалён');
  });

  bot.callbackQuery(/^test_tool_(\d+)$/, async (ctx) => {
    const tool = db.prepare('SELECT * FROM custom_tools WHERE id=?').get(parseInt(ctx.match![1])) as any;
    await ctx.answerCallbackQuery();
    if (tool) await safeSend(ctx, `🧪 Тест *${tool.name}*\n\nТриггер: \`${tool.trigger_pattern}\`\n\nНапиши сообщение с этим паттерном.`);
  });

  // ── Message handlers ───────────────────────────────────────────────────────

  // Photos
  bot.on('message:photo', async (ctx) => {
    const uid     = ctx.from!.id;
    ensureUser(uid, ctx.from?.username, ctx.from?.first_name);
    const caption = ctx.message.caption || '';
    const status  = await ctx.reply('👁 Анализирую...');
    try {
      const img    = await getImageB64(ctx, bot);
      if (!img) throw new Error('Не удалось загрузить фото');
      const result = await execute(uid, caption || 'Что на изображении?', img.data, img.mime);
      await safeEdit(ctx, ctx.chat!.id, status.message_id, result.text);
    } catch (e: any) {
      await safeEdit(ctx, ctx.chat!.id, status.message_id, `❌ ${e.message}`);
    }
  });

  // Documents
  bot.on('message:document', async (ctx) => {
    const uid  = ctx.from!.id;
    ensureUser(uid, ctx.from?.username, ctx.from?.first_name);
    const mime = ctx.message.document?.mime_type || '';
    if (mime.startsWith('image/')) {
      const status = await ctx.reply('👁 Анализирую...');
      try {
        const img = await getImageB64(ctx, bot);
        if (!img) throw new Error('Не удалось загрузить');
        const result = await execute(uid, ctx.message.caption || 'Что на изображении?', img.data, img.mime);
        await safeEdit(ctx, ctx.chat!.id, status.message_id, result.text);
      } catch (e: any) {
        await safeEdit(ctx, ctx.chat!.id, status.message_id, `❌ ${e.message}`);
      }
      return;
    }
    await safeSend(ctx, `📎 Файл: *${ctx.message.document.file_name || 'файл'}*\n_Поддержка документов скоро_`);
  });

  // Voice messages
  bot.on('message:voice', async (ctx) => {
    const uid    = ctx.from!.id;
    ensureUser(uid, ctx.from?.username, ctx.from?.first_name);
    const status = await ctx.reply('🎙 Слушаю...');
    try {
      const buf        = await downloadFile(ctx.message.voice.file_id, bot);
      const transcript = await transcribeVoice(buf, 'voice.ogg');
      await safeEdit(ctx, ctx.chat!.id, status.message_id, `🎙 _${transcript}_\n\n⏳ Думаю...`);
      const result = await execute(uid, transcript);
      const mode   = getVoiceMode(uid);
      if (mode !== 'never') {
        await ctx.api.deleteMessage(ctx.chat!.id, status.message_id).catch(() => {});
        try {
          await ctx.replyWithChatAction('record_voice');
          const tts = await textToSpeech(result.text, uid);
          await ctx.replyWithVoice(new InputFile(tts.buffer, `nexum.${tts.format}`), {
            caption: `_${transcript.slice(0, 100)}${transcript.length > 100 ? '...' : ''}_`,
            parse_mode: 'Markdown',
          });
        } catch {
          await safeSend(ctx, `🎙 _${transcript}_\n\n${result.text}`);
        }
      } else {
        await safeEdit(ctx, ctx.chat!.id, status.message_id, `🎙 _${transcript}_\n\n${result.text}`);
      }
    } catch (e: any) {
      await safeEdit(ctx, ctx.chat!.id, status.message_id, `❌ ${e.message}`).catch(() => ctx.reply(`❌ ${e.message}`));
    }
  });

  // Audio
  bot.on('message:audio', async (ctx) => {
    const uid    = ctx.from!.id;
    ensureUser(uid, ctx.from?.username, ctx.from?.first_name);
    const status = await ctx.reply('🎵 Обрабатываю...');
    try {
      const buf        = await downloadFile(ctx.message.audio.file_id, bot);
      const transcript = await transcribeVoice(buf, 'audio.mp3');
      await safeEdit(ctx, ctx.chat!.id, status.message_id, `🎵 _${transcript}_\n\n⏳...`);
      const result = await execute(uid, transcript);
      await safeEdit(ctx, ctx.chat!.id, status.message_id, `🎵 _${transcript}_\n\n${result.text}`);
    } catch (e: any) {
      await safeEdit(ctx, ctx.chat!.id, status.message_id, `❌ ${e.message}`);
    }
  });

  // Video notes (кружки)
  bot.on('message:video_note', async (ctx) => {
    const uid    = ctx.from!.id;
    ensureUser(uid, ctx.from?.username, ctx.from?.first_name);
    const status = await ctx.reply('🎥 Обрабатываю видео...');
    try {
      const buf        = await downloadFile(ctx.message.video_note.file_id, bot);
      const transcript = await transcribeVoice(buf, 'video.mp4');
      await safeEdit(ctx, ctx.chat!.id, status.message_id, `🎥 _${transcript}_\n\n⏳...`);
      const result = await execute(uid, transcript);
      await safeEdit(ctx, ctx.chat!.id, status.message_id, `🎥 _${transcript}_\n\n${result.text}`);
    } catch (e: any) {
      await safeEdit(ctx, ctx.chat!.id, status.message_id, `❌ ${e.message}`);
    }
  });

  // Stickers
  bot.on('message:sticker', async (ctx) => {
    const pool = ['😄','👍','🔥','💯','✨','🤩','😎'];
    await ctx.reply(pool[Math.floor(Math.random() * pool.length)]);
  });

  // Main text handler
  bot.on('message:text', async (ctx) => {
    const uid  = ctx.from!.id;
    const text = ctx.message.text;
    if (text.startsWith('/')) return;

    ensureUser(uid, ctx.from?.username, ctx.from?.first_name);
    react(ctx); // Fire-and-forget reaction

    const mode = getVoiceMode(uid);
    await ctx.replyWithChatAction(mode === 'always' ? 'record_voice' : 'typing');

    try {
      const result = await execute(uid, text);
      await voiceReply(ctx, result.text, uid, false);
    } catch (e: any) {
      console.error('[text handler]', e);
      await ctx.reply(`❌ ${e.message}`);
    }
  });
}
