/**
 * NEXUM — Database layer
 * Полная изоляция данных по uid
 */

import Database, { Database as DatabaseType } from "better-sqlite3";
import { Config } from "./config.js";
import { log } from "./logger.js";

const db: DatabaseType = new Database(Config.DB_PATH);
db.pragma("journal_mode = WAL");
db.pragma("foreign_keys = ON");

db.exec(`
CREATE TABLE IF NOT EXISTS users (
  uid         INTEGER PRIMARY KEY,
  name        TEXT    DEFAULT '',
  username    TEXT    DEFAULT '',
  lang        TEXT    DEFAULT 'ru',
  total_msgs  INTEGER DEFAULT 0,
  is_banned   INTEGER DEFAULT 0,
  voice_mode  INTEGER DEFAULT 0,
  first_seen  TEXT    DEFAULT (datetime('now')),
  last_seen   TEXT    DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS conversations (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  uid      INTEGER NOT NULL,
  chat_id  INTEGER NOT NULL,
  role     TEXT    NOT NULL,
  content  TEXT    NOT NULL,
  ts       TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_conv ON conversations(uid, chat_id, ts);

CREATE TABLE IF NOT EXISTS memories (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  uid        INTEGER NOT NULL,
  key        TEXT    NOT NULL,
  value      TEXT    NOT NULL,
  category   TEXT    DEFAULT 'general',
  importance INTEGER DEFAULT 5,
  ts         TEXT    DEFAULT (datetime('now')),
  UNIQUE(uid, key)
);
CREATE INDEX IF NOT EXISTS idx_mem ON memories(uid, importance DESC);

CREATE TABLE IF NOT EXISTS long_memory (
  uid   INTEGER NOT NULL,
  key   TEXT    NOT NULL,
  value TEXT    NOT NULL,
  ts    TEXT    DEFAULT (datetime('now')),
  PRIMARY KEY(uid, key)
);

CREATE TABLE IF NOT EXISTS memory_bank (
  uid      INTEGER NOT NULL,
  category TEXT    NOT NULL,
  key      TEXT    NOT NULL,
  content  TEXT    NOT NULL,
  weight   INTEGER DEFAULT 50,
  ts       TEXT    DEFAULT (datetime('now')),
  PRIMARY KEY(uid, category, key)
);

CREATE TABLE IF NOT EXISTS daily_logs (
  id    INTEGER PRIMARY KEY AUTOINCREMENT,
  uid   INTEGER NOT NULL,
  day   TEXT    NOT NULL,
  entry TEXT    NOT NULL,
  ts    TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_daily ON daily_logs(uid, day);

CREATE TABLE IF NOT EXISTS reminders (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  uid       INTEGER NOT NULL,
  chat_id   INTEGER NOT NULL,
  text      TEXT    NOT NULL,
  fire_at   TEXT    NOT NULL,
  repeat    TEXT    DEFAULT 'once',
  fired     INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_rem ON reminders(fired, fire_at);

CREATE TABLE IF NOT EXISTS user_profiles (
  uid     INTEGER PRIMARY KEY,
  profile TEXT    DEFAULT ''
);

CREATE TABLE IF NOT EXISTS pc_agents (
  uid        INTEGER PRIMARY KEY,
  agent_name TEXT    NOT NULL,
  platform   TEXT    DEFAULT '',
  last_seen  TEXT    DEFAULT (datetime('now')),
  active     INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS group_stats (
  chat_id     INTEGER NOT NULL,
  uid         INTEGER NOT NULL,
  name        TEXT    DEFAULT '',
  username    TEXT    DEFAULT '',
  msgs        INTEGER DEFAULT 0,
  last_active TEXT    DEFAULT (datetime('now')),
  PRIMARY KEY(chat_id, uid)
);

-- ── FINANCE APP ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fin_accounts (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  uid      INTEGER NOT NULL,
  name     TEXT    NOT NULL,
  type     TEXT    DEFAULT 'cash',
  currency TEXT    DEFAULT 'UZS',
  balance  REAL    DEFAULT 0,
  icon     TEXT    DEFAULT '💳',
  active   INTEGER DEFAULT 1,
  ts       TEXT    DEFAULT (datetime('now')),
  UNIQUE(uid, name)
);

CREATE TABLE IF NOT EXISTS fin_transactions (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  uid         INTEGER NOT NULL,
  type        TEXT    NOT NULL,
  amount      REAL    NOT NULL,
  currency    TEXT    DEFAULT 'UZS',
  category    TEXT    DEFAULT 'other',
  account_id  INTEGER,
  account2_id INTEGER,
  note        TEXT    DEFAULT '',
  payee       TEXT    DEFAULT '',
  ts          TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_fin ON fin_transactions(uid, ts DESC);

CREATE TABLE IF NOT EXISTS fin_categories (
  id    INTEGER PRIMARY KEY AUTOINCREMENT,
  uid   INTEGER NOT NULL,
  name  TEXT    NOT NULL,
  icon  TEXT    DEFAULT '📦',
  type  TEXT    DEFAULT 'expense',
  UNIQUE(uid, name)
);

CREATE TABLE IF NOT EXISTS fin_budgets (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  uid      INTEGER NOT NULL,
  category TEXT    NOT NULL,
  amount   REAL    NOT NULL,
  period   TEXT    DEFAULT 'monthly',
  ts       TEXT    DEFAULT (datetime('now')),
  UNIQUE(uid, category, period)
);

-- ── ALARM SYSTEM ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS alarms (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  uid          INTEGER NOT NULL,
  chat_id      INTEGER NOT NULL,
  text         TEXT    NOT NULL,
  fire_at      TEXT    NOT NULL,
  interval_min INTEGER DEFAULT 5,
  max_repeats  INTEGER DEFAULT 6,
  repeat_count INTEGER DEFAULT 0,
  status       TEXT    DEFAULT 'pending',
  created_at   TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_alarms ON alarms(status, fire_at);

-- ── TASKS ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tasks (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  uid         INTEGER NOT NULL,
  title       TEXT    NOT NULL,
  description TEXT    DEFAULT '',
  project     TEXT    DEFAULT 'Inbox',
  priority    INTEGER DEFAULT 2,
  status      TEXT    DEFAULT 'todo',
  due_at      TEXT,
  ts          TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_tasks ON tasks(uid, status);

-- ── NOTES ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS notes (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  uid     INTEGER NOT NULL,
  title   TEXT    DEFAULT '',
  content TEXT    NOT NULL,
  tags    TEXT    DEFAULT '',
  pinned  INTEGER DEFAULT 0,
  ts      TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_notes ON notes(uid, ts DESC);

-- ── HABITS ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS habits (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  uid            INTEGER NOT NULL,
  name           TEXT    NOT NULL,
  emoji          TEXT    DEFAULT '✅',
  frequency      TEXT    DEFAULT 'daily',
  reminder_time  TEXT    DEFAULT '',
  streak         INTEGER DEFAULT 0,
  ts             TEXT    DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS habit_logs (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  habit_id INTEGER NOT NULL,
  uid      INTEGER NOT NULL,
  date     TEXT    NOT NULL,
  done     INTEGER DEFAULT 1,
  UNIQUE(habit_id, date)
);

-- ── IMPROVEMENT LOG ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS improvement_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  proposal   TEXT    NOT NULL,
  status     TEXT    DEFAULT 'pending',
  admin_notes TEXT   DEFAULT '',
  metrics    TEXT    DEFAULT '',
  ts         TEXT    DEFAULT (datetime('now'))
);

-- ── ERROR LOG ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS error_log (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  module  TEXT DEFAULT '',
  message TEXT NOT NULL,
  stack   TEXT DEFAULT '',
  ts      TEXT DEFAULT (datetime('now'))
);
`);

