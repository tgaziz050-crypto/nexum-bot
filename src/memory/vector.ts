/**
 * NEXUM Vector Memory Module
 * Архитектура взята из OpenClaw src/memory/
 *
 * Возможности:
 *  - Семантический поиск по истории разговоров
 *  - Embeddings через OpenAI API (text-embedding-3-small)
 *  - Хранение в SQLite (совместим с existing DB)
 *  - Temporal decay — свежие воспоминания важнее
 *  - MMR (Maximal Marginal Relevance) — разнообразные результаты
 *  - Автоматическая индексация входящих сообщений
 */

import * as crypto from 'crypto';
import { db } from '../core/db';

// ─── DB schema ────────────────────────────────────────────────────────────────

db.exec(`
  CREATE TABLE IF NOT EXISTS vector_memories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    uid        INTEGER NOT NULL,
    content    TEXT NOT NULL,
    role       TEXT NOT NULL DEFAULT 'user',
    embedding  BLOB,          -- JSON array stored as text
    norm       REAL,          -- precomputed L2 norm
    created_at TEXT DEFAULT (datetime('now')),
    decay_at   TEXT           -- null = never decays
  );

  CREATE INDEX IF NOT EXISTS idx_vm_uid ON vector_memories(uid);
  CREATE INDEX IF NOT EXISTS idx_vm_created ON vector_memories(created_at);
`);

// ─── Embeddings ───────────────────────────────────────────────────────────────

const EMBEDDING_MODEL = 'text-embedding-3-small';
const EMBEDDING_DIM = 1536;
const OPENAI_BASE = 'https://api.openai.com/v1';

interface EmbeddingCache {
  [hash: string]: number[];
}
const _cache: EmbeddingCache = {};

async function getEmbedding(text: string, apiKey: string): Promise<number[] | null> {
  const hash = crypto.createHash('md5').update(text.slice(0, 500)).digest('hex');
  if (_cache[hash]) return _cache[hash];

  try {
    const resp = await fetch(`${OPENAI_BASE}/embeddings`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ model: EMBEDDING_MODEL, input: text.slice(0, 8000) }),
    });

    if (!resp.ok) {
      console.warn('[VectorMemory] Embedding API error:', resp.status);
      return null;
    }

    const data = await resp.json() as any;
    const vec = data.data?.[0]?.embedding as number[];
    if (!vec) return null;

    _cache[hash] = vec;
    return vec;
  } catch (e) {
    console.warn('[VectorMemory] Embedding fetch failed:', e);
    return null;
  }
}

// ─── Math utilities ───────────────────────────────────────────────────────────

function dotProduct(a: number[], b: number[]): number {
  let sum = 0;
  const len = Math.min(a.length, b.length);
  for (let i = 0; i < len; i++) sum += a[i] * b[i];
  return sum;
}

function l2Norm(v: number[]): number {
  return Math.sqrt(v.reduce((s, x) => s + x * x, 0));
}

function cosineSim(a: number[], b: number[], normA?: number, normB?: number): number {
  const dot = dotProduct(a, b);
  const na = normA ?? l2Norm(a);
  const nb = normB ?? l2Norm(b);
  if (na === 0 || nb === 0) return 0;
  return dot / (na * nb);
}

/**
 * Temporal decay — как в OpenClaw src/memory/temporal-decay.ts
 * Свежие записи получают бонус к релевантности
 */
function temporalScore(createdAt: string, decayFactor = 0.1): number {
  const ageMs = Date.now() - new Date(createdAt).getTime();
  const ageDays = ageMs / (1000 * 60 * 60 * 24);
  return Math.exp(-decayFactor * ageDays);
}

/**
 * MMR — Maximal Marginal Relevance
 * Как в OpenClaw src/memory/mmr.ts
 * Возвращает разнообразные результаты, а не все похожие
 */
function mmrSelect(
  candidates: { text: string; vec: number[]; norm: number; score: number; createdAt: string }[],
  k: number,
  lambda = 0.5,
): typeof candidates {
  if (candidates.length === 0) return [];
  const selected: typeof candidates = [];
  const remaining = [...candidates];

  while (selected.length < k && remaining.length > 0) {
    if (selected.length === 0) {
      // First: highest relevance
      const best = remaining.reduce((a, b) => a.score > b.score ? a : b);
      selected.push(best);
      remaining.splice(remaining.indexOf(best), 1);
      continue;
    }

    // MMR score = λ * relevance - (1-λ) * max_similarity_to_selected
    let bestIdx = 0;
    let bestMmr = -Infinity;

    for (let i = 0; i < remaining.length; i++) {
      const rel = remaining[i].score;
      const maxSim = Math.max(...selected.map(s =>
        cosineSim(remaining[i].vec, s.vec, remaining[i].norm, s.norm)
      ));
      const mmr = lambda * rel - (1 - lambda) * maxSim;
      if (mmr > bestMmr) { bestMmr = mmr; bestIdx = i; }
    }

    selected.push(remaining[bestIdx]);
    remaining.splice(bestIdx, 1);
  }

  return selected;
}

// ─── Public API ───────────────────────────────────────────────────────────────

export interface MemoryEntry {
  id: number;
  uid: number;
  content: string;
  role: string;
  createdAt: string;
  score?: number; // only in search results
}

