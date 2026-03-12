import { db } from '../core/db';

export function saveMemory(uid: number, key: string, value: string) {
  db.prepare(`INSERT INTO memory (uid, key, value) VALUES (?, ?, ?)
    ON CONFLICT(uid, key) DO UPDATE SET value=excluded.value`).run(uid, key, value);
}

export function getMemories(uid: number): Array<{ key: string; value: string }> {
  return db.prepare('SELECT key, value FROM memory WHERE uid = ? ORDER BY created_at DESC LIMIT 20').all(uid) as any;
}

export function clearMemory(uid: number) {
  db.prepare('DELETE FROM memory WHERE uid = ?').run(uid);
}

export function saveMessage(uid: number, role: 'user' | 'assistant', content: string) {
  db.prepare('INSERT INTO conversations (uid, role, content) VALUES (?, ?, ?)').run(uid, role, content);
  // Keep only last 30 messages
  db.prepare(`DELETE FROM conversations WHERE uid = ? AND id NOT IN (
    SELECT id FROM conversations WHERE uid = ? ORDER BY id DESC LIMIT 30
  )`).run(uid, uid);
}

export function getHistory(uid: number, limit = 10): Array<{ role: string; content: string }> {
  return (db.prepare('SELECT role, content FROM conversations WHERE uid = ? ORDER BY id DESC LIMIT ?').all(uid, limit) as any).reverse();
}

export function clearHistory(uid: number) {
  db.prepare('DELETE FROM conversations WHERE uid = ?').run(uid);
}
