/**
 * NEXUM Finance App
 */
import { Db } from "../core/db.js";
import { ask } from "../ai/engine.js";
import { buildSystemPrompt } from "../memory/prompt.js";
import { log } from "../core/logger.js";

function fmt(n: number, cur = "UZS"): string {
  return Math.round(n).toLocaleString("ru-RU") + " " + cur;
}
function startOfMonth(): Date {
  const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1);
}
function startOfDay(): Date {
  const d = new Date(); d.setHours(0,0,0,0); return d;
}

export async function sendFinanceDashboard(bot: any, chatId: number, uid: number, msgId?: number) {
  Db.finEnsureDefaults(uid);
  const accounts = Db.finGetAccounts(uid);
  const now = new Date();
  const { income, expense } = Db.finGetTotalByPeriod(uid, startOfMonth(), now);
  const cats = Db.finGetByCategory(uid, startOfMonth());
  const balance = accounts.reduce((s,a) => s + a.balance, 0);

  let text = `💼 *NEXUM Finance*\n━━━━━━━━━━━━━━━━━━━━\n\n`;
  text += `🏦 *Счета:*\n`;
  for (const a of accounts) text += `${a.icon} ${a.name}: *${fmt(a.balance, a.currency)}*\n`;
  text += `\n💰 *Общий баланс: ${fmt(balance)}*\n━━━━━━━━━━━━━━━━━━━━\n\n`;

  const mn = now.toLocaleString("ru", { month: "long" });
  text += `📊 *${mn.charAt(0).toUpperCase()+mn.slice(1)}:*\n`;
  text += `➕ Доходы: *${fmt(income)}*\n`;
  text += `➖ Расходы: *${fmt(expense)}*\n`;
  text += `📈 Остаток: *${fmt(income - expense)}*\n`;

  if (cats.length) {
    text += `\n📂 *Топ расходов:*\n`;
    for (const c of cats.slice(0,5)) {
      const bar = expense > 0 ? Math.round((c.total/expense)*10) : 0;
      text += `• ${c.category}: ${fmt(c.total)} ${"▓".repeat(bar)}${"░".repeat(10-bar)}\n`;
    }
  }

  const kb = buildFinKb();
  try {
    if (msgId) {
      await bot.api.editMessageText(chatId, msgId, text, { parse_mode:"Markdown", reply_markup:kb });
    } else {
      await bot.api.sendMessage(chatId, text, { parse_mode:"Markdown", reply_markup:kb });
    }
  } catch(e: any) {
    if (!msgId) await bot.api.sendMessage(chatId, text, { reply_markup:kb }).catch(()=>{});
  }
}

function buildFinKb() {
  return { inline_keyboard: [
    [{ text:"➕ Расход", callback_data:"fin:add:expense" }, { text:"💵 Доход", callback_data:"fin:add:income" }, { text:"🔄 Перевод", callback_data:"fin:add:transfer" }],
    [{ text:"📋 История", callback_data:"fin:history" }, { text:"📊 Статистика", callback_data:"fin:stats" }, { text:"🏦 Счета", callback_data:"fin:accounts" }],
    [{ text:"🎯 Бюджеты", callback_data:"fin:budgets" }, { text:"🤖 AI анализ", callback_data:"fin:ai_analysis" }],
    [{ text:"❌ Закрыть", callback_data:"fin:close" }],
  ]};
}

function backKb(back: string) {
  return { inline_keyboard:[[{ text:"◀️ Назад", callback_data:back }]] };
}

async function sendHistory(bot: any, chatId: number, uid: number, msgId: number) {
  const txs = Db.finGetTxs(uid, 15);
  if (!txs.length) {
    await bot.api.editMessageText(chatId, msgId, `📋 *История пуста*\n\nДобавь первую транзакцию!`, { parse_mode:"Markdown", reply_markup:backKb("fin:dashboard") }).catch(()=>{});
    return;
  }
  let text = `📋 *Последние транзакции:*\n━━━━━━━━━━━━━━━━━━━━\n\n`;
  for (const tx of txs) {
    const icon = tx.type==="income"?"🟢":tx.type==="transfer"?"🔵":"🔴";
    const sign = tx.type==="income"?"+":tx.type==="transfer"?"⟷":"-";
    const date = new Date(tx.ts).toLocaleDateString("ru",{day:"numeric",month:"short"});
    text += `${icon} ${sign}${fmt(tx.amount, tx.currency)}\n   ${tx.category}${tx.note?" · "+tx.note:""} · _${date}_\n\n`;
  }
  await bot.api.editMessageText(chatId, msgId, text, { parse_mode:"Markdown", reply_markup:backKb("fin:dashboard") }).catch(()=>{});
}

