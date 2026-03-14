// Reaction system — ported from OpenClaw status-reaction-variants architecture
// Smart status-based reactions: queued → thinking → tool → done/error

// Full set of Telegram-supported emoji reactions (from OpenClaw)
const TELEGRAM_SUPPORTED_REACTIONS = new Set([
  '❤','👍','👎','🔥','🥰','👏','😁','🤔','🤯','😱','🤬','😢','🎉','🤩','🤮',
  '💩','🙏','👌','🕊','🤡','🥱','🥴','😍','🐳','❤‍🔥','🌚','🌭','💯','🤣','⚡',
  '🍌','🏆','💔','🤨','😐','🍓','🍾','💋','🖕','😈','😴','😭','🤓','👻',
  '👨‍💻','👀','🎃','🙈','😇','😨','🤝','✍','🤗','🫡','🎅','🎄','☃','💅',
  '🤪','🗿','🆒','💘','🙉','🦄','😘','💊','🙊','😎','👾','🤷‍♂','🤷','🤷‍♀','😡',
]);

// Status reaction variants (OpenClaw architecture)
export const STATUS_REACTIONS = {
  queued:    ['👀', '👍', '🔥'],
  thinking:  ['🤔', '🤓', '👀'],
  tool:      ['🔥', '⚡', '👍'],
  coding:    ['👨‍💻', '🔥', '⚡'],
  web:       ['⚡', '🔥', '👍'],
  done:      ['👍', '🎉', '💯'],
  error:     ['😱', '😨', '🤯'],
  stallSoft: ['🥱', '😴', '🤔'],
  stallHard: ['😨', '😱', '⚡'],
};

export type StatusKey = keyof typeof STATUS_REACTIONS;

// Context-aware reaction picker (OpenClaw-style)
export function pickContextualReaction(text: string): string {
  const t = text.toLowerCase();

  // Sentiment-based (like OpenClaw)
  if (/спасибо|thank|merci|danke|gracias|شكر/i.test(t))     return '🙏';
  if (/люблю|love|amor|liebe/i.test(t))                     return '❤';
  if (/помоги|help|assist/i.test(t))                        return '👌';
  if (/привет|hello|hi\b|hey\b|salut|ciao/i.test(t))       return '🤗';
  if (/круто|отлично|супер|awesome|cool|wow|amazing/i.test(t)) return '🔥';
  if (/смешно|хаха|lol|funny|хехе/i.test(t))               return '😁';
  if (/грустно|sad|жаль|сочувств/i.test(t))                 return '😢';
  if (/деньги|финанс|money|cash|бюджет/i.test(t))           return '💯';
  if (/код|code|программ|debug|script/i.test(t))            return '👨‍💻';
  if (/поиск|search|найди|find|ищи/i.test(t))               return '👀';
  if (/сайт|website|web|html/i.test(t))                     return '🌚';
  if (/ошибка|error|fail|broke|сломал/i.test(t))            return '🤯';
  if (/вопрос|question|почему|why|how|как/i.test(t))        return '🤔';

  // Random from general pool (human-like)
  const pool = ['👍', '🔥', '❤', '⚡', '🎉', '👏', '💯', '🤩'];
  return pool[Math.floor(Math.random() * pool.length)];
}

export function isSupportedReaction(emoji: string): boolean {
  return TELEGRAM_SUPPORTED_REACTIONS.has(emoji);
}

// Resolve best variant for a status (OpenClaw fallback chain)
export function resolveStatusReaction(status: StatusKey): string {
  const variants = STATUS_REACTIONS[status];
  for (const emoji of variants) {
    if (isSupportedReaction(emoji)) return emoji;
  }
  return '👍';
}

// React with probability (OpenClaw: human-like, not every message)
export function shouldReact(probability = 0.4): boolean {
  return Math.random() < probability;
}
