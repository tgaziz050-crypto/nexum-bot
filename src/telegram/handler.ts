import { Bot, Context, InputFile } from 'grammy';
import { config } from '../core/config';
import { db, ensureUser, setUserApiKey } from '../core/db';
import { execute, generateWebsite, generateTool } from '../agent/executor';
import { transcribeVoice } from '../tools/stt';
import { textToSpeech, VOICES, getUserVoicePref, setUserVoicePref } from '../tools/tts';
import { webSearch } from '../tools/search';
import { getMemories, clearMemory, clearHistory } from '../agent/memory';
import { markdownToTelegramHtml, splitTelegramMessage, stripMarkdownForPlainText } from './format';
import { pendingApprovals, requestApproval } from '../apps/server';

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

// ── OpenClaw-style reactions ──────────────────────────────────────────────────
const ACK_REACTION = '👀';
const REACTION_MAP: Array<{ pattern: RegExp; emoji: string }> = [
  { pattern: /спасибо|thank|merci|danke|gracias|rahmat/i, emoji: '🙏' },
  { pattern: /люблю|love|amor|liebe/i,                    emoji: '❤' },
  { pattern: /помоги|help me/i,                           emoji: '👌' },
  { pattern: /привет|hello|hi |hey |salom/i,              emoji: '👋' },
  { pattern: /круто|отлично|awesome|cool|zo'r/i,          emoji: '🔥' },
  { pattern: /смешно|хаха|lol|funny/i,                    emoji: '😂' },
  { pattern: /грустно|sad|жаль/i,                         emoji: '🥺' },
  { pattern: /деньги|финанс|money|cash/i,                 emoji: '💰' },
  { pattern: /код|code|программ/i,                        emoji: '🖥' },
  { pattern: /вопрос|question/i,                          emoji: '🤔' },
  { pattern: /ошибка|error|баг|bug/i,                     emoji: '🤯' },
  { pattern: /срочно|urgent/i,                            emoji: '⚡' },
];
function pickReaction(text: string): string {
  for (const { pattern, emoji } of REACTION_MAP) if (pattern.test(text)) return emoji;
  const pool = ['👍','🔥','❤','⚡','🎉','👏','✨','💪','🤙','😎'];
  return pool[Math.floor(Math.random() * pool.length)];
}
async function ackReact(ctx: Context) {
  try { await ctx.api.raw.setMessageReaction({ chat_id: ctx.chat!.id, message_id: ctx.message!.message_id, reaction: [{ type: 'emoji', emoji: ACK_REACTION }] }); } catch {}
}
async function semanticReact(ctx: Context) {
  try {
    if (Math.random() > 0.5) return;
    const emoji = pickReaction(ctx.message?.text || '');
    await ctx.api.raw.setMessageReaction({ chat_id: ctx.chat!.id, message_id: ctx.message!.message_id, reaction: [{ type: 'emoji', emoji: emoji as any }] });
  } catch {}
}

// ── OpenClaw-style send helpers with HTML + chunking ──────────────────────────
async function safeSend(ctx: Context, text: string, extra?: any): Promise<any> {
  const html   = markdownToTelegramHtml(text);
  const chunks = splitTelegramMessage(html, 4000);
  let lastMsg: any = null;
  for (const chunk of chunks) {
    try { lastMsg = await ctx.reply(chunk, { parse_mode: 'HTML', ...extra }); }
    catch { try { lastMsg = await ctx.reply(stripMarkdownForPlainText(text), extra); } catch {} }
  }
  return lastMsg;
}
async function safeEdit(ctx: Context, chatId: number, msgId: number, text: string, extra?: any) {
  const html = markdownToTelegramHtml(text);
  try { return await ctx.api.editMessageText(chatId, msgId, html, { parse_mode: 'HTML', ...extra }); }
  catch (e: any) {
    if (!e?.description?.includes('not modified')) {
      try { return await ctx.api.editMessageText(chatId, msgId, stripMarkdownForPlainText(text), extra); } catch {}
    }
  }
}
async function safeSendToUser(bot: Bot, uid: number, text: string, extra?: any) {
  const html   = markdownToTelegramHtml(text);
  const chunks = splitTelegramMessage(html, 4000);
  for (const chunk of chunks) {
    try { await bot.api.sendMessage(uid, chunk, { parse_mode: 'HTML', ...extra }); }
    catch { try { await bot.api.sendMessage(uid, stripMarkdownForPlainText(text), extra); } catch {} }
  }
}

async function showTyping(ctx: Context, voice = false) {
  try { await ctx.replyWithChatAction(voice ? 'record_voice' : 'typing'); } catch {}
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
  let fileId: string | null = null, mime = 'image/jpeg';
  if (ctx.message?.photo) { const p = ctx.message.photo; fileId = p[p.length-1].file_id; }
  else if (ctx.message?.document?.mime_type?.startsWith('image/')) { fileId = ctx.message.document.file_id; mime = ctx.message.document.mime_type; }
  else if (ctx.message?.sticker) { fileId = ctx.message.sticker.file_id; mime = 'image/webp'; }
  if (!fileId) return null;
  const buf = await downloadFile(fileId, bot);
  return { data: buf.toString('base64'), mime };
}

// ── Voice reply ───────────────────────────────────────────────────────────────
async function voiceReply(ctx: Context, text: string, uid: number, isVoice: boolean) {
  const mode  = getVoiceMode(uid);
  const speak = mode === 'always' || (mode === 'auto' && isVoice);
  if (!speak) { await safeSend(ctx, text); return; }
  try {
    await ctx.replyWithChatAction('record_voice');
    const tts = await textToSpeech(text, uid);
    await ctx.replyWithVoice(new InputFile(tts.buffer, `nexum.${tts.format}`));
  } catch { await safeSend(ctx, text); }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function isAdmin(uid: number) { return config.adminIds.includes(uid); }

// ── OpenClaw-style approval check for dangerous PC commands ───────────────────
const DANGEROUS_PATTERNS = [
  /rm\s+-rf/i, /del\s+\/[sf]/i, /format\s+[a-z]:/i,
  /shutdown|reboot|halt|poweroff/i,
  /reg\s+delete/i, /del\s+.*system/i,
  /mkfs|dd\s+if=/i, /chmod\s+777/i,
  /sudo\s+rm|sudo\s+del/i,
];
function isDangerous(cmd: string): boolean {
  return DANGEROUS_PATTERNS.some(p => p.test(cmd));
}

async function requireAgent(ctx: Context, app: any): Promise<boolean> {
  const uid    = ctx.from!.id;
  const online = app.isAgentOnline?.(uid);
  if (!online) {
    await safeSend(ctx,
      `💻 **PC Agent офлайн**\n\nЗапусти агент на компьютере:\n\`\`\`\npip install websockets pyautogui pillow psutil requests pyperclip\npython nexum_agent.py\n\`\`\`\nЗатем: \`/link КОД\``
    );
    return false;
  }
  return true;
}

async function agentCmd(ctx: Context, app: any, bot: Bot, msg: object & { type: string; command?: string }, statusText?: string) {
  if (!await requireAgent(ctx, app)) return;
  const uid = ctx.from!.id;

  // OpenClaw-style: check if command is dangerous, request approval
  const cmd = (msg as any).command || '';
  if (cmd && isDangerous(cmd)) {
    const approvalMsg = await safeSend(ctx,
      `⚠️ **Опасная команда**\n\n\`${cmd}\`\n\nОтправил запрос на подтверждение администратору...`
    );
    const approved = await requestApproval({ bot, uid, command: cmd, type: 'dangerous' });
    if (!approved) {
      await safeSend(ctx, `❌ **Команда отклонена** администратором`);
      return;
    }
    await safeSend(ctx, `✅ Одобрено. Выполняю...`);
  }

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
export function setupHandlers(bot: Bot, app: any) {

  // /start
  bot.command('start', async (ctx) => {
    const uid = ctx.from!.id;
    ensureUser(uid, ctx.from?.username, ctx.from?.first_name);
    const name = ctx.from?.first_name || 'друг';
    await safeSend(ctx,
      `👋 Привет, **${name}**!\n\nЯ **NEXUM** — твой автономный AI-агент.\n\n` +
      `🤖 Отвечаю на любые вопросы\n🎙 Понимаю голосовые сообщения\n📸 Анализирую фото\n` +
      `🌐 Создаю готовые сайты\n🛠 Разрабатываю инструменты\n📝 Заметки, задачи, привычки\n` +
      `💰 Финансы\n⏰ Напоминания\n💻 Управляю твоим ПК\n\nПросто напиши что нужно!`,
      { reply_markup: { inline_keyboard: [[
        ...(config.webappUrl ? [{ text: '📱 Mini Apps', web_app: { url: `${config.webappUrl}/hub` } }] : []),
        { text: '❓ Помощь', callback_data: 'cmd_help' },
      ]] } }
    );
  });

  // /help
  bot.command('help', async (ctx) => {
    await safeSend(ctx,
      `**NEXUM — Команды**\n\n` +
      `**Основное:** просто пиши / голосовые / фото\n\n` +
      `**Создание:** /website /newtool /tools\n\n` +
      `**Mini Apps:** /apps /notes /tasks /habits /finance\n\n` +
      `**Утилиты:** /remind /search /memory /forget /clear /voice /voices /status\n\n` +
      `**PC Agent:** /pcagent /link /screenshot /run /bgrun /bglist\n` +
      `/sysinfo /ps /kill /files /clipboard /notify\n` +
      `/window /http /browser /openapp /mouse /keyboard /hotkey /network\n\n` +
      `**Ключи:** /setkey /mykeys /delkey`
    );
  });

  // /apps
  bot.command('apps', async (ctx) => {
    if (!config.webappUrl) return ctx.reply('WEBAPP_URL не настроен');
    await ctx.reply('📱 <b>NEXUM Mini Apps</b>', {
      parse_mode: 'HTML',
      reply_markup: { inline_keyboard: [
        [{ text: '💰 Финансы', web_app: { url: `${config.webappUrl}/finance` } }, { text: '📝 Заметки', web_app: { url: `${config.webappUrl}/notes` } }],
        [{ text: '✅ Задачи',  web_app: { url: `${config.webappUrl}/tasks` } },   { text: '🎯 Привычки', web_app: { url: `${config.webappUrl}/habits` } }],
        [{ text: '🌐 Сайты',  web_app: { url: `${config.webappUrl}/sites` } },    { text: '🛠 Инструменты', web_app: { url: `${config.webappUrl}/tools-app` } }],
      ] }
    });
  });

  // /status
  bot.command('status', async (ctx) => {
    const uid         = ctx.from!.id;
    const totalUsers  = (db.prepare('SELECT COUNT(*) as c FROM users').get() as any).c;
    const totalNotes  = (db.prepare('SELECT COUNT(*) as c FROM notes').get() as any).c;
    const totalTasks  = (db.prepare('SELECT COUNT(*) as c FROM tasks').get() as any).c;
    const agentOnline = app.isAgentOnline?.(uid);
    const uptime = process.uptime();
    await safeSend(ctx,
      `📊 **NEXUM v12**\n\n👥 ${totalUsers} пользователей\n📝 ${totalNotes} заметок\n✅ ${totalTasks} задач\n` +
      `💻 PC Agent: ${agentOnline ? '🟢 онлайн' : '🔴 офлайн'}\n⏱ Uptime: ${Math.floor(uptime/3600)}h ${Math.floor((uptime%3600)/60)}m`
    );
  });

  // /website
  bot.command('website', async (ctx) => {
    const uid = ctx.from!.id; const prompt = ctx.match?.trim();
    ensureUser(uid, ctx.from?.username, ctx.from?.first_name);
    if (!prompt) return safeSend(ctx, `🌐 **Создание сайта**\n\nПример:\n/website лендинг для фитнес-клуба\n/website портфолио разработчика`);
    const msg = await ctx.reply('🌐 Создаю сайт... <i>10–20 сек</i>', { parse_mode: 'HTML' });
    try {
      const site = await generateWebsite(uid, prompt);
      const url  = `${config.webappUrl}/site/${site.id}`;
      await safeEdit(ctx, ctx.chat!.id, msg.message_id, `✅ **Сайт готов!**\n\n_${site.name}_`, {
        reply_markup: { inline_keyboard: [[{ text: '🌐 Открыть', web_app: { url } }], [{ text: '🔗 Ссылка', callback_data: `site_link_${site.id}` }]] }
      });
    } catch (e: any) { await safeEdit(ctx, ctx.chat!.id, msg.message_id, `❌ ${e.message}`); }
  });

  // /newtool
  bot.command('newtool', async (ctx) => {
    const uid = ctx.from!.id; const desc = ctx.match?.trim();
    ensureUser(uid, ctx.from?.username, ctx.from?.first_name);
    if (!desc) {
      const tools = db.prepare('SELECT * FROM custom_tools WHERE (uid=? OR uid=0) AND active=1').all(uid) as any[];
      const list  = tools.length ? tools.map(t => `• **${t.name}** — ${t.description} (×${t.usage_count})`).join('\n') : '• Пока нет';
      return safeSend(ctx, `🛠 **Инструменты**\n\n/newtool конвертер валют\n/newtool генератор паролей\n\n**Текущие:**\n${list}`);
    }
    const msg = await ctx.reply('🔨 Создаю инструмент...');
    try {
      const toolData = await generateTool(uid, desc);
      const r = db.prepare('INSERT INTO custom_tools (uid,name,description,trigger_pattern,code,active) VALUES (?,?,?,?,?,1)')
        .run(uid, toolData.name, toolData.desc, toolData.trigger, toolData.code);
      await safeEdit(ctx, ctx.chat!.id, msg.message_id,
        `✅ **Инструмент создан!**\n\n🔧 **${toolData.name}**\n📝 ${toolData.desc}\n🎯 Триггер: \`${toolData.trigger}\``,
        { reply_markup: { inline_keyboard: [[{ text: '🧪 Тест', callback_data: `test_tool_${r.lastInsertRowid}` }], [{ text: '🗑 Удалить', callback_data: `del_tool_${r.lastInsertRowid}` }]] } }
      );
    } catch (e: any) { await safeEdit(ctx, ctx.chat!.id, msg.message_id, `❌ ${e.message}`); }
  });

  // /tools
  bot.command('tools', async (ctx) => {
    const uid   = ctx.from!.id;
    const tools = db.prepare('SELECT * FROM custom_tools WHERE (uid=? OR uid=0) AND active=1 ORDER BY usage_count DESC').all(uid) as any[];
    if (!tools.length) return safeSend(ctx, `🛠 Пока нет. Создай: /newtool описание`);
    const list = tools.map((t, i) => `${i+1}. **${t.name}** — ${t.description} (\`${t.trigger_pattern}\` ×${t.usage_count})`).join('\n');
    await safeSend(ctx, `🛠 **Инструменты (${tools.length})**\n\n${list}`);
  });

  // /notes /tasks /habits /finance
  bot.command('notes', async (ctx) => {
    const uid   = ctx.from!.id;
    const notes = db.prepare('SELECT * FROM notes WHERE uid=? ORDER BY pinned DESC, updated_at DESC LIMIT 10').all(uid) as any[];
    if (!notes.length) return ctx.reply('📝 Заметок нет.', { reply_markup: config.webappUrl ? { inline_keyboard: [[{ text: '📝 Открыть', web_app: { url: `${config.webappUrl}/notes` } }]] } : undefined });
    const text  = notes.map((n, i) => `${n.pinned?'📌 ':''}${i+1}. ${(n.title||n.content).slice(0,60)}`).join('\n');
    await safeSend(ctx, `📝 **Заметки:**\n\n${text}`, { reply_markup: config.webappUrl ? { inline_keyboard: [[{ text: '📝 Все', web_app: { url: `${config.webappUrl}/notes` } }]] } : undefined });
  });

  bot.command('tasks', async (ctx) => {
    const uid   = ctx.from!.id;
    const tasks = db.prepare(`SELECT * FROM tasks WHERE uid=? AND status!='done' ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, id DESC LIMIT 10`).all(uid) as any[];
    if (!tasks.length) return ctx.reply('✅ Задач нет.', { reply_markup: config.webappUrl ? { inline_keyboard: [[{ text: '✅ Открыть', web_app: { url: `${config.webappUrl}/tasks` } }]] } : undefined });
    const em: Record<string,string> = { critical:'🔴', high:'🟠', medium:'🟡', low:'🟢' };
    const text = tasks.map((t, i) => `${em[t.priority]||'⚪'} ${i+1}. ${t.title}${t.project!=='General' ? ` [${t.project}]` : ''}`).join('\n');
    await safeSend(ctx, `✅ **Задачи:**\n\n${text}`, { reply_markup: config.webappUrl ? { inline_keyboard: [[{ text: '✅ Все', web_app: { url: `${config.webappUrl}/tasks` } }]] } : undefined });
  });

  bot.command('habits', async (ctx) => {
    const uid    = ctx.from!.id;
    const habits = db.prepare('SELECT * FROM habits WHERE uid=? ORDER BY streak DESC').all(uid) as any[];
    if (!habits.length) return ctx.reply('🎯 Привычек нет.', { reply_markup: config.webappUrl ? { inline_keyboard: [[{ text: '🎯 Добавить', web_app: { url: `${config.webappUrl}/habits` } }]] } : undefined });
    const today  = new Date().toISOString().split('T')[0];
    const text   = habits.map(h => `${h.last_done?.startsWith(today)?'✅':'⬜'} ${h.emoji} **${h.name}** 🔥${h.streak}`).join('\n');
    await safeSend(ctx, `🎯 **Привычки:**\n\n${text}`, { reply_markup: config.webappUrl ? { inline_keyboard: [[{ text: '🎯 Все', web_app: { url: `${config.webappUrl}/habits` } }]] } : undefined });
  });

  bot.command('finance', async (ctx) => {
    const uid   = ctx.from!.id;
    const month = new Date().toISOString().slice(0,7);
    const stats = db.prepare(`SELECT type, SUM(amount) as total FROM finance WHERE uid=? AND created_at >= ? GROUP BY type`).all(uid, `${month}-01`) as any[];
    const inc = stats.find(s => s.type==='income')?.total || 0;
    const exp = stats.find(s => s.type==='expense')?.total || 0;
    await safeSend(ctx,
      `💰 **Финансы (${month}):**\n\n📈 Доходы: **${inc.toLocaleString('ru-RU')}**\n📉 Расходы: **${exp.toLocaleString('ru-RU')}**\n💵 Баланс: **${(inc-exp >= 0?'+':'')+(inc-exp).toLocaleString('ru-RU')}**`,
      { reply_markup: config.webappUrl ? { inline_keyboard: [[{ text: '💰 Детали', web_app: { url: `${config.webappUrl}/finance` } }]] } : undefined }
    );
  });

  // /search /remind /memory /forget /clear
  bot.command('search', async (ctx) => {
    const q = ctx.match?.trim(); if (!q) return ctx.reply('Укажи запрос: /search что искать');
    const msg = await ctx.reply('🔍 Ищу...');
    try { await safeEdit(ctx, ctx.chat!.id, msg.message_id, await webSearch(q)); }
    catch (e: any) { await safeEdit(ctx, ctx.chat!.id, msg.message_id, `❌ ${e.message}`); }
  });
  bot.command('remind', async (ctx) => {
    const text = ctx.match?.trim(); if (!text) return ctx.reply('Пример: /remind через 30 минут позвонить маме');
    const result = await execute(ctx.from!.id, `напомни ${text}`);
    await safeSend(ctx, result.text);
  });
  bot.command('memory', async (ctx) => {
    const uid = ctx.from!.id;
    const mem = getMemories(uid).filter(m => !['voice_mode','voice_lang','voice_idx'].includes(m.key));
    if (!mem.length) return safeSend(ctx, '🧠 Память пуста. Расскажи мне о себе!');
    await safeSend(ctx, `🧠 **Что я знаю о тебе:**\n\n${mem.map(m => `• **${m.key}**: ${m.value}`).join('\n')}`);
  });
  bot.command('forget', async (ctx) => { clearMemory(ctx.from!.id); await ctx.reply('🗑 Память очищена'); });
  bot.command('clear',  async (ctx) => { clearHistory(ctx.from!.id); await ctx.reply('🗑 История очищена'); });

  // /voice /voices
  bot.command('voice', async (ctx) => {
    const uid = ctx.from!.id, mode = getVoiceMode(uid), arg = ctx.match?.trim().toLowerCase();
    if (arg && ['auto','always','never'].includes(arg)) { setVoiceMode(uid, arg); return ctx.reply(`✅ Голосовой режим: <b>${modeLabel(arg)}</b>`, { parse_mode:'HTML' }); }
    await ctx.reply(`🎙 <b>Голосовой режим</b>\n\nТекущий: <b>${modeLabel(mode)}</b>`, { parse_mode:'HTML', reply_markup: { inline_keyboard: [
      [{ text: (mode==='auto'?'✅ ':'')+'🔁 Авто',          callback_data: 'voice_auto' }],
      [{ text: (mode==='always'?'✅ ':'')+'🔊 Всегда голосом', callback_data: 'voice_always' }],
      [{ text: (mode==='never'?'✅ ':'')+'💬 Только текст',   callback_data: 'voice_never' }],
    ] } });
  });
  bot.callbackQuery('voice_auto',   async (ctx) => { setVoiceMode(ctx.from.id,'auto');   await ctx.answerCallbackQuery(); await ctx.editMessageText(`🎙 Режим: <b>${modeLabel('auto')}</b>`,   { parse_mode:'HTML' }); });
  bot.callbackQuery('voice_always', async (ctx) => { setVoiceMode(ctx.from.id,'always'); await ctx.answerCallbackQuery(); await ctx.editMessageText(`🎙 Режим: <b>${modeLabel('always')}</b>`, { parse_mode:'HTML' }); });
  bot.callbackQuery('voice_never',  async (ctx) => { setVoiceMode(ctx.from.id,'never');  await ctx.answerCallbackQuery(); await ctx.editMessageText(`🎙 Режим: <b>${modeLabel('never')}</b>`,  { parse_mode:'HTML' }); });

  bot.command('voices', async (ctx) => {
    const uid = ctx.from!.id, pref = getUserVoicePref(uid);
    const btns = Object.entries(VOICES).slice(0,20).map(([lang, d]) => ({ text: (d as any).name, callback_data: `set_voice_${lang}_0` }));
    const rows: any[] = []; for (let i=0; i<btns.length; i+=2) rows.push(btns.slice(i,i+2));
    rows.push([{ text: '🌍 Авто', callback_data: 'set_voice_auto_0' }]);
    await ctx.reply(`🎙 <b>Голос</b>\n\nТекущий: <b>${pref.lang==='auto'?'Авто':((VOICES as any)[pref.lang]?.name||pref.lang)}</b>`, { parse_mode:'HTML', reply_markup: { inline_keyboard: rows } });
  });
  bot.callbackQuery(/^set_voice_(.+)_(\d+)$/, async (ctx) => {
    const lang = ctx.match![1]; setUserVoicePref(ctx.from.id, lang, parseInt(ctx.match![2]));
    await ctx.answerCallbackQuery(); await ctx.editMessageText(`✅ Голос: <b>${lang==='auto'?'Авто':((VOICES as any)[lang]?.name||lang)}</b>`, { parse_mode:'HTML' });
  });

  // /setkey /mykeys /delkey
  bot.command('setkey', async (ctx) => {
    const args = ctx.match?.trim().split(' ');
    if (!args || args.length < 2) return safeSend(ctx, `🔑 **API ключи**\n\n/setkey groq sk-...\n/setkey gemini AI...\n/setkey openrouter sk-...\n/setkey deepseek sk-...\n/setkey claude sk-ant-...\n/setkey cerebras csk-...`);
    const [provider, key] = args;
    const allowed = ['groq','gemini','openrouter','deepseek','claude','cerebras','together'];
    if (!allowed.includes(provider.toLowerCase())) return ctx.reply(`❌ Доступны: ${allowed.join(', ')}`);
    setUserApiKey(ctx.from!.id, provider.toLowerCase(), key);
    await ctx.reply(`✅ Ключ для <b>${provider}</b> сохранён`, { parse_mode:'HTML' });
  });
  bot.command('mykeys', async (ctx) => {
    const keys = db.prepare('SELECT provider, api_key FROM user_api_keys WHERE uid=?').all(ctx.from!.id) as any[];
    if (!keys.length) return safeSend(ctx, '🔑 Нет ключей. Добавь: /setkey провайдер ключ');
    await safeSend(ctx, `🔑 **Твои ключи:**\n\n${keys.map(k=>`• **${k.provider}**: \`${k.api_key.slice(0,8)}...\``).join('\n')}`);
  });
  bot.command('delkey', async (ctx) => {
    const p = ctx.match?.trim(); if (!p) return ctx.reply('Укажи провайдер: /delkey groq');
    db.prepare('DELETE FROM user_api_keys WHERE uid=? AND provider=?').run(ctx.from!.id, p);
    await ctx.reply(`✅ Ключ <b>${p}</b> удалён`, { parse_mode:'HTML' });
  });

  // ── PC Agent commands ──────────────────────────────────────────────────────

  bot.command('pcagent', async (ctx) => {
    const uid = ctx.from!.id, online = app.isAgentOnline?.(uid);
    await safeSend(ctx,
      `💻 **PC Agent**\n\n${online ? '🟢 Подключён' : '🔴 Не подключён'}\n\n` +
      `**Установка:**\n\`\`\`\npip install websockets pyautogui pillow psutil requests pyperclip\npython nexum_agent.py\n\`\`\`\n\n` +
      `После запуска агент покажет код — отправь его сюда: /link КОД\n\n` +
      `**Безопасность:** опасные команды (rm -rf, shutdown и т.д.) требуют подтверждения администратора`
    );
  });

  bot.command('pc', async (ctx) => {
    const uid   = ctx.from!.id;
    const agent = db.prepare('SELECT * FROM pc_agents WHERE uid=?').get(uid) as any;
    const online = app.isAgentOnline?.(uid);
    if (!agent) return safeSend(ctx, `💻 PC Agent не подключён. Используй /pcagent для инструкций`);
    const lastSeen = agent.last_seen ? new Date(agent.last_seen).toLocaleString('ru-RU') : 'неизвестно';
    await safeSend(ctx, `💻 **PC Agent**\n\n${online?'🟢 Онлайн':'🔴 Офлайн'}\n📱 ${agent.device_name||agent.platform||'?'}\n🕐 Последний раз: ${lastSeen}`);
  });

  bot.command('link', async (ctx) => {
    const code = ctx.match?.trim().toUpperCase(); if (!code) return ctx.reply('Укажи код: /link ABCDEF');
    const uid = ctx.from!.id, linked = app.linkAgent?.(code, uid);
    const lr  = db.prepare('SELECT * FROM link_codes WHERE code=?').get(code) as any;
    if (linked || lr) {
      db.prepare(`INSERT INTO pc_agents (uid,device_id,device_name,platform,last_seen,status) VALUES (?,?,?,?,datetime('now'),'online')
        ON CONFLICT(uid) DO UPDATE SET device_id=excluded.device_id,device_name=excluded.device_name,platform=excluded.platform,last_seen=excluded.last_seen,status='online'`)
        .run(uid, lr?.device_id||'PC', lr?.device_id||'PC', lr?.platform||'Unknown');
      db.prepare('DELETE FROM link_codes WHERE code=?').run(code);
      await ctx.reply(`✅ PC Agent подключён!\n💻 ${lr?.platform||'Unknown'}`);
    } else {
      await ctx.reply('❌ Код не найден. Перезапусти агент для нового кода.');
    }
  });

  bot.command('screenshot', async (ctx) => {
    if (!await requireAgent(ctx, app)) return;
    const uid = ctx.from!.id, region = ctx.match?.trim()?.split(',').map(Number);
    const s   = await ctx.reply('📸 Снимаю экран...');
    try {
      const result = await app.sendToAgent(uid, { type:'screenshot', region: region?.length===4 ? region : undefined });
      if (result?.data) {
        await ctx.replyWithPhoto(new InputFile(Buffer.from(result.data,'base64'),'screenshot.png'));
        await ctx.api.deleteMessage(ctx.chat!.id, s.message_id).catch(()=>{});
      } else await safeEdit(ctx, ctx.chat!.id, s.message_id, '❌ Не удалось сделать скриншот');
    } catch (e: any) { await safeEdit(ctx, ctx.chat!.id, s.message_id, `❌ ${e.message}`); }
  });

  bot.command('run',     async (ctx) => { const c = ctx.match?.trim(); if (!c) return ctx.reply('Укажи команду: /run ls'); await agentCmd(ctx, app, bot, { type:'run', command:c }, `⚙️ \`${c?.slice(0,50)}\`...`); });
  bot.command('bgrun',   async (ctx) => { const c = ctx.match?.trim(); if (!c) return ctx.reply('Укажи команду'); await agentCmd(ctx, app, bot, { type:'run_background', command:c }, '🔄 Запускаю фоново...'); });
  bot.command('bglist',  async (ctx) => { await agentCmd(ctx, app, bot, { type:'bg_list' }); });
  bot.command('bgstop',  async (ctx) => { const id = ctx.match?.trim(); if (!id) return ctx.reply('Укажи ID'); await agentCmd(ctx, app, bot, { type:'bg_stop', proc_id:id }); });
  bot.command('sysinfo', async (ctx) => { await agentCmd(ctx, app, bot, { type:'sysinfo' }, '📊 Собираю...'); });
  bot.command('ps',      async (ctx) => { const l = parseInt(ctx.match?.trim()||'15'); await agentCmd(ctx, app, bot, { type:'processes', limit: isNaN(l)?15:l }, '🔍 Процессы...'); });
  bot.command('kill',    async (ctx) => { const t = ctx.match?.trim(); if (!t) return ctx.reply('Укажи PID или имя'); await agentCmd(ctx, app, bot, { type:'kill_process', input:t }); });
  bot.command('network', async (ctx) => { await agentCmd(ctx, app, bot, { type:'network' }, '🌐 Сеть...'); });
  bot.command('files',   async (ctx) => { const a = (ctx.match?.trim()||'').split(' '); await agentCmd(ctx, app, bot, { type:'filesystem', op:a[0]||'list', path:a[1]||'~', content:a.slice(2).join(' ') }, `📁 ${a[0]||'list'}...`); });
  bot.command('clipboard', async (ctx) => { const a = (ctx.match?.trim()||'read').split(' '); await agentCmd(ctx, app, bot, { type:'clipboard', op:a[0]==='write'?'write':'read', text:a.slice(1).join(' ') }); });
  bot.command('notify',  async (ctx) => { const [t,...r] = (ctx.match?.trim()||'').split('|'); await agentCmd(ctx, app, bot, { type:'notify', title:t.trim()||'NEXUM', message:r.join('|').trim()||t.trim() }); });
  bot.command('window',  async (ctx) => { const a = (ctx.match?.trim()||'list').split(' '); await agentCmd(ctx, app, bot, { type:'window', op:a[0], window_id:a.slice(1).join(' ') }, a[0]==='list'?'🪟 Окна...':undefined); });
  bot.command('http',    async (ctx) => { const a = (ctx.match?.trim()||'').split(' '); const method = a[0]?.toUpperCase()||'GET', url = a[1]||''; if (!url) return ctx.reply('Укажи URL: /http GET https://...'); await agentCmd(ctx, app, bot, { type:'http', method, url, body:a.slice(2).join(' ') }, `🌐 ${method} ${url.slice(0,40)}...`); });
  bot.command('browser', async (ctx) => { const u = ctx.match?.trim(); if (!u) return ctx.reply('Укажи URL'); await agentCmd(ctx, app, bot, { type:'browser', input:u }); });
  bot.command('openapp', async (ctx) => { const n = ctx.match?.trim(); if (!n) return ctx.reply('Укажи приложение'); await agentCmd(ctx, app, bot, { type:'open_app', input:n }); });
  bot.command('mouse',   async (ctx) => { const a = (ctx.match?.trim()||'position').split(' '); await agentCmd(ctx, app, bot, { type:'mouse', action:a[0], x:parseInt(a[1]||'0'), y:parseInt(a[2]||'0'), text:a.slice(3).join(' ') }); });
  bot.command('keyboard',async (ctx) => { const t = ctx.match?.trim(); if (!t) return ctx.reply('Укажи текст'); await agentCmd(ctx, app, bot, { type:'keyboard', action:'type', text:t }); });
  bot.command('hotkey',  async (ctx) => { const k = ctx.match?.trim(); if (!k) return ctx.reply('Укажи комбо: ctrl+c'); await agentCmd(ctx, app, bot, { type:'keyboard', action:'hotkey', text:k }); });

  // ── Admin commands ─────────────────────────────────────────────────────────
  bot.command('admin', async (ctx) => {
    if (!isAdmin(ctx.from!.id)) return ctx.reply('❌ Нет доступа');
    const users = (db.prepare('SELECT COUNT(*) as c FROM users').get() as any).c;
    const msgs  = (db.prepare('SELECT COUNT(*) as c FROM conversations').get() as any).c;
    await safeSend(ctx, `🔐 **Admin Panel**\n\n👥 Users: ${users}\n💬 Messages: ${msgs}\n\n/stats /users /broadcast`);
  });
  bot.command('users', async (ctx) => {
    if (!isAdmin(ctx.from!.id)) return ctx.reply('❌ Нет доступа');
    const users = db.prepare('SELECT uid, username, first_name FROM users ORDER BY created_at DESC LIMIT 20').all() as any[];
    await safeSend(ctx, `👥 **Пользователи:**\n\n${users.map(u=>`• \`${u.uid}\` ${u.first_name||''} @${u.username||'—'}`).join('\n')}`);
  });
  bot.command('broadcast', async (ctx) => {
    if (!isAdmin(ctx.from!.id)) return ctx.reply('❌ Нет доступа');
    const text = ctx.match?.trim(); if (!text) return ctx.reply('Укажи текст: /broadcast Сообщение');
    const users = db.prepare('SELECT uid FROM users').all() as any[];
    let sent = 0, failed = 0;
    for (const u of users) { try { await bot.api.sendMessage(u.uid, text); sent++; } catch { failed++; } }
    await ctx.reply(`✅ Отправлено: ${sent} | Ошибок: ${failed}`);
  });

  // ── Approval callbacks (OpenClaw-style) ──────────────────────────────────
  bot.callbackQuery(/^approve_(.+)$/, async (ctx) => {
    if (!isAdmin(ctx.from.id)) return ctx.answerCallbackQuery('❌ Нет прав');
    const id = ctx.match![1];
    const pending = pendingApprovals.get(id);
    if (!pending) return ctx.answerCallbackQuery('❌ Запрос устарел');
    pending.resolve(true);
    pendingApprovals.delete(id);
    await ctx.answerCallbackQuery('✅ Одобрено');
    await ctx.editMessageText(`✅ <b>Одобрено</b>\n\n<code>${pending.command.slice(0,200)}</code>`, { parse_mode:'HTML' });
    // Notify user
    await safeSendToUser(bot, pending.uid, `✅ **Команда одобрена**\n\n\`${pending.command.slice(0,200)}\``);
  });
  bot.callbackQuery(/^deny_(.+)$/, async (ctx) => {
    if (!isAdmin(ctx.from.id)) return ctx.answerCallbackQuery('❌ Нет прав');
    const id = ctx.match![1];
    const pending = pendingApprovals.get(id);
    if (!pending) return ctx.answerCallbackQuery('❌ Запрос устарел');
    pending.resolve(false);
    pendingApprovals.delete(id);
    await ctx.answerCallbackQuery('❌ Отклонено');
    await ctx.editMessageText(`❌ <b>Отклонено</b>\n\n<code>${pending.command.slice(0,200)}</code>`, { parse_mode:'HTML' });
    await safeSendToUser(bot, pending.uid, `❌ **Команда отклонена** администратором`);
  });

  // ── Other callbacks ─────────────────────────────────────────────────────
  bot.callbackQuery('cmd_help', async (ctx) => {
    await ctx.answerCallbackQuery();
    await safeSend(ctx, `/notes /tasks /habits /finance\n/website /newtool /tools\n/voice /remind /search\n/memory /forget /clear\n/apps /status /setkey\n/pcagent — PC Agent`);
  });
  bot.callbackQuery(/^site_link_(\d+)$/, async (ctx) => {
    await ctx.answerCallbackQuery(); await safeSend(ctx, `🔗 ${config.webappUrl}/site/${ctx.match![1]}`);
  });
  bot.callbackQuery(/^del_tool_(\d+)$/, async (ctx) => {
    db.prepare('UPDATE custom_tools SET active=0 WHERE id=?').run(parseInt(ctx.match![1]));
    await ctx.answerCallbackQuery('🗑 Удалён'); await ctx.editMessageText('🗑 Инструмент удалён');
  });
  bot.callbackQuery(/^test_tool_(\d+)$/, async (ctx) => {
    const tool = db.prepare('SELECT * FROM custom_tools WHERE id=?').get(parseInt(ctx.match![1])) as any;
    await ctx.answerCallbackQuery();
    if (tool) await safeSend(ctx, `🧪 Тест **${tool.name}**\n\nТриггер: \`${tool.trigger_pattern}\``);
  });

  // ── Message handlers ───────────────────────────────────────────────────────

  bot.on('message:photo', async (ctx) => {
    const uid = ctx.from!.id; ensureUser(uid, ctx.from?.username, ctx.from?.first_name);
    await ackReact(ctx);
    const s = await ctx.reply('👁 Анализирую...');
    try {
      const img = await getImageB64(ctx, bot); if (!img) throw new Error('Не удалось загрузить');
      const result = await execute(uid, ctx.message.caption||'Что на изображении?', img.data, img.mime);
      await safeEdit(ctx, ctx.chat!.id, s.message_id, result.text); await semanticReact(ctx);
    } catch (e: any) { await safeEdit(ctx, ctx.chat!.id, s.message_id, `❌ ${e.message}`); }
  });

  bot.on('message:document', async (ctx) => {
    const uid = ctx.from!.id; ensureUser(uid, ctx.from?.username, ctx.from?.first_name);
    const mime = ctx.message.document?.mime_type||'';
    if (mime.startsWith('image/')) {
      await ackReact(ctx); const s = await ctx.reply('👁 Анализирую...');
      try {
        const img = await getImageB64(ctx, bot); if (!img) throw new Error('Не удалось загрузить');
        const result = await execute(uid, ctx.message.caption||'Что на изображении?', img.data, img.mime);
        await safeEdit(ctx, ctx.chat!.id, s.message_id, result.text);
      } catch (e: any) { await safeEdit(ctx, ctx.chat!.id, s.message_id, `❌ ${e.message}`); }
      return;
    }
    await safeSend(ctx, `📎 Файл: **${ctx.message.document.file_name||'файл'}**`);
  });

  // Voice — OpenClaw pipeline: STT → AI → TTS
  bot.on('message:voice', async (ctx) => {
    const uid = ctx.from!.id; ensureUser(uid, ctx.from?.username, ctx.from?.first_name);
    await ackReact(ctx);
    const s = await ctx.reply('🎙 Слушаю...');
    try {
      const buf        = await downloadFile(ctx.message.voice.file_id, bot);
      const transcript = await transcribeVoice(buf, 'voice.ogg');
      await safeEdit(ctx, ctx.chat!.id, s.message_id, `🎙 _${transcript}_\n\n⏳ Думаю...`);
      const result = await execute(uid, transcript);
      const mode   = getVoiceMode(uid);
      if (mode !== 'never') {
        await ctx.api.deleteMessage(ctx.chat!.id, s.message_id).catch(()=>{});
        try {
          await ctx.replyWithChatAction('record_voice');
          const tts = await textToSpeech(result.text, uid);
          await ctx.replyWithVoice(new InputFile(tts.buffer, `nexum.${tts.format}`), {
            caption: `🎙 _${transcript.slice(0,200)}${transcript.length>200?'...':''}_`, parse_mode:'HTML',
          });
        } catch { await safeSend(ctx, `🎙 _${transcript}_\n\n${result.text}`); }
      } else {
        await safeEdit(ctx, ctx.chat!.id, s.message_id, `🎙 _${transcript}_\n\n${result.text}`);
      }
      await semanticReact(ctx);
    } catch (e: any) { await safeEdit(ctx, ctx.chat!.id, s.message_id, `❌ ${e.message}`).catch(()=>ctx.reply(`❌ ${e.message}`)); }
  });

  bot.on('message:audio', async (ctx) => {
    const uid = ctx.from!.id; ensureUser(uid, ctx.from?.username, ctx.from?.first_name);
    await ackReact(ctx); const s = await ctx.reply('🎵 Обрабатываю...');
    try {
      const buf = await downloadFile(ctx.message.audio.file_id, bot);
      const transcript = await transcribeVoice(buf, 'audio.mp3');
      await safeEdit(ctx, ctx.chat!.id, s.message_id, `🎵 _${transcript}_\n\n⏳...`);
      const result = await execute(uid, transcript);
      await safeEdit(ctx, ctx.chat!.id, s.message_id, `🎵 _${transcript}_\n\n${result.text}`);
    } catch (e: any) { await safeEdit(ctx, ctx.chat!.id, s.message_id, `❌ ${e.message}`); }
  });

  bot.on('message:video_note', async (ctx) => {
    const uid = ctx.from!.id; ensureUser(uid, ctx.from?.username, ctx.from?.first_name);
    await ackReact(ctx); const s = await ctx.reply('🎥 Обрабатываю...');
    try {
      const buf = await downloadFile(ctx.message.video_note.file_id, bot);
      const transcript = await transcribeVoice(buf, 'video.mp4');
      await safeEdit(ctx, ctx.chat!.id, s.message_id, `🎥 _${transcript}_\n\n⏳...`);
      const result = await execute(uid, transcript);
      await safeEdit(ctx, ctx.chat!.id, s.message_id, `🎥 _${transcript}_\n\n${result.text}`);
    } catch (e: any) { await safeEdit(ctx, ctx.chat!.id, s.message_id, `❌ ${e.message}`); }
  });

  bot.on('message:sticker', async (ctx) => {
    const pool = ['😄','👍','🔥','💯','✨','🤩','😎','🫡','🤙'];
    try { await ctx.api.raw.setMessageReaction({ chat_id: ctx.chat!.id, message_id: ctx.message!.message_id, reaction: [{ type:'emoji', emoji: pool[Math.floor(Math.random()*pool.length)] as any }] }); }
    catch { await ctx.reply(pool[Math.floor(Math.random()*pool.length)]); }
  });

  // Main text handler — OpenClaw pattern: ack → type → execute → semantic react
  bot.on('message:text', async (ctx) => {
    const uid = ctx.from!.id, text = ctx.message.text;
    if (text.startsWith('/')) return;
    ensureUser(uid, ctx.from?.username, ctx.from?.first_name);
    await ackReact(ctx);
    const mode = getVoiceMode(uid);
    await showTyping(ctx, mode === 'always');
    try {
      const result = await execute(uid, text);
      await voiceReply(ctx, result.text, uid, false);
      await semanticReact(ctx);
    } catch (e: any) { console.error('[text handler]', e); await ctx.reply(`❌ ${e.message}`); }
  });
}