async function sendStats(bot: any, chatId: number, uid: number, msgId: number) {
  const now = new Date();
  const today = Db.finGetTotalByPeriod(uid, startOfDay(), now);
  const month = Db.finGetTotalByPeriod(uid, startOfMonth(), now);
  const cats = Db.finGetByCategory(uid, startOfMonth());
  let text = `📊 *Статистика*\n━━━━━━━━━━━━━━━━━━━━\n\n`;
  text += `📅 *Сегодня:*\n➕ ${fmt(today.income)}  ➖ ${fmt(today.expense)}\n\n`;
  const mn = now.toLocaleString("ru",{month:"long"});
  text += `📆 *${mn.charAt(0).toUpperCase()+mn.slice(1)}:*\n`;
  text += `➕ ${fmt(month.income)}\n➖ ${fmt(month.expense)}\n📈 ${fmt(month.income-month.expense)}\n`;
  if (cats.length) {
    text += `\n📂 *По категориям:*\n`;
    for (const c of cats.slice(0,8)) {
      const pct = month.expense>0?Math.round((c.total/month.expense)*100):0;
      text += `• ${c.category}: ${fmt(c.total)} _(${pct}%)_\n`;
    }
  }
  await bot.api.editMessageText(chatId, msgId, text, { parse_mode:"Markdown", reply_markup:backKb("fin:dashboard") }).catch(()=>{});
}

async function sendAccounts(bot: any, chatId: number, uid: number, msgId: number) {
  const accs = Db.finGetAccounts(uid);
  let text = `🏦 *Мои счета:*\n━━━━━━━━━━━━━━━━━━━━\n\n`;
  for (const a of accs) text += `${a.icon} *${a.name}*\n   ${fmt(a.balance, a.currency)}\n\n`;
  const total = accs.reduce((s,a)=>s+a.balance,0);
  text += `━━━━━━━━━━━━━━━━━━━━\n💰 *Итого: ${fmt(total)}*`;
  const kb = { inline_keyboard:[[{ text:"➕ Добавить счёт", callback_data:"fin:account:add" }],[{ text:"◀️ Назад", callback_data:"fin:dashboard" }]] };
  await bot.api.editMessageText(chatId, msgId, text, { parse_mode:"Markdown", reply_markup:kb }).catch(()=>{});
}

async function sendBudgets(bot: any, chatId: number, uid: number, msgId: number) {
  const budgets = Db.finGetBudgets(uid);
  const cats = Db.finGetByCategory(uid, startOfMonth());
  let text = `🎯 *Бюджеты на месяц:*\n━━━━━━━━━━━━━━━━━━━━\n\n`;
  if (!budgets.length) {
    text += `Бюджеты не установлены.\n\nНапиши мне: _"установи бюджет на еду 500000"_`;
  } else {
    for (const b of budgets) {
      const spent = cats.find((c:any)=>c.category===b.category)?.total ?? 0;
      const pct = Math.round((spent/b.amount)*100);
      const bar = Math.min(Math.round(pct/10),10);
      const color = pct>100?"🔴":pct>75?"🟡":"🟢";
      text += `${color} *${b.category}*\n   ${fmt(spent)} / ${fmt(b.amount)} (${pct}%)\n   ${"▓".repeat(bar)}${"░".repeat(10-bar)}\n\n`;
    }
  }
  await bot.api.editMessageText(chatId, msgId, text, { parse_mode:"Markdown", reply_markup:backKb("fin:dashboard") }).catch(()=>{});
}

