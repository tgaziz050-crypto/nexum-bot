import { Config } from "../core/config.js";
import { log } from "../core/logger.js";

async function serperSearch(q: string): Promise<string | null> {
  const key = Config.SERPER_KEYS[0];
  if (!key) return null;
  try {
    const res = await fetch("https://google.serper.dev/search", {
      method:  "POST",
      headers: { "X-API-KEY": key, "Content-Type": "application/json" },
      body:    JSON.stringify({ q, num: 8 }),
    });
    const d = await res.json() as {
      organic?: { title: string; snippet: string; link: string }[];
      knowledgeGraph?: { description?: string };
    };
    const parts: string[] = [];
    if (d.knowledgeGraph?.description) parts.push(d.knowledgeGraph.description);
    for (const r of (d.organic ?? []).slice(0, 6)) {
      if (r.snippet) parts.push(`• ${r.title}: ${r.snippet}`);
    }
    return parts.join("\n") || null;
  } catch (e) {
    log.debug(`Serper: ${e}`);
    return null;
  }
}

async function braveSearch(q: string): Promise<string | null> {
  const key = Config.BRAVE_KEYS[0];
  if (!key) return null;
  try {
    const res = await fetch(`https://api.search.brave.com/res/v1/web/search?q=${encodeURIComponent(q)}&count=6`, {
      headers: { "Accept": "application/json", "X-Subscription-Token": key },
    });
    const d = await res.json() as { web?: { results?: { title: string; description: string }[] } };
    const parts = (d.web?.results ?? []).slice(0, 6)
      .filter(r => r.description)
      .map(r => `• ${r.title}: ${r.description}`);
    return parts.join("\n") || null;
  } catch (e) {
    log.debug(`Brave: ${e}`);
    return null;
  }
}

async function ddgSearch(q: string): Promise<string | null> {
  try {
    const url = `https://api.duckduckgo.com/?q=${encodeURIComponent(q)}&format=json&no_html=1&skip_disambig=1`;
    const res = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0" } });
    const d   = await res.json() as {
      AbstractText?: string;
      RelatedTopics?: { Text?: string }[];
    };
    const parts: string[] = [];
    if (d.AbstractText) parts.push(d.AbstractText);
    for (const r of (d.RelatedTopics ?? []).slice(0, 5)) {
      if (r.Text) parts.push(`• ${r.Text}`);
    }
    return parts.join("\n") || null;
  } catch (e) {
    log.debug(`DDG: ${e}`);
    return null;
  }
}

export async function webSearch(query: string): Promise<string | null> {
  // Serper → Brave → DDG
  const r1 = await serperSearch(query);
  if (r1) return r1;

  const r2 = await braveSearch(query);
  if (r2) return r2;

  return ddgSearch(query);
}

export async function readPage(url: string): Promise<string | null> {
  try {
    // Try Jina reader first (free, handles JS)
    const res = await fetch(`https://r.jina.ai/${url}`, {
      headers: { "Accept": "text/plain", "User-Agent": "Mozilla/5.0" },
      signal: AbortSignal.timeout(15_000),
    });
    if (res.ok) {
      const text = await res.text();
      return text.slice(0, 6000) || null;
    }
  } catch {}

  // Fallback: raw fetch
  try {
    const res  = await fetch(url, {
      headers: { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" },
      signal: AbortSignal.timeout(10_000),
    });
    const html = await res.text();
    // Strip HTML tags
    const text = html
      .replace(/<script[\s\S]*?<\/script>/gi, "")
      .replace(/<style[\s\S]*?<\/style>/gi, "")
      .replace(/<[^>]+>/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    return text.slice(0, 5000) || null;
  } catch {
    return null;
  }
}
