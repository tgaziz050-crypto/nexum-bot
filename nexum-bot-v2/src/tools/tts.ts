import { execFile } from "child_process";
import { promisify } from "util";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { log } from "../core/logger.js";

const exec = promisify(execFile);

// Full multilingual voice map — natural, accent-free voices
const VOICE_MAP: Record<string, string> = {
  ru: "ru-RU-DmitryNeural",        // Russian male — natural
  en: "en-US-AndrewNeural",         // English US — natural male
  "en-gb": "en-GB-RyanNeural",      // British
  uz: "uz-UZ-SardorNeural",         // Uzbek male
  kk: "kk-KZ-DauletNeural",         // Kazakh
  tr: "tr-TR-AhmetNeural",          // Turkish
  ar: "ar-SA-HamedNeural",          // Arabic
  de: "de-DE-ConradNeural",         // German
  fr: "fr-FR-HenriNeural",          // French
  es: "es-ES-AlvaroNeural",         // Spanish
  "es-mx": "es-MX-JorgeNeural",     // Mexican Spanish
  zh: "zh-CN-YunxiNeural",          // Chinese
  ja: "ja-JP-KeitaNeural",          // Japanese
  ko: "ko-KR-InJoonNeural",         // Korean
  it: "it-IT-DiegoNeural",          // Italian
  pt: "pt-BR-AntonioNeural",        // Portuguese BR
  "pt-pt": "pt-PT-DuarteNeural",    // Portuguese EU
  uk: "uk-UA-OstapNeural",          // Ukrainian
  pl: "pl-PL-MarekNeural",          // Polish
  nl: "nl-NL-MaartenNeural",        // Dutch
  sv: "sv-SE-MattiasNeural",        // Swedish
  no: "nb-NO-FinnNeural",           // Norwegian
  da: "da-DK-JeppeNeural",          // Danish
  fi: "fi-FI-HarriNeural",          // Finnish
  el: "el-GR-NestorasNeural",       // Greek
  he: "he-IL-AvriNeural",           // Hebrew
  hi: "hi-IN-MadhurNeural",         // Hindi
  bn: "bn-BD-PradeepNeural",        // Bengali
  th: "th-TH-NiwatNeural",          // Thai
  vi: "vi-VN-NamMinhNeural",        // Vietnamese
  id: "id-ID-ArdiNeural",           // Indonesian
  ms: "ms-MY-OsmanNeural",          // Malay
  ro: "ro-RO-EmilNeural",           // Romanian
  cs: "cs-CZ-AntoninNeural",        // Czech
  sk: "sk-SK-LukasNeural",          // Slovak
  hu: "hu-HU-TamasNeural",          // Hungarian
  bg: "bg-BG-BorislavNeural",       // Bulgarian
  sr: "sr-RS-NicholasNeural",       // Serbian
  hr: "hr-HR-SreckoNeural",         // Croatian
  az: "az-AZ-BaburNeural",          // Azerbaijani
  ka: "ka-GE-GiorgiNeural",         // Georgian
  hy: "hy-AM-HaykNeural",           // Armenian
  sw: "sw-KE-RafikiNeural",         // Swahili
  af: "af-ZA-WillemNeural",         // Afrikaans
  tl: "fil-PH-AngeloNeural",        // Filipino
  ur: "ur-PK-AsadNeural",           // Urdu
  fa: "fa-IR-FaridNeural",          // Farsi/Persian
  ta: "ta-IN-ValluvarNeural",       // Tamil
  te: "te-IN-MohanNeural",          // Telugu
  mr: "mr-IN-ManoharNeural",        // Marathi
  gu: "gu-IN-NiranjanNeural",       // Gujarati
  ml: "ml-IN-MidhunNeural",         // Malayalam
  lv: "lv-LV-NilsNeural",           // Latvian
  lt: "lt-LT-LeonasNeural",         // Lithuanian
  et: "et-EE-KertNeural",           // Estonian
  sl: "sl-SI-RokNeural",            // Slovenian
  mk: "mk-MK-AleksandarNeural",     // Macedonian
  sq: "sq-AL-IlirNeural",           // Albanian
  mt: "mt-MT-JosephNeural",         // Maltese
  cy: "cy-GB-AledNeural",           // Welsh
  is: "is-IS-GunnarNeural",         // Icelandic
  ga: "ga-IE-ColmNeural",           // Irish
};

// Detect language from text (simple heuristic + Unicode ranges)
function detectLang(text: string): string {
  if (/[\u0600-\u06FF]/.test(text)) return "ar";
  if (/[\u0900-\u097F]/.test(text)) return "hi";
  if (/[\u4E00-\u9FFF\u3040-\u309F\u30A0-\u30FF]/.test(text)) {
    if (/[\u3040-\u309F\u30A0-\u30FF]/.test(text)) return "ja";
    return "zh";
  }
  if (/[\uAC00-\uD7AF]/.test(text)) return "ko";
  if (/[\u0400-\u04FF]/.test(text)) {
    // Distinguish Russian/Ukrainian/Bulgarian etc.
    if (/[іїєґ]/.test(text.toLowerCase())) return "uk";
    return "ru";
  }
  if (/[\u0500-\u052F]/.test(text)) return "ka";
  if (/[\u0530-\u058F]/.test(text)) return "hy";
  return "en";
}

export async function tts(text: string, lang?: string): Promise<Buffer | null> {
  // Auto-detect language if not provided or if it's a generic fallback
  const effectiveLang = lang && lang !== "ru" ? lang : detectLang(text) || lang || "en";
  const voice = VOICE_MAP[effectiveLang] ?? VOICE_MAP["en"]!;
  const tmpOut = path.join(os.tmpdir(), `nexum_tts_${Date.now()}.mp3`);

  try {
    await exec("edge-tts", [
      "--voice", voice,
      "--text",  text.slice(0, 3000),
      "--write-media", tmpOut,
      "--rate", "+0%",   // natural speed
      "--pitch", "+0Hz", // natural pitch
    ]);
    const buf = fs.readFileSync(tmpOut);
    fs.unlinkSync(tmpOut);
    return buf;
  } catch (e) {
    log.debug(`TTS failed (${effectiveLang}/${voice}): ${e}`);
    // Fallback to English
    if (effectiveLang !== "en") {
      try {
        await exec("edge-tts", [
          "--voice", VOICE_MAP["en"]!,
          "--text",  text.slice(0, 3000),
          "--write-media", tmpOut,
        ]);
        const buf = fs.readFileSync(tmpOut);
        fs.unlinkSync(tmpOut);
        return buf;
      } catch {}
    }
    try { fs.unlinkSync(tmpOut); } catch {}
    return null;
  }
}