async function sendAIAnalysis(bot: any, chatId: number, uid: number, msgId: number) {
  await bot.api.editMessageText(chatId, msgId, `🤖 *Анализирую финансы...*`, { parse_mode:"Markdown" }).catch(()=>{});
  const now = new Date();
  const accounts = Db.finGetAccounts(uid);
  const { income, expense } = Db.finGetTotalByPeriod(uid, startOfMonth(), now);
  const cats = Db.finGetByCategory(uid, startOfMonth());
  const txs = Db.finGetTxsByPeriod(uid, startOfMonth(), now);
  const balance = accounts.reduce((s,a)=>s+a.balance,0);

  const finData = `Финансовые данные:\n- Баланс: ${fmt(balance)}\n- Счета: ${accounts.map(a=>`${a.name}:${fmt(a.balance,a.currency)}`).join(", ")}\n- Доходы: ${fmt(income)}, Расходы: ${fmt(expense)}\n- Категории: ${cats.map((c:any)=>`${c.category}:${fmt(c.total)}`).join(", ")}\n- Транзакций: ${txs.length}`;

  const sys = buildSystemPrompt(uid, chatId, "private");
  const msgs = [
    { role:"system" as const, content: sys + `\n\n${finData}` },
    { role:"user" as const, content:"Проанализируй мои финансы. Дай конкретные советы по оптимизации расходов. Честно и по делу, как личный финансовый советник." },
  ];
  const analysis = await ask(msgs, "analysis");
  await bot.api.editMessageText(chatId, msgId, `🤖 *AI Анализ:*\n\n${analysis}`, { parse_mode:"Markdown", reply_markup:backKb("fin:dashboard") }).catch(async ()=>{
    await bot.api.editMessageText(chatId, msgId, analysis, { reply_markup:backKb("fin:dashboard") }).catch(()=>{});
  });
}

export async function parseFinanceFromText(text: string): Promise<{ detected:boolean; type?:string; amount?:number; category?:string; note?:string }> {
  const lower = text.toLowerCase();
  const finWords = ["потратил","купил","заплатил","spent","paid","bought","доход","получил","заработал","income","earned","перевёл","перекинул","transfer","сумм","тысяч","рублей","usd","uzs","rub"];
  if (!finWords.some(w=>lower.includes(w)) || !/\d+/.test(text)) return { detected:false };

  try {
    const res = await ask([{ role:"user", content:`Это финансовая транзакция? "${text}"\nОтветь ТОЛЬКО JSON без markdown: {"detected":true/false,"type":"expense/income/transfer","amount":число,"category":"Еда/Транспорт/Покупки/Развлечения/Связь/Здоровье/Жильё/Инвестиции/Зарплата/Прочее","note":""}` }], "fast");
    return JSON.parse(res.replace(/```json|```/g,"").trim());
  } catch { return { detected:false }; }
}

export function getFinanceContext(uid: number): string {
  try {
    const accs = Db.finGetAccounts(uid);
    if (!accs.length) return "";
    const { income, expense } = Db.finGetTotalByPeriod(uid, startOfMonth(), new Date());
    const bal = accs.reduce((s,a)=>s+a.balance,0);
    return `[FINANCE]\nБаланс: ${fmt(bal)} | Счета: ${accs.map(a=>`${a.name}:${fmt(a.balance,a.currency)}`).join(", ")} | Месяц: +${fmt(income)} -${fmt(expense)}`;
  } catch { return ""; }
}

export function registerFinanceHandlers(bot: any) {
  bot.on("callback_query:data", async (ctx: any) => {
    const data: string = ctx.callbackQuery?.data ?? "";
    if (!data.startsWith("fin:")) return;
    const uid = ctx.from.id;
    const chatId = ctx.callbackQuery.message?.chat?.id;
    const msgId = ctx.callbackQuery.message?.message_id;
    await ctx.answerCallbackQuery().catch(()=>{});
    try {
      if (data==="fin:dashboard")      await sendFinanceDashboard(bot, chatId, uid, msgId);
      else if (data==="fin:history")   await sendHistory(bot, chatId, uid, msgId);
      else if (data==="fin:stats")     await sendStats(bot, chatId, uid, msgId);
      else if (data==="fin:accounts")  await sendAccounts(bot, chatId, uid, msgId);
      else if (data==="fin:ai_analysis") await sendAIAnalysis(bot, chatId, uid, msgId);
      else if (data==="fin:budgets")   await sendBudgets(bot, chatId, uid, msgId);
      else if (data==="fin:close")     await bot.api.deleteMessage(chatId, msgId).catch(()=>{});
      else if (data.startsWith("fin:add:")) {
        const type = data.split(":")[2];
        const hints: any = { expense:`💸 *Добавить расход*\n\nНапиши мне:\n_"потратил 50000 на еду"_\n_"купил телефон за 2 млн"_`, income:`💵 *Добавить доход*\n\nНапиши:\n_"получил зарплату 5 миллионов"_`, transfer:`🔄 *Перевод*\n\nНапиши:\n_"перевёл 100000 с наличных на карту"_` };
        await bot.api.editMessageText(chatId, msgId, hints[type]||"Напиши сумму", { parse_mode:"Markdown", reply_markup:backKb("fin:dashboard") }).catch(()=>{});
      }
    } catch(e: any) { log.error(`Finance error: ${e.message}`); }
  });
  log.info("Finance handlers registered");
}
