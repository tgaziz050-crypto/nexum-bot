import { config, getKey } from '../core/config';

export interface Message { role: 'user' | 'assistant' | 'system'; content: string | any[]; }

async function callCerebras(messages: Message[], key: string): Promise<string> {
  const r = await fetch('https://api.cerebras.ai/v1/chat/completions', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${key}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: 'llama-3.3-70b', messages, max_tokens: 2048, temperature: 0.7 })
  });
  if (!r.ok) throw new Error(`Cerebras ${r.status}`);
  const d = await r.json() as any;
  return d.choices[0].message.content;
}

async function callGroq(messages: Message[], key: string): Promise<string> {
  const r = await fetch('https://api.groq.com/openai/v1/chat/completions', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${key}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: 'llama-3.3-70b-versatile', messages, max_tokens: 2048, temperature: 0.7 })
  });
  if (!r.ok) throw new Error(`Groq ${r.status}`);
  const d = await r.json() as any;
  return d.choices[0].message.content;
}

async function callGemini(messages: Message[], key: string, hasImage = false): Promise<string> {
  const model = 'gemini-1.5-flash';
  const contents = messages.filter(m => m.role !== 'system').map(m => {
    if (!Array.isArray(m.content)) return { role: m.role === 'assistant' ? 'model' : 'user', parts: [{ text: m.content }] };
    // Convert OpenAI image_url format → Gemini inline_data format
    const parts = m.content.map((p: any) => {
      if (p.type === 'image_url' && p.image_url?.url) {
        const match = p.image_url.url.match(/^data:([^;]+);base64,(.+)$/);
        if (match) return { inline_data: { mime_type: match[1], data: match[2] } };
      }
      if (p.type === 'text') return { text: p.text };
      return p;
    });
    return { role: m.role === 'assistant' ? 'model' : 'user', parts };
  });
  const systemMsg = messages.find(m => m.role === 'system');
  const body: any = { contents, generationConfig: { maxOutputTokens: 2048, temperature: 0.7 } };
  if (systemMsg) body.systemInstruction = { parts: [{ text: systemMsg.content }] };

  const r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${key}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!r.ok) throw new Error(`Gemini ${r.status}`);
  const d = await r.json() as any;
  return d.candidates[0].content.parts[0].text;
}

async function callOpenRouter(messages: Message[], key: string): Promise<string> {
  const r = await fetch('https://openrouter.ai/api/v1/chat/completions', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${key}`, 'Content-Type': 'application/json', 'HTTP-Referer': 'https://nexum.app' },
    body: JSON.stringify({ model: 'meta-llama/llama-3.3-70b-instruct', messages, max_tokens: 2048 })
  });
  if (!r.ok) throw new Error(`OpenRouter ${r.status}`);
  const d = await r.json() as any;
  return d.choices[0].message.content;
}

async function callDeepSeek(messages: Message[], key: string): Promise<string> {
  const r = await fetch('https://api.deepseek.com/chat/completions', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${key}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: 'deepseek-chat', messages, max_tokens: 2048 })
  });
  if (!r.ok) throw new Error(`DeepSeek ${r.status}`);
  const d = await r.json() as any;
  return d.choices[0].message.content;
}

async function callSambaNova(messages: Message[], key: string): Promise<string> {
  const r = await fetch('https://api.sambanova.ai/v1/chat/completions', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${key}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: 'Meta-Llama-3.3-70B-Instruct', messages, max_tokens: 2048 })
  });
  if (!r.ok) throw new Error(`SambaNova ${r.status}`);
  const d = await r.json() as any;
  return d.choices[0].message.content;
}

async function callTogether(messages: Message[], key: string): Promise<string> {
  const r = await fetch('https://api.together.xyz/v1/chat/completions', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${key}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: 'meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo', messages, max_tokens: 2048 })
  });
  if (!r.ok) throw new Error(`Together ${r.status}`);
  const d = await r.json() as any;
  return d.choices[0].message.content;
}

export async function chat(messages: Message[], hasImage = false): Promise<string> {
  // If image present, prefer Gemini
  if (hasImage) {
    const gKey = getKey('gemini');
    if (gKey) {
      try { return await callGemini(messages, gKey, true); } catch (e) { console.warn('[gemini vision]', e); }
    }
  }

  const providers: Array<[string, () => Promise<string>]> = [];

  const cb = getKey('cerebras');
  if (cb) providers.push(['cerebras', () => callCerebras(messages, cb)]);

  const gr = getKey('groq');
  if (gr) providers.push(['groq', () => callGroq(messages, gr)]);

  const gm = getKey('gemini');
  if (gm) providers.push(['gemini', () => callGemini(messages, gm)]);

  const or = getKey('openrouter');
  if (or) providers.push(['openrouter', () => callOpenRouter(messages, or)]);

  const ds = getKey('deepseek');
  if (ds) providers.push(['deepseek', () => callDeepSeek(messages, ds)]);

  const sn = getKey('sambanova');
  if (sn) providers.push(['sambanova', () => callSambaNova(messages, sn)]);

  const to = getKey('together');
  if (to) providers.push(['together', () => callTogether(messages, to)]);

  for (const [name, fn] of providers) {
    try {
      const result = await fn();
      console.log(`[ai] provider=${name}`);
      return result;
    } catch (e) {
      console.warn(`[ai] ${name} failed:`, e);
    }
  }

  return '❌ Все AI-провайдеры недоступны. Проверьте ключи.';
}
