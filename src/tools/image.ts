import { ask } from "../ai/engine.js";
import { log } from "../core/logger.js";

async function translateToEn(text: string): Promise<string> {
  if (/^[a-zA-Z\s\d.,!?'-]+$/.test(text)) return text;
  try {
    return await ask([{ role: "user", content: `Translate to English for image generation (just translation, nothing else): ${text}` }], "fast");
  } catch {
    return text;
  }
}

export async function generateImage(prompt: string): Promise<Buffer | null> {
  try {
    const en   = await translateToEn(prompt);
    const seed = Math.floor(Math.random() * 1_000_000);
    const url  = `https://image.pollinations.ai/prompt/${encodeURIComponent(en.slice(0, 500))}?seed=${seed}&width=1024&height=1024&nologo=true`;

    const res = await fetch(url, { signal: AbortSignal.timeout(60_000) });
    if (!res.ok) return null;
    const buf = Buffer.from(await res.arrayBuffer());
    if (buf.length < 5000) return null;
    return buf;
  } catch (e) {
    log.debug(`genImg: ${e}`);
    return null;
  }
}
