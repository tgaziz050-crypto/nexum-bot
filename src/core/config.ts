import 'dotenv/config';

function getKeys(prefix: string): string[] {
  const keys: string[] = [];
  for (let i = 1; i <= 10; i++) {
    const v = process.env[`${prefix}${i}`]?.trim();
    if (v) keys.push(v);
  }
  return keys;
}

export const config = {
  botToken: process.env.BOT_TOKEN!,
  adminIds: (process.env.ADMIN_IDS || '').split(',').map(s => parseInt(s.trim())).filter(Boolean),
  webappUrl: process.env.WEBAPP_URL || '',
  port: parseInt(process.env.PORT || '3000'),

  ai: {
    cerebras:   getKeys('CB'),
    groq:       getKeys('GR'),
    gemini:     getKeys('G'),
    grok:       getKeys('GK'),
    sambanova:  getKeys('SN'),
    together:   getKeys('TO'),
    openrouter: getKeys('OR'),
    deepseek:   getKeys('DS'),
    claude:     getKeys('CL'),
  },

  serper: getKeys('SERPER_KEY'),

  voiceMode: process.env.VOICE_MODE || 'auto', // auto | always | never

  wsPort: parseInt(process.env.WS_PORT || '18790'),
};

// Rotate through keys
const rotations: Record<string, number> = {};
export function getKey(provider: keyof typeof config.ai): string | null {
  const keys = config.ai[provider];
  if (!keys.length) return null;
  const idx = (rotations[provider] || 0) % keys.length;
  rotations[provider] = idx + 1;
  return keys[idx];
}

export function getAnyKey(): { key: string; provider: string } | null {
  const order: (keyof typeof config.ai)[] = [
    'cerebras', 'groq', 'gemini', 'grok', 'sambanova',
    'together', 'openrouter', 'deepseek', 'claude'
  ];
  for (const p of order) {
    const k = getKey(p);
    if (k) return { key: k, provider: p };
  }
  return null;
}
