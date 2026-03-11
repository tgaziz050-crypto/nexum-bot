/**
 * NEXUM v5 — Task Planner
 * Breaks complex goals into executable steps (OpenClaw-style)
 */
import { ask, type Msg } from "./engine.js";
import { DbV5 } from "../core/db.js";
import { log } from "../core/logger.js";

export interface PlanStep {
  id:     number;
  action: string;   // human-readable description
  tool:   string;   // tool name to call
  input:  string;   // tool input/params
  done:   boolean;
}

export interface Plan {
  id:    number;
  goal:  string;
  steps: PlanStep[];
}

// Tasks that require planning (multi-step)
const COMPLEX_PATTERNS = [
  /скачай|загрузи|download/i,
  /найди и|search and|найди потом/i,
  /открой.*потом|open.*then/i,
  /сделай.*шаги|step by step|пошагово/i,
  /план |create plan|составь план/i,
  /автоматизируй|automate/i,
  /запусти.*установи|run.*install/i,
];

export function needsPlanning(text: string): boolean {
  return COMPLEX_PATTERNS.some(p => p.test(text));
}

export async function createPlan(uid: number, goal: string, context: string): Promise<Plan | null> {
  try {
    const prompt: Msg[] = [{
      role: "user",
      content: `You are a task planner for an AI assistant. Break this goal into 2-6 concrete steps.

GOAL: "${goal}"

CONTEXT: ${context}

Available tools:
- web_search: Search the internet for information
- browser: Open a URL in the browser
- terminal: Execute a shell command on the user's PC
- filesystem: Read/write files on the user's PC
- screenshot: Take a screenshot of the user's screen
- vision: Analyze an image
- notes_add: Add a note
- task_add: Add a task
- reminder_add: Set a reminder
- message: Send a message to the user

Return ONLY a JSON array of steps, no explanation, no markdown:
[
  {"id":1,"action":"Description of what this step does","tool":"tool_name","input":"what to pass to the tool"},
  {"id":2,...}
]

Be specific and realistic. Only use terminal/filesystem/browser if the user has a PC agent connected.`,
    }];

    const result = await ask(prompt, "plan");
    const clean = result.replace(/```json|```/g, "").trim();
    const idx = clean.indexOf("[");
    const raw = idx >= 0 ? clean.slice(idx) : clean;
    const rawSteps = JSON.parse(raw) as any[];

    const steps: PlanStep[] = rawSteps.map((s, i) => ({
      id:     s.id ?? i + 1,
      action: s.action ?? `Step ${i + 1}`,
      tool:   s.tool ?? "message",
      input:  s.input ?? "",
      done:   false,
    }));

    const planId = DbV5.createPlan(uid, goal, steps);
    return { id: planId, goal, steps };
  } catch (e: any) {
    log.debug(`Planner error: ${e.message}`);
    return null;
  }
}

export function formatPlan(plan: Plan): string {
  const lines = [`🗺 *План выполнения:*\n`];
  lines.push(`🎯 Цель: ${plan.goal}\n`);
  for (const s of plan.steps) {
    const icon = s.done ? "✅" : "⏳";
    lines.push(`${icon} ${s.id}. ${s.action}`);
    if (s.tool !== "message") lines.push(`   _[${s.tool}]_`);
  }
  return lines.join("\n");
}
