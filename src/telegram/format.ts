/**
 * NEXUM — Format AI response for Telegram.
 * Handles Markdown cleanup, splits long messages, strips think-tags.
 */

export function formatForTelegram(text: string): string {
  if (!text) return "";
  let t = text;

  // Remove <think>...</think> (DeepSeek, etc.)
  t = t.replace(/<think>[\s\S]*?<\/think>/gi, "").trim();

  // Remove HTML-like tags that AI sometimes inserts
  t = t.replace(/<[^>]{1,50}>/g, "");

  // Normalize line breaks
  t = t.replace(/\r\n/g, "\n").replace(/\r/g, "\n");

  // Max 2 consecutive newlines
  t = t.replace(/\n{3,}/g, "\n\n");

  // Fix common Markdown escape issues that Telegram can't handle
  // Telegram only supports: *bold* _italic_ `code` ```code blocks``` [links]
  // Remove HTML entities
  t = t.replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">");

  return t.trim();
}

export function smartSplit(text: string, max = 4000): string[] {
  if (text.length <= max) return [text];

  const chunks: string[] = [];
  const paras = text.split("\n\n");
  let cur = "";

  for (const para of paras) {
    const candidate = cur ? cur + "\n\n" + para : para;
    if (candidate.length <= max) {
      cur = candidate;
    } else {
      if (cur) chunks.push(cur);
      if (para.length > max) {
        // Split by lines
        const lines = para.split("\n");
        let buf = "";
        for (const line of lines) {
          const lc = buf ? buf + "\n" + line : line;
          if (lc.length <= max) {
            buf = lc;
          } else {
            if (buf) chunks.push(buf);
            // Hard split
            let l = line;
            while (l.length > max) { chunks.push(l.slice(0, max)); l = l.slice(max); }
            buf = l;
          }
        }
        cur = buf;
      } else {
        cur = para;
      }
    }
  }
  if (cur.trim()) chunks.push(cur);
  return chunks.filter(c => c.trim());
}

/** Strip all Markdown for plain-text fallback */
export function stripMarkdown(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/__(.+?)__/g, "$1")
    .replace(/\*(.+?)\*/g, "$1")
    .replace(/_(.+?)_/g, "$1")
    .replace(/```[\s\S]*?```/g, (m) => m.replace(/```\w*\n?/g, "").trim())
    .replace(/`(.+?)`/g, "$1")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .trim();
}
