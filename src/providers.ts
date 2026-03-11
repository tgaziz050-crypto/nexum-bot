import { Config } from "../core/config.js";
import { log } from "../core/logger.js";

export type Msg = { role: "system" | "user" | "assistant"; content: string };

// Round-robin индексы и счётчики ошибок per-ключ
const idx:   Record<string, number> = {};
const fails: Record<string, number> = {};

function nextKey(pool: string, keys: readonly string[]): string | null {
  if (!keys.length) return null;
  const start = idx[pool] ?? 0;
  for (let i = 0; i < keys.length; i++) {
    const ki = (start + i) % keys.length;
    const k  = `${pool}:${ki}`;
    if ((fails[k] ?? 0) < 3) { idx[pool] = (ki + 1) % keys.length; return keys[ki]!; }
  }
  // Сбрасываем счётчики если все ключи "упали"
  for (let i = 0; i < keys.length; i++) fails[`${pool}:${i}`] = 0;
  idx[pool] = 0;
  return keys[0]!;
}
function markFail(pool: string, key: string, keys: readonly string[]) {
  const ki = keys.indexOf(key);
  if (ki >= 0) fails[`${pool}:${ki}`] = (fails[`${pool}:${ki}`] ?? 0) + 1;
}

async function post(url: string, headers: Record<string, string>, body: unknown, timeout = 30_000): Promise<unknown> {
  const ctrl = new AbortController();
  const tid  = setTimeout(() => ctrl.abort(), timeout);
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...headers },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } finally {
    clearTimeout(tid);
  }
}

export async function cerebras(msgs: Msg[], maxTokens = 8192): Promise<string> {
  const key = nextKey("cb", Config.CEREBRAS_KEYS);
  if (!key) throw new Error("No Cerebras keys");
  try {
    const d = await post("https://api.cerebras.ai/v1/chat/completions",
      { Authorization: `Bearer ${key}` },
      { model: "llama-3.3-70b", messages: msgs, max_tokens: maxTokens, temperature: 0.8 }
    ) as { choices: { message: { content: string } }[] };
    const text = d.choices?.[0]?.message?.content ?? "";
    if (!text) throw new Error("Empty");
    return text;
  } catch (e) { markFail("cb", key, Config.CEREBRAS_KEYS); throw e; }
}

export async function groq(msgs: Msg[], model = "llama-3.3-70b-versatile", maxTokens = 6000): Promise<string> {
  const key = nextKey("gr", Config.GROQ_KEYS);
  if (!key) throw new Error("No Groq keys");
  try {
    const d = await post("https://api.groq.com/openai/v1/chat/completions",
      { Authorization: `Bearer ${key}` },
      { model, messages: msgs, max_tokens: maxTokens, temperature: 0.8 }
    ) as { choices: { message: { content: string } }[] };
    const text = d.choices?.[0]?.message?.content ?? "";
    if (!text) throw new Error("Empty");
    return text;
  } catch (e) { markFail("gr", key, Config.GROQ_KEYS); throw e; }
}

