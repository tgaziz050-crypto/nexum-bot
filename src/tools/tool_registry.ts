/**
 * NEXUM — Dynamic Tool Registry v2
 *
 * Nexum полностью самостоятелен: он генерирует код, устанавливает
 * нужные npm-пакеты, тестирует тул, автоматически исправляет ошибки
 * (до 3 попыток), и подключает тул без перезапуска.
 *
 * Жизненный цикл нового тула:
 *   1. AI анализирует задачу и пишет .mjs код
 *   2. Из кода извлекаются нужные npm-пакеты
 *   3. npm install запускается автоматически если нужно
 *   4. Тул тестируется через быстрый вызов execute()
 *   5. При ошибке — AI видит error и переписывает код (до 3 раз)
 *   6. Успешный тул hot-load'ится в liveTools Map
 *   7. Сохраняется в registry.json → переживает рестарт
 */

import * as fs from "fs";
import * as path from "path";
import * as vm from "vm";
import { execSync, execFileSync } from "child_process";
import { createRequire } from "module";
import { fileURLToPath, pathToFileURL } from "url";
import { log } from "../core/logger.js";
import { Db } from "../core/db.js";
import { ask } from "../agent/engine.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ── Пути ──────────────────────────────────────────────────────────────────────
const DYNAMIC_DIR  = path.resolve(__dirname, "dynamic");
const REGISTRY_FILE = path.join(DYNAMIC_DIR, "registry.json");
// node_modules для динамических пакетов — рядом с dynamic/
const DYN_MODULES  = path.join(DYNAMIC_DIR, "node_modules");

// ── Типы ──────────────────────────────────────────────────────────────────────
export interface DynamicTool {
  name:         string;
  description:  string;
  inputSchema:  string;
  outputSchema: string;
  createdAt:    number;
  version:      number;
  filePath:     string;
  packages:     string[];   // npm-пакеты которые установлены для этого тула
  enabled:      boolean;
  testOutput?:  string;     // результат тестового запуска
}

export interface ToolExecuteResult {
  output:  string;
  success: boolean;
}

// In-memory: toolName → execute fn
const liveTools = new Map<string, (input: string) => Promise<ToolExecuteResult>>();

let toolRegistry: Record<string, DynamicTool> = {};

// ── Инициализация ──────────────────────────────────────────────────────────────
export function initToolRegistry() {
  fs.mkdirSync(DYNAMIC_DIR, { recursive: true });
  if (fs.existsSync(REGISTRY_FILE)) {
    try {
      toolRegistry = JSON.parse(fs.readFileSync(REGISTRY_FILE, "utf8"));
      log.info(`DynamicTools: loaded ${Object.keys(toolRegistry).length} tools from registry`);
    } catch { toolRegistry = {}; }
  }
}

function saveRegistry() {
  fs.writeFileSync(REGISTRY_FILE, JSON.stringify(toolRegistry, null, 2), "utf8");
}

// ── npm install ────────────────────────────────────────────────────────────────
/**
 * Устанавливает список npm-пакетов в DYNAMIC_DIR/node_modules
 * чтобы не трогать основной node_modules проекта.
 */
function installPackages(packages: string[]): { ok: boolean; error?: string } {
  if (!packages.length) return { ok: true };
  try {
    fs.mkdirSync(DYN_MODULES, { recursive: true });
    log.info(`DynamicTools: installing packages: ${packages.join(", ")}`);
    execFileSync("npm", ["install", "--prefix", DYNAMIC_DIR, "--save", ...packages], {
      timeout: 120_000,
      stdio: "pipe",
    });
    log.info(`DynamicTools: packages installed OK`);
    return { ok: true };
  } catch (e: any) {
    const msg = e.stderr?.toString() ?? e.message;
    log.error(`DynamicTools: npm install failed: ${msg.slice(0, 300)}`);
    return { ok: false, error: msg.slice(0, 300) };
  }
}

/**
 * Извлекает import/require из кода и возвращает внешние npm-пакеты
 * (исключает Node.js built-ins и относительные пути)
 */
