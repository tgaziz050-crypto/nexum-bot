import { exec } from 'child_process';
import { promisify } from 'util';
import fs from 'fs/promises';
import path from 'path';
import os from 'os';

const execAsync = promisify(exec);

// ── 60+ Microsoft Neural voices — все языки мира без акцента ──────────────
export const VOICES: Record<string, { name: string; voices: string[] }> = {
  ru: { name: 'Русский', voices: ['ru-RU-SvetlanaNeural', 'ru-RU-DmitryNeural', 'ru-RU-DariyaNeural'] },
  en: { name: 'English', voices: ['en-US-AriaNeural', 'en-US-GuyNeural', 'en-US-JennyNeural', 'en-GB-SoniaNeural', 'en-AU-NatashaNeural'] },
  uz: { name: "O'zbek", voices: ['uz-UZ-MadinaNeural', 'uz-UZ-SardorNeural'] },
  de: { name: 'Deutsch', voices: ['de-DE-KatjaNeural', 'de-DE-ConradNeural', 'de-DE-AmalaNeural'] },
  fr: { name: 'Français', voices: ['fr-FR-DeniseNeural', 'fr-FR-HenriNeural', 'fr-FR-EloiseNeural'] },
  es: { name: 'Español', voices: ['es-ES-ElviraNeural', 'es-ES-AlvaroNeural', 'es-MX-DaliaNeural'] },
  it: { name: 'Italiano', voices: ['it-IT-ElsaNeural', 'it-IT-DiegoNeural', 'it-IT-IsabellaNeural'] },
  pt: { name: 'Português', voices: ['pt-BR-FranciscaNeural', 'pt-BR-AntonioNeural', 'pt-PT-RaquelNeural'] },
  ar: { name: 'العربية', voices: ['ar-SA-ZariyahNeural', 'ar-SA-HamedNeural', 'ar-EG-SalmaNeural'] },
  zh: { name: '中文', voices: ['zh-CN-XiaoxiaoNeural', 'zh-CN-YunxiNeural', 'zh-TW-HsiaoChenNeural'] },
  ja: { name: '日本語', voices: ['ja-JP-NanamiNeural', 'ja-JP-KeitaNeural', 'ja-JP-MayuNeural'] },
  ko: { name: '한국어', voices: ['ko-KR-SunHiNeural', 'ko-KR-InJoonNeural', 'ko-KR-BongJinNeural'] },
  tr: { name: 'Türkçe', voices: ['tr-TR-EmelNeural', 'tr-TR-AhmetNeural'] },
  uk: { name: 'Українська', voices: ['uk-UA-PolinaNeural', 'uk-UA-OstapNeural'] },
  kk: { name: 'Қазақша', voices: ['kk-KZ-AigulNeural', 'kk-KZ-DauletNeural'] },
  pl: { name: 'Polski', voices: ['pl-PL-ZofiaNeural', 'pl-PL-MarekNeural', 'pl-PL-AgnieszkaNeural'] },
  hi: { name: 'हिन्दी', voices: ['hi-IN-SwaraNeural', 'hi-IN-MadhurNeural', 'hi-IN-AaravNeural'] },
  he: { name: 'עברית', voices: ['he-IL-HilaNeural', 'he-IL-AvriNeural'] },
  th: { name: 'ภาษาไทย', voices: ['th-TH-PremwadeeNeural', 'th-TH-NiwatNeural', 'th-TH-AcharaNeural'] },
  vi: { name: 'Tiếng Việt', voices: ['vi-VN-HoaiMyNeural', 'vi-VN-NamMinhNeural'] },
  nl: { name: 'Nederlands', voices: ['nl-NL-ColetteNeural', 'nl-NL-MaartenNeural', 'nl-BE-DenaNeural'] },
  sv: { name: 'Svenska', voices: ['sv-SE-SofieNeural', 'sv-SE-MattiasNeural'] },
  da: { name: 'Dansk', voices: ['da-DK-ChristelNeural', 'da-DK-JeppeNeural'] },
  fi: { name: 'Suomi', voices: ['fi-FI-SelmaNeural', 'fi-FI-HarriNeural', 'fi-FI-NooraNeural'] },
  nb: { name: 'Norsk', voices: ['nb-NO-PernilleNeural', 'nb-NO-FinnNeural', 'nb-NO-IselinNeural'] },
  cs: { name: 'Čeština', voices: ['cs-CZ-VlastaNeural', 'cs-CZ-AntoninNeural'] },
  sk: { name: 'Slovenčina', voices: ['sk-SK-ViktoriaNeural', 'sk-SK-LukasNeural'] },
  ro: { name: 'Română', voices: ['ro-RO-AlinaNeural', 'ro-RO-EmilNeural'] },
  hu: { name: 'Magyar', voices: ['hu-HU-NoemiNeural', 'hu-HU-TamasNeural'] },
  bg: { name: 'Български', voices: ['bg-BG-KalinaNeural', 'bg-BG-BorislavNeural'] },
  hr: { name: 'Hrvatski', voices: ['hr-HR-GabrijelaNeural', 'hr-HR-SreckoNeural'] },
  sr: { name: 'Српски', voices: ['sr-RS-SophieNeural', 'sr-RS-NicholasNeural'] },
  el: { name: 'Ελληνικά', voices: ['el-GR-AthinaNeural', 'el-GR-NestorasNeural'] },
  id: { name: 'Bahasa Indonesia', voices: ['id-ID-GadisNeural', 'id-ID-ArdiNeural'] },
  ms: { name: 'Bahasa Melayu', voices: ['ms-MY-YasminNeural', 'ms-MY-OsmanNeural'] },
  tl: { name: 'Filipino', voices: ['fil-PH-BlessicaNeural', 'fil-PH-AngeloNeural'] },
  ta: { name: 'தமிழ்', voices: ['ta-IN-PallaviNeural', 'ta-IN-ValluvarNeural'] },
  te: { name: 'తెలుగు', voices: ['te-IN-ShrutiNeural', 'te-IN-MohanNeural'] },
  bn: { name: 'বাংলা', voices: ['bn-BD-NabanitaNeural', 'bn-BD-PradeepNeural'] },
  fa: { name: 'فارسی', voices: ['fa-IR-DilaraNeural', 'fa-IR-FaridNeural'] },
  ur: { name: 'اردو', voices: ['ur-PK-UzmaNeural', 'ur-PK-AsadNeural'] },
  sw: { name: 'Kiswahili', voices: ['sw-KE-ZuriNeural', 'sw-KE-RafikiNeural'] },
  af: { name: 'Afrikaans', voices: ['af-ZA-AdriNeural', 'af-ZA-WillemNeural'] },
  az: { name: 'Azərbaycan', voices: ['az-AZ-BabekNeural', 'az-AZ-BanuNeural'] },
  ka: { name: 'ქართული', voices: ['ka-GE-EkaNeural', 'ka-GE-GiorgiNeural'] },
  lt: { name: 'Lietuvių', voices: ['lt-LT-OnaNeural', 'lt-LT-LeonasNeural'] },
  lv: { name: 'Latviešu', voices: ['lv-LV-EveritaNeural', 'lv-LV-NilsNeural'] },
  et: { name: 'Eesti', voices: ['et-EE-AnuNeural', 'et-EE-KertNeural'] },
  sl: { name: 'Slovenščina', voices: ['sl-SI-PetraNeural', 'sl-SI-RokNeural'] },
  sq: { name: 'Shqip', voices: ['sq-AL-AnilaNeural', 'sq-AL-IlirNeural'] },
  mk: { name: 'Македонски', voices: ['mk-MK-MarijaNeural', 'mk-MK-AleksandarNeural'] },
  mt: { name: 'Malti', voices: ['mt-MT-GraceNeural', 'mt-MT-JosephNeural'] },
  cy: { name: 'Cymraeg', voices: ['cy-GB-NiaNeural', 'cy-GB-AledNeural'] },
  is: { name: 'Íslenska', voices: ['is-IS-GudrunNeural', 'is-IS-GunnarNeural'] },
  ga: { name: 'Gaeilge', voices: ['ga-IE-OrlaNeural', 'ga-IE-ColmNeural'] },
  gl: { name: 'Galego', voices: ['gl-ES-SabelaNeural', 'gl-ES-RoiNeural'] },
  ca: { name: 'Català', voices: ['ca-ES-JoanaNeural', 'ca-ES-EnricNeural'] },
  eu: { name: 'Euskara', voices: ['eu-ES-AinhoaNeural', 'eu-ES-AnderNeural'] },
  mn: { name: 'Монгол', voices: ['mn-MN-YesuiNeural', 'mn-MN-BataaNeural'] },
  jv: { name: 'Basa Jawa', voices: ['jv-ID-SitiNeural', 'jv-ID-DimasNeural'] },
  su: { name: 'Basa Sunda', voices: ['su-ID-TutiNeural', 'su-ID-JajangNeural'] },
  zu: { name: 'IsiZulu', voices: ['zu-ZA-ThandoNeural', 'zu-ZA-ThembaNeural'] },
  so: { name: 'Soomaali', voices: ['so-SO-UbaxNeural', 'so-SO-MuuseNeural'] },
  ps: { name: 'پښتو', voices: ['ps-AF-LatifaNeural', 'ps-AF-GulNawazNeural'] },
  ky: { name: 'Кыргызча', voices: ['ky-KG-AisuluyNeural', 'ky-KG-ManasNeural'] },
  tg: { name: 'Тоҷикӣ', voices: ['tg-TJ-OmidNeural', 'tg-TJ-DiloromNeural'] },
  tk: { name: 'Türkmen', voices: ['tk-TM-AysheNeural', 'tk-TM-SaparmyratNeural'] },
};

