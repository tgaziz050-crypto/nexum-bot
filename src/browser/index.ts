/**
 * NEXUM Browser Module — Chrome CDP/Playwright automation
 * Архитектура взята из OpenClaw src/browser/
 *
 * Возможности:
 *  - navigate(url)           — открыть страницу
 *  - screenshot()            — скриншот (base64 PNG)
 *  - snapshot()              — accessibility snapshot (AI-friendly DOM)
 *  - click(ref)              — клик по элементу
 *  - fill(ref, text)         — ввод текста в поле
 *  - select(ref, values)     — выбор из dropdown
 *  - hover(ref)              — hover
 *  - scroll(direction, amt)  — прокрутка
 *  - evaluate(js)            — выполнение JS на странице
 *  - extractText()           — извлечь весь текст страницы
 *  - getUrl()                — текущий URL
 *  - tabs()                  — список открытых вкладок
 *  - newTab(url)             — новая вкладка
 *  - closeTab()              — закрыть вкладку
 *  - goBack() / goForward()  — история
 *  - waitForNavigation()     — ждать загрузки
 *  - findElements(selector)  — найти элементы
 */

import { chromium, Browser, BrowserContext, Page } from 'playwright';
import * as path from 'path';
import * as os from 'os';

export interface BrowserConfig {
  headless?: boolean;
  userDataDir?: string;
  cdpUrl?: string; // подключиться к существующему Chrome
  timeout?: number;
}

export interface SnapshotElement {
  ref: string;
  role: string;
  name: string;
  value?: string;
  checked?: boolean;
  disabled?: boolean;
  children?: SnapshotElement[];
}

export interface TabInfo {
  id: string;
  url: string;
  title: string;
  active: boolean;
}

let _browser: Browser | null = null;
let _context: BrowserContext | null = null;
let _page: Page | null = null;
let _refMap: Map<string, string> = new Map(); // ref → selector
let _refCounter = 0;

function nextRef(): string {
  return `e${++_refCounter}`;
}

export async function ensureBrowser(cfg: BrowserConfig = {}): Promise<Page> {
  if (_page && !_page.isClosed()) return _page;

  // Если есть CDP URL — подключаемся к существующему Chrome (как OpenClaw)
  if (cfg.cdpUrl) {
    _browser = await chromium.connectOverCDP(cfg.cdpUrl);
    const contexts = _browser.contexts();
    _context = contexts[0] || await _browser.newContext();
    const pages = _context.pages();
    _page = pages[0] || await _context.newPage();
    return _page;
  }

  // Иначе — запускаем свой Chrome
  const userDataDir = cfg.userDataDir || path.join(os.homedir(), '.nexum', 'chrome-profile');

  _context = await chromium.launchPersistentContext(userDataDir, {
    headless: cfg.headless ?? true,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-blink-features=AutomationControlled',
      '--remote-debugging-port=9222',
    ],
    viewport: { width: 1280, height: 800 },
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36',
  });

  const pages = _context.pages();
  _page = pages[0] || await _context.newPage();
  _page.setDefaultTimeout(cfg.timeout ?? 15000);
  return _page;
}

export async function closeBrowser(): Promise<void> {
  try { await _page?.close(); } catch {}
  try { await _context?.close(); } catch {}
  try { await _browser?.close(); } catch {}
  _page = null; _context = null; _browser = null;
}

// ─── Navigation ─────────────────────────────────────────────────────────────

export async function navigate(url: string, cfg?: BrowserConfig): Promise<string> {
  const page = await ensureBrowser(cfg);
  if (!url.startsWith('http')) url = 'https://' + url;
  const response = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 20000 });
  _refMap.clear();
  return `Navigated to ${url} — status: ${response?.status() ?? 'unknown'}`;
}

export async function getUrl(cfg?: BrowserConfig): Promise<string> {
  const page = await ensureBrowser(cfg);
  return page.url();
}

export async function goBack(cfg?: BrowserConfig): Promise<string> {
  const page = await ensureBrowser(cfg);
  await page.goBack({ waitUntil: 'domcontentloaded' });
  return `Back → ${page.url()}`;
}

export async function goForward(cfg?: BrowserConfig): Promise<string> {
  const page = await ensureBrowser(cfg);
  await page.goForward({ waitUntil: 'domcontentloaded' });
  return `Forward → ${page.url()}`;
}

