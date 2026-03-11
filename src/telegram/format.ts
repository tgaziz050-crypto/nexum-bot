/**
 * Format AI response for Telegram.
 * AI outputs Markdown → we send with parse_mode: "Markdown"
 * But Telegram's Markdown is picky — clean it up.
 */
export function formatForTelegram(text: string): string {
  if (!text) return "";

  let t = text;

  // Remove <think>...</think> blocks (some models like DeepSeek)
  t = t.replace(/<think>[\s\S]*?<\/think>/g, "").trim();

  // Strip accidental CJK chars injected by some providers
  t = t.replace(/[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]+/g, "");

  // Normalize line breaks
  t = t.replace(/\r\n/g, "\n").replace(/\r/g, "\n");

  // Max 2 consecutive newlines
  t = t.replace(/\n{3,}/g, "\n\n");

  return t.trim();
}

/**
 * Smart split: break long text at paragraph boundaries, max 4000 chars per chunk.
 */
export function smartSplit(text: string, max = 4000): string[] {
  if (text.length <= max) return [text];
  const chunks: string[] = [];
  const paras  = text.split("\n\n");
  let cur       = "";

  for (const para of paras) {
    const candidate = cur ? cur + "\n\n" + para : para;
    if (candidate.length <= max) {
      cur = candidate;
    } else {
      if (cur) chunks.push(cur);
      // If single paragraph too long, split by lines
      if (para.length > max) {
        const lines = para.split("\n");
        let lineBuf = "";
        for (const line of lines) {
          const lc = lineBuf ? lineBuf + "\n" + line : line;
          if (lc.length <= max) {
            lineBuf = lc;
          } else {
            if (lineBuf) chunks.push(lineBuf);
            // Hard split if single line > max
            let l = line;
            while (l.length > max) { chunks.push(l.slice(0, max)); l = l.slice(max); }
            lineBuf = l;
          }
        }
        cur = lineBuf;
      } else {
        cur = para;
      }
    }
  }
  if (cur.trim()) chunks.push(cur);
  return chunks.filter(c => c.trim());
}
