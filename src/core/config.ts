import "dotenv/config";

function env(key: string, fallback = ""): string {
  return process.env[key] ?? fallback;
}
function envList(prefix: string): string[] {
  const keys: string[] = [];
  for (let i = 1; i <= 20; i++) {
    const v = process.env[`${prefix}${i}`];
    if (v?.trim()) keys.push(v.trim());
  }
  return keys;
}

export const Config = {
  BOT_TOKEN:   env("BOT_TOKEN"),
  DB_PATH:     env("DB_PATH", "./nexum.db"),
  ADMIN_IDS:   env("ADMIN_IDS").split(",").map(s => parseInt(s.trim())).filter(Boolean),
  PUBLIC_BOT:  env("PUBLIC_BOT", "true") === "true",
  NODE_PORT:   parseInt(env("NODE_PORT", "18790")),
  WEBAPP_PORT: parseInt(env("WEBAPP_PORT", "3000")),
  WEBAPP_URL:  env("WEBAPP_URL", ""),
  LOG_LEVEL:   env("LOG_LEVEL", "info"),
  VERSION:     "5.0.0",

  // AI Keys — stored in Railway, never in code
  CEREBRAS_KEYS:   envList("CB"),
  GROQ_KEYS:       envList("GR"),
  GEMINI_KEYS:     envList("G"),
  GROK_KEYS:       envList("GK"),
  SAMBANOVA_KEYS:  envList("SN"),
  TOGETHER_KEYS:   envList("TO"),
  OPENROUTER_KEYS: envList("OR"),
  DEEPSEEK_KEYS:   envList("DS"),
  CLAUDE_KEYS:     envList("CL"),

  SERPER_KEYS: envList("SERPER_KEY"),
  BRAVE_KEYS:  envList("BRAVE_KEY"),
} as const;

if (!Config.BOT_TOKEN) {
  console.error("❌ BOT_TOKEN не задан. Добавь в Railway → Variables.");
  process.exit(1);
}

const totalKeys =
  Config.CEREBRAS_KEYS.length + Config.GROQ_KEYS.length +
  Config.GEMINI_KEYS.length   + Config.GROK_KEYS.length +
  Config.SAMBANOVA_KEYS.length + Config.TOGETHER_KEYS.length +
  Config.OPENROUTER_KEYS.length + Config.DEEPSEEK_KEYS.length +
  Config.CLAUDE_KEYS.length;

if (totalKeys === 0) {
  console.error("❌ Нет AI ключей. Добавь CB1, GR1 или G1 в Railway Variables.");
  process.exit(1);
}

console.log(
  `✅ NEXUM v${Config.VERSION} | ` +
  `CB×${Config.CEREBRAS_KEYS.length} GR×${Config.GROQ_KEYS.length} ` +
  `G×${Config.GEMINI_KEYS.length} GK×${Config.GROK_KEYS.length} ` +
  `OR×${Config.OPENROUTER_KEYS.length} DS×${Config.DEEPSEEK_KEYS.length} ` +
  `CL×${Config.CLAUDE_KEYS.length} | ` +
  `PUBLIC=${Config.PUBLIC_BOT} ADMINS=${Config.ADMIN_IDS.length}`
);
