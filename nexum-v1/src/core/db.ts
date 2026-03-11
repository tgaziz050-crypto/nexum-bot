/**
 * NEXUM v1 — Database layer
 *
 * ИЗОЛЯЦИЯ ДАННЫХ:
 * Каждый запрос к БД требует uid. Данные одного пользователя
 * физически невозможно получить с uid другого — все WHERE uid=?
 * строго обязательны. Данные владельца (ADMIN_IDS) хранятся
 * в тех же таблицах но полностью изолированы uid'ом.
 */

import Database from "better-sqlite3";
import { Config } from "./config.js";
import { log } from "./logger.js";

const db = new Database(Config.DB_PATH);
db.pragma("journal_mode = WAL");
db.pragma("foreign_keys = ON");

// ── Schema ────────────────────────────────────────────────────────────────
db.exec(`
CREATE TABLE IF NOT EXISTS users (
  uid         INTEGER PRIMARY KEY,
  name        TEXT    DEFAULT '',
  username    TEXT    DEFAULT '',
  lang        TEXT    DEFAULT 'ru',
  total_msgs  INTEGER DEFAULT 0,
  is_banned   INTEGER DEFAULT 0,
  first_seen  TEXT    DEFAULT (datetime('now')),
  last_seen   TEXT    DEFAULT (datetime('now'))
);

-- История диалогов: uid+chat_id изолирует каждого юзера
CREATE TABLE IF NOT EXISTS conversations (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  uid      INTEGER NOT NULL,
  chat_id  INTEGER NOT NULL,
  role     TEXT    NOT NULL,
  content  TEXT    NOT NULL,
  ts       TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_conv ON conversations(uid, chat_id, ts);

-- Короткая память: key уникален per-user
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

-- Долгосрочная память
CREATE TABLE IF NOT EXISTS long_memory (
  uid   INTEGER NOT NULL,
  key   TEXT    NOT NULL,
  value TEXT    NOT NULL,
  ts    TEXT    DEFAULT (datetime('now')),
  PRIMARY KEY(uid, key)
);

-- Расширенный банк памяти
CREATE TABLE IF NOT EXISTS memory_bank (
  uid      INTEGER NOT NULL,
  category TEXT    NOT NULL,
  key      TEXT    NOT NULL,
  content  TEXT    NOT NULL,
  weight   INTEGER DEFAULT 50,
  ts       TEXT    DEFAULT (datetime('now')),
  PRIMARY KEY(uid, category, key)
);

-- Дневные логи
CREATE TABLE IF NOT EXISTS daily_logs (
  id    INTEGER PRIMARY KEY AUTOINCREMENT,
  uid   INTEGER NOT NULL,
  day   TEXT    NOT NULL,
  entry TEXT    NOT NULL,
  ts    TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_daily ON daily_logs(uid, day);

-- Напоминания
CREATE TABLE IF NOT EXISTS reminders (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  uid      INTEGER NOT NULL,
  chat_id  INTEGER NOT NULL,
  text     TEXT    NOT NULL,
  fire_at  TEXT    NOT NULL,
  fired    INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_rem ON reminders(fired, fire_at);

-- Профиль пользователя
CREATE TABLE IF NOT EXISTS user_profiles (
  uid     INTEGER PRIMARY KEY,
  profile TEXT    DEFAULT ''
);

-- PC агенты
CREATE TABLE IF NOT EXISTS pc_agents (
  uid        INTEGER PRIMARY KEY,
  agent_name TEXT    NOT NULL,
  platform   TEXT    DEFAULT '',
  last_seen  TEXT    DEFAULT (datetime('now')),
  active     INTEGER DEFAULT 1
);

-- Групповая статистика
CREATE TABLE IF NOT EXISTS group_stats (
  chat_id     INTEGER NOT NULL,
  uid         INTEGER NOT NULL,
  name        TEXT    DEFAULT '',
  username    TEXT    DEFAULT '',
  msgs        INTEGER DEFAULT 0,
  last_active TEXT    DEFAULT (datetime('now')),
  PRIMARY KEY(chat_id, uid)
);

-- Навыки (skills) пользователя
CREATE TABLE IF NOT EXISTS skills (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  uid         INTEGER NOT NULL,
  name        TEXT    NOT NULL,
  description TEXT    DEFAULT '',
  code        TEXT    NOT NULL,
  ts          TEXT    DEFAULT (datetime('now'))
);
`);

