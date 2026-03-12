/**
 * NEXUM Subagents Module
 * Архитектура взята из OpenClaw src/agents/pi-embedded-runner/
 *
 * Возможности:
 *  - spawn(task) — запустить подзадачу параллельно
 *  - spawnMany(tasks) — несколько подзадач параллельно
 *  - waitAll() — дождаться всех
 *  - status() — статус всех агентов
 *  - cancel(id) — отменить
 *  - Инструменты: exec, read, write, http, browser_snapshot
 *  - Полная история инструментальных вызовов
 */

import * as crypto from 'crypto';
import Anthropic from '@anthropic-ai/sdk';

// ─── Types ────────────────────────────────────────────────────────────────────

export type SubagentStatus = 'pending' | 'running' | 'done' | 'error' | 'cancelled';

export interface SubagentRun {
  id: string;
  task: string;
  status: SubagentStatus;
  result?: string;
  error?: string;
  startedAt: Date;
  finishedAt?: Date;
  model: string;
  toolCalls: { tool: string; input: any; output: string }[];
  tokens: { input: number; output: number };
}

export interface SpawnOpts {
  model?: string;
  systemPrompt?: string;
  tools?: string[]; // which tools to allow
  maxTokens?: number;
  apiKey?: string;
  timeout?: number; // ms
}

// ─── Registry ─────────────────────────────────────────────────────────────────

const _runs = new Map<string, SubagentRun>();
const _controllers = new Map<string, AbortController>();

// ─── Built-in tools ───────────────────────────────────────────────────────────

import * as child_process from 'child_process';
import * as fs from 'fs';
import * as path from 'path';

const SUBAGENT_TOOLS: Anthropic.Tool[] = [
  {
    name: 'exec',
    description: 'Execute a shell command and return stdout/stderr',
    input_schema: {
      type: 'object' as const,
      properties: {
        command: { type: 'string', description: 'Shell command to run' },
        cwd: { type: 'string', description: 'Working directory (optional)' },
        timeout: { type: 'number', description: 'Timeout in seconds (default 30)' },
      },
      required: ['command'],
    },
  },
  {
    name: 'read_file',
    description: 'Read a file from disk',
    input_schema: {
      type: 'object' as const,
      properties: {
        path: { type: 'string', description: 'Absolute or relative file path' },
      },
      required: ['path'],
    },
  },
  {
    name: 'write_file',
    description: 'Write content to a file',
    input_schema: {
      type: 'object' as const,
      properties: {
        path: { type: 'string', description: 'File path' },
        content: { type: 'string', description: 'Content to write' },
      },
      required: ['path', 'content'],
    },
  },
  {
    name: 'list_dir',
    description: 'List directory contents',
    input_schema: {
      type: 'object' as const,
      properties: {
        path: { type: 'string', description: 'Directory path' },
      },
      required: ['path'],
    },
  },
  {
    name: 'http_fetch',
    description: 'Make an HTTP request',
    input_schema: {
      type: 'object' as const,
      properties: {
        url: { type: 'string' },
        method: { type: 'string', enum: ['GET', 'POST', 'PUT', 'DELETE'] },
        body: { type: 'string', description: 'JSON body for POST/PUT' },
        headers: { type: 'object', description: 'HTTP headers' },
      },
      required: ['url'],
    },
  },
  {
    name: 'search_web',
    description: 'Search the web for information',
    input_schema: {
      type: 'object' as const,
      properties: {
        query: { type: 'string', description: 'Search query' },
      },
      required: ['query'],
    },
  },
];

// ─── Tool execution ───────────────────────────────────────────────────────────

