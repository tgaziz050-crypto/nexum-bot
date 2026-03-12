import * as crypto from 'crypto';
import { db } from '../core/db';

// ── DB schema ─────────────────────────────────────────────────────────────────
db.exec(`
  CREATE TABLE IF NOT EXISTS vector_memories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    uid        INTEGER NOT NULL,
    content    TEXT NOT NULL,
    role       TEXT NOT NULL DEFAULT 'user',
    embedding  TEXT,
    norm       REAL,
    created_at TEXT DEFAULT (datetime('now'))
  );
  CREATE INDEX IF NOT EXISTS idx_vm_uid ON vector_memories(uid);
  CREATE INDEX IF NOT EXISTS idx_vm_created ON vector_memories(created_at);
`);

const _cache: Record<string, number[]> = {};

async function getEmbedding(text: string, apiKey: string): Promise<number[] | null> {
  const hash = crypto.createHash('md5').update(text.slice(0, 500)).digest('hex');
  if (_cache[hash]) return _cache[hash];
  try {
    const resp = await fetch('https://api.openai.com/v1/embeddings', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: 'text-embedding-3-small', input: text.slice(0, 8000) }),
    });
    if (!resp.ok) return null;
    const data = await resp.json() as any;
    const vec = data.data?.[0]?.embedding as number[];
    if (!vec) return null;
    _cache[hash] = vec;
    return vec;
  } catch { return null; }
}

function cosineSim(a: number[], b: number[]): number {
  let dot = 0, na = 0, nb = 0;
  for (let i = 0; i < a.length; i++) { dot += a[i]*b[i]; na += a[i]*a[i]; nb += b[i]*b[i]; }
  if (!na || !nb) return 0;
  return dot / (Math.sqrt(na) * Math.sqrt(nb));
}

function temporalScore(createdAt: string): number {
  const ageDays = (Date.now() - new Date(createdAt).getTime()) / 86400000;
  return Math.exp(-0.05 * ageDays);
}

export interface MemoryEntry {
  id: number; uid: number; content: string; role: string; createdAt: string; score?: number;
}

export async function saveToVectorMemory(uid: number, content: string, role: 'user'|'assistant' = 'user', apiKey?: string): Promise<void> {
  const key = apiKey || process.env.OPENAI_API_KEY;
  let embedding: number[] | null = null;
  let norm: number | null = null;
  if (key && content.trim().length > 3) {
    embedding = await getEmbedding(content, key);
    if (embedding) { let n=0; for(const x of embedding) n+=x*x; norm=Math.sqrt(n); }
  }
  db.prepare('INSERT INTO vector_memories (uid, content, role, embedding, norm) VALUES (?, ?, ?, ?, ?)').run(
    uid, content, role, embedding ? JSON.stringify(embedding) : null, norm
  );
  db.prepare('DELETE FROM vector_memories WHERE uid = ? AND id NOT IN (SELECT id FROM vector_memories WHERE uid = ? ORDER BY id DESC LIMIT 1000)').run(uid, uid);
}

export async function getRelevantContext(uid: number, query: string, opts: { k?: number; apiKey?: string } = {}): Promise<string> {
  const k = opts.k ?? 5;
  const key = opts.apiKey || process.env.OPENAI_API_KEY;

  const rows = db.prepare('SELECT id, uid, content, role, embedding, norm, created_at FROM vector_memories WHERE uid = ? ORDER BY id DESC LIMIT 500').all(uid) as any[];
  if (!rows.length) return '';

  if (!key) {
    const textRows = db.prepare('SELECT content, role, created_at FROM vector_memories WHERE uid = ? AND content LIKE ? ORDER BY id DESC LIMIT ?').all(uid, `%${query.slice(0,50)}%`, k) as any[];
    if (!textRows.length) return '';
    return '\n[Из памяти:]\n' + textRows.map((r:any) => `${r.role}: ${r.content.slice(0,200)}`).join('\n') + '\n';
  }

  const queryVec = await getEmbedding(query, key);
  if (!queryVec) return '';

  const scored = rows.map((r: any) => {
    if (!r.embedding) return null;
    try {
      const vec = JSON.parse(r.embedding) as number[];
      const sim = cosineSim(queryVec, vec);
      const decay = temporalScore(r.created_at);
      return { content: r.content, role: r.role, createdAt: r.created_at, score: sim * 0.8 + decay * 0.2 };
    } catch { return null; }
  }).filter((x): x is NonNullable<typeof x> => x !== null && x.score > 0.1);

  scored.sort((a, b) => b.score - a.score);
  const top = scored.slice(0, k);
  if (!top.length) return '';
  return '\n[Из памяти:]\n' + top.map(m => `${m.role}: ${m.content.slice(0, 200)}`).join('\n') + '\n';
}

export function clearVectorMemory(uid: number): void {
  db.prepare('DELETE FROM vector_memories WHERE uid = ?').run(uid);
}
