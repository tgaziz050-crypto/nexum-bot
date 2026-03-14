// TTS system — ported from OpenClaw tts-core architecture
// Supports: edge-tts (default), OpenAI TTS, ElevenLabs
// Falls back through providers automatically

import { execFile } from 'child_process';
import { promisify } from 'util';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import { db } from '../core/db';

const execFileAsync = promisify(execFile);

export type TtsProvider = 'edge' | 'openai' | 'elevenlabs';
export type TtsResult = { success: boolean; buffer?: Buffer; format: string; voiceCompatible: boolean; provider?: string; error?: string; };

export const VOICES: Record<string, { name: string; voices: string[] }> = {
  ru: { name: '🇷🇺 Русский',  voices: ['ru-RU-SvetlanaNeural', 'ru-RU-DmitryNeural'] },
  en: { name: '🇺🇸 English',  voices: ['en-US-JennyNeural', 'en-US-GuyNeural', 'en-US-AriaNeural'] },
  uz: { name: "🇺🇿 O'zbek",   voices: ['uz-UZ-MadinaNeural', 'uz-UZ-SardorNeural'] },
  es: { name: '🇪🇸 Español',  voices: ['es-ES-ElviraNeural', 'es-ES-AlvaroNeural'] },
  fr: { name: '🇫🇷 Français', voices: ['fr-FR-DeniseNeural', 'fr-FR-HenriNeural'] },
  de: { name: '🇩🇪 Deutsch',  voices: ['de-DE-KatjaNeural', 'de-DE-ConradNeural'] },
  tr: { name: '🇹🇷 Türkçe',   voices: ['tr-TR-EmelNeural', 'tr-TR-AhmetNeural'] },
  ar: { name: '🇸🇦 العربية',  voices: ['ar-SA-ZariyahNeural', 'ar-SA-HamedNeural'] },
  zh: { name: '🇨🇳 中文',      voices: ['zh-CN-XiaoxiaoNeural', 'zh-CN-YunxiNeural'] },
  ja: { name: '🇯🇵 日本語',    voices: ['ja-JP-NanamiNeural', 'ja-JP-KeitaNeural'] },
};

export function getUserVoicePref(uid: number): { lang: string; idx: number } {
  const r = db.prepare("SELECT value FROM memory WHERE uid=? AND key='voice_pref'").get(uid) as any;
  if (r?.value) { try { return JSON.parse(r.value); } catch {} }
  return { lang: 'auto', idx: 0 };
}

export function setUserVoicePref(uid: number, lang: string, idx = 0) {
  db.prepare("INSERT INTO memory (uid,key,value) VALUES (?,'voice_pref',?) ON CONFLICT(uid,key) DO UPDATE SET value=excluded.value")
    .run(uid, JSON.stringify({ lang, idx }));
}

export function detectLang(text: string): string {
  if (/[а-яё]/i.test(text)) return 'ru';
  if (/[\u0600-\u06FF]/.test(text)) return 'ar';
  if (/[\u4e00-\u9fff]/.test(text)) return 'zh';
  if (/[\u3040-\u309f\u30a0-\u30ff]/.test(text)) return 'ja';
  if (/[öüşçğı]/i.test(text)) return 'tr';
  if (/[àâçèéêëîïôùûü]/i.test(text)) return 'fr';
  if (/[äöüß]/i.test(text)) return 'de';
  if (/[áéíóúüñ]/i.test(text)) return 'es';
  if (/[oʻgʻ]/i.test(text)) return 'uz';
  return 'en';
}

function resolveVoice(uid: number, textLang: string): string {
  const pref = getUserVoicePref(uid);
  const lang = pref.lang === 'auto' ? textLang : pref.lang;
  const entry = VOICES[lang] || VOICES['en'];
  return entry.voices[pref.idx % entry.voices.length];
}

async function edgeTTS(text: string, voice: string): Promise<Buffer> {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'nexum-tts-'));
  const outFile = path.join(tmpDir, 'voice.mp3');
  try {
    await execFileAsync('edge-tts', ['--voice', voice, '--text', text.slice(0, 1500), '--write-media', outFile], { timeout: 30000 });
    return fs.readFileSync(outFile);
  } finally {
    try { fs.rmSync(tmpDir, { recursive: true, force: true }); } catch {}
  }
}

async function openaiTTS(text: string, apiKey: string): Promise<Buffer> {
  const resp = await fetch('https://api.openai.com/v1/audio/speech', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: 'tts-1', voice: 'nova', input: text.slice(0, 4096), response_format: 'mp3' }),
  });
  if (!resp.ok) throw new Error(`OpenAI TTS ${resp.status}`);
  return Buffer.from(await resp.arrayBuffer());
}

async function elevenLabsTTS(text: string, apiKey: string): Promise<Buffer> {
  const resp = await fetch('https://api.elevenlabs.io/v1/text-to-speech/pMsXgVXv3BLzUgSXRplE', {
    method: 'POST',
    headers: { 'xi-api-key': apiKey, 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: text.slice(0, 2500), model_id: 'eleven_multilingual_v2', voice_settings: { stability: 0.5, similarity_boost: 0.75 } }),
  });
  if (!resp.ok) throw new Error(`ElevenLabs ${resp.status}`);
  return Buffer.from(await resp.arrayBuffer());
}

export function stripMarkdownForTTS(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, ' код ')
    .replace(/`[^`]+`/g, ' код ')
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/\*(.+?)\*/g, '$1')
    .replace(/__(.+?)__/g, '$1')
    .replace(/_(.+?)_/g, '$1')
    .replace(/~~(.+?)~~/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/^#+\s/gm, '')
    .replace(/^[-*]\s/gm, '')
    .trim();
}

export async function textToSpeech(text: string, uid: number, userApiKeys?: Record<string, string>): Promise<TtsResult> {
  const cleanText = stripMarkdownForTTS(text);
  if (cleanText.length < 5) return { success: false, format: 'mp3', voiceCompatible: false, error: 'Too short' };

  const lang = detectLang(cleanText);
  const voice = resolveVoice(uid, lang);
  const openaiKey = userApiKeys?.openai || process.env.OPENAI_API_KEY;
  const elevenKey = userApiKeys?.elevenlabs || process.env.ELEVENLABS_API_KEY;

  // Provider order with fallback (OpenClaw pattern)
  const providers: Array<{ name: string; fn: () => Promise<Buffer> }> = [];
  if (elevenKey) providers.push({ name: 'elevenlabs', fn: () => elevenLabsTTS(cleanText, elevenKey) });
  if (openaiKey) providers.push({ name: 'openai', fn: () => openaiTTS(cleanText, openaiKey) });
  providers.push({ name: 'edge', fn: () => edgeTTS(cleanText, voice) });

  const errors: string[] = [];
  for (const p of providers) {
    try {
      const buffer = await p.fn();
      return { success: true, buffer, format: 'mp3', voiceCompatible: true, provider: p.name };
    } catch (e: any) {
      errors.push(`${p.name}: ${e.message}`);
    }
  }
  return { success: false, format: 'mp3', voiceCompatible: false, error: errors.join('; ') };
}
