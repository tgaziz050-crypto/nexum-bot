import Database = require('better-sqlite3');
import path = require('path');
import fs = require('fs');

const DB_PATH = process.env.DB_PATH || path.join(process.cwd(), 'data', 'nexum.db');

fs.mkdirSync(path.dirname(DB_PATH), { recursive: true });

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const db: any = new (Database as any)(DB_PATH);

db.pragma('journal_mode = WAL');
db.pragma('foreign_keys = ON');

db.exec(`
  CREATE TABLE IF NOT EXISTS users (
    uid INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    lang TEXT DEFAULT 'ru',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid INTEGER NOT NULL,
    title TEXT,
    content TEXT NOT NULL,
    pinned INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    project TEXT DEFAULT 'General',
    priority TEXT DEFAULT 'medium',
    status TEXT DEFAULT 'todo',
    due_date TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS habits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid INTEGER NOT NULL,
    name TEXT NOT NULL,
    emoji TEXT DEFAULT '🎯',
    frequency TEXT DEFAULT 'daily',
    streak INTEGER DEFAULT 0,
    best_streak INTEGER DEFAULT 0,
    last_done TEXT,
    created_at TEXT DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS habit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    habit_id INTEGER NOT NULL,
    uid INTEGER NOT NULL,
    done_at TEXT DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS finance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid INTEGER NOT NULL,
    type TEXT NOT NULL,
    amount REAL NOT NULL,
    category TEXT DEFAULT 'Other',
    note TEXT,
    created_at TEXT DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS budgets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid INTEGER NOT NULL,
    category TEXT NOT NULL,
    amount REAL NOT NULL,
    month TEXT NOT NULL,
    UNIQUE(uid, category, month)
  );

  CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    fire_at TEXT NOT NULL,
    done INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid INTEGER NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(uid, key)
  );

  CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS pc_agents (
    uid INTEGER PRIMARY KEY,
    device_id TEXT,
    platform TEXT,
    ws_id TEXT,
    last_seen TEXT
  );

  CREATE TABLE IF NOT EXISTS link_codes (
    code TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    platform TEXT,
    created_at TEXT DEFAULT (datetime('now'))
  );
`);

export function ensureUser(uid: number, username?: string, firstName?: string) {
  db.prepare(`
    INSERT INTO users (uid, username, first_name) VALUES (?, ?, ?)
    ON CONFLICT(uid) DO UPDATE SET username=excluded.username, first_name=excluded.first_name, updated_at=datetime('now')
  `).run(uid, username || null, firstName || null);
}
