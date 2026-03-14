import * as dotenv from 'dotenv';
dotenv.config();

function keys(prefix: string): string[] {
  const out: string[] = [];
  for (let i = 1; i <= 10; i++) {
    const v = process.env[`${prefix}${i}`]?.trim();
    if (v) out.push(v);
  }
  return out;
}

export const config = {
  botToken:   process.env.BOT_TOKEN!,
  adminIds:   (process.env.ADMIN_IDS || '').split(',').map(s => parseInt(s.trim())).filter(Boolean),
  webappUrl:  (process.env.WEBAPP_URL || '').replace(/\/$/, ''),
  port:       parseInt(process.env.PORT || process.env.NODE_PORT || '3000'),
  dbPath:     process.env.DB_PATH || './data/nexum.db',
  publicBot:  process.env.PUBLIC_BOT === 'true',

  ai: {
    cerebras:   keys('CB'),
    groq:       keys('GR'),
    gemini:     keys('G'),
    grok:       keys('GK'),
    sambanova:  keys('SN'),
    together:   keys('TO'),
    openrouter: keys('OR'),
    deepseek:   keys('DS'),
    claude:     keys('CL'),
  },
  serper: [
    process.env.SERPER_KEY,
    process.env.SERPER_KEY2,
    process.env.SERPER_KEY3,
  ].filter(Boolean) as string[],
};

// Round-robin key rotation per provider
const _idx: Record<string, number> = {};
export function getKey(provider: keyof typeof config.ai): string | null {
  const list = config.ai[provider];
  if (!list.length) return null;
  const i = (_idx[provider] || 0) % list.length;
  _idx[provider] = i + 1;
  return list[i];
}

export function getSerperKey(): string | null {
  if (!config.serper.length) return null;
  const i = (_idx['serper'] || 0) % config.serper.length;
  _idx['serper'] = i + 1;
  return config.serper[i];
}