export async function gemini(msgs: Msg[], model = "gemini-2.0-flash", maxTokens = 8192): Promise<string> {
  const key = nextKey("g", Config.GEMINI_KEYS);
  if (!key) throw new Error("No Gemini keys");
  try {
    const contents = msgs.filter(m => m.role !== "system").map(m => ({
      role: m.role === "assistant" ? "model" : "user",
      parts: [{ text: m.content }],
    }));
    const sysMsg = msgs.find(m => m.role === "system");
    const body: Record<string, unknown> = {
      contents,
      generationConfig: { maxOutputTokens: maxTokens, temperature: 0.85 },
      safetySettings: ["HARM_CATEGORY_HARASSMENT","HARM_CATEGORY_HATE_SPEECH",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT","HARM_CATEGORY_DANGEROUS_CONTENT"].map(c => ({ category: c, threshold: "BLOCK_NONE" })),
    };
    if (sysMsg) body.systemInstruction = { parts: [{ text: sysMsg.content }] };
    const d = await post(
      `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${key}`, {}, body
    ) as { candidates: { content: { parts: { text: string }[] } }[] };
    const text = d.candidates?.[0]?.content?.parts?.[0]?.text ?? "";
    if (!text) throw new Error("Empty");
    return text;
  } catch (e) { markFail("g", key, Config.GEMINI_KEYS); throw e; }
}

export async function grok(msgs: Msg[], model = "grok-3-mini-fast", maxTokens = 8192): Promise<string> {
  const key = nextKey("gk", Config.GROK_KEYS);
  if (!key) throw new Error("No Grok keys");
  try {
    const d = await post("https://api.x.ai/v1/chat/completions",
      { Authorization: `Bearer ${key}` },
      { model, messages: msgs, max_tokens: maxTokens, temperature: 0.8 }
    ) as { choices: { message: { content: string } }[] };
    const text = d.choices?.[0]?.message?.content ?? "";
    if (!text) throw new Error("Empty");
    return text;
  } catch (e) { markFail("gk", key, Config.GROK_KEYS); throw e; }
}

export async function sambanova(msgs: Msg[], model = "Meta-Llama-3.3-70B-Instruct", maxTokens = 8192): Promise<string> {
  const key = nextKey("sn", Config.SAMBANOVA_KEYS);
  if (!key) throw new Error("No SambaNova keys");
  try {
    const d = await post("https://api.sambanova.ai/v1/chat/completions",
      { Authorization: `Bearer ${key}` },
      { model, messages: msgs, max_tokens: maxTokens, temperature: 0.8 }
    ) as { choices: { message: { content: string } }[] };
    const text = d.choices?.[0]?.message?.content ?? "";
    if (!text) throw new Error("Empty");
    return text;
  } catch (e) { markFail("sn", key, Config.SAMBANOVA_KEYS); throw e; }
}

export async function together(msgs: Msg[], model = "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free", maxTokens = 8192): Promise<string> {
  const key = nextKey("to", Config.TOGETHER_KEYS);
  if (!key) throw new Error("No Together keys");
  try {
    const d = await post("https://api.together.xyz/v1/chat/completions",
      { Authorization: `Bearer ${key}` },
      { model, messages: msgs, max_tokens: maxTokens, temperature: 0.8 }
    ) as { choices: { message: { content: string } }[] };
    const text = d.choices?.[0]?.message?.content ?? "";
    if (!text) throw new Error("Empty");
    return text;
  } catch (e) { markFail("to", key, Config.TOGETHER_KEYS); throw e; }
}

export async function openrouter(msgs: Msg[], model = "google/gemini-2.0-flash-exp:free", maxTokens = 8192): Promise<string> {
  const key = nextKey("or", Config.OPENROUTER_KEYS);
  if (!key) throw new Error("No OpenRouter keys");
  try {
    const d = await post("https://openrouter.ai/api/v1/chat/completions",
      { Authorization: `Bearer ${key}`, "HTTP-Referer": "https://nexum.ai" },
      { model, messages: msgs, max_tokens: maxTokens, temperature: 0.85 }
    ) as { choices: { message: { content: string } }[] };
    const text = d.choices?.[0]?.message?.content ?? "";
    if (!text) throw new Error("Empty");
    return text;
  } catch (e) { markFail("or", key, Config.OPENROUTER_KEYS); throw e; }
}

export async function deepseek(msgs: Msg[], maxTokens = 4096): Promise<string> {
  const key = nextKey("ds", Config.DEEPSEEK_KEYS);
  if (!key) throw new Error("No DeepSeek keys");
  try {
    const d = await post("https://api.deepseek.com/chat/completions",
      { Authorization: `Bearer ${key}` },
      { model: "deepseek-chat", messages: msgs, max_tokens: maxTokens, temperature: 0.8 }
    ) as { choices: { message: { content: string } }[] };
    const text = d.choices?.[0]?.message?.content ?? "";
    if (!text) throw new Error("Empty");
    return text;
  } catch (e) { markFail("ds", key, Config.DEEPSEEK_KEYS); throw e; }
}

export async function claude(msgs: Msg[], maxTokens = 4096): Promise<string> {
  const key = nextKey("cl", Config.CLAUDE_KEYS);
  if (!key) throw new Error("No Claude keys");
  try {
    const sys  = msgs.find(m => m.role === "system")?.content ?? "";
    const rest = msgs.filter(m => m.role !== "system");
    const d = await post("https://api.anthropic.com/v1/messages",
      { "x-api-key": key, "anthropic-version": "2023-06-01" },
      { model: "claude-sonnet-4-6", max_tokens: maxTokens, system: sys, messages: rest }
    ) as { content: { text: string }[] };
    const text = d.content?.[0]?.text ?? "";
    if (!text) throw new Error("Empty");
    return text;
  } catch (e) { markFail("cl", key, Config.CLAUDE_KEYS); throw e; }
}

// Vision
export async function geminiVision(b64: string, prompt: string, mime = "image/jpeg"): Promise<string> {
  const key = nextKey("g", Config.GEMINI_KEYS);
  if (!key) throw new Error("No Gemini keys");
  const body = {
    contents: [{ parts: [{ inline_data: { mime_type: mime, data: b64 } }, { text: prompt }] }],
    generationConfig: { maxOutputTokens: 3000 },
    safetySettings: ["HARM_CATEGORY_HARASSMENT","HARM_CATEGORY_HATE_SPEECH",
      "HARM_CATEGORY_SEXUALLY_EXPLICIT","HARM_CATEGORY_DANGEROUS_CONTENT"].map(c => ({ category: c, threshold: "BLOCK_NONE" })),
  };
  const d = await post(
    `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${key}`, {}, body
  ) as { candidates: { content: { parts: { text: string }[] } }[] };
  return d.candidates?.[0]?.content?.parts?.[0]?.text ?? "";
}

export async function claudeVision(b64: string, prompt: string): Promise<string> {
  const key = nextKey("cl", Config.CLAUDE_KEYS);
  if (!key) throw new Error("No Claude keys");
  const d = await post("https://api.anthropic.com/v1/messages",
    { "x-api-key": key, "anthropic-version": "2023-06-01" },
    { model: "claude-sonnet-4-6", max_tokens: 3000, messages: [{ role: "user", content: [
      { type: "image", source: { type: "base64", media_type: "image/jpeg", data: b64 } },
      { type: "text", text: prompt },
    ] }] }
  ) as { content: { text: string }[] };
  return d.content?.[0]?.text ?? "";
}

export async function openrouterVision(b64: string, prompt: string): Promise<string> {
  const key = nextKey("or", Config.OPENROUTER_KEYS);
  if (!key) throw new Error("No OR keys");
  const d = await post("https://openrouter.ai/api/v1/chat/completions",
    { Authorization: `Bearer ${key}`, "HTTP-Referer": "https://nexum.ai" },
    { model: "google/gemini-2.0-flash-exp:free", max_tokens: 3000, messages: [{ role: "user", content: [
      { type: "image_url", image_url: { url: `data:image/jpeg;base64,${b64}` } },
      { type: "text", text: prompt },
    ] }] }
  ) as { choices: { message: { content: string } }[] };
  return d.choices?.[0]?.message?.content ?? "";
}