export interface UserRow    { uid: number; name: string; username: string; lang: string; total_msgs: number; is_banned: number; voice_mode: number }
export interface ConvRow    { role: string; content: string }
export interface MemRow     { key: string; value: string; category: string; importance: number }
export interface ReminderRow { id: number; uid: number; chat_id: number; text: string; fire_at: string; repeat: string }
export interface FinTx      { id: number; uid: number; type: string; amount: number; currency: string; category: string; account_id: number; note: string; payee: string; ts: string }
export interface FinAccount { id: number; uid: number; name: string; type: string; currency: string; balance: number; icon: string }

const s = {
  upsertUser:   db.prepare(`
    INSERT INTO users(uid,name,username,first_seen,last_seen,total_msgs)
    VALUES(?,?,?,datetime('now'),datetime('now'),1)
    ON CONFLICT(uid) DO UPDATE SET
      name=CASE WHEN excluded.name!='' THEN excluded.name ELSE name END,
      username=CASE WHEN excluded.username!='' THEN excluded.username ELSE username END,
      last_seen=datetime('now'), total_msgs=total_msgs+1
  `),
  getUser:         db.prepare(`SELECT * FROM users WHERE uid=? LIMIT 1`),
  banUser:         db.prepare(`UPDATE users SET is_banned=1 WHERE uid=?`),
  unbanUser:       db.prepare(`UPDATE users SET is_banned=0 WHERE uid=?`),
  isBanned:        db.prepare(`SELECT is_banned FROM users WHERE uid=? LIMIT 1`),
  setVoiceMode:    db.prepare(`UPDATE users SET voice_mode=? WHERE uid=?`),
  setLang:         db.prepare(`UPDATE users SET lang=? WHERE uid=?`),

  addMsg:          db.prepare(`INSERT INTO conversations(uid,chat_id,role,content) VALUES(?,?,?,?)`),
  getHistory:      db.prepare(`SELECT role,content FROM conversations WHERE uid=? AND chat_id=? ORDER BY ts DESC LIMIT ?`),
  getHistoryFull:  db.prepare(`SELECT id,role,content FROM conversations WHERE uid=? AND chat_id=? ORDER BY ts ASC LIMIT ?`),
  deleteOldMsgs:   db.prepare(`DELETE FROM conversations WHERE uid=? AND chat_id=? AND id IN (SELECT id FROM conversations WHERE uid=? AND chat_id=? ORDER BY ts ASC LIMIT ?)`),
  clearHistory:    db.prepare(`DELETE FROM conversations WHERE uid=? AND chat_id=?`),
  countHistory:    db.prepare(`SELECT COUNT(*) as n FROM conversations WHERE uid=? AND chat_id=?`),

  upsertMem:       db.prepare(`INSERT INTO memories(uid,key,value,category,importance) VALUES(?,?,?,?,?) ON CONFLICT(uid,key) DO UPDATE SET value=excluded.value,importance=excluded.importance,ts=datetime('now')`),
  getMems:         db.prepare(`SELECT key,value,category,importance FROM memories WHERE uid=? ORDER BY importance DESC LIMIT 30`),
  clearMems:       db.prepare(`DELETE FROM memories WHERE uid=?`),

  setLong:         db.prepare(`INSERT OR REPLACE INTO long_memory(uid,key,value) VALUES(?,?,?)`),
  getLong:         db.prepare(`SELECT key,value FROM long_memory WHERE uid=?`),
  clearLong:       db.prepare(`DELETE FROM long_memory WHERE uid=?`),

  setBank:         db.prepare(`INSERT OR REPLACE INTO memory_bank(uid,category,key,content,weight) VALUES(?,?,?,?,?)`),
  getBank:         db.prepare(`SELECT category,key,content,weight FROM memory_bank WHERE uid=? ORDER BY weight DESC LIMIT 40`),

  addLog:          db.prepare(`INSERT INTO daily_logs(uid,day,entry) VALUES(?,?,?)`),
  getLogs:         db.prepare(`SELECT entry FROM daily_logs WHERE uid=? AND day>=? ORDER BY ts DESC LIMIT 30`),

  addRem:          db.prepare(`INSERT INTO reminders(uid,chat_id,text,fire_at,repeat) VALUES(?,?,?,?,?)`),
  getPending:      db.prepare(`SELECT * FROM reminders WHERE fired=0 AND fire_at<=datetime('now')`),
  markFired:       db.prepare(`UPDATE reminders SET fired=1 WHERE id=?`),
  reschedule:      db.prepare(`UPDATE reminders SET fire_at=?, fired=0 WHERE id=?`),
  getUserRems:     db.prepare(`SELECT * FROM reminders WHERE uid=? AND fired=0 ORDER BY fire_at`),
  cancelRem:       db.prepare(`UPDATE reminders SET fired=1 WHERE id=? AND uid=?`),

  setProfile:      db.prepare(`INSERT OR REPLACE INTO user_profiles(uid,profile) VALUES(?,?)`),
  getProfile:      db.prepare(`SELECT profile FROM user_profiles WHERE uid=?`),

  upsertAgent:     db.prepare(`INSERT OR REPLACE INTO pc_agents(uid,agent_name,platform,last_seen,active) VALUES(?,?,?,datetime('now'),1)`),
  getAgent:        db.prepare(`SELECT * FROM pc_agents WHERE uid=? AND active=1`),
  deactAgent:      db.prepare(`UPDATE pc_agents SET active=0 WHERE uid=?`),

  grpSave:         db.prepare(`INSERT INTO group_stats(chat_id,uid,name,username,msgs,last_active) VALUES(?,?,?,?,1,datetime('now')) ON CONFLICT(chat_id,uid) DO UPDATE SET msgs=msgs+1,last_active=datetime('now'),name=CASE WHEN excluded.name!='' THEN excluded.name ELSE name END`),
  grpTop:          db.prepare(`SELECT name,username,msgs FROM group_stats WHERE chat_id=? ORDER BY msgs DESC LIMIT 10`),

  allUsers:        db.prepare(`SELECT uid,name,username,total_msgs,last_seen FROM users ORDER BY total_msgs DESC LIMIT 50`),
  userCount:       db.prepare(`SELECT COUNT(*) as n FROM users`),
  msgCount:        db.prepare(`SELECT COUNT(*) as n FROM conversations`),

  // Finance
  upsertAccount:   db.prepare(`INSERT INTO fin_accounts(uid,name,type,currency,balance,icon) VALUES(?,?,?,?,?,?) ON CONFLICT(uid,name) DO UPDATE SET balance=excluded.balance,icon=excluded.icon`),
  getAccounts:     db.prepare(`SELECT * FROM fin_accounts WHERE uid=? AND active=1 ORDER BY ts`),
  getAccount:      db.prepare(`SELECT * FROM fin_accounts WHERE uid=? AND id=?`),
  updateBalance:   db.prepare(`UPDATE fin_accounts SET balance=balance+? WHERE id=? AND uid=?`),
  setBalance:      db.prepare(`UPDATE fin_accounts SET balance=? WHERE id=? AND uid=?`),

  addTx:           db.prepare(`INSERT INTO fin_transactions(uid,type,amount,currency,category,account_id,account2_id,note,payee) VALUES(?,?,?,?,?,?,?,?,?)`),
  getTxs:          db.prepare(`SELECT * FROM fin_transactions WHERE uid=? ORDER BY ts DESC LIMIT ?`),
  getTxsByPeriod:  db.prepare(`SELECT * FROM fin_transactions WHERE uid=? AND ts>=? AND ts<=? ORDER BY ts DESC`),
  getTxsByCategory:db.prepare(`SELECT category, SUM(amount) as total FROM fin_transactions WHERE uid=? AND type='expense' AND ts>=? GROUP BY category ORDER BY total DESC`),
  getLastTx:       db.prepare(`SELECT * FROM fin_transactions WHERE uid=? ORDER BY ts DESC LIMIT 1`),
  deleteTx:        db.prepare(`DELETE FROM fin_transactions WHERE id=? AND uid=?`),

  upsertCategory:  db.prepare(`INSERT OR IGNORE INTO fin_categories(uid,name,icon,type) VALUES(?,?,?,?)`),
  getCategories:   db.prepare(`SELECT * FROM fin_categories WHERE uid=?`),

  setBudget:       db.prepare(`INSERT OR REPLACE INTO fin_budgets(uid,category,amount,period) VALUES(?,?,?,?)`),
  getBudgets:      db.prepare(`SELECT * FROM fin_budgets WHERE uid=?`),

  // Alarms
  addAlarm:        db.prepare(`INSERT INTO alarms(uid,chat_id,text,fire_at,interval_min,max_repeats) VALUES(?,?,?,?,?,?)`),
  getPendingAlarms:db.prepare(`SELECT * FROM alarms WHERE status='pending' AND fire_at<=datetime('now')`),
  updateAlarm:     db.prepare(`UPDATE alarms SET repeat_count=repeat_count+1, fire_at=?, status=? WHERE id=?`),
  confirmAlarm:    db.prepare(`UPDATE alarms SET status='confirmed' WHERE id=?`),
  snoozeAlarm:     db.prepare(`UPDATE alarms SET fire_at=datetime(fire_at,'+5 minutes'), repeat_count=repeat_count+1 WHERE id=?`),
  getUserAlarms:   db.prepare(`SELECT * FROM alarms WHERE uid=? AND status='pending' ORDER BY fire_at`),
  cancelAlarm:     db.prepare(`UPDATE alarms SET status='cancelled' WHERE id=? AND uid=?`),

  // Tasks
  addTask:         db.prepare(`INSERT INTO tasks(uid,title,description,project,priority,due_at) VALUES(?,?,?,?,?,?)`),
  getTasks:        db.prepare(`SELECT * FROM tasks WHERE uid=? AND status!=? ORDER BY priority DESC, ts DESC`),
  getTask:         db.prepare(`SELECT * FROM tasks WHERE id=? AND uid=?`),
  updateTaskStatus:db.prepare(`UPDATE tasks SET status=? WHERE id=? AND uid=?`),
  updateTask:      db.prepare(`UPDATE tasks SET title=?,description=?,project=?,priority=?,due_at=? WHERE id=? AND uid=?`),
  deleteTask:      db.prepare(`DELETE FROM tasks WHERE id=? AND uid=?`),

  // Notes
  addNote:         db.prepare(`INSERT INTO notes(uid,title,content,tags) VALUES(?,?,?,?)`),
  getNotes:        db.prepare(`SELECT * FROM notes WHERE uid=? ORDER BY pinned DESC, ts DESC LIMIT ?`),
  getNote:         db.prepare(`SELECT * FROM notes WHERE id=? AND uid=?`),
  searchNotes:     db.prepare(`SELECT * FROM notes WHERE uid=? AND (content LIKE ? OR title LIKE ? OR tags LIKE ?) LIMIT 10`),
  updateNote:      db.prepare(`UPDATE notes SET title=?,content=?,tags=? WHERE id=? AND uid=?`),
  pinNote:         db.prepare(`UPDATE notes SET pinned=? WHERE id=? AND uid=?`),
  deleteNote:      db.prepare(`DELETE FROM notes WHERE id=? AND uid=?`),

  // Habits
  addHabit:        db.prepare(`INSERT INTO habits(uid,name,emoji,frequency,reminder_time) VALUES(?,?,?,?,?)`),
  getHabits:       db.prepare(`SELECT * FROM habits WHERE uid=? ORDER BY ts`),
  logHabit:        db.prepare(`INSERT OR REPLACE INTO habit_logs(habit_id,uid,date,done) VALUES(?,?,?,1)`),
  getHabitLog:     db.prepare(`SELECT * FROM habit_logs WHERE habit_id=? AND date=?`),
  getHabitStreak:  db.prepare(`SELECT COUNT(*) as n FROM habit_logs WHERE habit_id=? AND done=1 AND date>=date('now','-30 days')`),
  updateHabitStreak:db.prepare(`UPDATE habits SET streak=? WHERE id=?`),
  deleteHabit:     db.prepare(`DELETE FROM habits WHERE id=? AND uid=?`),

  // Improvement log
  addImprovement:  db.prepare(`INSERT INTO improvement_log(proposal,metrics) VALUES(?,?)`),
  updateImprovement:db.prepare(`UPDATE improvement_log SET status=?,admin_notes=? WHERE id=?`),
  getPendingImprovements:db.prepare(`SELECT * FROM improvement_log WHERE status='pending' ORDER BY ts DESC LIMIT 5`),

  // Error log
  addError:        db.prepare(`INSERT INTO error_log(module,message,stack) VALUES(?,?,?)`),
  getErrors:       db.prepare(`SELECT * FROM error_log ORDER BY ts DESC LIMIT ?`),
};

