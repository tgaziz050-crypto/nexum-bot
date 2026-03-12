/**
 * NEXUM STT — Speech to Text
 * Primary: Groq Whisper (whisper-large-v3-turbo) — fastest, free
 * Fallback: Gemini audio understanding
 * Supports: voice messages (.ogg), video notes (.mp4), any audio
 */
import * as fs from "fs";
import * as path from "path";
import { log } from "../core/logger.js";

// Collect all Groq keys
function getGroqKeys(): string[] {
  const keys: string[] = [];
  for (let i = 1; i <= 7; i++) {
    const k = process.env[`GR${i}`]?.trim();
    if (k) keys.push(k);
  }
  return keys;
}

// Collect all Gemini keys
function getGeminiKeys(): string[] {
  const keys: string[] = [];
  for (let i = 1; i <= 7; i++) {
    const k = process.env[`G${i}`]?.trim();
    if (k) keys.push(k);
  }
  return keys;
}

/**
 * Transcribe audio file using Groq Whisper API
 * Groq supports: flac, mp3, mp4, mpeg, mpga, m4a, ogg, opus, wav, webm
 */
async function sttGroq(filePath: string, apiKey: string): Promise<string | null> {
  try {
    const fileBuffer = fs.readFileSync(filePath);
    const fileName = path.basename(filePath);
    const ext = path.extname(filePath).slice(1).toLowerCase();

    // Map extensions to MIME types Groq accepts
    const mimeMap: Record<string, string> = {
      ogg: "audio/ogg",
      oga: "audio/ogg",
      mp3: "audio/mpeg",
      mp4: "video/mp4",
      m4a: "audio/m4a",
      wav: "audio/wav",
      webm: "audio/webm",
      flac: "audio/flac",
      opus: "audio/ogg",
    };
    const mimeType = mimeMap[ext] ?? "audio/ogg";

    const form = new FormData();
    form.append("file", new Blob([fileBuffer], { type: mimeType }), fileName);
    form.append("model", "whisper-large-v3-turbo");
    form.append("response_format", "json");
    // No language specified = auto-detect (Russian, Uzbek, English, etc.)

    const ctrl = new AbortController();
    const timeout = setTimeout(() => ctrl.abort(), 30_000);

    const res = await fetch("https://api.groq.com/openai/v1/audio/transcriptions", {
      method: "POST",
      headers: { Authorization: `Bearer ${apiKey}` },
      body: form,
      signal: ctrl.signal,
    });
    clearTimeout(timeout);

    if (!res.ok) {
      const errText = await res.text().catch(() => "");
      log.warn(`Groq STT ${res.status}: ${errText.slice(0, 200)}`);
      return null;
    }

    const data = await res.json() as { text?: string };
    const text = data.text?.trim();
    if (!text || text.length < 1) return null;
    log.info(`Groq STT: "${text.slice(0, 60)}"`);
    return text;
  } catch (e: any) {
    if (e.name === "AbortError") {
      log.warn("Groq STT timeout");
    } else {
      log.warn(`Groq STT error: ${e.message}`);
    }
    return null;
  }
}

/**
 * Transcribe using Gemini as fallback
 * Sends audio as base64 to Gemini's multimodal API
 */
async function sttGemini(filePath: string, apiKey: string): Promise<string | null> {
  try {
    const fileBuffer = fs.readFileSync(filePath);
    const base64Data = fileBuffer.toString("base64");
    const ext = path.extname(filePath).slice(1).toLowerCase();
    const mimeMap: Record<string, string> = {
      ogg: "audio/ogg",
      mp3: "audio/mpeg",
      mp4: "video/mp4",
      m4a: "audio/mp4",
      wav: "audio/wav",
      webm: "audio/webm",
    };
    const mimeType = mimeMap[ext] ?? "audio/ogg";

    const ctrl = new AbortController();
    const timeout = setTimeout(() => ctrl.abort(), 40_000);

    const res = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${apiKey}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          contents: [{
            parts: [
              {
                inline_data: {
                  mime_type: mimeType,
                  data: base64Data,
                }
              },
              {
                text: "Transcribe exactly what is spoken in this audio. Output ONLY the transcription text, nothing else. Detect language automatically."
              }
            ]
          }],
          generationConfig: { maxOutputTokens: 1000, temperature: 0 },
        }),
        signal: ctrl.signal,
      }
    );
    clearTimeout(timeout);

    if (!res.ok) {
      log.warn(`Gemini STT ${res.status}`);
      return null;
    }

    const data = await res.json() as any;
    const text = data?.candidates?.[0]?.content?.parts?.[0]?.text?.trim();
    if (!text || text.length < 1) return null;
    log.info(`Gemini STT: "${text.slice(0, 60)}"`);
    return text;
  } catch (e: any) {
    log.warn(`Gemini STT error: ${e.message}`);
    return null;
  }
}

/**
 * Main STT function — tries all Groq keys, then falls back to Gemini
 */
export async function stt(filePath: string): Promise<string | null> {
  const groqKeys = getGroqKeys();
  const geminiKeys = getGeminiKeys();

  if (groqKeys.length === 0 && geminiKeys.length === 0) {
    log.error("STT: No API keys available (GR1..GR7 or G1..G7)");
    return null;
  }

  // Try Groq keys in order
  for (const key of groqKeys) {
    const result = await sttGroq(filePath, key);
    if (result) return result;
  }

  // Fallback to Gemini
  log.warn("STT: Groq failed, trying Gemini fallback");
  for (const key of geminiKeys) {
    const result = await sttGemini(filePath, key);
    if (result) return result;
  }

  log.error("STT: All providers failed");
  return null;
}
