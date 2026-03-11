import { Config } from "../core/config.js";
import * as fs from "fs";
import { log } from "../core/logger.js";

export async function stt(audioPath: string): Promise<string | null> {
  // Try Groq Whisper first (fastest, free)
  const key = Config.GROQ_KEYS[0];
  if (key) {
    try {
      const FormData = (await import("form-data")).default;
      const form = new FormData();
      form.append("file", fs.createReadStream(audioPath), { filename: "audio.ogg", contentType: "audio/ogg" });
      form.append("model", "whisper-large-v3-turbo");
      form.append("response_format", "text");

      const res = await fetch("https://api.groq.com/openai/v1/audio/transcriptions", {
        method:  "POST",
        headers: { Authorization: `Bearer ${key}`, ...form.getHeaders() },
        body:    form as unknown as BodyInit,
      });
      if (res.ok) {
        const text = (await res.text()).trim();
        if (text) return text;
      }
    } catch (e) {
      log.debug(`Groq STT: ${e}`);
    }
  }

  // Try OpenAI-compatible Whisper via OpenRouter
  const orKey = Config.OPENROUTER_KEYS[0];
  if (orKey) {
    try {
      const FormData = (await import("form-data")).default;
      const form = new FormData();
      form.append("file", fs.createReadStream(audioPath), { filename: "audio.ogg", contentType: "audio/ogg" });
      form.append("model", "openai/whisper-1");

      const res = await fetch("https://openrouter.ai/api/v1/audio/transcriptions", {
        method:  "POST",
        headers: { Authorization: `Bearer ${orKey}`, ...form.getHeaders() },
        body:    form as unknown as BodyInit,
      });
      if (res.ok) {
        const d    = await res.json() as { text?: string };
        const text = d.text?.trim();
        if (text) return text;
      }
    } catch (e) {
      log.debug(`OR STT: ${e}`);
    }
  }

  return null;
}
