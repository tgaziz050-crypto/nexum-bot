import { exec } from 'child_process';
import { promisify } from 'util';
import fs from 'fs/promises';
import path from 'path';
import os from 'os';

const execAsync = promisify(exec);

// Microsoft Neural voices — полностью бесплатно, 50+ языков
const VOICE_MAP: Record<string, string> = {
  ru: 'ru-RU-SvetlanaNeural',
  en: 'en-US-AriaNeural',
  uz: 'uz-UZ-MadinaNeural',
  de: 'de-DE-KatjaNeural',
  fr: 'fr-FR-DeniseNeural',
  es: 'es-ES-ElviraNeural',
  it: 'it-IT-ElsaNeural',
  pt: 'pt-BR-FranciscaNeural',
  ar: 'ar-SA-ZariyahNeural',
  zh: 'zh-CN-XiaoxiaoNeural',
  ja: 'ja-JP-NanamiNeural',
  ko: 'ko-KR-SunHiNeural',
  tr: 'tr-TR-EmelNeural',
  uk: 'uk-UA-PolinaNeural',
  kk: 'kk-KZ-AigulNeural',
  pl: 'pl-PL-ZofiaNeural',
  hi: 'hi-IN-SwaraNeural',
  he: 'he-IL-HilaNeural',
  th: 'th-TH-PremwadeeNeural',
  vi: 'vi-VN-HoaiMyNeural',
};

export function detectLanguage(text: string): string {
  if (/[\u0400-\u04FF]/.test(text)) {
    if (/ї|є/.test(text)) return 'uk';
    if (/қ|ғ|ү|ұ|ң|ө|ә/.test(text)) return 'kk';
    return 'ru';
  }
  if (/[\u0600-\u06FF]/.test(text)) return 'ar';
  if (/[\u4E00-\u9FFF]/.test(text)) return 'zh';
  if (/[\u3040-\u30FF]/.test(text)) return 'ja';
  if (/[\uAC00-\uD7AF]/.test(text)) return 'ko';
  if (/[\u0900-\u097F]/.test(text)) return 'hi';
  if (/[\u0590-\u05FF]/.test(text)) return 'he';
  if (/[\u0E00-\u0E7F]/.test(text)) return 'th';
  const l = text.toLowerCase();
  if (/\b(ich|und|der|die|das|nicht)\b/.test(l)) return 'de';
  if (/\b(je|tu|il|nous|vous|est)\b/.test(l)) return 'fr';
  if (/\b(yo|tú|él|que|con|los)\b/.test(l)) return 'es';
  if (/\b(bir|bu|ve|için|ile)\b/.test(l)) return 'tr';
  if (/\b(siz|bu|va|men|uchun)\b/.test(l)) return 'uz';
  return 'en';
}

function cleanText(text: string): string {
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
    .substring(0, 3000);
}

export interface TTSResult {
  buffer: Buffer;
  format: 'mp3';
  provider: string;
  lang: string;
}

// Путь к edge-tts CLI (из env или дефолт)
function getEdgeTTSPath(): string {
  return process.env.EDGE_TTS_PATH || 'edge-tts';
}

export async function textToSpeech(text: string): Promise<TTSResult> {
  const clean = cleanText(text);
  if (!clean) throw new Error('Empty text');

  const lang  = detectLanguage(clean);
  const voice = VOICE_MAP[lang] || VOICE_MAP['en'];
  const outFile = path.join(os.tmpdir(), `nx_tts_${Date.now()}_${Math.random().toString(36).slice(2)}.mp3`);
  const txtFile = path.join(os.tmpdir(), `nx_txt_${Date.now()}.txt`);

  try {
    // Записываем текст в файл (избегаем проблем с кавычками в shell)
    await fs.writeFile(txtFile, clean, 'utf8');

    const edgeBin = getEdgeTTSPath();

    // Метод 1: edge-tts CLI напрямую (самый надёжный)
    try {
      await execAsync(
        `${edgeBin} --voice "${voice}" --file "${txtFile}" --write-media "${outFile}"`,
        { timeout: 30000 }
      );
      const buf = await fs.readFile(outFile);
      console.log(`[tts] ✅ CLI voice=${voice} lang=${lang} bytes=${buf.length}`);
      return { buffer: buf, format: 'mp3', provider: 'edge-tts-cli', lang };
    } catch (cliErr: any) {
      console.warn('[tts] CLI failed:', cliErr.message?.slice(0, 100));
    }

    // Метод 2: через Python venv (fallback)
    const pythonBin = process.env.EDGE_PYTHON_PATH || '/opt/edge-tts-env/bin/python3';
    const pyScript = `
import asyncio, edge_tts, sys

async def run():
    text = open(sys.argv[1], encoding='utf-8').read()
    await edge_tts.Communicate(text, sys.argv[2]).save(sys.argv[3])

asyncio.run(run())
`.trim();

    const pyFile = path.join(os.tmpdir(), `nx_tts_script_${Date.now()}.py`);
    await fs.writeFile(pyFile, pyScript, 'utf8');

    await execAsync(
      `${pythonBin} "${pyFile}" "${txtFile}" "${voice}" "${outFile}"`,
      { timeout: 30000 }
    );
    await fs.unlink(pyFile).catch(() => {});

    const buf = await fs.readFile(outFile);
    console.log(`[tts] ✅ Python voice=${voice} lang=${lang} bytes=${buf.length}`);
    return { buffer: buf, format: 'mp3', provider: 'edge-tts-python', lang };

  } finally {
    await fs.unlink(outFile).catch(() => {});
    await fs.unlink(txtFile).catch(() => {});
  }
}
