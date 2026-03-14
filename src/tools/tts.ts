import { exec } from 'child_process';
import { promisify } from 'util';
import fs   from 'fs/promises';
import path from 'path';
import os   from 'os';

const execAsync = promisify(exec);

export const VOICES: Record<string, { name: string; voices: string[] }> = {
  ru: { name: 'Русский',     voices: ['ru-RU-SvetlanaNeural','ru-RU-DmitryNeural','ru-RU-DariyaNeural'] },
  en: { name: 'English',     voices: ['en-US-AriaNeural','en-US-GuyNeural','en-US-JennyNeural','en-GB-SoniaNeural'] },
  uz: { name: "O'zbek",      voices: ['uz-UZ-MadinaNeural','uz-UZ-SardorNeural'] },
  de: { name: 'Deutsch',     voices: ['de-DE-KatjaNeural','de-DE-ConradNeural'] },
  fr: { name: 'Français',    voices: ['fr-FR-DeniseNeural','fr-FR-HenriNeural'] },
  es: { name: 'Español',     voices: ['es-ES-ElviraNeural','es-ES-AlvaroNeural','es-MX-DaliaNeural'] },
  ar: { name: 'العربية',     voices: ['ar-SA-ZariyahNeural','ar-SA-HamedNeural'] },
  zh: { name: '中文',        voices: ['zh-CN-XiaoxiaoNeural','zh-CN-YunxiNeural'] },
  ja: { name: '日本語',      voices: ['ja-JP-NanamiNeural','ja-JP-KeitaNeural'] },
  ko: { name: '한국어',      voices: ['ko-KR-SunHiNeural','ko-KR-InJoonNeural'] },
  tr: { name: 'Türkçe',      voices: ['tr-TR-EmelNeural','tr-TR-AhmetNeural'] },
  hi: { name: 'हिन्दी',     voices: ['hi-IN-SwaraNeural','hi-IN-MadhurNeural'] },
  uk: { name: 'Українська',  voices: ['uk-UA-PolinaNeural','uk-UA-OstapNeural'] },
  kk: { name: 'Қазақша',    voices: ['kk-KZ-AigulNeural','kk-KZ-DauletNeural'] },
  pl: { name: 'Polski',      voices: ['pl-PL-ZofiaNeural','pl-PL-MarekNeural'] },
  it: { name: 'Italiano',    voices: ['it-IT-ElsaNeural','it-IT-DiegoNeural'] },
  pt: { name: 'Português',   voices: ['pt-BR-FranciscaNeural','pt-BR-AntonioNeural'] },
  nl: { name: 'Nederlands',  voices: ['nl-NL-ColetteNeural','nl-NL-MaartenNeural'] },
  sv: { name: 'Svenska',     voices: ['sv-SE-SofieNeural','sv-SE-MattiasNeural'] },
  fa: { name: 'فارسی',       voices: ['fa-IR-DilaraNeural','fa-IR-FaridNeural'] },
};

const _prefs = new Map<number, { lang: string; idx: number }>();
export function getUserVoicePref(uid: number) { return _prefs.get(uid) || { lang: 'auto', idx: 0 }; }
export function setUserVoicePref(uid: number, lang: string, idx = 0) { _prefs.set(uid, { lang, idx }); }

export function detectLang(text: string): string {
  if (/[АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя]/.test(text)) {
    if (/ї|є|і/.test(text)) return 'uk';
    if (/қ|ғ|ү|ұ|ң|ө|ә/.test(text)) return 'kk';
    return 'ru';
  }
  if (/[ا-ي]/.test(text)) return 'ar';
  if (/[\u4E00-\u9FFF]/.test(text)) return 'zh';
  if (/[\u3040-\u30FF]/.test(text)) return 'ja';
  if (/[\uAC00-\uD7AF]/.test(text)) return 'ko';
  if (/[\u0900-\u097F]/.test(text)) return 'hi';
  if (/[\u0600-\u06FF]/.test(text)) return 'fa';
  const l = text.toLowerCase();
  if (/\b(ich|und|der|die|das|nicht)\b/.test(l)) return 'de';
  if (/\b(je|tu|il|nous|est|les)\b/.test(l))     return 'fr';
  if (/\b(yo|tú|él|que|con|los)\b/.test(l))       return 'es';
  if (/\b(bir|bu|ve|için|ile)\b/.test(l))          return 'tr';
  if (/\b(siz|bu|va|men|uchun)\b/.test(l))         return 'uz';
  return 'en';
}

function clean(text: string): string {
  return text
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/\*(.*?)\*/g, '$1')
    .replace(/`{1,3}[^`]*`{1,3}/g, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/#{1,6}\s/g, '')
    .replace(/[_~]/g, '')
    .replace(/https?:\/\/\S+/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
    .slice(0, 3000);
}

export interface TTSResult { buffer: Buffer; format: 'mp3'; lang: string; voice: string }

export async function textToSpeech(text: string, uid?: number): Promise<TTSResult> {
  const t = clean(text);
  if (!t) throw new Error('Empty text');

  const pref = uid ? getUserVoicePref(uid) : { lang: 'auto', idx: 0 };
  const lang  = pref.lang === 'auto' ? detectLang(t) : pref.lang;
  const vData = VOICES[lang] || VOICES['en'];
  const voice = vData.voices[pref.idx % vData.voices.length];

  const outFile = path.join(os.tmpdir(), `nx_tts_${Date.now()}.mp3`);
  const txtFile = path.join(os.tmpdir(), `nx_txt_${Date.now()}.txt`);

  try {
    await fs.writeFile(txtFile, t, 'utf8');
    const bin = process.env.EDGE_TTS_PATH || 'edge-tts';

    // Try CLI first
    try {
      await execAsync(`${bin} --voice "${voice}" --file "${txtFile}" --write-media "${outFile}"`, { timeout: 30000 });
      const buf = await fs.readFile(outFile);
      return { buffer: buf, format: 'mp3', lang, voice };
    } catch { /* try python */ }

    // Try Python fallback
    const py = process.env.EDGE_PYTHON_PATH || '/opt/edge-tts-env/bin/python3';
    const script = `import asyncio,edge_tts,sys\nasync def r():\n    t=open(sys.argv[1],encoding='utf-8').read()\n    await edge_tts.Communicate(t,sys.argv[2]).save(sys.argv[3])\nasyncio.run(r())`;
    const pyFile = path.join(os.tmpdir(), `nx_tts_py_${Date.now()}.py`);
    await fs.writeFile(pyFile, script);
    await execAsync(`${py} "${pyFile}" "${txtFile}" "${voice}" "${outFile}"`, { timeout: 30000 });
    await fs.unlink(pyFile).catch(() => {});
    const buf = await fs.readFile(outFile);
    return { buffer: buf, format: 'mp3', lang, voice };
  } finally {
    await fs.unlink(outFile).catch(() => {});
    await fs.unlink(txtFile).catch(() => {});
  }
}