export async function reload(cfg?: BrowserConfig): Promise<string> {
  const page = await ensureBrowser(cfg);
  await page.reload({ waitUntil: 'domcontentloaded' });
  return `Reloaded ${page.url()}`;
}

// ─── Screenshot ─────────────────────────────────────────────────────────────

export async function screenshot(opts: {
  fullPage?: boolean;
  selector?: string;
  cfg?: BrowserConfig;
} = {}): Promise<Buffer> {
  const page = await ensureBrowser(opts.cfg);
  if (opts.selector) {
    const el = page.locator(opts.selector).first();
    return await el.screenshot({ type: 'png' });
  }
  return await page.screenshot({ type: 'png', fullPage: opts.fullPage ?? false });
}

export async function screenshotBase64(opts: { fullPage?: boolean; cfg?: BrowserConfig } = {}): Promise<string> {
  const buf = await screenshot(opts);
  return buf.toString('base64');
}

// ─── Accessibility snapshot (AI-friendly DOM) ────────────────────────────────
// Аналог OpenClaw pw-tools-core.snapshot.ts

export async function snapshot(cfg?: BrowserConfig): Promise<{ text: string; refs: Map<string, string> }> {
  const page = await ensureBrowser(cfg);
  _refMap.clear();

  const rawSnap = await page.accessibility.snapshot({ interestingOnly: true });
  if (!rawSnap) return { text: '(empty page)', refs: _refMap };

  const lines: string[] = [];
  lines.push(`Page: ${page.title()} — ${page.url()}`);
  lines.push('');

  function walk(node: any, depth: number) {
    const indent = '  '.repeat(depth);
    const role = node.role || '';
    const name = node.name || '';
    const value = node.value ? ` value="${node.value}"` : '';
    const checked = node.checked !== undefined ? ` checked=${node.checked}` : '';
    const disabled = node.disabled ? ' [disabled]' : '';

    // Назначаем ref только интерактивным элементам
    const interactive = ['button', 'link', 'textbox', 'checkbox', 'radio',
      'combobox', 'listbox', 'menuitem', 'tab', 'searchbox', 'spinbutton'].includes(role);

    if (interactive || name) {
      const ref = nextRef();
      // Попробуем найти selector
      const selector = name
        ? `[aria-label="${name.replace(/"/g, '\\"')}"], [placeholder="${name.replace(/"/g, '\\"')}"]`
        : `[role="${role}"]`;
      _refMap.set(ref, selector);

      lines.push(`${indent}[${ref}] ${role}${name ? ` "${name}"` : ''}${value}${checked}${disabled}`);
    } else if (role && role !== 'none') {
      lines.push(`${indent}${role}${name ? ` "${name}"` : ''}`);
    }

    if (node.children) {
      for (const child of node.children) walk(child, depth + 1);
    }
  }

  walk(rawSnap, 0);
  return { text: lines.join('\n'), refs: _refMap };
}

// ─── Interactions ────────────────────────────────────────────────────────────
// Аналог OpenClaw pw-tools-core.interactions.ts

function resolveLocator(page: Page, ref: string) {
  // ref может быть: e1, e2... или CSS selector или text="..."
  if (_refMap.has(ref)) {
    const selector = _refMap.get(ref)!;
    return page.locator(selector).first();
  }
  // Прямой CSS/XPath selector
  return page.locator(ref).first();
}

export async function click(ref: string, opts: {
  double?: boolean;
  right?: boolean;
  cfg?: BrowserConfig;
} = {}): Promise<string> {
  const page = await ensureBrowser(opts.cfg);
  const loc = resolveLocator(page, ref);
  try {
    if (opts.double) await loc.dblclick({ timeout: 10000 });
    else if (opts.right) await loc.click({ button: 'right', timeout: 10000 });
    else await loc.click({ timeout: 10000 });
    return `✅ Clicked [${ref}]`;
  } catch (e: any) {
    return `❌ Click failed [${ref}]: ${e.message}`;
  }
}

export async function fill(ref: string, text: string, cfg?: BrowserConfig): Promise<string> {
  const page = await ensureBrowser(cfg);
  const loc = resolveLocator(page, ref);
  try {
    await loc.fill(text, { timeout: 10000 });
    return `✅ Filled [${ref}] with "${text}"`;
  } catch (e: any) {
    // Fallback: press keys
    try {
      await loc.focus();
      await loc.clear();
      await page.keyboard.type(text, { delay: 30 });
      return `✅ Typed [${ref}] "${text}"`;
    } catch (e2: any) {
      return `❌ Fill failed [${ref}]: ${e2.message}`;
    }
  }
}

