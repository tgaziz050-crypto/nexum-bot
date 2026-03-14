import { db } from '../core/db';

export function saveMemory(uid: number, key: string, value: string) {
  db.prepare(`
    INSERT INTO memory (uid, key, value) VALUES (?, ?, ?)
    ON CONFLICT(uid, key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')
  `).run(uid, key, value);
}

export function getMemories(uid: number): Array<{ key: string; value: string }> {
  return db.prepare('SELECT key, value FROM memory WHERE uid=? ORDER BY id DESC LIMIT 30').all(uid) as any;
}

export function clearMemory(uid: number) {
  db.prepare('DELETE FROM memory WHERE uid=?').run(uid);
}

export function saveMessage(uid: number, role: 'user' | 'assistant', content: string) {
  db.prepare('INSERT INTO conversations (uid, role, content) VALUES (?,?,?)').run(uid, role, content.slice(0, 4000));
  // Keep last 120 per user
  db.prepare(`
    DELETE FROM conversations WHERE uid=? AND id NOT IN (
      SELECT id FROM conversations WHERE uid=? ORDER BY id DESC LIMIT 120
    )
  `).run(uid, uid);
}

export function getHistory(uid: number, limit = 12): Array<{ role: string; content: string }> {
  return (db.prepare('SELECT role, content FROM conversations WHERE uid=? ORDER BY id DESC LIMIT ?').all(uid, limit) as any[]).reverse();
}

export function clearHistory(uid: number) {
  db.prepare('DELETE FROM conversations WHERE uid=?').run(uid);
}

// Auto-extract facts from conversation
export function autoExtract(uid: number, userText: string) {
  const save = (k: string, v: string) => saveMemory(uid, k, v);
  const nameMatch = userText.match(/меня зовут\s+([А-ЯЁA-Z][а-яёa-z]+)/i);
  if (nameMatch) save('name', nameMatch[1]);
  const cityMatch = userText.match(/(?:я из|живу в|нахожусь в)\s+([А-ЯЁA-Z][а-яёa-z]+)/i);
  if (cityMatch) save('city', cityMatch[1]);
  const ageMatch = userText.match(/мне\s+(\d{1,2})\s+лет/i);
  if (ageMatch) save('age', ageMatch[1]);
  if (/работаю|разработчик|дизайнер|менеджер|врач|учитель|студент/i.test(userText)) {
    save('occupation', userText.slice(0, 80));
  }
}
