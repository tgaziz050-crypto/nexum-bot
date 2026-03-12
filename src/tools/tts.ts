import { exec } from 'child_process';
import { promisify } from 'util';
import fs from 'fs/promises';
import path from 'path';
import os from 'os';

const execAsync = promisify(exec);

// Microsoft Neural voices — 400+ voices, 50+ languages, completely free
const EDGE_VOICE_MAP: Record<string, string> = {
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
  pl: 'pl-PL-ZofiaNeural',
  uk: 'uk-UA-PolinaNeural',
  nl: 'nl-NL-ColetteNeural',
  sv: 'sv-SE-SofieNeural',
  da: 'da-DK-ChristelNeural',
  fi: 'fi-FI-NooraNeural',
  cs: 'cs-CZ-VlastaNeural',
  ro: 'ro-RO-AlinaNeural',
  hu: 'hu-HU-NoemiNeural',
  el: 'el-GR-AthinaNeural',
  bg: 'bg-BG-KalinaNeural',
  vi: 'vi-VN-HoaiMyNeural',
  th: 'th-TH-PremwadeeNeural',
  hi: 'hi-IN-SwaraNeural',
  id: 'id-ID-GadisNeural',
  ms: 'ms-MY-YasminNeural',
  he: 'he-IL-HilaNeural',
  fa: 'fa-IR-DilaraNeural',
  kk: 'kk-KZ-AigulNeural',
  az: 'az-AZ-BanuNeural',
  ka: 'ka-GE-EkaNeural',
  bn: 'bn-BD-NabanitaNeural',
  ta: 'ta-IN-PallaviNeural',
  ur: 'ur-PK-UzmaNeural',
  sw: 'sw-KE-ZuriNeural',
  af: 'af-ZA-AdriNeural',
};

export function detectLanguage(text: string): string {
  if (/[\u0400-\u04FF]/.test(text)) {
    if (/ї|є/.test(text)) return 'uk';
    if (/қ|ғ|ү|ұ|ң|ө|ә/.test(text)) return 'kk';
    return 'ru';
  }
  if (/[\u0600-\u06FF]/.test(text)) {
    if (/\u0698/.test(text)) return 'fa';
    return 'ar';
  }
  if (/[\u4E00-\u9FFF]/.test(text)) return 'zh';
  if (/[\u3040-\u30FF]/.test(text)) return 'ja';
  if (/[\uAC00-\uD7AF]/.test(text)) return 'ko';
  if (/[\u0900-\u097F]/.test(text)) return 'hi';
  if (/[\u0980-\u09FF]/.test(text)) return 'bn';
  if (/[\u0B80-\u0BFF]/.test(text)) return 'ta';
  if (/[\u10A0-\u10FF]/.test(text)) return 'ka';
  if (/[\u0590-\u05FF]/.test(text)) return 'he';
  if (/[\u0E00-\u0E7F]/.test(text)) return 'th';
  const lower = text.toLowerCase();
  if (/\b(ich|und|der|die|das|nicht|ist)\b/.test(lower)) return 'de';
  if (/\b(je|tu|il|nous|vous|et|un|une|est)\b/.test(lower)) return 'fr';
  if (/\b(yo|tú|él|que|con|por|una|los)\b/.test(lower)) return 'es';
  if (/\b(io|tu|lui|che|con|per|una)\b/.test(lower)) return 'it';
  if (/\b(eu|você|ele|que|com|por|uma)\b/.test(lower)) return 'pt';
  if (/\b(bir|bu|ve|için|ile|ne|biz)\b/.test(lower)) return 'tr';
  if (/\b(siz|bu|va|men|biz|uchun)\b/.test(lower)) return 'uz';
  return 'en';
}

function cleanForTTS(text: string): string {
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

export async function textToSpeech(text: string): Promise<TTSResult> {
  const clean = cleanForTTS(text);
  if (!clean) throw new Error('Empty text');

  const lang = detectLanguage(clean);
  const voice = EDGE_VOICE_MAP[lang] || EDGE_VOICE_MAP['en'];

  const tmpFile = path.join(os.tmpdir(), `nexum_tts_${Date.now()}.mp3`);

  // Escape text safely for Python string
  const escaped = clean
    .replace(/\\/g, '\\\\')
    .replace(/"""/g, '\\"\\"\\"')
    .replace(/\r?\n/g, ' ');

  const script = `
import asyncio
import edge_tts

async def main():
    communicate = edge_tts.Communicate(text="""${escaped}""", voice="${voice}")
    await communicate.save("${tmpFile}")

asyncio.run(main())
`.trim();

  try {
    await execAsync(`python3 -c '${script.replace(/'/g, "'\\''")}' `, { timeout: 30000 });
    const buf = await fs.readFile(tmpFile);
    await fs.unlink(tmpFile).catch(() => {});
    console.log(`[tts] edge voice=${voice} lang=${lang} len=${clean.length}`);
    return { buffer: buf, format: 'mp3', provider: 'edge-tts', lang };
  } catch (err: any) {
    await fs.unlink(tmpFile).catch(() => {});
    // Retry with simpler python call
    const tmpFile2 = path.join(os.tmpdir(), `nexum_tts2_${Date.now()}.mp3`);
    const textFile = path.join(os.tmpdir(), `nexum_txt_${Date.now()}.txt`);
    await fs.writeFile(textFile, clean, 'utf8');
    try {
      await execAsync(
        `python3 -c "import asyncio,edge_tts; asyncio.run(edge_tts.Communicate(open('${textFile}').read(), '${voice}').save('${tmpFile2}'))"`,
        { timeout: 30000 }
      );
      const buf = await fs.readFile(tmpFile2);
      await fs.unlink(tmpFile2).catch(() => {});
      await fs.unlink(textFile).catch(() => {});
      return { buffer: buf, format: 'mp3', provider: 'edge-tts', lang };
    } catch (err2: any) {
      await fs.unlink(tmpFile2).catch(() => {});
      await fs.unlink(textFile).catch(() => {});
      throw new Error(`Edge-TTS failed: ${err2.message}`);
    }
  }
}