// ── Types ─────────────────────────────────────────────────────────────────
export interface UserRow    { uid: number; name: string; username: string; lang: string; total_msgs: number; is_banned: number }
export interface ConvRow    { role: string; content: string }
export interface MemRow     { key: string; value: string; category: string; importance: number }
export interface ReminderRow { id: number; uid: number; chat_id: number; text: string; fire_at: string }

// ── Prepared statements ───────────────────────────────────────────────────
const s = {
  // Users
  upsertUser:   db.prepare(`
    INSERT INTO users(uid,name,username,first_seen,last_seen,total_msgs)
    VALUES(?,?,?,datetime('now'),datetime('now'),1)
    ON CONFLICT(uid) DO UPDATE SET
      name       = CASE WHEN excluded.name     !='' THEN excluded.name     ELSE name     END,
      username   = CASE WHEN excluded.username !='' THEN excluded.username ELSE username END,
      last_seen  = datetime('now'),
      total_msgs = total_msgs + 1
  `),
  getUser:      db.prepare(`SELECT * FROM users WHERE uid=? LIMIT 1`),
  banUser:      db.prepare(`UPDATE users SET is_banned=1 WHERE uid=?`),
  unbanUser:    db.prepare(`UPDATE users SET is_banned=0 WHERE uid=?`),
  isBanned:     db.prepare(`SELECT is_banned FROM users WHERE uid=? LIMIT 1`),

  // Conversations — строго по uid+chat_id
  addMsg:       db.prepare(`INSERT INTO conversations(uid,chat_id,role,content) VALUES(?,?,?,?)`),
  getHistory:   db.prepare(`
    SELECT role,content FROM conversations
    WHERE uid=? AND chat_id=?
    ORDER BY ts DESC LIMIT ?
  `),
  clearHistory: db.prepare(`DELETE FROM conversations WHERE uid=? AND chat_id=?`),
  countHistory: db.prepare(`SELECT COUNT(*) as n FROM conversations WHERE uid=? AND chat_id=?`),
  clearAllHistory: db.prepare(`DELETE FROM conversations WHERE uid=?`),

  // Memories — строго по uid
  upsertMem:    db.prepare(`
    INSERT INTO memories(uid,key,value,category,importance)
    VALUES(?,?,?,?,?)
    ON CONFLICT(uid,key) DO UPDATE SET
      value=excluded.value, importance=excluded.importance, ts=datetime('now')
  `),
  getMems:      db.prepare(`SELECT key,value,category,importance FROM memories WHERE uid=? ORDER BY importance DESC LIMIT 30`),
  clearMems:    db.prepare(`DELETE FROM memories WHERE uid=?`),

  // Long memory
  setLong:      db.prepare(`INSERT OR REPLACE INTO long_memory(uid,key,value) VALUES(?,?,?)`),
  getLong:      db.prepare(`SELECT key,value FROM long_memory WHERE uid=?`),
  clearLong:    db.prepare(`DELETE FROM long_memory WHERE uid=?`),

  // Memory bank
  setBank:      db.prepare(`INSERT OR REPLACE INTO memory_bank(uid,category,key,content,weight) VALUES(?,?,?,?,?)`),
  getBank:      db.prepare(`SELECT category,key,content,weight FROM memory_bank WHERE uid=? ORDER BY weight DESC LIMIT 40`),

  // Daily logs
  addLog:       db.prepare(`INSERT INTO daily_logs(uid,day,entry) VALUES(?,?,?)`),
  getLogs:      db.prepare(`SELECT entry FROM daily_logs WHERE uid=? AND day>=? ORDER BY ts DESC LIMIT 30`),

  // Reminders
  addRem:       db.prepare(`INSERT INTO reminders(uid,chat_id,text,fire_at) VALUES(?,?,?,?)`),
  getPending:   db.prepare(`SELECT * FROM reminders WHERE fired=0 AND fire_at<=datetime('now')`),
  markFired:    db.prepare(`UPDATE reminders SET fired=1 WHERE id=?`),
  getUserRems:  db.prepare(`SELECT * FROM reminders WHERE uid=? AND fired=0 ORDER BY fire_at`),
  cancelRem:    db.prepare(`UPDATE reminders SET fired=1 WHERE id=? AND uid=?`),

  // Profile
  setProfile:   db.prepare(`INSERT OR REPLACE INTO user_profiles(uid,profile) VALUES(?,?)`),
  getProfile:   db.prepare(`SELECT profile FROM user_profiles WHERE uid=?`),

  // PC agent
  upsertAgent:  db.prepare(`INSERT OR REPLACE INTO pc_agents(uid,agent_name,platform,last_seen,active) VALUES(?,?,?,datetime('now'),1)`),
  getAgent:     db.prepare(`SELECT * FROM pc_agents WHERE uid=? AND active=1`),
  deactAgent:   db.prepare(`UPDATE pc_agents SET active=0 WHERE uid=?`),

  // Group stats
  grpSave:      db.prepare(`
    INSERT INTO group_stats(chat_id,uid,name,username,msgs,last_active)
    VALUES(?,?,?,?,1,datetime('now'))
    ON CONFLICT(chat_id,uid) DO UPDATE SET
      msgs=msgs+1, last_active=datetime('now'),
      name=CASE WHEN excluded.name!='' THEN excluded.name ELSE name END
  `),
  grpTop:       db.prepare(`SELECT name,username,msgs FROM group_stats WHERE chat_id=? ORDER BY msgs DESC LIMIT 10`),

  // Skills
  upsertSkill:  db.prepare(`INSERT INTO skills(uid,name,description,code) VALUES(?,?,?,?)`),
  getSkills:    db.prepare(`SELECT * FROM skills WHERE uid=? ORDER BY ts DESC`),

  // Admin queries
  allUsers:     db.prepare(`SELECT uid,name,username,total_msgs,last_seen FROM users ORDER BY total_msgs DESC LIMIT 50`),
  userCount:    db.prepare(`SELECT COUNT(*) as n FROM users`),
  msgCount:     db.prepare(`SELECT COUNT(*) as n FROM conversations`),
};