export async function selectOption(ref: string, values: string[], cfg?: BrowserConfig): Promise<string> {
  const page = await ensureBrowser(cfg);
  const loc = resolveLocator(page, ref);
  try {
    await loc.selectOption(values, { timeout: 8000 });
    return `✅ Selected [${ref}]: ${values.join(', ')}`;
  } catch (e: any) {
    return `❌ Select failed [${ref}]: ${e.message}`;
  }
}

export async function hover(ref: string, cfg?: BrowserConfig): Promise<string> {
  const page = await ensureBrowser(cfg);
  const loc = resolveLocator(page, ref);
  try {
    await loc.hover({ timeout: 8000 });
    return `✅ Hovered [${ref}]`;
  } catch (e: any) {
    return `❌ Hover failed: ${e.message}`;
  }
}

export async function pressKey(key: string, cfg?: BrowserConfig): Promise<string> {
  const page = await ensureBrowser(cfg);
  await page.keyboard.press(key);
  return `✅ Pressed ${key}`;
}

export async function typeText(text: string, cfg?: BrowserConfig): Promise<string> {
  const page = await ensureBrowser(cfg);
  await page.keyboard.type(text, { delay: 30 });
  return `✅ Typed: ${text}`;
}

// ─── Scroll ──────────────────────────────────────────────────────────────────

export async function scroll(direction: 'up' | 'down' | 'left' | 'right', amount = 300, cfg?: BrowserConfig): Promise<string> {
  const page = await ensureBrowser(cfg);
  const delta = {
    up:    { x: 0, y: -amount },
    down:  { x: 0, y: amount },
    left:  { x: -amount, y: 0 },
    right: { x: amount, y: 0 },
  }[direction];
  await page.mouse.wheel(delta.x, delta.y);
  return `✅ Scrolled ${direction} ${amount}px`;
}

// ─── JavaScript evaluation ───────────────────────────────────────────────────

export async function evaluate(js: string, cfg?: BrowserConfig): Promise<string> {
  const page = await ensureBrowser(cfg);
  try {
    const result = await page.evaluate(js);
    return typeof result === 'object' ? JSON.stringify(result, null, 2) : String(result ?? '');
  } catch (e: any) {
    return `❌ JS error: ${e.message}`;
  }
}

// ─── Content extraction ──────────────────────────────────────────────────────

export async function extractText(cfg?: BrowserConfig): Promise<string> {
  const page = await ensureBrowser(cfg);
  const text = await page.evaluate(() => {
    // Remove scripts, styles, nav
    const clone = document.body.cloneNode(true) as HTMLElement;
    clone.querySelectorAll('script, style, nav, footer, header, aside, .ad, [class*="cookie"]')
      .forEach(el => el.remove());
    return (clone.textContent || '').replace(/\s+/g, ' ').trim();
  });
  return text.slice(0, 8000); // Limit
}

export async function extractLinks(cfg?: BrowserConfig): Promise<string> {
  const page = await ensureBrowser(cfg);
  const links = await page.evaluate(() =>
    Array.from(document.querySelectorAll('a[href]'))
      .map(a => ({ text: (a as HTMLAnchorElement).textContent?.trim(), href: (a as HTMLAnchorElement).href }))
      .filter(l => l.href.startsWith('http'))
      .slice(0, 50)
  );
  return links.map(l => `${l.text} → ${l.href}`).join('\n');
}

export async function findElements(selector: string, cfg?: BrowserConfig): Promise<string> {
  const page = await ensureBrowser(cfg);
  try {
    const elements = await page.locator(selector).all();
    const results: string[] = [];
    for (const el of elements.slice(0, 20)) {
      const text = await el.textContent();
      const tag = await el.evaluate(e => e.tagName.toLowerCase());
      results.push(`<${tag}> ${text?.trim().slice(0, 100)}`);
    }
    return results.join('\n') || '(no elements found)';
  } catch (e: any) {
    return `❌ ${e.message}`;
  }
}

// ─── Tabs ────────────────────────────────────────────────────────────────────

export async function getTabs(cfg?: BrowserConfig): Promise<TabInfo[]> {
  await ensureBrowser(cfg);
  if (!_context) return [];
  const pages = _context.pages();
  return Promise.all(pages.map(async (p, i) => ({
    id: String(i),
    url: p.url(),
    title: await p.title(),
    active: p === _page,
  })));
}