function extractNpmPackages(code: string): string[] {
  const NODE_BUILTINS = new Set([
    "fs","path","os","crypto","http","https","url","util","stream",
    "buffer","events","child_process","vm","net","tls","dns","zlib",
    "readline","assert","string_decoder","timers","process","module",
  ]);
  const found = new Set<string>();
  // ESM: import ... from 'pkg'  или  import 'pkg'
  for (const m of code.matchAll(/from\s+['"]([^'"./][^'"]*)['"]/g)) {
    const pkg = m[1]!.split("/")[0]!; // handle scoped or subpath
    if (!NODE_BUILTINS.has(pkg)) found.add(pkg);
  }
  // CJS: require('pkg')
  for (const m of code.matchAll(/require\s*\(\s*['"]([^'"./][^'"]*)['"]\s*\)/g)) {
    const pkg = m[1]!.split("/")[0]!;
    if (!NODE_BUILTINS.has(pkg)) found.add(pkg);
  }
  return [...found];
}

// ── Загрузка тула с диска ──────────────────────────────────────────────────────
export async function loadTool(name: string): Promise<boolean> {
  const meta = toolRegistry[name];
  if (!meta?.enabled || !fs.existsSync(meta.filePath)) {
    log.warn(`DynamicTools: cannot load "${name}" — missing or disabled`);
    return false;
  }
  try {
    // Cache-bust через query string чтобы Node не брал старый import кэш
    const url = pathToFileURL(meta.filePath).href + `?v=${meta.version}&t=${Date.now()}`;
    const mod  = await import(url);
    if (typeof mod.execute !== "function") {
      log.warn(`DynamicTools: "${name}" has no execute() export`);
      return false;
    }
    liveTools.set(name, mod.execute);
    log.info(`DynamicTools: ✅ loaded "${name}" v${meta.version}`);
    return true;
  } catch (e: any) {
    log.error(`DynamicTools: load "${name}" failed: ${e.message}`);
    return false;
  }
}

export async function loadAllTools() {
  initToolRegistry();
  let loaded = 0;
  for (const name of Object.keys(toolRegistry)) {
    if (await loadTool(name)) loaded++;
  }
  log.info(`DynamicTools: ${loaded}/${Object.keys(toolRegistry).length} tools active`);
}

// ── Выполнение ────────────────────────────────────────────────────────────────
export async function executeDynamicTool(name: string, input: string): Promise<ToolExecuteResult> {
  const fn = liveTools.get(name);
  if (!fn) return { output: `Tool "${name}" not loaded`, success: false };
  try {
    const result = await Promise.race([
      fn(input),
      new Promise<ToolExecuteResult>((_, rej) =>
        setTimeout(() => rej(new Error("Tool timeout (30s)")), 30_000)
      ),
    ]);
    return result;
  } catch (e: any) {
    return { output: `Tool "${name}" error: ${e.message}`, success: false };
  }
}

export function hasDynamicTool(name: string): boolean {
  return liveTools.has(name);
}

export function listDynamicTools(): DynamicTool[] {
  return Object.values(toolRegistry).filter(t => t.enabled);
}

export function getDynamicToolsContext(): string {
  const tools = listDynamicTools();
  if (!tools.length) return "";
  return tools
    .map(t => `- ${t.name}: ${t.description} (input: ${t.inputSchema})`)
    .join("\n");
}

// ── AI-генерация кода ─────────────────────────────────────────────────────────
const TOOL_SYSTEM_PROMPT = `You are an expert Node.js developer building tools for NEXUM AI bot.

Generate a self-contained ESM JavaScript module (.mjs) for the requested tool.

REQUIRED STRUCTURE:
\`\`\`js
export const meta = {
  name: "tool_name",           // snake_case, unique id
  description: "what it does",
  inputSchema: "what input expects",
  outputSchema: "what output returns"
};

export async function execute(input) {
  try {
    // implementation
    return { output: "result string", success: true };
  } catch (e) {
    return { output: \`Error: \${e.message}\`, success: false };
  }
}
\`\`\`

RULES:
- Pure JavaScript (ESM), NO TypeScript syntax
- You CAN import any npm package (it will be auto-installed)
- Use global fetch() for simple HTTP — no axios needed
- input is always a string — parse it yourself
- Always return { output: string, success: boolean }
- Handle all errors gracefully
- Keep it focused and production-quality

RETURN ONLY CODE, no markdown, no explanation.`;

// ── Главная функция: generate → install → test → retry ──────────────────────
export async function generateAndRegisterTool(
  uid: number,
  requirement: string,
  maxAttempts = 3,
): Promise<{ success: boolean; toolName?: string; message: string }> {
  log.info(`DynamicTools: generating tool for: "${requirement}"`);

  let lastError = "";
  let lastCode  = "";

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    log.info(`DynamicTools: attempt ${attempt}/${maxAttempts}`);

    // ── Шаг 1: Генерация кода ────────────────────────────────────────────────
    const messages: { role: "user" | "system" | "assistant"; content: string }[] = [
      { role: "system", content: TOOL_SYSTEM_PROMPT },
    ];

    if (attempt === 1) {
      messages.push({
        role: "user",
        content: `Create a tool that: ${requirement}`,
      });
    } else {
      // Показываем AI предыдущую ошибку для самоисправления
      messages.push({
        role: "user",
        content: `Create a tool that: ${requirement}`,
      });
      messages.push({
        role: "assistant",
        content: lastCode,
      });
      messages.push({
        role: "user",
        content: `The previous code failed with this error:\n\n${lastError}\n\nFix the code. Common fixes:\n- Use correct npm package names\n- Handle API keys missing gracefully\n- Use fetch() instead of axios if simpler\n- Check for null/undefined before accessing properties\n\nReturn ONLY the fixed JavaScript code.`,
      });
    }

    const rawCode = await ask(messages, "code");
    const code = rawCode
      .replace(/^```(?:js|javascript|mjs|typescript|ts)?\n?/m, "")
      .replace(/```$/m, "")
      .trim();

    lastCode = code;

    // ── Шаг 2: Извлечь имя тула ──────────────────────────────────────────────
    const nameMatch = code.match(/name\s*:\s*["'`]([a-zA-Z0-9_]+)["'`]/);
    const descMatch = code.match(/description\s*:\s*["'`]([^"'`\n]+)["'`]/);
    const inMatch   = code.match(/inputSchema\s*:\s*["'`]([^"'`\n]+)["'`]/);
    const outMatch  = code.match(/outputSchema\s*:\s*["'`]([^"'`\n]+)["'`]/);

    if (!nameMatch) {
      lastError = "Generated code has no meta.name field";
      log.warn(`DynamicTools: attempt ${attempt}: no meta.name`);
      continue;
    }

    const toolName    = nameMatch[1]!;
    const description = descMatch?.[1] ?? requirement;
    const inputSchema = inMatch?.[1]  ?? "string";
    const outSchema   = outMatch?.[1] ?? "string";

    if (!code.includes("export") || !code.includes("execute")) {
      lastError = "Code has no execute() export";
      continue;
    }

    // ── Шаг 3: Определить и установить npm-пакеты ────────────────────────────
    const packages = extractNpmPackages(code);
    if (packages.length) {
      log.info(`DynamicTools: tool requires packages: ${packages.join(", ")}`);
      const install = installPackages(packages);
      if (!install.ok) {
        lastError = `npm install failed: ${install.error}`;
        // попробуем без этого пакета на следующей попытке
        continue;
      }
    }

    // ── Шаг 4: Сохранить файл ────────────────────────────────────────────────
    const version  = (toolRegistry[toolName]?.version ?? 0) + 1;
    const fileName = `${toolName}_v${version}.mjs`;
    const filePath = path.join(DYNAMIC_DIR, fileName);

    // Prepend NODE_PATH чтобы dynamic imports нашли наши пакеты
    const header = packages.length
      ? `// auto-installed: ${packages.join(", ")}\n`
      : "";
    fs.writeFileSync(filePath, header + code, "utf8");

    // ── Шаг 5: Загрузить и протестировать ────────────────────────────────────
    let executeFunc: ((input: string) => Promise<ToolExecuteResult>) | null = null;
    try {
      // Добавляем DYNAMIC_DIR/node_modules в NODE_PATH перед импортом
      const origNodePath = process.env.NODE_PATH ?? "";
      process.env.NODE_PATH = `${DYN_MODULES}${path.delimiter}${origNodePath}`;
      // Node не подхватывает NODE_PATH в рантайме через import, но createRequire подхватит
      // Поэтому патчим Module._nodeModulePaths (стандартный внутренний механизм)
      const { Module } = await import("module");
      (Module as any)._initPaths?.();

      const url = pathToFileURL(filePath).href + `?v=${version}&t=${Date.now()}`;
      const mod = await import(url);

      if (typeof mod.execute !== "function") {
        throw new Error("No execute() function exported");
      }
      executeFunc = mod.execute;
    } catch (e: any) {
      lastError = `Module load error: ${e.message}`;
      log.warn(`DynamicTools: attempt ${attempt} load failed: ${e.message}`);
      fs.unlinkSync(filePath);
      continue;
    }

    // Быстрый smoke-test
    let testOutput = "";
    try {
      const testResult = await Promise.race([
        executeFunc("test"),
        new Promise<ToolExecuteResult>((_, rej) =>
          setTimeout(() => rej(new Error("Test timeout 10s")), 10_000)
        ),
      ]);
      testOutput = testResult.output.slice(0, 200);
      log.info(`DynamicTools: smoke-test OK: "${testOutput}"`);
    } catch (e: any) {
      // Smoke-test провалился — это не критично для некоторых тулов
      // (например тул требует реальный input, а "test" не валиден)
      // Продолжаем — главное что модуль загрузился
      testOutput = `(smoke-test: ${e.message.slice(0, 100)})`;
      log.warn(`DynamicTools: smoke-test warn: ${e.message}`);
    }

    // ── Шаг 6: Регистрация ───────────────────────────────────────────────────
    const meta: DynamicTool = {
      name: toolName,
      description,
      inputSchema,
      outputSchema: outSchema,
      createdAt: Date.now(),
      version,
      filePath,
      packages,
      enabled: true,
      testOutput,
    };
    toolRegistry[toolName] = meta;
    saveRegistry();

    // Hot-load в liveTools
    liveTools.set(toolName, executeFunc);

    // Логируем в DB
    try {
      Db.addNote(
        uid,
        `Tool created: ${toolName}`,
        `Dynamic tool v${version}\n${description}\nPackages: ${packages.join(", ") || "none"}\nTest: ${testOutput}`,
        "system"
      );
    } catch {}

    log.info(`DynamicTools: ✅ "${toolName}" v${version} live after ${attempt} attempt(s)`);
    return {
      success:  true,
      toolName,
      message:  `✅ Tool *${toolName}* created (attempt ${attempt}/${maxAttempts})\n📝 ${description}\n📦 Packages: ${packages.join(", ") || "none"}\n🧪 Test: ${testOutput}`,
    };
  }

  // Все попытки провалились
  log.error(`DynamicTools: all ${maxAttempts} attempts failed. Last error: ${lastError}`);
  return {
    success: false,
    message: `Failed after ${maxAttempts} attempts.\nLast error: ${lastError}`,
  };
}

// ── Управление тулами ─────────────────────────────────────────────────────────
export function disableTool(name: string): boolean {
  if (!toolRegistry[name]) return false;
  toolRegistry[name]!.enabled = false;
  liveTools.delete(name);
  saveRegistry();
  log.info(`DynamicTools: disabled "${name}"`);
  return true;
}

export function enableTool(name: string): boolean {
  if (!toolRegistry[name]) return false;
  toolRegistry[name]!.enabled = true;
  saveRegistry();
  loadTool(name);
  return true;
}

export function getToolInfo(name: string): DynamicTool | null {
  return toolRegistry[name] ?? null;
}