export const Db = {
  ensureUser(uid: number, name: string, username: string) { s.upsertUser.run(uid, name, username); },
  getUser(uid: number): UserRow | undefined { return s.getUser.get(uid) as UserRow | undefined; },
  isBanned(uid: number): boolean { return ((s.isBanned.get(uid) as any)?.is_banned ?? 0) === 1; },
  banUser(uid: number) { s.banUser.run(uid); },
  unbanUser(uid: number) { s.unbanUser.run(uid); },
  setVoiceMode(uid: number, on: boolean) { s.setVoiceMode.run(on ? 1 : 0, uid); },
  setLang(uid: number, lang: string) { s.setLang.run(lang, uid); },

  addMsg(uid: number, chatId: number, role: "user"|"assistant"|"system", content: string) {
    s.addMsg.run(uid, chatId, role, content.slice(0, 8000));
  },
  getHistory(uid: number, chatId: number, limit = 50): ConvRow[] {
    return (s.getHistory.all(uid, chatId, limit) as ConvRow[]).reverse();
  },
  getHistoryFull(uid: number, chatId: number, limit = 60): any[] {
    return s.getHistoryFull.all(uid, chatId, limit) as any[];
  },
  deleteOldMessages(uid: number, chatId: number, count: number) {
    s.deleteOldMsgs.run(uid, chatId, uid, chatId, count);
  },
  clearHistory(uid: number, chatId: number) { s.clearHistory.run(uid, chatId); },
  historyCount(uid: number, chatId: number): number { return (s.countHistory.get(uid, chatId) as any).n; },

  remember(uid: number, key: string, value: string, category = "general", importance = 5) {
    s.upsertMem.run(uid, key.slice(0, 200), value.slice(0, 500), category, importance);
  },
  getMemories(uid: number): MemRow[] { return s.getMems.all(uid) as MemRow[]; },
  clearMemories(uid: number) { s.clearMems.run(uid); },

  setLongMem(uid: number, key: string, value: string) { s.setLong.run(uid, key.slice(0, 100), value.slice(0, 500)); },
  getLongMem(uid: number): Record<string, string> {
    return Object.fromEntries((s.getLong.all(uid) as any[]).map(r => [r.key, r.value]));
  },
  clearLongMem(uid: number) { s.clearLong.run(uid); },

  setBankEntry(uid: number, category: string, key: string, content: string, weight = 50) {
    s.setBank.run(uid, category, key, content.slice(0, 600), weight);
  },
  getBankAll(uid: number): any[] { return s.getBank.all(uid) as any[]; },

  addDailyLog(uid: number, entry: string) {
    s.addLog.run(uid, new Date().toISOString().split("T")[0], entry.slice(0, 500));
  },
  getDailyLogs(uid: number, days = 2): string[] {
    const cutoff = new Date(Date.now() - days * 86400000).toISOString().split("T")[0];
    return (s.getLogs.all(uid, cutoff) as any[]).map(r => r.entry);
  },

  addReminder(uid: number, chatId: number, text: string, fireAt: Date, repeat = "once"): number {
    return (s.addRem.run(uid, chatId, text, fireAt.toISOString(), repeat)).lastInsertRowid as number;
  },
  getPendingReminders(): ReminderRow[] { return s.getPending.all() as ReminderRow[]; },
  markReminderFired(id: number) { s.markFired.run(id); },
  rescheduleReminder(id: number, next: Date) { s.reschedule.run(next.toISOString(), id); },
  getUserReminders(uid: number): ReminderRow[] { return s.getUserRems.all(uid) as ReminderRow[]; },
  cancelReminder(id: number, uid: number) { s.cancelRem.run(id, uid); },

  setProfile(uid: number, profile: string) { s.setProfile.run(uid, profile); },
  getProfile(uid: number): string { return (s.getProfile.get(uid) as any)?.profile ?? ""; },

  upsertAgent(uid: number, name: string, platform: string) { s.upsertAgent.run(uid, name, platform); },
  getAgent(uid: number): any { return s.getAgent.get(uid); },
  deactivateAgent(uid: number) { s.deactAgent.run(uid); },

  grpSave(chatId: number, uid: number, name: string, username: string) { s.grpSave.run(chatId, uid, name, username); },
  grpTop(chatId: number): any[] { return s.grpTop.all(chatId) as any[]; },

  getStats(): { users: number; messages: number } {
    return { users: (s.userCount.get() as any).n, messages: (s.msgCount.get() as any).n };
  },
  getTopUsers(): any[] { return s.allUsers.all() as any[]; },

  // ── FINANCE ──────────────────────────────────────────────────────────────
  finEnsureDefaults(uid: number) {
    const accounts = [
      { name: "Наличные", type: "cash", currency: "UZS", icon: "💵" },
      { name: "Карта", type: "card", currency: "UZS", icon: "💳" },
    ];
    for (const a of accounts) {
      s.upsertAccount.run(uid, a.name, a.type, a.currency, 0, a.icon);
    }
    const cats = [
      ["Еда", "🍕", "expense"], ["Транспорт", "🚕", "expense"], ["Покупки", "🛍", "expense"],
      ["Развлечения", "🎮", "expense"], ["Связь", "📱", "expense"], ["Здоровье", "💊", "expense"],
      ["Жильё", "🏠", "expense"], ["Инвестиции", "📈", "expense"], ["Зарплата", "💰", "income"],
      ["Прочее", "📦", "expense"],
    ];
    for (const [name, icon, type] of cats) s.upsertCategory.run(uid, name, icon, type);
  },

  finGetAccounts(uid: number): FinAccount[] { return s.getAccounts.all(uid) as FinAccount[]; },
  finGetAccount(uid: number, id: number): FinAccount | undefined { return s.getAccount.get(uid, id) as FinAccount | undefined; },

  finAddTransaction(uid: number, type: string, amount: number, category: string, accountId: number | null, note = "", payee = "", currency = "UZS", account2Id: number | null = null): number {
    const r = s.addTx.run(uid, type, amount, currency, category, accountId, account2Id, note, payee);
    // Update account balance
    if (accountId) {
      const delta = type === "income" ? amount : type === "expense" ? -amount : -amount;
      s.updateBalance.run(delta, accountId, uid);
    }
    if (account2Id && type === "transfer") {
      s.updateBalance.run(amount, account2Id, uid);
    }
    return r.lastInsertRowid as number;
  },

  finGetTxs(uid: number, limit = 20): FinTx[] { return s.getTxs.all(uid, limit) as FinTx[]; },
  finGetTxsByPeriod(uid: number, from: Date, to: Date): FinTx[] {
    return s.getTxsByPeriod.all(uid, from.toISOString(), to.toISOString()) as FinTx[];
  },
  finGetByCategory(uid: number, from: Date): any[] {
    return s.getTxsByCategory.all(uid, from.toISOString()) as any[];
  },
  finDeleteTx(uid: number, id: number) { s.deleteTx.run(id, uid); },

  finGetCategories(uid: number): any[] { return s.getCategories.all(uid) as any[]; },
  finAddCategory(uid: number, name: string, icon: string, type: string) {
    s.upsertCategory.run(uid, name, icon, type);
  },

  finSetBudget(uid: number, category: string, amount: number, period = "monthly") {
    s.setBudget.run(uid, category, amount, period);
  },
  finGetBudgets(uid: number): any[] { return s.getBudgets.all(uid) as any[]; },

  finGetTotalByPeriod(uid: number, from: Date, to: Date): { income: number; expense: number } {
    const txs = Db.finGetTxsByPeriod(uid, from, to);
    const income = txs.filter(t => t.type === "income").reduce((s, t) => s + t.amount, 0);
    const expense = txs.filter(t => t.type === "expense").reduce((s, t) => s + t.amount, 0);
    return { income, expense };
  },

  // ── ALARMS ───────────────────────────────────────────────────────────────
  addAlarm(uid: number, chatId: number, text: string, fireAt: Date, intervalMin = 5, maxRepeats = 6): number {
    return s.addAlarm.run(uid, chatId, text, fireAt.toISOString(), intervalMin, maxRepeats).lastInsertRowid as number;
  },
  getPendingAlarms(): any[] { return s.getPendingAlarms.all() as any[]; },
  tickAlarm(id: number, nextFireAt: Date, done: boolean) {
    s.updateAlarm.run(nextFireAt.toISOString(), done ? 'done' : 'pending', id);
  },
  confirmAlarm(id: number) { s.confirmAlarm.run(id); },
  snoozeAlarm(id: number) { s.snoozeAlarm.run(id); },
  getUserAlarms(uid: number): any[] { return s.getUserAlarms.all(uid) as any[]; },
  cancelAlarm(id: number, uid: number) { s.cancelAlarm.run(id, uid); },

  // ── TASKS ────────────────────────────────────────────────────────────────
  addTask(uid: number, title: string, desc = '', project = 'Inbox', priority = 2, dueAt: string | null = null): number {
    return s.addTask.run(uid, title, desc, project, priority, dueAt).lastInsertRowid as number;
  },
  getTasks(uid: number, excludeStatus = 'done'): any[] { return s.getTasks.all(uid, excludeStatus) as any[]; },
  getAllTasks(uid: number): any[] { return (db.prepare(`SELECT * FROM tasks WHERE uid=? ORDER BY priority DESC, ts DESC`).all(uid) as any[]); },
  getTask(uid: number, id: number): any { return s.getTask.get(id, uid); },
  updateTaskStatus(uid: number, id: number, status: string) { s.updateTaskStatus.run(status, id, uid); },
  doneTask(uid: number, id: number) { s.updateTaskStatus.run('done', id, uid); },
  cancelTask(uid: number, id: number) { s.updateTaskStatus.run('cancelled', id, uid); },
  deleteTask(uid: number, id: number) { s.deleteTask.run(id, uid); },

  // ── NOTES ────────────────────────────────────────────────────────────────
  addNote(uid: number, title: string, content: string, tags = ''): number {
    return s.addNote.run(uid, title, content, tags).lastInsertRowid as number;
  },
  getNotes(uid: number, limit = 10): any[] { return s.getNotes.all(uid, limit) as any[]; },
  getNote(uid: number, id: number): any { return s.getNote.get(id, uid); },
  searchNotes(uid: number, q: string): any[] {
    const like = `%${q}%`;
    return s.searchNotes.all(uid, like, like, like) as any[];
  },
  updateNote(uid: number, id: number, title: string, content: string, tags: string) {
    s.updateNote.run(title, content, tags, id, uid);
  },
  pinNote(uid: number, id: number, pin: boolean) { s.pinNote.run(pin ? 1 : 0, id, uid); },
  deleteNote(uid: number, id: number) { s.deleteNote.run(id, uid); },

  // ── HABITS ───────────────────────────────────────────────────────────────
  addHabit(uid: number, name: string, emoji = '✅', frequency = 'daily', reminderTime = ''): number {
    return s.addHabit.run(uid, name, emoji, frequency, reminderTime).lastInsertRowid as number;
  },
  getHabits(uid: number): any[] { return s.getHabits.all(uid) as any[]; },
  logHabit(habitId: number, uid: number, date?: string) {
    const d = date || new Date().toISOString().split('T')[0]!;
    s.logHabit.run(habitId, uid, d);
    const streak = (s.getHabitStreak.get(habitId) as any).n;
    s.updateHabitStreak.run(streak, habitId);
  },
  getHabitLog(habitId: number, date: string): any { return s.getHabitLog.get(habitId, date); },
  getHabitStreak(habitId: number): any { return s.getHabitStreak.get(habitId); },
  updateHabitStreak(habitId: number, streak: number) { s.updateHabitStreak.run(streak, habitId); },
  isHabitDoneToday(habitId: number): boolean {
    const today = new Date().toISOString().split('T')[0]!;
    return !!s.getHabitLog.get(habitId, today);
  },
  deleteHabit(uid: number, id: number) { s.deleteHabit.run(id, uid); },

  // ── IMPROVEMENT ──────────────────────────────────────────────────────────
  addImprovement(proposal: string, metrics: string): number {
    return s.addImprovement.run(proposal, metrics).lastInsertRowid as number;
  },
  resolveImprovement(id: number, status: 'approved' | 'rejected', notes = '') {
    s.updateImprovement.run(status, notes, id);
  },
  getPendingImprovements(): any[] { return s.getPendingImprovements.all() as any[]; },

  // ── ERROR LOG ────────────────────────────────────────────────────────────
  logError(module: string, message: string, stack = '') {
    try { s.addError.run(module, message.slice(0, 1000), stack.slice(0, 2000)); } catch {}
  },
  getRecentErrors(limit = 50): any[] { return s.getErrors.all(limit) as any[]; },
};

log.info(`DB ready: ${Config.DB_PATH}`);
export default db;
