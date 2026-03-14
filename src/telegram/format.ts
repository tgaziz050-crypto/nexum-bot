// Telegram HTML formatter — ported from OpenClaw architecture
// Converts Markdown to Telegram HTML with safe escaping and chunking

export type FormattedChunk = { html: string; text: string };

// ── HTML escaping ────────────────────────────────────────────────────────────

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function escapeHtmlAttr(text: string): string {
  return escapeHtml(text).replace(/"/g, '&quot;');
}

// File extensions that share TLDs — wrap in <code> to prevent Telegram link previews
const FILE_EXTENSIONS_WITH_TLD = new Set(['md','go','py','pl','sh','am','at','be','cc']);

function isAutoLinkedFileRef(href: string, label: string): boolean {
  const stripped = href.replace(/^https?:\/\//i, '');
  if (stripped !== label) return false;
  const dotIndex = label.lastIndexOf('.');
  if (dotIndex < 1) return false;
  const ext = label.slice(dotIndex + 1).toLowerCase();
  return FILE_EXTENSIONS_WITH_TLD.has(ext);
}

// ── Core Markdown → Telegram HTML ───────────────────────────────────────────

export function markdownToTelegramHtml(markdown: string): string {
  if (!markdown) return '';
  let text = markdown;

  // Code blocks (must be first)
  text = text.replace(/```(\w+)?\n?([\s\S]*?)```/g, (_m, _lang, code) =>
    `<pre><code>${escapeHtml(code.trim())}</code></pre>`
  );

  // Inline code
  text = text.replace(/`([^`]+)`/g, (_m, code) =>
    `<code>${escapeHtml(code)}</code>`
  );

  // Bold
  text = text.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
  text = text.replace(/__(.+?)__/g, '<b>$1</b>');

  // Italic
  text = text.replace(/\*(.+?)\*/g, '<i>$1</i>');
  text = text.replace(/_(.+?)_/g, '<i>$1</i>');

  // Strikethrough
  text = text.replace(/~~(.+?)~~/g, '<s>$1</s>');

  // Spoiler (||text||)
  text = text.replace(/\|\|(.+?)\|\|/g, '<tg-spoiler>$1</tg-spoiler>');

  // Blockquote
  text = text.replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>');

  // Headers → bold
  text = text.replace(/^#{1,6}\s+(.+)$/gm, '<b>$1</b>');

  // Links
  text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_m, label, href) => {
    if (isAutoLinkedFileRef(href, label)) return `<code>${escapeHtml(label)}</code>`;
    return `<a href="${escapeHtmlAttr(href)}">${label}</a>`;
  });

  // Horizontal rules
  text = text.replace(/^(-{3,}|\*{3,}|_{3,})$/gm, '—————');

  // Escape remaining < > & that aren't inside our HTML tags
  // (already handled above for content, protect raw HTML)

  return text.trim();
}

// ── Smart text chunking (OpenClaw-style) ────────────────────────────────────

const MAX_TELEGRAM_MESSAGE = 4096;
const CHUNK_SOFT_MAX = 3000;

export function chunkTelegramText(text: string): string[] {
  if (text.length <= MAX_TELEGRAM_MESSAGE) return [text];

  const chunks: string[] = [];
  const paragraphs = text.split(/\n\n+/);
  let current = '';

  for (const para of paragraphs) {
    if ((current + '\n\n' + para).length > CHUNK_SOFT_MAX && current) {
      chunks.push(current.trim());
      current = para;
    } else {
      current = current ? current + '\n\n' + para : para;
    }
  }

  if (current.trim()) chunks.push(current.trim());

  // Hard split anything still too long
  const result: string[] = [];
  for (const chunk of chunks) {
    if (chunk.length <= MAX_TELEGRAM_MESSAGE) {
      result.push(chunk);
    } else {
      for (let i = 0; i < chunk.length; i += MAX_TELEGRAM_MESSAGE) {
        result.push(chunk.slice(i, i + MAX_TELEGRAM_MESSAGE));
      }
    }
  }

  return result;
}

// ── Streaming draft helper ───────────────────────────────────────────────────

export class DraftStream {
  private buffer = '';
  private lastSent = '';
  private readonly minChars: number;
  private readonly maxChars: number;

  constructor(opts: { minChars?: number; maxChars?: number } = {}) {
    this.minChars = opts.minChars ?? 200;
    this.maxChars = opts.maxChars ?? 800;
  }

  push(chunk: string): string | null {
    this.buffer += chunk;
    const delta = this.buffer.length - this.lastSent.length;
    if (delta >= this.minChars || this.buffer.length >= this.maxChars) {
      const toSend = this.buffer;
      this.lastSent = toSend;
      return toSend;
    }
    return null;
  }

  flush(): string | null {
    if (this.buffer !== this.lastSent) {
      this.lastSent = this.buffer;
      return this.buffer;
    }
    return null;
  }
}
