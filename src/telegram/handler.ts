import { Bot, Context, InputFile } from 'grammy';
import { config } from '../core/config';
import { db, ensureUser, setUserApiKey } from '../core/db';
import { execute, generateWebsite, generateTool } from '../agent/executor';
import { transcribeVoice } from '../tools/stt';
import { textToSpeech, VOICES, getUserVoicePref, setUserVoicePref, detectLang, stripMarkdownForTTS } from '../tools/tts';
import { webSearch } from '../tools/search';
import { getMemories, clearMemory, clearHistory } from '../agent/memory';
import { markdownToTelegramHtml, chunkTelegramText } from './format';
import { pickContextualReaction, resolveStatusReaction, shouldReact } from './reactions';

// ── Admin check ───────────────────────────────────────────────────────────────
function isAdmin(uid: number): boolean {
  return config.adminIds.includes(uid);
}

// ── Voice mode (OpenClaw: off/always/inbound/tagged mapped to never/always/auto) ──
function getVoiceMode(uid: number): 'auto' | 'always' | 'never' {
  const r = db.prepare("SELECT value FROM memory WHERE uid=? AND key='voice_mode'").get(uid) as any;
  return (r?.value as any) || 'auto';
}
function setVoiceMode(uid: number, mode: string) {
  db.prepare("INSERT INTO memory (uid,key,value) VALUES (?,'voice_mode',?) ON CONFLICT(uid,key) DO UPDATE SET value=excluded.value").run(uid, mode);
}
function modeLabel(m: string): string {
  return { auto: 'Авто (голос → голос)', always: 'Всегда голосом', never: 'Только текст' }[m] || m;
}

// ── React with status (OpenClaw status-reaction architecture) ─────────────────
async function setStatusReaction(ctx: Context, status: 'queued' | 'thinking' | 'done' | 'error' | 'tool' | 'web') {
  try {
    const emoji = resolveStatusReaction(status);
    await ctx.api.raw.setMessageReaction({
      chat_id: ctx.chat!.id,
      message_id: ctx.message!.message_id,
      reaction: [{ type: 'emoji', emoji }],
    });
  } catch { /* silently ignore */ }
}

async function react(ctx: Context) {
  if (!shouldReact(0.4)) return;
  try {
    const emoji = pickContextualReaction(ctx.message?.text || ctx.message?.caption || '');
    await ctx.api.raw.setMessageReaction({
      chat_id: ctx.chat!.id,
      message_id: ctx.message!.message_id,
      reaction: [{ type: 'emoji', emoji }],
    });
  } catch { /* silently ignore */ }
}

// ── HTML-mode send (OpenClaw: HTML parse_mode with Markdown fallback) ─────────
async function safeSend(ctx: Context, text: string, extra?: any): Promise<any> {
  const html = markdownToTelegramHtml(text);
  const chunks = chunkTelegramText(html);
  let lastMsg: any;
  for (const chunk of chunks) {
    try {
      lastMsg = await ctx.reply(chunk, { parse_mode: 'HTML', ...extra });
    } catch (e: any) {
      // Fallback: plain text
      try { lastMsg = await ctx.reply(text.replace(/[<>*_`\[\]]/g, ''), extra); } catch {}
    }
  }
  return lastMsg;
}

async function safeEdit(ctx: Context, chatId: number, msgId: number, text: string, extra?: any) {
  const html = markdownToTelegramHtml(text);
  try {
    return await ctx.api.editMessageText(chatId, msgId, html, { parse_mode: 'HTML', ...extra });
  } catch (e: any) {
    if (!e?.description?.includes('not modified')) {
      try { return await ctx.api.editMessageText(chatId, msgId, text.replace(/[<>*_`\[\]]/g, ''), extra); } catch {}
    }
  }
}

// ── File download ─────────────────────────────────────────────────────────────
async function downloadFile(fileId: string, bot: Bot): Promise<Buffer> {
  const file = await bot.api.getFile(fileId);
  const url  = `https://api.telegram.org/file/bot${config.botToken}/${file.file_path}`;
  const r    = await fetch(url);
  if (!r.ok) throw new Error(`Download failed: ${r.status}`);
  return Buffer.from(await r.arrayBuffer());
}

