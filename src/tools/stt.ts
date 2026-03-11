import { Config } from "../core/config.js";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { execFile } from "child_process";
import { promisify } from "util";
import { log } from "../core/logger.js";

const exec = promisify(execFile);

// Convert audio to mp3 using ffmpeg (handles ogg, mp4, webm, etc.)
async function convertToMp3(inputPath: string): Promise<string | null> {
  const outPath = path.join(os.tmpdir(), `nexum_conv_${Date.now()}.mp3`);
  try {
    await exec("ffmpeg", [
      "-y", "-i", inputPath,
      "-ar", "16000",    // 16kHz — optimal for Whisper
      "-ac", "1",        // mono
      "-c:a", "libmp3lame",
      "-q:a", "2",
      outPath,
    ]);
    return outPath;
  } catch (e) {
    log.debug(`ffmpeg convert failed: ${e}`);
    return null;
  }
}

export async function stt(audioPath: string): Promise<string | null> {
  // Convert to mp3 first for better compatibility
  const mp3Path = await convertToMp3(audioPath);
  const filePath = mp3Path ?? audioPath;
  const fileName = mp3Path ? "audio.mp3" : path.basename(audioPath);
  const mimeType = mp3Path ? "audio/mpeg" : "audio/ogg";

  try {
    // Try Groq Whisper first (fastest, free)
    const key = Config.GROQ_KEYS[0];
    if (key) {
      try {
        const FormData = (await import("form-data")).default;
        const form = new FormData();
        form.append("file", fs.createReadStream(filePath), { filename: fileName, contentType: mimeType });
        form.append("model", "whisper-large-v3-turbo");
        form.append("response_format", "text");
        form.append("language", "ru"); // hint — helps with Russian

        const res = await fetch("https://api.groq.com/openai/v1/audio/transcriptions", {
          method:  "POST",
          headers: { Authorization: `Bearer ${key}`, ...form.getHeaders() },
          body:    form as unknown as BodyInit,
        });
        if (res.ok) {
          const text = (await res.text()).trim();
          if (text) return text;
        } else {
          log.debug(`Groq STT error: ${res.status} ${await res.text()}`);
        }
      } catch (e) {
        log.debug(`Groq STT: ${e}`);
      }
    }

    // Fallback: try Gemini audio understanding
    const geminiKey = Config.GEMINI_KEYS[0];
    if (geminiKey) {
      try {
        const audioData = fs.readFileSync(filePath).toString("base64");
        const res = await fetch(
          `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${geminiKey}`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              contents: [{
                parts: [
                  { text: "Transcribe this audio message exactly as spoken. Return only the transcription text, nothing else." },
                  { inline_data: { mime_type: "audio/mp3", data: audioData } },
                ],
              }],
            }),
          }
        );
        if (res.ok) {
          const d = await res.json() as any;
          const text = d?.candidates?.[0]?.content?.parts?.[0]?.text?.trim();
          if (text && text.length > 0) return text;
        }
      } catch (e) {
        log.debug(`Gemini STT: ${e}`);
      }
    }

    return null;
  } finally {
    // Cleanup converted file
    if (mp3Path) {
      try { fs.unlinkSync(mp3Path); } catch {}
    }
  }
}