// User voice preferences: uid -> { lang, voiceIdx }
const userVoicePrefs = new Map<number, { lang: string; voiceIdx: number }>();

export function getUserVoicePref(uid: number): { lang: string; voiceIdx: number } {
  return userVoicePrefs.get(uid) || { lang: 'auto', voiceIdx: 0 };
}

export function setUserVoicePref(uid: number, lang: string, voiceIdx: number = 0) {
  userVoicePrefs.set(uid, { lang, voiceIdx });
}

export function detectLanguage(text: string): string {
  if (/[АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя]/.test(text)) {
    if (/ї|є|і/.test(text)) return 'uk';
    if (/қ|ғ|ү|ұ|ң|ө|ә/.test(text)) return 'kk';
    if (/ё|й/.test(text)) return 'ru';
    return 'ru';
  }
  if (/[ا-ي]/.test(text)) return 'ar';
  if (/[\u4E00-\u9FFF]/.test(text)) return 'zh';
  if (/[\u3040-\u30FF]/.test(text)) return 'ja';
  if (/[\uAC00-\uD7AF]/.test(text)) return 'ko';
  if (/[\u0900-\u097F]/.test(text)) return 'hi';
  if (/[\u0590-\u05FF]/.test(text)) return 'he';
  if (/[\u0E00-\u0E7F]/.test(text)) return 'th';
  if (/[\u0600-\u06FF]/.test(text)) {
    if (/[\u067E\u0686\u06AF]/.test(text)) return 'fa';
    return 'ur';
  }
  const l = text.toLowerCase();
  if (/\b(ich|und|der|die|das|nicht|mit|von)\b/.test(l)) return 'de';
  if (/\b(je|tu|il|nous|vous|est|les|des)\b/.test(l)) return 'fr';
  if (/\b(yo|tú|él|que|con|los|las|una)\b/.test(l)) return 'es';
  if (/\b(bir|bu|ve|için|ile|değil)\b/.test(l)) return 'tr';
  if (/\b(siz|bu|va|men|uchun|ham)\b/.test(l)) return 'uz';
  if (/\b(ke|wa|ya|na|ni|kwa)\b/.test(l)) return 'sw';
  if (/\b(ik|het|een|zijn|van|aan)\b/.test(l)) return 'nl';
  if (/\b(en|ett|det|som|med|för)\b/.test(l)) return 'sv';
  if (/\b(da|og|er|til|for|med)\b/.test(l)) return 'da';
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
  voice: string;
}

