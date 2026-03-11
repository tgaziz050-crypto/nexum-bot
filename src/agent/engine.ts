/**
 * NEXUM v5 — AI Engine
 * Multi-provider fallback chain for all task types
 */
import { log } from "../core/logger.js";
import { Config } from "../core/config.js";
import * as P from "../providers.js";
import type { Msg } from "../providers.js";

export type { Msg };
export type Task = "general" | "code" | "analysis" | "creative" | "fast" | "plan";

type ProviderFn = (msgs: Msg[]) => Promise<string>;

function buildChain(task: Task): ProviderFn[] {
  const chain: ProviderFn[] = [];

  if (task === "fast") {
    if (Config.CEREBRAS_KEYS.length)  chain.push(m => P.cerebras(m, 512));
    if (Config.GROQ_KEYS.length)      chain.push(m => P.groq(m, "llama-3.1-8b-instant", 512));
    if (Config.GROK_KEYS.length)      chain.push(m => P.grok(m, "grok-3-mini-fast", 512));
    if (Config.SAMBANOVA_KEYS.length) chain.push(m => P.sambanova(m, "Meta-Llama-3.1-8B-Instruct", 512));
    if (Config.GEMINI_KEYS.length)    chain.push(m => P.gemini(m, "gemini-2.0-flash", 512));
    return chain;
  }

  if (task === "code") {
    if (Config.DEEPSEEK_KEYS.length)   chain.push(m => P.deepseek(m));
    if (Config.GEMINI_KEYS.length)     chain.push(m => P.gemini(m, "gemini-2.0-flash"));
    if (Config.OPENROUTER_KEYS.length) chain.push(m => P.openrouter(m, "deepseek/deepseek-r1:free"));
    if (Config.GROK_KEYS.length)       chain.push(m => P.grok(m));
    if (Config.CEREBRAS_KEYS.length)   chain.push(m => P.cerebras(m));
    if (Config.GROQ_KEYS.length)       chain.push(m => P.groq(m));
    if (Config.CLAUDE_KEYS.length)     chain.push(m => P.claude(m));
    return chain;
  }

  if (task === "plan" || task === "analysis") {
    if (Config.GEMINI_KEYS.length)     chain.push(m => P.gemini(m, "gemini-2.5-pro-preview-05-06"));
    if (Config.GEMINI_KEYS.length)     chain.push(m => P.gemini(m, "gemini-2.0-flash"));
    if (Config.GROK_KEYS.length)       chain.push(m => P.grok(m, "grok-3-mini"));
    if (Config.OPENROUTER_KEYS.length) chain.push(m => P.openrouter(m, "google/gemini-2.0-flash-exp:free"));
    if (Config.CEREBRAS_KEYS.length)   chain.push(m => P.cerebras(m));
    if (Config.GROQ_KEYS.length)       chain.push(m => P.groq(m));
    if (Config.CLAUDE_KEYS.length)     chain.push(m => P.claude(m));
    return chain;
  }

  if (task === "creative") {
    if (Config.GEMINI_KEYS.length)     chain.push(m => P.gemini(m, "gemini-2.5-pro-preview-05-06"));
    if (Config.GEMINI_KEYS.length)     chain.push(m => P.gemini(m, "gemini-2.0-flash"));
    if (Config.GROK_KEYS.length)       chain.push(m => P.grok(m));
    if (Config.CLAUDE_KEYS.length)     chain.push(m => P.claude(m));
    if (Config.CEREBRAS_KEYS.length)   chain.push(m => P.cerebras(m));
    if (Config.GROQ_KEYS.length)       chain.push(m => P.groq(m));
    return chain;
  }

  // general
  if (Config.CEREBRAS_KEYS.length)    chain.push(m => P.cerebras(m));
  if (Config.GROQ_KEYS.length)        chain.push(m => P.groq(m));
  if (Config.GEMINI_KEYS.length)      chain.push(m => P.gemini(m, "gemini-2.0-flash"));
  if (Config.GROK_KEYS.length)        chain.push(m => P.grok(m));
  if (Config.SAMBANOVA_KEYS.length)   chain.push(m => P.sambanova(m));
  if (Config.TOGETHER_KEYS.length)    chain.push(m => P.together(m));
  if (Config.OPENROUTER_KEYS.length)  chain.push(m => P.openrouter(m));
  if (Config.DEEPSEEK_KEYS.length)    chain.push(m => P.deepseek(m));
  if (Config.CLAUDE_KEYS.length)      chain.push(m => P.claude(m));
  return chain;
}

export async function ask(msgs: Msg[], task: Task = "general"): Promise<string> {
  const chain = buildChain(task);
  if (!chain.length) throw new Error("Нет AI провайдеров. Добавь CB1, GR1 или G1 в Railway Variables.");
  for (const provider of chain) {
    try {
      const text = await provider(msgs);
      if (text?.trim()) return text.trim();
    } catch (e: unknown) {
      const err = e instanceof Error ? e.message : String(e);
      if (!err.includes("429") && !err.includes("quota") && !err.includes("rate")) {
        log.debug(`Provider failed: ${err}`);
      }
    }
  }
  throw new Error("Все AI провайдеры недоступны. Проверь ключи в Railway Variables.");
}

export async function vision(b64: string, prompt: string): Promise<string> {
  const tasks: Promise<string>[] = [];
  if (Config.GEMINI_KEYS.length)     tasks.push(P.geminiVision(b64, prompt));
  if (Config.OPENROUTER_KEYS.length) tasks.push(P.openrouterVision(b64, prompt));
  if (Config.CLAUDE_KEYS.length)     tasks.push(P.claudeVision(b64, prompt));
  if (!tasks.length) throw new Error("Нет vision провайдеров. Добавь G1 или OR1.");
  return new Promise((resolve, reject) => {
    let settled = 0;
    const errs: string[] = [];
    for (const t of tasks) {
      t.then(text => { if (text?.trim()) resolve(text.trim()); else check(); })
       .catch(e => { errs.push(String(e)); check(); });
    }
    function check() { if (++settled === tasks.length) reject(new Error(`Vision failed: ${errs.join(", ")}`)); }
  });
}