async function executeTool(name: string, input: any): Promise<string> {
  try {
    switch (name) {
      case 'exec': {
        const timeout = (input.timeout || 30) * 1000;
        return await new Promise<string>((resolve) => {
          const proc = child_process.exec(
            input.command,
            { cwd: input.cwd || process.cwd(), timeout },
            (err, stdout, stderr) => {
              const out = stdout?.trim() || '';
              const err2 = stderr?.trim() || '';
              resolve([out, err2 ? `STDERR: ${err2}` : ''].filter(Boolean).join('\n') || '(no output)');
            }
          );
        });
      }

      case 'read_file': {
        const p = path.resolve(input.path);
        if (!fs.existsSync(p)) return `❌ File not found: ${p}`;
        const content = fs.readFileSync(p, 'utf-8');
        return content.slice(0, 8000);
      }

      case 'write_file': {
        const p = path.resolve(input.path);
        fs.mkdirSync(path.dirname(p), { recursive: true });
        fs.writeFileSync(p, input.content, 'utf-8');
        return `✅ Written ${content_length(input.content)} bytes to ${p}`;
      }

      case 'list_dir': {
        const p = path.resolve(input.path);
        if (!fs.existsSync(p)) return `❌ Not found: ${p}`;
        const items = fs.readdirSync(p, { withFileTypes: true });
        return items.slice(0, 50).map(i =>
          `${i.isDirectory() ? '📁' : '📄'} ${i.name}`
        ).join('\n');
      }

      case 'http_fetch': {
        const method = input.method || 'GET';
        const headers: any = { 'User-Agent': 'NEXUM-Agent/1.0', ...input.headers };
        const opts: any = { method, headers };
        if (input.body && (method === 'POST' || method === 'PUT')) {
          opts.body = input.body;
          headers['Content-Type'] = 'application/json';
        }
        const resp = await fetch(input.url, opts);
        const text = await resp.text();
        return `Status: ${resp.status}\n\n${text.slice(0, 3000)}`;
      }

      case 'search_web': {
        const resp = await fetch(
          `https://ddg-webapp-aagd.vercel.app/search?q=${encodeURIComponent(input.query)}&max_results=5`
        );
        if (resp.ok) {
          const data = await resp.json() as any;
          const results = data.results || data;
          if (Array.isArray(results)) {
            return results.slice(0, 5).map((r: any, i: number) =>
              `${i+1}. ${r.title}\n   ${r.href || r.url}\n   ${r.body || r.snippet || ''}`
            ).join('\n\n');
          }
        }
        // Fallback: DuckDuckGo HTML
        const r2 = await fetch(`https://html.duckduckgo.com/html/?q=${encodeURIComponent(input.query)}`);
        const html = await r2.text();
        const matches = [...html.matchAll(/class="result__title">.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)<\/a>/gs)];
        return matches.slice(0, 5).map((m, i) =>
          `${i+1}. ${m[2].replace(/<[^>]+>/g, '').trim()}\n   ${decodeURIComponent(m[1])}`
        ).join('\n\n') || '(no results)';
      }

      default:
        return `❌ Unknown tool: ${name}`;
    }
  } catch (e: any) {
    return `❌ Tool error: ${e.message}`;
  }
}

function content_length(s: string): number { return Buffer.byteLength(s, 'utf8'); }

// ─── Agent runner ─────────────────────────────────────────────────────────────

async function runSubagentLoop(
  run: SubagentRun,
  opts: SpawnOpts,
  signal: AbortSignal,
): Promise<void> {
  const apiKey = opts.apiKey || process.env.ANTHROPIC_API_KEY || process.env.OPENAI_API_KEY;
  if (!apiKey) {
    run.status = 'error';
    run.error = '❌ No API key (set ANTHROPIC_API_KEY)';
    run.finishedAt = new Date();
    return;
  }

  const client = new Anthropic({ apiKey });
  const model = opts.model || 'claude-sonnet-4-20250514';
  const maxTokens = opts.maxTokens || 4096;
  const timeoutMs = opts.timeout || 120_000;

  const systemPrompt = opts.systemPrompt ||
    `You are a capable AI subagent. Complete the given task efficiently.
Use available tools as needed. Be concise in responses.
Current time: ${new Date().toISOString()}`;

  const messages: Anthropic.MessageParam[] = [
    { role: 'user', content: run.task },
  ];

  const tools = SUBAGENT_TOOLS.filter(t =>
    !opts.tools || opts.tools.includes(t.name)
  );

  const deadline = Date.now() + timeoutMs;
  run.status = 'running';

  try {
    while (Date.now() < deadline) {
      if (signal.aborted) {
        run.status = 'cancelled';
        return;
      }

      const response = await client.messages.create({
        model,
        max_tokens: maxTokens,
        system: systemPrompt,
        tools,
        messages,
      });

      run.tokens.input += response.usage.input_tokens;
      run.tokens.output += response.usage.output_tokens;

      // Collect text and tool uses
      const toolUses: Anthropic.ToolUseBlock[] = [];
      let textContent = '';

      for (const block of response.content) {
        if (block.type === 'text') textContent += block.text;
        if (block.type === 'tool_use') toolUses.push(block);
      }

      messages.push({ role: 'assistant', content: response.content });

      if (response.stop_reason === 'end_turn' || toolUses.length === 0) {
        run.result = textContent || '(done)';
        run.status = 'done';
        run.finishedAt = new Date();
        return;
      }

      // Execute tools
      const toolResults: Anthropic.ToolResultBlockParam[] = [];
      for (const toolUse of toolUses) {
        if (signal.aborted) {
          run.status = 'cancelled';
          return;
        }

        const output = await executeTool(toolUse.name, toolUse.input);
        run.toolCalls.push({ tool: toolUse.name, input: toolUse.input, output });

        toolResults.push({
          type: 'tool_result',
          tool_use_id: toolUse.id,
          content: output,
        });
      }

      messages.push({ role: 'user', content: toolResults });
    }

    // Timeout
    run.status = 'error';
    run.error = `Timeout after ${timeoutMs / 1000}s`;
    run.finishedAt = new Date();

  } catch (e: any) {
    if (signal.aborted) {
      run.status = 'cancelled';
    } else {
      run.status = 'error';
      run.error = e.message;
    }
    run.finishedAt = new Date();
  }
}