async function getImageB64(ctx: Context, bot: Bot): Promise<{ data: string; mime: string } | null> {
  let fileId: string | null = null;
  let mime = 'image/jpeg';
  if (ctx.message?.photo) {
    fileId = ctx.message.photo[ctx.message.photo.length - 1].file_id;
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

// ── Get user API keys for TTS ─────────────────────────────────────────────────
function getUserApiKeys(uid: number): Record<string, string> {
  const keys = db.prepare('SELECT provider, api_key FROM user_api_keys WHERE uid=?').all(uid) as any[];
  return Object.fromEntries(keys.map(k => [k.provider, k.api_key]));
}

// ── Voice reply (OpenClaw: smart TTS with mode awareness) ────────────────────
async function voiceReply(ctx: Context, text: string, uid: number, inboundAudio: boolean) {
  const mode = getVoiceMode(uid);
  const shouldVoice = mode === 'always' || (mode === 'auto' && inboundAudio);

  if (shouldVoice) {
    try {
      const userKeys = getUserApiKeys(uid);
      const tts = await textToSpeech(text, uid, userKeys);
      if (tts.success && tts.buffer) {
        await ctx.replyWithChatAction('record_voice');
        await ctx.replyWithVoice(new InputFile(tts.buffer, `nexum.${tts.format}`));
        return;
      }
    } catch { /* fall through to text */ }
  }

  await safeSend(ctx, text);
}

// ── PC Agent helpers ──────────────────────────────────────────────────────────
async function requireAgent(ctx: Context, app: any): Promise<boolean> {
  const uid = ctx.from!.id;
  if (!app.isAgentOnline?.(uid)) {
    await ctx.reply(
      '💻 <b>PC Agent офлайн</b>\n\nЗапусти агента на компьютере:\n<code>python nexum_agent.py</code>',
      { parse_mode: 'HTML' }
    );
    return false;
  }
  return true;
}

async function agentCmd(ctx: Context, app: any, cmd: object, statusText?: string) {
  if (!await requireAgent(ctx, app)) return;
  const uid = ctx.from!.id;
  const statusMsg = statusText ? await ctx.reply(statusText) : null;
  try {
    const result = await app.sendToAgent(uid, cmd);
    const out = result?.output || result?.result || result?.text || JSON.stringify(result || {});
    const text = String(out).slice(0, 3500);
    if (statusMsg) {
      await safeEdit(ctx, ctx.chat!.id, statusMsg.message_id, `<pre><code>${text.replace(/</g,'&lt;').replace(/>/g,'&gt;')}</code></pre>`);
    } else {
      await ctx.reply(`<pre><code>${text.replace(/</g,'&lt;').replace(/>/g,'&gt;')}</code></pre>`, { parse_mode: 'HTML' });
    }
  } catch (e: any) {
    const msg = `❌ ${e.message}`;
    if (statusMsg) await safeEdit(ctx, ctx.chat!.id, statusMsg.message_id, msg);
    else await ctx.reply(msg);
  }
}

// ── MAIN HANDLER SETUP ────────────────────────────────────────────────────────
export function setupHandlers(bot: Bot, app: any) {

  // /start
  bot.command('start', async (ctx) => {
    const uid = ctx.from!.id;
    ensureUser(uid, ctx.from?.username, ctx.from?.first_name);
    const name = ctx.from?.first_name || 'друг';
    await ctx.reply(
      `👋 Привет, <b>${name}</b>!\n\nЯ <b>NEXUM</b> — твой автономный AI-агент.\n\n` +
      `🤖 Отвечаю на любые вопросы\n🎙 Понимаю голосовые сообщения\n📸 Анализирую фото\n` +
      `🌐 Создаю сайты\n🛠 Разрабатываю инструменты\n📝 Заметки, задачи, привычки\n` +
      `💰 Финансы и аналитика\n⏰ Напоминания\n💻 Управляю ПК\n\nПросто напиши что нужно!`,
      {
        parse_mode: 'HTML',
        reply_markup: {
          inline_keyboard: [[
            config.webappUrl ? { text: '📱 Mini Apps', web_app: { url: `${config.webappUrl}/hub` } } : { text: '❓ Помощь', callback_data: 'cmd_help' },
            { text: '❓ Помощь', callback_data: 'cmd_help' },
          ]]
        }
      }
    );
  });

  // /help
  bot.command('help', async (ctx) => {
    await ctx.reply(
      `<b>NEXUM — Команды</b>\n\n` +
      `<b>Основное</b>\nПросто пиши — отвечу\nГолосовое — расшифрую + отвечу\nФото — опишу\n\n` +
      `<b>Создание</b>\n/website — создать сайт\n/newtool — создать инструмент\n/tools — мои инструменты\n\n` +
      `<b>Mini Apps</b>\n/apps — открыть приложения\n/notes /tasks /habits /finance\n\n` +
      `<b>Утилиты</b>\n/remind /search /memory /forget /clear\n/voice /voices /status\n\n` +
      `<b>PC Agent</b>\n/pc /link /screenshot /run /bgrun /bglist\n/sysinfo /ps /kill /files /clipboard\n/notify /window /http /browser /openapp\n/mouse /keyboard /hotkey /network\n\n` +
      `<b>API ключи</b>\n/setkey — добавить ключ\n/mykeys — мои ключи\n/delkey — удалить ключ`,
      { parse_mode: 'HTML' }
    );
  });

  // /apps
  bot.command('apps', async (ctx) => {
    if (!config.webappUrl) return ctx.reply('WEBAPP_URL не настроен');
    await ctx.reply('<b>📱 NEXUM Mini Apps</b>', {
      parse_mode: 'HTML',
      reply_markup: {
        inline_keyboard: [
          [{ text: '💰 Финансы', web_app: { url: `${config.webappUrl}/finance` } }, { text: '📝 Заметки', web_app: { url: `${config.webappUrl}/notes` } }],
          [{ text: '✅ Задачи',  web_app: { url: `${config.webappUrl}/tasks` } },   { text: '🎯 Привычки', web_app: { url: `${config.webappUrl}/habits` } }],
          [{ text: '🌐 Сайты',  web_app: { url: `${config.webappUrl}/sites` } },    { text: '🛠 Инструменты', web_app: { url: `${config.webappUrl}/tools-app` } }],
        ]
      }
    });
  });

  // /status
  bot.command('status', async (ctx) => {
    const uid = ctx.from!.id;
    const totalUsers = (db.prepare('SELECT COUNT(*) as c FROM users').get() as any).c;
    const totalNotes = (db.prepare('SELECT COUNT(*) as c FROM notes').get() as any).c;
    const totalTasks = (db.prepare('SELECT COUNT(*) as c FROM tasks').get() as any).c;
    const totalTools = (db.prepare('SELECT COUNT(*) as c FROM custom_tools WHERE active=1').get() as any).c;
    const totalSites = (db.prepare('SELECT COUNT(*) as c FROM websites').get() as any).c;
    const agentOnline = app.isAgentOnline?.(uid);
    const uptime = process.uptime();
    const hrs = Math.floor(uptime / 3600), mins = Math.floor((uptime % 3600) / 60);
    await ctx.reply(
      `📊 <b>NEXUM v11</b>\n\n` +
      `👥 Пользователей: ${totalUsers}\n📝 Заметок: ${totalNotes}\n✅ Задач: ${totalTasks}\n` +
      `🛠 Инструментов: ${totalTools}\n🌐 Сайтов: ${totalSites}\n` +
      `🤖 AI: активен\n💻 PC Agent: ${agentOnline ? '🟢 онлайн' : '🔴 офлайн'}\n⏱ Uptime: ${hrs}h ${mins}m`,
      { parse_mode: 'HTML' }
    );
  });

  // /website
  bot.command('website', async (ctx) => {
    const uid    = ctx.from!.id;
    const prompt = ctx.match?.trim();
    ensureUser(uid, ctx.from?.username, ctx.from?.first_name);
    if (!prompt) {
      return safeSend(ctx, `🌐 <b>Создание сайта</b>\n\nПример:\n<code>/website лендинг для фитнес-клуба</code>\n<code>/website портфолио разработчика</code>`);
    }
    const msg = await ctx.reply('🌐 Создаю сайт... <i>10–20 сек</i>', { parse_mode: 'HTML' });
    try {
      const site    = await generateWebsite(uid, prompt);
      const siteUrl = `${config.webappUrl}/site/${site.id}`;
      await safeEdit(ctx, ctx.chat!.id, msg.message_id, `✅ <b>Сайт готов!</b>\n\n<i>${site.name}</i>`, {
        reply_markup: { inline_keyboard: [[{ text: '🌐 Открыть', web_app: { url: siteUrl } }], [{ text: '🔗 Ссылка', callback_data: `site_link_${site.id}` }]] }
      });
    } catch (e: any) {
      await safeEdit(ctx, ctx.chat!.id, msg.message_id, `❌ ${e.message}`);
    }
  });

  // /newtool
  bot.command('newtool', async (ctx) => {
    const uid  = ctx.from!.id;
    const desc = ctx.match?.trim();
    ensureUser(uid, ctx.from?.username, ctx.from?.first_name);
    if (!desc) {
      const tools = db.prepare('SELECT * FROM custom_tools WHERE (uid=? OR uid=0) AND active=1').all(uid) as any[];
      const list  = tools.length ? tools.map(t => `• <b>${t.name}</b> — ${t.description} (×${t.usage_count})`).join('\n') : '• Пока нет';
      return ctx.reply(`🛠 <b>Самообучающиеся инструменты</b>\n\n<code>/newtool конвертер валют</code>\n<code>/newtool генератор паролей</code>\n\n<b>Текущие:</b>\n${list}`, { parse_mode: 'HTML' });
    }
    const msg = await ctx.reply('🔨 Создаю инструмент...');
    try {
      const toolData = await generateTool(uid, desc);
      const r = db.prepare('INSERT INTO custom_tools (uid,name,description,trigger_pattern,code,active) VALUES (?,?,?,?,?,1)')
        .run(uid, toolData.name, toolData.desc, toolData.trigger, toolData.code);
      await safeEdit(ctx, ctx.chat!.id, msg.message_id,
        `✅ <b>Инструмент создан!</b>\n\n🔧 <b>${toolData.name}</b>\n📝 ${toolData.desc}\n🎯 Триггер: <code>${toolData.trigger}</code>\n\n<i>Буду использовать его автоматически</i>`,
        { reply_markup: { inline_keyboard: [[{ text: '🧪 Тест', callback_data: `test_tool_${r.lastInsertRowid}` }], [{ text: '🗑 Удалить', callback_data: `del_tool_${r.lastInsertRowid}` }]] } }
      );
    } catch (e: any) {
      await safeEdit(ctx, ctx.chat!.id, msg.message_id, `❌ ${e.message}`);
    }
  });

  // /tools
  bot.command('tools', async (ctx) => {
    const uid   = ctx.from!.id;
    const tools = db.prepare('SELECT * FROM custom_tools WHERE (uid=? OR uid=0) AND active=1 ORDER BY usage_count DESC').all(uid) as any[];
    if (!tools.length) return safeSend(ctx, '🛠 Инструментов нет. Создай: <code>/newtool описание</code>');
    const list = tools.map((t, i) => `${i+1}. <b>${t.name}</b> — ${t.description}\n   <code>${t.trigger_pattern}</code> · ×${t.usage_count}`).join('\n\n');
    await ctx.reply(`🛠 <b>Инструменты (${tools.length})</b>\n\n${list}`, { parse_mode: 'HTML' });
  });

  // /notes
  bot.command('notes', async (ctx) => {
    const uid   = ctx.from!.id;
    const notes = db.prepare('SELECT * FROM notes WHERE uid=? ORDER BY pinned DESC, updated_at DESC LIMIT 10').all(uid) as any[];
    if (!notes.length) return ctx.reply('📝 Заметок нет. Просто напиши "запиши..."', {
      reply_markup: config.webappUrl ? { inline_keyboard: [[{ text: '📝 Открыть', web_app: { url: `${config.webappUrl}/notes` } }]] } : undefined
    });
    const text = notes.map((n, i) => `${n.pinned ? '📌 ' : ''}<b>${i+1}.</b> ${(n.title || n.content).slice(0, 50)}${(n.title || n.content).length > 50 ? '...' : ''}`).join('\n');
    await ctx.reply(`📝 <b>Заметки:</b>\n\n${text}`, {
      parse_mode: 'HTML',
      reply_markup: config.webappUrl ? { inline_keyboard: [[{ text: '📝 Все', web_app: { url: `${config.webappUrl}/notes` } }]] } : undefined
    });
  });

  // /tasks
  bot.command('tasks', async (ctx) => {
    const uid   = ctx.from!.id;
    const tasks = db.prepare(`SELECT * FROM tasks WHERE uid=? AND status!='done' ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, id DESC LIMIT 10`).all(uid) as any[];
    if (!tasks.length) return ctx.reply('✅ Задач нет. Скажи "создай задачу..."', {
      reply_markup: config.webappUrl ? { inline_keyboard: [[{ text: '✅ Открыть', web_app: { url: `${config.webappUrl}/tasks` } }]] } : undefined
    });
    const emoji: Record<string,string> = { critical:'🔴', high:'🟠', medium:'🟡', low:'🟢' };
    const text = tasks.map((t, i) => `${emoji[t.priority]||'⚪'} <b>${i+1}.</b> ${t.title}${t.project!=='General' ? ` <i>[${t.project}]</i>` : ''}`).join('\n');
    await ctx.reply(`✅ <b>Задачи:</b>\n\n${text}`, {
      parse_mode: 'HTML',
      reply_markup: config.webappUrl ? { inline_keyboard: [[{ text: '✅ Все', web_app: { url: `${config.webappUrl}/tasks` } }]] } : undefined
    });
  });

  // /habits
  bot.command('habits', async (ctx) => {
    const uid    = ctx.from!.id;
    const habits = db.prepare('SELECT * FROM habits WHERE uid=? ORDER BY streak DESC').all(uid) as any[];
    if (!habits.length) return ctx.reply('🎯 Привычек нет.', {
      reply_markup: config.webappUrl ? { inline_keyboard: [[{ text: '🎯 Добавить', web_app: { url: `${config.webappUrl}/habits` } }]] } : undefined
    });
    const today = new Date().toISOString().split('T')[0];
    const text  = habits.map(h => `${h.last_done?.startsWith(today) ? '✅' : '⬜'} ${h.emoji} <b>${h.name}</b> — 🔥${h.streak}`).join('\n');
    await ctx.reply(`🎯 <b>Привычки:</b>\n\n${text}`, {
      parse_mode: 'HTML',
      reply_markup: config.webappUrl ? { inline_keyboard: [[{ text: '🎯 Все', web_app: { url: `${config.webappUrl}/habits` } }]] } : undefined
    });
  });

  // /finance
  bot.command('finance', async (ctx) => {
    const uid   = ctx.from!.id;
    const month = new Date().toISOString().slice(0, 7);
    const stats = db.prepare(`SELECT type, SUM(amount) as total FROM finance WHERE uid=? AND created_at >= ? GROUP BY type`).all(uid, `${month}-01`) as any[];
    const income  = stats.find(s => s.type === 'income')?.total  || 0;
    const expense = stats.find(s => s.type === 'expense')?.total || 0;
    const bal     = income - expense;
    await ctx.reply(
      `💰 <b>Финансы (${month}):</b>\n\n📈 Доходы: <b>${income.toLocaleString('ru-RU')}</b>\n📉 Расходы: <b>${expense.toLocaleString('ru-RU')}</b>\n💵 Баланс: <b>${bal >= 0 ? '+' : ''}${bal.toLocaleString('ru-RU')}</b>`,
      { parse_mode: 'HTML', reply_markup: config.webappUrl ? { inline_keyboard: [[{ text: '💰 Детали', web_app: { url: `${config.webappUrl}/finance` } }]] } : undefined }
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
    if (!text) return ctx.reply('Пример: /remind через 30 минут позвонить маме');
    const result = await execute(ctx.from!.id, `напомни ${text}`);
    await safeSend(ctx, result.text);
  });

  // /memory
  bot.command('memory', async (ctx) => {
    const uid = ctx.from!.id;
    const mem = getMemories(uid).filter(m => !['voice_mode','voice_pref'].includes(m.key));
    if (!mem.length) return safeSend(ctx, '🧠 Память пуста. Расскажи мне о себе!');
    const text = mem.map(m => `• <b>${m.key}</b>: ${m.value}`).join('\n');
    await ctx.reply(`🧠 <b>Что я знаю о тебе:</b>\n\n${text}`, { parse_mode: 'HTML' });
  });

  bot.command('forget', async (ctx) => { clearMemory(ctx.from!.id); await ctx.reply('🗑 Память очищена'); });
  bot.command('clear',  async (ctx) => { clearHistory(ctx.from!.id); await ctx.reply('🗑 История очищена'); });

  // /voice
  bot.command('voice', async (ctx) => {
    const uid  = ctx.from!.id;
    const mode = getVoiceMode(uid);
    const arg  = ctx.match?.trim().toLowerCase();
    if (arg && ['auto','always','never'].includes(arg)) {
      setVoiceMode(uid, arg);
      return ctx.reply(`✅ Голосовой режим: <b>${modeLabel(arg)}</b>`, { parse_mode: 'HTML' });
    }
    await ctx.reply(`🎙 <b>Голосовой режим</b>\n\nТекущий: <b>${modeLabel(mode)}</b>`, {
      parse_mode: 'HTML',
      reply_markup: {
        inline_keyboard: [
          [{ text: (mode==='auto'   ?'✅ ':'')+'🔁 Авто',         callback_data: 'voice_auto' }],
          [{ text: (mode==='always' ?'✅ ':'')+'🔊 Всегда',        callback_data: 'voice_always' }],
          [{ text: (mode==='never'  ?'✅ ':'')+'💬 Только текст',  callback_data: 'voice_never' }],
        ]
      }
    });
  });

  bot.callbackQuery('voice_auto',   async (ctx) => { setVoiceMode(ctx.from.id,'auto');   await ctx.answerCallbackQuery(); await ctx.editMessageText(`🎙 Режим: <b>${modeLabel('auto')}</b>`,   { parse_mode:'HTML' }); });
  bot.callbackQuery('voice_always', async (ctx) => { setVoiceMode(ctx.from.id,'always'); await ctx.answerCallbackQuery(); await ctx.editMessageText(`🎙 Режим: <b>${modeLabel('always')}</b>`, { parse_mode:'HTML' }); });
  bot.callbackQuery('voice_never',  async (ctx) => { setVoiceMode(ctx.from.id,'never');  await ctx.answerCallbackQuery(); await ctx.editMessageText(`🎙 Режим: <b>${modeLabel('never')}</b>`,  { parse_mode:'HTML' }); });

  // /voices
  bot.command('voices', async (ctx) => {
    const uid  = ctx.from!.id;
    const pref = getUserVoicePref(uid);
    const btns = Object.entries(VOICES).map(([lang, d]) => ({ text: d.name, callback_data: `set_voice_${lang}_0` }));
    const rows: any[] = [];
    for (let i = 0; i < btns.length; i += 2) rows.push(btns.slice(i, i + 2));
    rows.push([{ text: '🌍 Авто', callback_data: 'set_voice_auto_0' }]);
    await ctx.reply(`🎙 <b>Выбор голоса</b>\n\nТекущий: <b>${pref.lang === 'auto' ? 'Авто' : (VOICES[pref.lang]?.name || pref.lang)}</b>`, {
      parse_mode: 'HTML', reply_markup: { inline_keyboard: rows }
    });
  });

  bot.callbackQuery(/^set_voice_(.+)_(\d+)$/, async (ctx) => {
    const lang = ctx.match![1], idx = parseInt(ctx.match![2]);
    setUserVoicePref(ctx.from.id, lang, idx);
    await ctx.answerCallbackQuery();
    const name = lang === 'auto' ? 'Авто' : (VOICES[lang]?.name || lang);
    await ctx.editMessageText(`✅ Голос: <b>${name}</b>`, { parse_mode: 'HTML' });
  });

  // /setkey — user API keys (OpenClaw pattern: user key first)
  bot.command('setkey', async (ctx) => {
    const args = ctx.match?.trim().split(' ');
    if (!args || args.length < 2) {
      return ctx.reply(
        `🔑 <b>Добавить API ключ</b>\n\n<code>/setkey groq sk-...</code>\n<code>/setkey gemini AI...</code>\n<code>/setkey openrouter sk-...</code>\n<code>/setkey deepseek sk-...</code>\n<code>/setkey claude sk-ant-...</code>\n<code>/setkey cerebras csk-...</code>\n<code>/setkey openai sk-...</code>\n<code>/setkey elevenlabs xi-...</code>\n\n<i>Твой ключ будет использоваться первым</i>`,
        { parse_mode: 'HTML' }
      );
    }
    const [provider, key] = args;
    const allowed = ['groq','gemini','openrouter','deepseek','claude','cerebras','together','openai','elevenlabs'];
    if (!allowed.includes(provider.toLowerCase())) return ctx.reply(`❌ Неизвестный провайдер. Доступны: ${allowed.join(', ')}`);
    setUserApiKey(ctx.from!.id, provider.toLowerCase(), key);
    await ctx.reply(`✅ Ключ для <b>${provider}</b> сохранён`, { parse_mode: 'HTML' });
  });

  bot.command('mykeys', async (ctx) => {
    const uid  = ctx.from!.id;
    const keys = db.prepare('SELECT provider, api_key FROM user_api_keys WHERE uid=?').all(uid) as any[];
    if (!keys.length) return safeSend(ctx, '🔑 Нет своих ключей. Добавь: <code>/setkey провайдер ключ</code>');
    const list = keys.map(k => `• <b>${k.provider}</b>: <code>${k.api_key.slice(0,8)}...</code>`).join('\n');
    await ctx.reply(`🔑 <b>Твои API ключи:</b>\n\n${list}\n\nУдалить: <code>/delkey провайдер</code>`, { parse_mode: 'HTML' });
  });

  bot.command('delkey', async (ctx) => {
    const provider = ctx.match?.trim();
    if (!provider) return ctx.reply('Укажи провайдер: /delkey groq');
    db.prepare('DELETE FROM user_api_keys WHERE uid=? AND provider=?').run(ctx.from!.id, provider);
    await ctx.reply(`✅ Ключ <b>${provider}</b> удалён`, { parse_mode: 'HTML' });
  });

  // ── PC Agent commands ──────────────────────────────────────────────────────
  bot.command('pc', async (ctx) => {
    const uid    = ctx.from!.id;
    const agent  = db.prepare('SELECT * FROM pc_agents WHERE uid=?').get(uid) as any;
    const online = app.isAgentOnline?.(uid);
    if (!agent) {
      return ctx.reply(
        `💻 <b>PC Agent не подключён</b>\n\n<pre><code>pip install websockets pyautogui pillow psutil requests pyperclip\npython nexum_agent.py</code></pre>\nЗатем: <code>/link КОД</code>`,
        { parse_mode: 'HTML' }
      );
    }
    const lastSeen = agent.last_seen ? new Date(agent.last_seen).toLocaleString('ru-RU') : 'неизвестно';
    await ctx.reply(
      `💻 <b>PC Agent</b>\n\n${online ? '🟢 Онлайн' : '🔴 Офлайн'}\n📱 ${agent.device_name || agent.platform || 'неизвестно'}\n🕐 Последний раз: ${lastSeen}\n\nКоманды: /screenshot /run /sysinfo /ps /kill\n/files /clipboard /notify /window /http\n/mouse /keyboard /hotkey /network /bgrun /bglist`,
      { parse_mode: 'HTML' }
    );
  });

  bot.command('link', async (ctx) => {
    const code = ctx.match?.trim().toUpperCase();
    if (!code) return ctx.reply('Укажи код: /link ABCDEF');
    const uid    = ctx.from!.id;
    const linked = app.linkAgent?.(code, uid);
    const lr     = db.prepare('SELECT * FROM link_codes WHERE code=?').get(code) as any;
    if (linked) {
      db.prepare(`INSERT INTO pc_agents (uid,device_id,device_name,platform,last_seen,status) VALUES (?,?,?,?,datetime('now'),'online') ON CONFLICT(uid) DO UPDATE SET device_id=excluded.device_id,device_name=excluded.device_name,platform=excluded.platform,last_seen=excluded.last_seen,status='online'`)
        .run(uid, lr?.device_id||'PC', lr?.device_id||'PC', lr?.platform||'Unknown');
      db.prepare('DELETE FROM link_codes WHERE code=?').run(code);
      await ctx.reply(`✅ <b>PC Agent подключён!</b>\n💻 ${lr?.platform||'Unknown'}\n\nПри следующем запуске привязка автоматическая.`, { parse_mode: 'HTML' });
    } else {
      if (!lr) return ctx.reply('❌ Код не найден или устарел');
      db.prepare(`INSERT INTO pc_agents (uid,device_name,platform,last_seen,status) VALUES (?,?,?,datetime('now'),'online') ON CONFLICT(uid) DO UPDATE SET device_name=excluded.device_name,platform=excluded.platform,last_seen=excluded.last_seen,status='online'`)
        .run(uid, lr.device_id||'PC', lr.platform||'Unknown');
      db.prepare('DELETE FROM link_codes WHERE code=?').run(code);
      await ctx.reply(`✅ <b>PC Agent привязан!</b>\n💻 ${lr.platform||'Unknown'}`, { parse_mode: 'HTML' });
    }
  });

  bot.command('screenshot', async (ctx) => {
    if (!await requireAgent(ctx, app)) return;
    const uid    = ctx.from!.id;
    const region = ctx.match?.trim()?.split(',').map(Number);
    const statusMsg = await ctx.reply('📸 Снимаю экран...');
    try {
      const result = await app.sendToAgent(uid, { type: 'screenshot', region: region?.length === 4 ? region : undefined });
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

  bot.command('run',     async (ctx) => { const c = ctx.match?.trim(); if (!c) return ctx.reply('Укажи команду: /run ls'); await agentCmd(ctx, app, { type:'run', command:c }, `⚙️ <code>${c?.slice(0,50)}</code>...`); });
  bot.command('bgrun',   async (ctx) => { const c = ctx.match?.trim(); if (!c) return ctx.reply('Укажи команду'); await agentCmd(ctx, app, { type:'run_background', command:c }, '🔄 Запускаю фоново...'); });
  bot.command('bglist',  async (ctx) => { await agentCmd(ctx, app, { type:'bg_list' }); });
  bot.command('bgstop',  async (ctx) => { const id = ctx.match?.trim(); if (!id) return ctx.reply('Укажи ID'); await agentCmd(ctx, app, { type:'bg_stop', proc_id:id }); });
  bot.command('sysinfo', async (ctx) => { await agentCmd(ctx, app, { type:'sysinfo' }, '📊 Собираю...'); });
  bot.command('ps',      async (ctx) => { const l = parseInt(ctx.match?.trim()||'15'); await agentCmd(ctx, app, { type:'processes', limit: isNaN(l)?15:l }, '🔍 Процессы...'); });
  bot.command('kill',    async (ctx) => { const t = ctx.match?.trim(); if (!t) return ctx.reply('Укажи PID или имя'); await agentCmd(ctx, app, { type:'kill_process', input:t }); });
  bot.command('network', async (ctx) => { await agentCmd(ctx, app, { type:'network' }, '🌐 Сеть...'); });
  bot.command('files',   async (ctx) => { const a = (ctx.match?.trim()||'').split(' '); await agentCmd(ctx, app, { type:'filesystem', op:a[0]||'list', path:a[1]||'~', content:a.slice(2).join(' ') }, `📁 ${a[0]||'list'}...`); });
  bot.command('clipboard', async (ctx) => { const a = (ctx.match?.trim()||'read').split(' '); await agentCmd(ctx, app, { type:'clipboard', op:a[0]==='write'?'write':'read', text:a.slice(1).join(' ') }); });
  bot.command('notify',  async (ctx) => { const [title, ...rest] = (ctx.match?.trim()||'').split('|'); await agentCmd(ctx, app, { type:'notify', title:title.trim()||'NEXUM', message:rest.join('|').trim()||title.trim() }); });
  bot.command('window',  async (ctx) => { const a = (ctx.match?.trim()||'list').split(' '); await agentCmd(ctx, app, { type:'window', op:a[0], window_id:a.slice(1).join(' ') }, a[0]==='list'?'🪟 Окна...':undefined); });
  bot.command('http',    async (ctx) => { const a = (ctx.match?.trim()||'').split(' '); const method=a[0]?.toUpperCase()||'GET', url=a[1]||''; if (!url) return ctx.reply('Укажи URL: /http GET https://api.github.com'); await agentCmd(ctx, app, { type:'http', method, url, body:a.slice(2).join(' ') }, `🌐 ${method} ${url.slice(0,40)}...`); });
  bot.command('browser', async (ctx) => { const u = ctx.match?.trim(); if (!u) return ctx.reply('Укажи URL'); await agentCmd(ctx, app, { type:'browser', input:u }); });
  bot.command('openapp', async (ctx) => { const n = ctx.match?.trim(); if (!n) return ctx.reply('Укажи приложение'); await agentCmd(ctx, app, { type:'open_app', input:n }); });
  bot.command('mouse',   async (ctx) => { const a = (ctx.match?.trim()||'position').split(' '); await agentCmd(ctx, app, { type:'mouse', action:a[0], x:parseInt(a[1]||'0'), y:parseInt(a[2]||'0'), text:a.slice(3).join(' ') }); });
  bot.command('keyboard',async (ctx) => { const t = ctx.match?.trim(); if (!t) return ctx.reply('Укажи текст'); await agentCmd(ctx, app, { type:'keyboard', action:'type', text:t }); });
  bot.command('hotkey',  async (ctx) => { const k = ctx.match?.trim(); if (!k) return ctx.reply('Укажи комбо: ctrl+c'); await agentCmd(ctx, app, { type:'keyboard', action:'hotkey', text:k }); });

  // ── Admin ──────────────────────────────────────────────────────────────────
  bot.command('admin', async (ctx) => {
    if (!isAdmin(ctx.from!.id)) return ctx.reply('❌ Нет доступа');
    const users = (db.prepare('SELECT COUNT(*) as c FROM users').get() as any).c;
    const msgs  = (db.prepare('SELECT COUNT(*) as c FROM conversations').get() as any).c;
    await ctx.reply(`🔐 <b>Admin Panel</b>\n\n👥 Users: ${users}\n💬 Messages: ${msgs}\n\n/stats /logs /users /broadcast`, { parse_mode: 'HTML' });
  });

  bot.command('users', async (ctx) => {
    if (!isAdmin(ctx.from!.id)) return ctx.reply('❌ Нет доступа');
    const users = db.prepare('SELECT uid, username, first_name, created_at FROM users ORDER BY created_at DESC LIMIT 20').all() as any[];
    const text  = users.map(u => `• <code>${u.uid}</code> ${u.first_name||''} @${u.username||'—'}`).join('\n');
    await ctx.reply(`👥 <b>Пользователи (${users.length}):</b>\n\n${text}`, { parse_mode: 'HTML' });
  });

  bot.command('broadcast', async (ctx) => {
    if (!isAdmin(ctx.from!.id)) return ctx.reply('❌ Нет доступа');
    const text = ctx.match?.trim();
    if (!text) return ctx.reply('Укажи текст: /broadcast Сообщение');
    const users = db.prepare('SELECT uid FROM users').all() as any[];
    let sent = 0, failed = 0;
    for (const u of users) {
      try { await bot.api.sendMessage(u.uid, text); sent++; } catch { failed++; }
    }
    await ctx.reply(`✅ Отправлено: ${sent} | Ошибок: ${failed}`);
  });

  // ── Callback queries ───────────────────────────────────────────────────────
  bot.callbackQuery('cmd_help', async (ctx) => {
    await ctx.answerCallbackQuery();
    await ctx.reply(`<b>NEXUM — Команды</b>\n\n/notes /tasks /habits /finance\n/website /newtool /tools\n/voice /remind /search\n/memory /forget /clear\n/apps /status /setkey`, { parse_mode: 'HTML' });
  });

  bot.callbackQuery(/^site_link_(\d+)$/, async (ctx) => {
    const url = `${config.webappUrl}/site/${ctx.match![1]}`;
    await ctx.answerCallbackQuery();
    await ctx.reply(`🔗 ${url}`);
  });

  bot.callbackQuery(/^del_tool_(\d+)$/, async (ctx) => {
    db.prepare('UPDATE custom_tools SET active=0 WHERE id=?').run(parseInt(ctx.match![1]));
    await ctx.answerCallbackQuery('🗑 Удалён');
    await ctx.editMessageText('🗑 Инструмент удалён');
  });

  bot.callbackQuery(/^test_tool_(\d+)$/, async (ctx) => {
    const tool = db.prepare('SELECT * FROM custom_tools WHERE id=?').get(parseInt(ctx.match![1])) as any;
    await ctx.answerCallbackQuery();
    if (tool) await ctx.reply(`🧪 Тест <b>${tool.name}</b>\n\nТриггер: <code>${tool.trigger_pattern}</code>\n\nНапиши сообщение с этим паттерном.`, { parse_mode: 'HTML' });
  });

  // ── Message handlers ───────────────────────────────────────────────────────

  bot.on('message:photo', async (ctx) => {
    const uid     = ctx.from!.id;
    ensureUser(uid, ctx.from?.username, ctx.from?.first_name);
    const caption = ctx.message.caption || '';
    await setStatusReaction(ctx, 'thinking');
    const status  = await ctx.reply('👁 Анализирую...');
    try {
      const img    = await getImageB64(ctx, bot);
      if (!img) throw new Error('Не удалось загрузить фото');
      const result = await execute(uid, caption || 'Что на изображении?', img.data, img.mime);
      await setStatusReaction(ctx, 'done');
      await safeEdit(ctx, ctx.chat!.id, status.message_id, result.text);
    } catch (e: any) {
      await setStatusReaction(ctx, 'error');
      await safeEdit(ctx, ctx.chat!.id, status.message_id, `❌ ${e.message}`);
    }
  });

  bot.on('message:document', async (ctx) => {
    const uid  = ctx.from!.id;
    ensureUser(uid, ctx.from?.username, ctx.from?.first_name);
    const mime = ctx.message.document?.mime_type || '';
    if (mime.startsWith('image/')) {
      await setStatusReaction(ctx, 'thinking');
      const status = await ctx.reply('👁 Анализирую...');
      try {
        const img = await getImageB64(ctx, bot);
        if (!img) throw new Error('Не удалось загрузить');
        const result = await execute(uid, ctx.message.caption || 'Что на изображении?', img.data, img.mime);
        await setStatusReaction(ctx, 'done');
        await safeEdit(ctx, ctx.chat!.id, status.message_id, result.text);
      } catch (e: any) {
        await setStatusReaction(ctx, 'error');
        await safeEdit(ctx, ctx.chat!.id, status.message_id, `❌ ${e.message}`);
      }
      return;
    }
    await safeSend(ctx, `📎 Файл: <b>${ctx.message.document.file_name || 'файл'}</b>\n<i>Поддержка документов скоро</i>`);
  });

  bot.on('message:voice', async (ctx) => {
    const uid    = ctx.from!.id;
    ensureUser(uid, ctx.from?.username, ctx.from?.first_name);
    await setStatusReaction(ctx, 'queued');
    const status = await ctx.reply('🎙 Слушаю...');
    try {
      const buf        = await downloadFile(ctx.message.voice.file_id, bot);
      const transcript = await transcribeVoice(buf, 'voice.ogg');
      await setStatusReaction(ctx, 'thinking');
      await safeEdit(ctx, ctx.chat!.id, status.message_id, `🎙 <i>${transcript}</i>\n\n⏳ Думаю...`);
      const result = await execute(uid, transcript);
      await setStatusReaction(ctx, 'done');
      const mode = getVoiceMode(uid);
      if (mode !== 'never') {
        await ctx.api.deleteMessage(ctx.chat!.id, status.message_id).catch(() => {});
        try {
          await ctx.replyWithChatAction('record_voice');
          const userKeys = getUserApiKeys(uid);
          const tts = await textToSpeech(result.text, uid, userKeys);
          if (tts.success && tts.buffer) {
            await ctx.replyWithVoice(new InputFile(tts.buffer, `nexum.${tts.format}`), {
              caption: `<i>${transcript.slice(0, 100)}${transcript.length > 100 ? '...' : ''}</i>`,
              parse_mode: 'HTML',
            });
            return;
          }
        } catch {}
      }
      await safeEdit(ctx, ctx.chat!.id, status.message_id, `🎙 <i>${transcript}</i>\n\n${markdownToTelegramHtml(result.text)}`);
    } catch (e: any) {
      await setStatusReaction(ctx, 'error');
      await safeEdit(ctx, ctx.chat!.id, status.message_id, `❌ ${e.message}`).catch(() => ctx.reply(`❌ ${e.message}`));
    }
  });

  bot.on('message:audio', async (ctx) => {
    const uid    = ctx.from!.id;
    ensureUser(uid, ctx.from?.username, ctx.from?.first_name);
    const status = await ctx.reply('🎵 Обрабатываю...');
    try {
      const buf        = await downloadFile(ctx.message.audio.file_id, bot);
      const transcript = await transcribeVoice(buf, 'audio.mp3');
      await safeEdit(ctx, ctx.chat!.id, status.message_id, `🎵 <i>${transcript}</i>\n\n⏳...`);
      const result = await execute(uid, transcript);
      await safeEdit(ctx, ctx.chat!.id, status.message_id, `🎵 <i>${transcript}</i>\n\n${markdownToTelegramHtml(result.text)}`);
    } catch (e: any) {
      await safeEdit(ctx, ctx.chat!.id, status.message_id, `❌ ${e.message}`);
    }
  });

  bot.on('message:video_note', async (ctx) => {
    const uid    = ctx.from!.id;
    ensureUser(uid, ctx.from?.username, ctx.from?.first_name);
    await setStatusReaction(ctx, 'queued');
    const status = await ctx.reply('🎥 Обрабатываю видео...');
    try {
      const buf        = await downloadFile(ctx.message.video_note.file_id, bot);
      const transcript = await transcribeVoice(buf, 'video.mp4');
      await setStatusReaction(ctx, 'thinking');
      await safeEdit(ctx, ctx.chat!.id, status.message_id, `🎥 <i>${transcript}</i>\n\n⏳...`);
      const result = await execute(uid, transcript);
      await setStatusReaction(ctx, 'done');
      await safeEdit(ctx, ctx.chat!.id, status.message_id, `🎥 <i>${transcript}</i>\n\n${markdownToTelegramHtml(result.text)}`);
    } catch (e: any) {
      await setStatusReaction(ctx, 'error');
      await safeEdit(ctx, ctx.chat!.id, status.message_id, `❌ ${e.message}`);
    }
  });

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

    // Status reaction: queued (OpenClaw pattern)
    await setStatusReaction(ctx, 'queued');

    const mode = getVoiceMode(uid);
    await ctx.replyWithChatAction(mode === 'always' ? 'record_voice' : 'typing');

    try {
      // Status: thinking
      await setStatusReaction(ctx, 'thinking');
      const result = await execute(uid, text);

      // Status: done
      await setStatusReaction(ctx, 'done');

      await voiceReply(ctx, result.text, uid, false);
    } catch (e: any) {
      await setStatusReaction(ctx, 'error');
      console.error('[text handler]', e);
      await ctx.reply(`❌ ${e.message}`);
    }
  });

  // Catch contextual reactions (non-command messages)
  bot.on('message', async (ctx) => {
    if (!ctx.message?.text || ctx.message.text.startsWith('/')) return;
    react(ctx); // Fire-and-forget
  });
}