function getEdgeTTSPath(): string {
  return process.env.EDGE_TTS_PATH || 'edge-tts';
}

export async function textToSpeech(text: string, uid?: number): Promise<TTSResult> {
  const clean = cleanText(text);
  if (!clean) throw new Error('Empty text');

  let lang: string;
  let voiceIdx: number = 0;

  if (uid) {
    const pref = getUserVoicePref(uid);
    lang = pref.lang === 'auto' ? detectLanguage(clean) : pref.lang;
    voiceIdx = pref.voiceIdx;
  } else {
    lang = detectLanguage(clean);
  }

  const voiceData = VOICES[lang] || VOICES['en'];
  const voice = voiceData.voices[voiceIdx % voiceData.voices.length];

  const outFile = path.join(os.tmpdir(), `nx_tts_${Date.now()}_${Math.random().toString(36).slice(2)}.mp3`);
  const txtFile = path.join(os.tmpdir(), `nx_txt_${Date.now()}.txt`);

  try {
    await fs.writeFile(txtFile, clean, 'utf8');
    const edgeBin = getEdgeTTSPath();

    try {
      await execAsync(
        `${edgeBin} --voice "${voice}" --file "${txtFile}" --write-media "${outFile}"`,
        { timeout: 30000 }
      );
      const buf = await fs.readFile(outFile);
      console.log(`[tts] ✅ CLI voice=${voice} lang=${lang} bytes=${buf.length}`);
      return { buffer: buf, format: 'mp3', provider: 'edge-tts-cli', lang, voice };
    } catch (cliErr: any) {
      console.warn('[tts] CLI failed:', cliErr.message?.slice(0, 100));
    }

    const pythonBin = process.env.EDGE_PYTHON_PATH || '/opt/edge-tts-env/bin/python3';
    const pyScript = `import asyncio, edge_tts, sys
async def run():
    text = open(sys.argv[1], encoding='utf-8').read()
    await edge_tts.Communicate(text, sys.argv[2]).save(sys.argv[3])
asyncio.run(run())`;

    const pyFile = path.join(os.tmpdir(), `nx_tts_script_${Date.now()}.py`);
    await fs.writeFile(pyFile, pyScript, 'utf8');
    await execAsync(`${pythonBin} "${pyFile}" "${txtFile}" "${voice}" "${outFile}"`, { timeout: 30000 });
    await fs.unlink(pyFile).catch(() => {});

    const buf = await fs.readFile(outFile);
    console.log(`[tts] ✅ Python voice=${voice} lang=${lang} bytes=${buf.length}`);
    return { buffer: buf, format: 'mp3', provider: 'edge-tts-python', lang, voice };

  } finally {
    await fs.unlink(outFile).catch(() => {});
    await fs.unlink(txtFile).catch(() => {});
  }
}

// Get voice list for UI display
export function getVoiceList(): Array<{ lang: string; name: string; voices: string[] }> {
  return Object.entries(VOICES).map(([lang, data]) => ({
    lang,
    name: data.name,
    voices: data.voices,
  }));
}