// ─── Public API ───────────────────────────────────────────────────────────────

/**
 * Запустить один подагент асинхронно
 */
export function spawn(task: string, opts: SpawnOpts = {}): SubagentRun {
  const id = crypto.randomBytes(4).toString('hex');
  const run: SubagentRun = {
    id,
    task,
    status: 'pending',
    startedAt: new Date(),
    model: opts.model || 'claude-sonnet-4-20250514',
    toolCalls: [],
    tokens: { input: 0, output: 0 },
  };

  _runs.set(id, run);
  const controller = new AbortController();
  _controllers.set(id, controller);

  // Start async, don't await
  runSubagentLoop(run, opts, controller.signal).catch(e => {
    run.status = 'error';
    run.error = String(e);
    run.finishedAt = new Date();
  });

  return run;
}

/**
 * Запустить несколько подагентов параллельно и дождаться всех
 */
export async function spawnMany(
  tasks: string[],
  opts: SpawnOpts = {},
  onProgress?: (id: string, status: SubagentStatus, result?: string) => void,
): Promise<SubagentRun[]> {
  const runs = tasks.map(task => spawn(task, opts));

  return new Promise((resolve) => {
    const check = () => {
      for (const run of runs) {
        if (onProgress && (run.status === 'done' || run.status === 'error')) {
          onProgress(run.id, run.status, run.result || run.error);
        }
      }
      const allDone = runs.every(r =>
        r.status === 'done' || r.status === 'error' || r.status === 'cancelled'
      );
      if (allDone) {
        resolve(runs);
      } else {
        setTimeout(check, 500);
      }
    };
    setTimeout(check, 500);
  });
}

/**
 * Дождаться конкретного агента
 */
export async function waitForRun(id: string, timeoutMs = 120_000): Promise<SubagentRun> {
  const run = _runs.get(id);
  if (!run) throw new Error(`Run ${id} not found`);

  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    const check = () => {
      if (run.status === 'done' || run.status === 'error' || run.status === 'cancelled') {
        resolve(run);
      } else if (Date.now() > deadline) {
        reject(new Error(`Timeout waiting for run ${id}`));
      } else {
        setTimeout(check, 300);
      }
    };
    check();
  });
}

/**
 * Отменить агента
 */
export function cancel(id: string): boolean {
  const controller = _controllers.get(id);
  if (!controller) return false;
  controller.abort();
  const run = _runs.get(id);
  if (run && run.status === 'running') run.status = 'cancelled';
  return true;
}

/**
 * Статус всех агентов
 */
export function getAllRuns(): SubagentRun[] {
  return Array.from(_runs.values()).sort((a, b) =>
    b.startedAt.getTime() - a.startedAt.getTime()
  );
}

export function getRun(id: string): SubagentRun | undefined {
  return _runs.get(id);
}

export function clearFinishedRuns(): void {
  for (const [id, run] of _runs) {
    if (run.status === 'done' || run.status === 'error' || run.status === 'cancelled') {
      _runs.delete(id);
      _controllers.delete(id);
    }
  }
}

/**
 * Форматированный статус для Telegram
 */
export function formatRunStatus(run: SubagentRun): string {
  const icon = {
    pending: '⏳',
    running: '🔄',
    done: '✅',
    error: '❌',
    cancelled: '🚫',
  }[run.status];

  const elapsed = run.finishedAt
    ? `${((run.finishedAt.getTime() - run.startedAt.getTime()) / 1000).toFixed(1)}s`
    : `${((Date.now() - run.startedAt.getTime()) / 1000).toFixed(0)}s…`;

  const tools = run.toolCalls.length > 0
    ? `\n🔧 Tools: ${run.toolCalls.map(t => t.tool).join(', ')}`
    : '';

  const tokens = run.tokens.input > 0
    ? `\n🪙 Tokens: ${run.tokens.input}↑ ${run.tokens.output}↓`
    : '';

  const result = run.result
    ? `\n\n${run.result.slice(0, 500)}${run.result.length > 500 ? '…' : ''}`
    : run.error
    ? `\n\n❌ ${run.error}`
    : '';

  return `${icon} [${run.id}] ${elapsed}${tools}${tokens}${result}`;
}
