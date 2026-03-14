import { getKey, config } from '../core/config';
import { getUserApiKey } from '../core/db';

export interface Message {
  role: 'user' | 'assistant' | 'system';
  content: string | any[];
}

// ── Provider callers ──────────────────────────────────────────────────────────

async function cerebras(msgs: Message[], key: string): Promise<string> {
  const r = await fetch('https://api.cerebras.ai/v1/chat/completions', {
    method: 'POST',
    headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: 'llama-3.3-70b', messages: msgs, max_tokens: 2048, temperature: 0.7 }),
  });
  if (!r.ok) throw new Error(`Cerebras ${r.status}`);
  return ((await r.json()) as any).choices[0].message.content;
}

async function groq(msgs: Message[], key: string): Promise<string> {
  const r = await fetch('https://api.groq.com/openai/v1/chat/completions', {
    method: 'POST',
    headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: 'llama-3.3-70b-versatile', messages: msgs, max_tokens: 2048, temperature: 0.7 }),
  });
  if (!r.ok) throw new Error(`Groq ${r.status}`);
  return ((await r.json()) as any).choices[0].message.content;
}

async function gemini(msgs: Message[], key: string, vision = false): Promise<string> {
  const model = vision ? 'gemini-1.5-flash' : 'gemini-1.5-flash';
  const contents = msgs
    .filter(m => m.role !== 'system')
    .map(m => {
      if (!Array.isArray(m.content)) {
        return { role: m.role === 'assistant' ? 'model' : 'user', parts: [{ text: m.content }] };
      }
      const parts = (m.content as any[]).map((p: any) => {
        if (p.type === 'image_url' && p.image_url?.url) {
          const match = p.image_url.url.match(/^data:([^;]+);base64,(.+)$/);
          if (match) return { inline_data: { mime_type: match[1], data: match[2] } };
        }
        if (p.type === 'text') return { text: p.text };
        return p;
      });
      return { role: m.role === 'assistant' ? 'model' : 'user', parts };
    });
  const sys = msgs.find(m => m.role === 'system');
  const body: any = { contents, generationConfig: { maxOutputTokens: 2048, temperature: 0.7 } };
  if (sys) body.systemInstruction = { parts: [{ text: sys.content }] };
  const r = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${key}`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
  );
  if (!r.ok) throw new Error(`Gemini ${r.status}`);
  const d = (await r.json()) as any;
  return d.candidates[0].content.parts[0].text;
}

async function openrouter(msgs: Message[], key: string): Promise<string> {
  const r = await fetch('https://openrouter.ai/api/v1/chat/completions', {
    method: 'POST',
    headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json', 'HTTP-Referer': 'https://nexum.app' },
    body: JSON.stringify({ model: 'meta-llama/llama-3.3-70b-instruct', messages: msgs, max_tokens: 2048 }),
  });
  if (!r.ok) throw new Error(`OpenRouter ${r.status}`);
  return ((await r.json()) as any).choices[0].message.content;
}

async function deepseek(msgs: Message[], key: string): Promise<string> {
  const r = await fetch('https://api.deepseek.com/chat/completions', {
    method: 'POST',
    headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: 'deepseek-chat', messages: msgs, max_tokens: 2048 }),
  });
  if (!r.ok) throw new Error(`DeepSeek ${r.status}`);
  return ((await r.json()) as any).choices[0].message.content;
}

async function sambanova(msgs: Message[], key: string): Promise<string> {
  const r = await fetch('https://api.sambanova.ai/v1/chat/completions', {
    method: 'POST',
    headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: 'Meta-Llama-3.3-70B-Instruct', messages: msgs, max_tokens: 2048 }),
  });
  if (!r.ok) throw new Error(`SambaNova ${r.status}`);
  return ((await r.json()) as any).choices[0].message.content;
}

async function together(msgs: Message[], key: string): Promise<string> {
  const r = await fetch('https://api.together.xyz/v1/chat/completions', {
    method: 'POST',
    headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: 'meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo', messages: msgs, max_tokens: 2048 }),
  });
  if (!r.ok) throw new Error(`Together ${r.status}`);
  return ((await r.json()) as any).choices[0].message.content;
}

async function grok(msgs: Message[], key: string): Promise<string> {
  const r = await fetch('https://api.x.ai/v1/chat/completions', {
    method: 'POST',
    headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: 'grok-beta', messages: msgs, max_tokens: 2048 }),
  });
  if (!r.ok) throw new Error(`Grok ${r.status}`);
  return ((await r.json()) as any).choices[0].message.content;
}

async function claude(msgs: Message[], key: string): Promise<string> {
  const system = msgs.find(m => m.role === 'system')?.content as string || '';
  const filtered = msgs.filter(m => m.role !== 'system');
  const r = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: { 'x-api-key': key, 'anthropic-version': '2023-06-01', 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: 'claude-haiku-4-5-20251001', max_tokens: 2048, system, messages: filtered }),
  });
  if (!r.ok) throw new Error(`Claude ${r.status}`);
  const d = (await r.json()) as any;
  return d.content[0].text;
}

// ── Main chat function ────────────────────────────────────────────────────────
export async function chat(messages: Message[], hasImage = false, uid?: number): Promise<string> {
  // Check user API keys first
  if (uid) {
    const providers: Array<[string, () => Promise<string>]> = [];
    const userCb = getUserApiKey(uid, 'cerebras'); if (userCb) providers.push(['cerebras', () => cerebras(messages, userCb)]);
    const userGr = getUserApiKey(uid, 'groq');     if (userGr) providers.push(['groq',     () => groq(messages, userGr)]);
    const userGm = getUserApiKey(uid, 'gemini');   if (userGm) providers.push(['gemini',   () => gemini(messages, userGm, hasImage)]);
    const userOr = getUserApiKey(uid, 'openrouter'); if (userOr) providers.push(['openrouter', () => openrouter(messages, userOr)]);
    const userDs = getUserApiKey(uid, 'deepseek'); if (userDs) providers.push(['deepseek', () => deepseek(messages, userDs)]);
    const userCl = getUserApiKey(uid, 'claude');   if (userCl) providers.push(['claude',   () => claude(messages, userCl)]);

    for (const [name, fn] of providers) {
      try {
        const result = await fn();
        console.log(`[ai] user_key provider=${name} uid=${uid}`);
        return result;
      } catch (e) {
        console.warn(`[ai] user ${name} failed:`, e);
      }
    }
  }

  // Vision: prefer Gemini
  if (hasImage) {
    const gKey = getKey('gemini');
    if (gKey) {
      try { return await gemini(messages, gKey, true); } catch (e) { console.warn('[gemini vision]', e); }
    }
  }

  // System key round-robin fallback chain
  const chain: Array<[string, () => Promise<string>]> = [];
  const k = (p: keyof typeof config.ai) => getKey(p);
  if (k('cerebras'))   chain.push(['cerebras',   () => cerebras(messages,   k('cerebras')!)]);
  if (k('groq'))       chain.push(['groq',        () => groq(messages,       k('groq')!)]);
  if (k('gemini'))     chain.push(['gemini',      () => gemini(messages,     k('gemini')!, false)]);
  if (k('grok'))       chain.push(['grok',        () => grok(messages,       k('grok')!)]);
  if (k('openrouter')) chain.push(['openrouter',  () => openrouter(messages, k('openrouter')!)]);
  if (k('deepseek'))   chain.push(['deepseek',    () => deepseek(messages,   k('deepseek')!)]);
  if (k('sambanova'))  chain.push(['sambanova',   () => sambanova(messages,  k('sambanova')!)]);
  if (k('together'))   chain.push(['together',    () => together(messages,   k('together')!)]);
  if (k('claude'))     chain.push(['claude',      () => claude(messages,     k('claude')!)]);

  for (const [name, fn] of chain) {
    try {
      const result = await fn();
      console.log(`[ai] provider=${name}`);
      return result;
    } catch (e) {
      console.warn(`[ai] ${name} failed:`, e);
    }
  }

  return '❌ Все AI-провайдеры недоступны. Проверь ключи в Railway.';
}
