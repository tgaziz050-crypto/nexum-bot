import { execFile } from "child_process";
import { promisify } from "util";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { log } from "../core/logger.js";

const exec = promisify(execFile);

// Voice map: language → edge-tts voice
const VOICE_MAP: Record<string, string> = {
  ru: "ru-RU-SvetlanaNeural",
  en: "en-US-AriaNeural",
  uz: "uz-UZ-MadinaNeural",
  kk: "kk-KZ-AigulNeural",
  tr: "tr-TR-EmelNeural",
  ar: "ar-SA-ZariyahNeural",
  de: "de-DE-KatjaNeural",
  fr: "fr-FR-DeniseNeural",
  es: "es-ES-ElviraNeural",
  zh: "zh-CN-XiaoxiaoNeural",
  ja: "ja-JP-NanamiNeural",
  ko: "ko-KR-SunHiNeural",
  it: "it-IT-ElsaNeural",
  pt: "pt-BR-FranciscaNeural",
  uk: "uk-UA-PolinaNeural",
  pl: "pl-PL-ZofiaNeural",
};

export async function tts(text: string, lang = "ru"): Promise<Buffer | null> {
  const voice  = VOICE_MAP[lang] ?? VOICE_MAP["ru"]!;
  const tmpOut = path.join(os.tmpdir(), `nexum_tts_${Date.now()}.mp3`);
  try {
    await exec("edge-tts", [
      "--voice", voice,
      "--text",  text.slice(0, 3000),
      "--write-media", tmpOut,
    ]);
    const buf = fs.readFileSync(tmpOut);
    fs.unlinkSync(tmpOut);
    return buf;
  } catch (e) {
    log.debug(`TTS failed: ${e}`);
    try { fs.unlinkSync(tmpOut); } catch {}
    return null;
  }
}
