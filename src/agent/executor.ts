/**
 * NEXUM v5 — Action Executor (with Dynamic Tools)
 * Executes plan steps using built-in tools + hot-loaded dynamic tools
 */
import { DbV5 } from "../core/db.js";
import { webSearch } from "../tools/search.js";
import { log } from "../core/logger.js";
import {
  hasDynamicTool,
  executeDynamicTool,
  generateAndRegisterTool,
} from "../tools/tool_registry.js";
import type { PlanStep } from "./planner.js";

export interface ExecutionResult {
  step:    PlanStep;
  output:  string;
  success: boolean;
}

// Sensitive actions that require confirmation
const SENSITIVE_TOOLS = ["terminal", "filesystem", "browser"];

export function isSensitive(tool: string): boolean {
  return SENSITIVE_TOOLS.includes(tool);
}

// Execute a single step
export async function executeStep(
  uid: number,
  planId: number,
  step: PlanStep,
  pcSend?: (uid: number, type: string, payload: any) => Promise<string | null>
): Promise<ExecutionResult> {
  let output = "";
  let success = false;

  try {
    switch (step.tool) {

      case "web_search": {
        const result = await webSearch(step.input);
        output = result ?? "No results found";
        success = !!result;
        break;
      }

      case "notes_add": {
        const { Db } = await import("../core/db.js");
        Db.addNote(uid, step.input.slice(0, 50), step.input, '');
        output = `Note saved: ${step.input}`;
        success = true;
        break;
      }

      case "task_add": {
        const { Db } = await import("../core/db.js");
        Db.addTask(uid, step.input, '', 'Inbox', 2, null);
        output = `Task saved: ${step.input}`;
        success = true;
        break;
      }

      case "message": {
        output = step.input;
        success = true;
        break;
      }

      // Special: self-develop a new tool on the fly
      case "create_tool": {
        const result = await generateAndRegisterTool(uid, step.input);
        output = result.message;
        success = result.success;
        break;
      }

      // PC Agent tools — require pcSend
      case "terminal":
      case "filesystem":
      case "browser":
      case "screenshot": {
        if (!pcSend) {
          output = "PC Agent not connected. Use /pc_connect to set it up.";
          success = false;
          break;
        }
        const result = await pcSend(uid, step.tool, { input: step.input });
        output = result ?? "Command executed";
        success = true;
        break;
      }

      default: {
        // ── Dynamic tool fallback ─────────────────────────────────────────
        if (hasDynamicTool(step.tool)) {
          const result = await executeDynamicTool(step.tool, step.input);
          output = result.output;
          success = result.success;
        } else {
          output = `Tool "${step.tool}" not yet implemented.`;
          success = false;
        }
      }
    }
  } catch (e: any) {
    output = `Error: ${e.message}`;
    success = false;
    log.debug(`Executor step ${step.id} failed: ${e.message}`);
  }

  DbV5.logAgentAction(uid, planId, step.tool, step.input, output, success ? "ok" : "error");
  return { step, output, success };
}

// Execute all plan steps sequentially
export async function executePlan(
  uid: number,
  planId: number,
  steps: PlanStep[],
  pcSend?: (uid: number, type: string, payload: any) => Promise<string | null>,
  onStep?: (result: ExecutionResult) => Promise<void>
): Promise<ExecutionResult[]> {
  const results: ExecutionResult[] = [];

  DbV5.updatePlanStatus(planId, "running");

  for (const step of steps) {
    if (isSensitive(step.tool)) {
      results.push({ step, output: "Requires confirmation", success: false });
      continue;
    }

    const result = await executeStep(uid, planId, step, pcSend);
    results.push(result);

    if (onStep) await onStep(result);

    if (!result.success && step.tool !== "message") {
      log.debug(`Plan ${planId} stopped at step ${step.id}: ${result.output}`);
      break;
    }
  }

  DbV5.updatePlanStatus(planId, "done");
  return results;
}

export const PC_TOOLS = ["terminal", "filesystem", "browser", "screenshot", "open_app", "mouse", "keyboard"];