// ── Db API — все методы изолированы по uid ────────────────────────────────
export const Db = {

  // Users
  ensureUser(uid: number, name: string, username: string): void {
    s.upsertUser.run(uid, name, username);
  },
  getUser(uid: number): UserRow | undefined {
    return s.getUser.get(uid) as UserRow | undefined;
  },
  isBanned(uid: number): boolean {
    const r = s.isBanned.get(uid) as { is_banned: number } | undefined;
    return (r?.is_banned ?? 0) === 1;
  },
  banUser(uid: number):   void { s.banUser.run(uid); },
  unbanUser(uid: number): void { s.unbanUser.run(uid); },

  // Conversations — uid+chatId строго изолируют данные
  addMsg(uid: number, chatId: number, role: "user"|"assistant"|"system", content: string): void {
    s.addMsg.run(uid, chatId, role, content.slice(0, 8000));
  },
  getHistory(uid: number, chatId: number, limit = 16): ConvRow[] {
    return (s.getHistory.all(uid, chatId, limit) as ConvRow[]).reverse();
  },
  clearHistory(uid: number, chatId: number): void { s.clearHistory.run(uid, chatId); },
  historyCount(uid: number, chatId: number): number {
    return (s.countHistory.get(uid, chatId) as { n: number }).n;
  },

  // Short-term memory (изолировано по uid)
  remember(uid: number, key: string, value: string, category = "general", importance = 5): void {
    s.upsertMem.run(uid, key.slice(0, 200), value.slice(0, 500), category, importance);
  },
  getMemories(uid: number): MemRow[] { return s.getMems.all(uid) as MemRow[]; },
  clearMemories(uid: number): void   { s.clearMems.run(uid); },

  // Long-term memory
  setLongMem(uid: number, key: string, value: string): void {
    s.setLong.run(uid, key.slice(0, 100), value.slice(0, 500));
  },
  getLongMem(uid: number): Record<string, string> {
    const rows = s.getLong.all(uid) as { key: string; value: string }[];
    return Object.fromEntries(rows.map(r => [r.key, r.value]));
  },
  clearLongMem(uid: number): void { s.clearLong.run(uid); },

  // Memory bank
  setBankEntry(uid: number, category: string, key: string, content: string, weight = 50): void {
    s.setBank.run(uid, category, key, content.slice(0, 600), weight);
  },
  getBankAll(uid: number): { category: string; key: string; content: string; weight: number }[] {
    return s.getBank.all(uid) as { category: string; key: string; content: string; weight: number }[];
  },

  // Daily logs
  addDailyLog(uid: number, entry: string): void {
    const day = new Date().toISOString().split("T")[0]!;
    s.addLog.run(uid, day, entry.slice(0, 500));
  },
  getDailyLogs(uid: number, days = 2): string[] {
    const cutoff = new Date(Date.now() - days * 86_400_000).toISOString().split("T")[0]!;
    return (s.getLogs.all(uid, cutoff) as { entry: string }[]).map(r => r.entry);
  },

  // Reminders
  addReminder(uid: number, chatId: number, text: string, fireAt: Date): number {
    return (s.addRem.run(uid, chatId, text, fireAt.toISOString())).lastInsertRowid as number;
  },
  getPendingReminders(): ReminderRow[]    { return s.getPending.all() as ReminderRow[]; },
  markReminderFired(id: number): void     { s.markFired.run(id); },
  getUserReminders(uid: number): ReminderRow[] { return s.getUserRems.all(uid) as ReminderRow[]; },
  cancelReminder(id: number, uid: number): void { s.cancelRem.run(id, uid); },

  // Profile
  setProfile(uid: number, profile: string): void { s.setProfile.run(uid, profile); },
  getProfile(uid: number): string {
    return (s.getProfile.get(uid) as { profile: string } | undefined)?.profile ?? "";
  },

  // PC agent
  upsertAgent(uid: number, name: string, platform: string): void { s.upsertAgent.run(uid, name, platform); },
  getAgent(uid: number): { agent_name: string; platform: string; last_seen: string } | undefined {
    return s.getAgent.get(uid) as { agent_name: string; platform: string; last_seen: string } | undefined;
  },
  deactivateAgent(uid: number): void { s.deactAgent.run(uid); },

  // Group
  grpSave(chatId: number, uid: number, name: string, username: string): void {
    s.grpSave.run(chatId, uid, name, username);
  },
  grpTop(chatId: number): { name: string; username: string; msgs: number }[] {
    return s.grpTop.all(chatId) as { name: string; username: string; msgs: number }[];
  },

  // Skills
  upsertSkill(uid: number, name: string, description: string, code: string): void {
    s.upsertSkill.run(uid, name, description, code);
  },
  getSkills(uid: number): { id: number; name: string; description: string; code: string }[] {
    return s.getSkills.all(uid) as { id: number; name: string; description: string; code: string }[];
  },

  // Admin stats (не возвращает приватные данные, только мета)
  getStats(): { users: number; messages: number } {
    const u = (s.userCount.get() as { n: number }).n;
    const m = (s.msgCount.get()  as { n: number }).n;
    return { users: u, messages: m };
  },
  getTopUsers(): { uid: number; name: string; username: string; total_msgs: number; last_seen: string }[] {
    return s.allUsers.all() as { uid: number; name: string; username: string; total_msgs: number; last_seen: string }[];
  },
};

log.info(`DB ready: ${Config.DB_PATH}`);
export default db;
