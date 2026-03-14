// Telegram message formatter — architecture from OpenClaw
// Converts Markdown to proper Telegram HTML with safe chunking

export function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function escapeHtmlAttr(text: string): string {
  return escapeHtml(text).replace(/"/g, '&quot;');
}

export function markdownToTelegramHtml(markdown: string): string {
  let text = (markdown ?? '').toString();
  text = text.replace(/```(\w*)\n?([\s\S]*?)```/g, (_m: string, _lang: string, code: string) =>
    `<pre><code>${escapeHtml(code.trim())}</code></pre>`
  );
  text = text.replace(/`([^`\n]+)`/g, (_m: string, code: string) => `<code>${escapeHtml(code)}</code>`);
  text = text.replace(/\*\*(.+?)\*\*/gs, '<b>$1</b>');
  text = text.replace(/\*([^*\n]+?)\*/g, '<b>$1</b>');
  text = text.replace(/__(.+?)__/gs, '<i>$1</i>');
  text = text.replace(/_([^_\n]+?)_/g, '<i>$1</i>');
  text = text.replace(/~~(.+?)~~/gs, '<s>$1</s>');
  text = text.replace(/\|\|(.+?)\|\|/gs, '<tg-spoiler>$1</tg-spoiler>');
  text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_m: string, label: string, href: string) =>
    `<a href="${escapeHtmlAttr(href.trim())}">${label}</a>`
  );
  text = text.replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>');
  text = text.replace(/^#{1,6}\s+(.+)$/gm, '<b>$1</b>');
  text = text.replace(/^---+$/gm, '─────────────────');
  return text;
}

export function splitTelegramMessage(text: string, limit = 4000): string[] {
  if (text.length <= limit) return [text];
  const chunks: string[] = [];
  let remaining = text;
  while (remaining.length > limit) {
    let splitAt = remaining.lastIndexOf('\n\n', limit);
    if (splitAt < Math.floor(limit * 0.5)) splitAt = remaining.lastIndexOf('\n', limit);
    if (splitAt < Math.floor(limit * 0.3)) splitAt = remaining.lastIndexOf('. ', limit);
    if (splitAt < 1) splitAt = limit;
    chunks.push(remaining.slice(0, splitAt).trimEnd());
    remaining = remaining.slice(splitAt).trim();
  }
  if (remaining) chunks.push(remaining);
  return chunks;
}

export function stripMarkdownForPlainText(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, '[код]')
    .replace(/`[^`]+`/g, (m: string) => m.slice(1, -1))
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/\*(.+?)\*/g, '$1')
    .replace(/__(.+?)__/g, '$1')
    .replace(/_(.+?)_/g, '$1')
    .replace(/~~(.+?)~~/g, '$1')
    .replace(/\|\|(.+?)\|\|/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^> /gm, '')
    .trim();
}