/**
 * Сохранить сообщение в векторную память
 * Если OPENAI_API_KEY есть — создаёт embedding, иначе сохраняет без него (только текстовый поиск)
 */
export async function saveToVectorMemory(
  uid: number,
  content: string,
  role: 'user' | 'assistant' = 'user',
  apiKey?: string,
): Promise<void> {
  const key = apiKey || process.env.OPENAI_API_KEY;
  let embedding: number[] | null = null;
  let norm: number | null = null;

  if (key && content.trim().length > 3) {
    embedding = await getEmbedding(content, key);
    if (embedding) norm = l2Norm(embedding);
  }

  db.prepare(`
    INSERT INTO vector_memories (uid, content, role, embedding, norm)
    VALUES (?, ?, ?, ?, ?)
  `).run(
    uid,
    content,
    role,
    embedding ? JSON.stringify(embedding) : null,
    norm,
  );

  // Keep max 1000 per user
  db.prepare(`
    DELETE FROM vector_memories
    WHERE uid = ? AND id NOT IN (
      SELECT id FROM vector_memories WHERE uid = ? ORDER BY id DESC LIMIT 1000
    )
  `).run(uid, uid);
}

/**
 * Семантический поиск по памяти
 * Если embeddings есть — косинусное сходство + temporal decay + MMR
 * Если нет — fallback на FTS (LIKE)
 */
export async function searchVectorMemory(
  uid: number,
  query: string,
  opts: {
    k?: number;
    apiKey?: string;
    lambda?: number;  // MMR diversity (0=max diversity, 1=max relevance)
    decayFactor?: number;
    minScore?: number;
  } = {},
): Promise<MemoryEntry[]> {
  const k = opts.k ?? 5;
  const key = opts.apiKey || process.env.OPENAI_API_KEY;
  const lambda = opts.lambda ?? 0.7;
  const decayFactor = opts.decayFactor ?? 0.05;

  // Get all memories with embeddings for this user
  const rows = db.prepare(`
    SELECT id, uid, content, role, embedding, norm, created_at
    FROM vector_memories
    WHERE uid = ? AND embedding IS NOT NULL
    ORDER BY id DESC LIMIT 500
  `).all(uid) as any[];

  if (rows.length === 0 || !key) {
    // Fallback: simple text search
    const textRows = db.prepare(`
      SELECT id, uid, content, role, created_at
      FROM vector_memories
      WHERE uid = ? AND content LIKE ?
      ORDER BY id DESC LIMIT ?
    `).all(uid, `%${query}%`, k) as any[];

    return textRows.map(r => ({
      id: r.id, uid: r.uid, content: r.content,
      role: r.role, createdAt: r.created_at, score: 0.5,
    }));
  }

  // Get query embedding
  const queryVec = await getEmbedding(query, key);
  if (!queryVec) {
    // Fallback to text
    return searchVectorMemory(uid, query, { ...opts, apiKey: undefined });
  }
  const queryNorm = l2Norm(queryVec);

  // Score each memory
  const candidates = rows
    .map(row => {
      let vec: number[];
      try { vec = JSON.parse(row.embedding); }
      catch { return null; }

      const norm = row.norm || l2Norm(vec);
      const sim = cosineSim(queryVec, vec, queryNorm, norm);
      const decay = temporalScore(row.created_at, decayFactor);
      const score = sim * 0.8 + decay * 0.2; // weighted

      return {
        id: row.id, uid: row.uid, content: row.content,
        role: row.role, createdAt: row.created_at,
        vec, norm, score,
      };
    })
    .filter((x): x is NonNullable<typeof x> => x !== null && x.score > (opts.minScore ?? 0.1));

  candidates.sort((a, b) => b.score - a.score);

  // Apply MMR for diversity
  const selected = mmrSelect(candidates.slice(0, 50), k, lambda);

  return selected.map(s => ({
    id: s.id, uid: s.uid, content: s.content,
    role: s.role, createdAt: s.createdAt, score: s.score,
  }));
}

/**
 * Форматированный контекст для вставки в промпт
 */
export async function getRelevantContext(
  uid: number,
  query: string,
  opts: { k?: number; apiKey?: string } = {},
): Promise<string> {
  const memories = await searchVectorMemory(uid, query, opts);
  if (memories.length === 0) return '';

  const lines = memories.map(m => {
    const date = new Date(m.createdAt).toLocaleDateString('ru-RU');
    const score = m.score ? ` (${(m.score * 100).toFixed(0)}%)` : '';
    return `[${date}${score}] ${m.role}: ${m.content.slice(0, 300)}`;
  });

  return `\n\n[Из памяти — похожие разговоры:]\n${lines.join('\n')}\n`;
}

export function getVectorMemoryStats(uid: number): { total: number; withEmbeddings: number } {
  const total = (db.prepare('SELECT COUNT(*) as c FROM vector_memories WHERE uid = ?').get(uid) as any).c;
  const withEmbeddings = (db.prepare('SELECT COUNT(*) as c FROM vector_memories WHERE uid = ? AND embedding IS NOT NULL').get(uid) as any).c;
  return { total, withEmbeddings };
}

export function clearVectorMemory(uid: number): void {
  db.prepare('DELETE FROM vector_memories WHERE uid = ?').run(uid);
}