export async function newTab(url: string, cfg?: BrowserConfig): Promise<string> {
  await ensureBrowser(cfg);
  if (!_context) return '❌ No browser context';
  const newPage = await _context.newPage();
  _page = newPage;
  if (url) {
    if (!url.startsWith('http')) url = 'https://' + url;
    await newPage.goto(url, { waitUntil: 'domcontentloaded', timeout: 20000 });
  }
  return `✅ New tab: ${url}`;
}

export async function switchTab(index: number, cfg?: BrowserConfig): Promise<string> {
  await ensureBrowser(cfg);
  if (!_context) return '❌ No context';
  const pages = _context.pages();
  if (index < 0 || index >= pages.length) return `❌ Tab ${index} not found`;
  _page = pages[index];
  return `✅ Switched to tab ${index}: ${_page.url()}`;
}

export async function closeTab(cfg?: BrowserConfig): Promise<string> {
  const page = await ensureBrowser(cfg);
  await page.close();
  if (_context) {
    const pages = _context.pages();
    _page = pages[pages.length - 1] || null;
  }
  return '✅ Tab closed';
}

// ─── Wait ────────────────────────────────────────────────────────────────────

export async function waitForText(text: string, timeout = 10000, cfg?: BrowserConfig): Promise<string> {
  const page = await ensureBrowser(cfg);
  try {
    await page.waitForSelector(`text=${text}`, { timeout });
    return `✅ Found: "${text}"`;
  } catch {
    return `❌ Timeout: "${text}" not found within ${timeout}ms`;
  }
}

export async function waitForSelector(selector: string, timeout = 10000, cfg?: BrowserConfig): Promise<string> {
  const page = await ensureBrowser(cfg);
  try {
    await page.waitForSelector(selector, { timeout });
    return `✅ Selector visible: ${selector}`;
  } catch {
    return `❌ Timeout: ${selector}`;
  }
}

// ─── Forms ───────────────────────────────────────────────────────────────────

export async function fillForm(fields: { ref: string; value: string }[], cfg?: BrowserConfig): Promise<string> {
  const results: string[] = [];
  for (const field of fields) {
    results.push(await fill(field.ref, field.value, cfg));
  }
  return results.join('\n');
}

export async function submitForm(ref?: string, cfg?: BrowserConfig): Promise<string> {
  const page = await ensureBrowser(cfg);
  if (ref) {
    return await click(ref, { cfg });
  }
  // Find submit button
  try {
    await page.locator('button[type="submit"], input[type="submit"], button:has-text("Submit"), button:has-text("Send")').first().click({ timeout: 5000 });
    return '✅ Form submitted';
  } catch {
    await page.keyboard.press('Enter');
    return '✅ Submitted via Enter';
  }
}

// ─── High-level helpers ──────────────────────────────────────────────────────

/**
 * Полный цикл: открыть страницу → сделать снапшот → вернуть
 * Используется агентом для "посмотри на страницу"
 */
export async function openAndSnapshot(url: string, cfg?: BrowserConfig): Promise<{
  url: string;
  title: string;
  snapshot: string;
  screenshot: string; // base64
}> {
  await navigate(url, cfg);
  const page = await ensureBrowser(cfg);
  const { text: snapText } = await snapshot(cfg);
  const imgBase64 = await screenshotBase64({ cfg });

  return {
    url: page.url(),
    title: await page.title(),
    snapshot: snapText,
    screenshot: imgBase64,
  };
}

/**
 * Поиск Google и возврат результатов
 */
export async function googleSearch(query: string, cfg?: BrowserConfig): Promise<string> {
  await navigate(`https://www.google.com/search?q=${encodeURIComponent(query)}`, cfg);
  const page = await ensureBrowser(cfg);

  const results = await page.evaluate(() => {
    const items: { title: string; url: string; snippet: string }[] = [];
    document.querySelectorAll('div.g').forEach(el => {
      const a = el.querySelector('a');
      const h3 = el.querySelector('h3');
      const span = el.querySelector('.VwiC3b, .s3v9rd, .IsZvec');
      if (a && h3) {
        items.push({
          title: h3.textContent || '',
          url: (a as HTMLAnchorElement).href,
          snippet: span?.textContent?.trim() || '',
        });
      }
    });
    return items.slice(0, 10);
  });

  return results.map((r, i) => `${i + 1}. ${r.title}\n   ${r.url}\n   ${r.snippet}`).join('\n\n');
}
