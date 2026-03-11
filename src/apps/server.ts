/**
 * NEXUM v5 — Web App Server
 * Serves mini-apps and REST API for Finance, Notes, Tasks, Habits
 */
import express from "express";
import * as path from "path";
import * as fs from "fs";
import * as crypto from "crypto";
import { Db } from "../core/db.js";
import { log } from "../core/logger.js";
import { Config } from "../core/config.js";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webDir = path.join(__dirname);

function generateWebAppToken(uid: number): string {
  return crypto.createHmac("sha256", Config.BOT_TOKEN).update(String(uid)).digest("hex").slice(0, 16);
}

function verifyToken(uid: string | undefined, token: string | undefined): number | null {
  if (!uid || !token) return null;
  const expected = generateWebAppToken(parseInt(uid));
  if (token !== expected) return null;
  return parseInt(uid);
}

function serveFile(res: express.Response, filePath: string) {
  if (!fs.existsSync(filePath)) {
    res.status(404).send("Not found");
    return;
  }
  res.sendFile(filePath);
}

export function startWebAppServer(port: number) {
  const app = express();
  app.use(express.json());

  // Fallback HTML for when static files don't exist
  const fallbackHtml = (title: string, content: string) => `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NEXUM — ${title}</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: var(--tg-theme-bg-color, #1a1a2e);
  color: var(--tg-theme-text-color, #fff);
  min-height: 100vh; display: flex; flex-direction: column;
  align-items: center; justify-content: center; padding: 20px; }
.logo { font-size: 48px; font-weight: 900; letter-spacing: 4px;
  background: linear-gradient(135deg, #667eea, #764ba2);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  margin-bottom: 8px; }
.subtitle { color: #888; font-size: 14px; margin-bottom: 40px; }
.card { background: rgba(255,255,255,0.05); border-radius: 16px;
  padding: 24px; width: 100%; max-width: 400px; text-align: center; }
h2 { font-size: 20px; margin-bottom: 16px; }
p { color: #aaa; line-height: 1.6; }
.btn { display: inline-block; margin-top: 20px; padding: 12px 28px;
  background: linear-gradient(135deg, #667eea, #764ba2);
  border-radius: 12px; color: white; font-weight: 600;
  text-decoration: none; cursor: pointer; border: none; font-size: 15px; }
</style>
</head>
<body>
<div class="logo">NEXUM</div>
<div class="subtitle">Autonomous AI Agent</div>
<div class="card">
<h2>${title}</h2>
${content}
</div>
<script>
  window.Telegram?.WebApp?.ready();
  window.Telegram?.WebApp?.expand();
</script>
</body>
</html>`;

  function serveFileOrFallback(res: express.Response, filePath: string, title: string, content: string) {
    if (fs.existsSync(filePath)) {
      res.sendFile(filePath);
    } else {
      res.setHeader("Content-Type", "text/html");
      res.send(fallbackHtml(title, content));
    }
  }

  // ── HTML pages ────────────────────────────────────────────────────────
  app.get("/", (_req, res) => serveFileOrFallback(res,
    path.join(webDir, "index.html"), "Finance",
    `<p>Finance dashboard loading...</p><p style="margin-top:12px;color:#888">Open via Telegram bot</p>`
  ));
  app.get("/hub", (_req, res) => serveFileOrFallback(res,
    path.join(webDir, "hub.html"), "Apps Hub",
    `<p>All NEXUM apps in one place.</p><p style="margin-top:12px;color:#888">Use buttons in the bot to open specific apps</p>`
  ));
  app.get("/notes", (_req, res) => serveFileOrFallback(res,
    path.join(webDir, "notes.html"), "Notes",
    `<p>📝 Your notes are loading...</p>`
  ));
  app.get("/tasks", (_req, res) => serveFileOrFallback(res,
    path.join(webDir, "tasks.html"), "Tasks",
    `<p>✅ Your tasks are loading...</p>`
  ));
  app.get("/habits", (_req, res) => serveFileOrFallback(res,
    path.join(webDir, "habits.html"), "Habits",
    `<p>🎯 Your habits are loading...</p>`
  ));

  // ── /api/data — Finance dashboard ────────────────────────────────────
  app.get("/api/data", async (req, res) => {
    const uid = verifyToken(req.query.uid as string, req.query.token as string);
    if (!uid) { res.status(401).json({ error: "Unauthorized" }); return; }
    try {
      const now  = new Date();
      const from = new Date(now.getFullYear(), now.getMonth(), 1);
      const accounts        = Db.finGetAccounts(uid);
      const { income, expense } = Db.finGetTotalByPeriod(uid, from, now);
      const txs             = Db.finGetTxs(uid, 30);
      const categoryBreakdown = Db.finGetByCategory(uid, from);
      const budgets         = Db.finGetBudgets(uid);
      const user            = Db.getUser(uid);
      const habits          = Db.getHabits(uid);
      const today           = now.toISOString().slice(0, 10);
      const todayDone       = habits.filter((h: any) => Db.isHabitDoneToday(h.id)).length;

      // Uzbekistan CBU exchange rates
      let rates: Record<string, string> = {};
      try {
        const r = await fetch("https://cbu.uz/uz/arkhiv-kursov-valyut/json/", {
          signal: AbortSignal.timeout(5000),
        });
        if (r.ok) {
          const raw = await r.json() as any[];
          for (const c of raw.slice(0, 15)) rates[c.Ccy] = c.Rate;
        }
      } catch {}

      res.json({
        accounts,
        income,
        expense,
        txs: txs.slice(0, 25),
        categoryBreakdown,
        budgets,
        rates,
        userName:   user?.name ?? "",
        totalMsgs:  user?.total_msgs ?? 0,
        todayHabits: habits.length,
        todayDone,
      });
    } catch (e: any) {
      log.error(`/api/data: ${e.message}`);
      res.status(500).json({ error: "Internal error" });
    }
  });

  // ── /api/add — Add finance transaction ───────────────────────────────
  app.post("/api/add", (req, res) => {
    const uid = verifyToken(req.query.uid as string, req.query.token as string);
    if (!uid) { res.status(401).json({ error: "Unauthorized" }); return; }
    try {
      const { type, amount, category, note, account_id, currency } = req.body;
      if (!type || !amount || !category) { res.status(400).json({ error: "Missing fields" }); return; }
      Db.finEnsureDefaults(uid);
      const accs  = Db.finGetAccounts(uid);
      const accId = account_id ?? accs[0]?.id;
      if (!accId) { res.status(400).json({ error: "No account" }); return; }
      Db.finAddTransaction(uid, type, parseFloat(amount), category, accId, note ?? "", "", currency ?? "UZS");
      res.json({ ok: true });
    } catch (e: any) {
      log.error(`/api/add: ${e.message}`);
      res.status(500).json({ error: "Internal error" });
    }
  });

  // ── /api/accounts — list accounts ────────────────────────────────────
  app.get("/api/accounts", (req, res) => {
    const uid = verifyToken(req.query.uid as string, req.query.token as string);
    if (!uid) { res.status(401).json({ error: "Unauthorized" }); return; }
    try {
      Db.finEnsureDefaults(uid);
      res.json({ accounts: Db.finGetAccounts(uid) });
    } catch (e: any) { res.status(500).json({ error: e.message }); }
  });

  // ── Notes API ─────────────────────────────────────────────────────────
  app.get("/api/notes", (req, res) => {
    const uid = verifyToken(req.query.uid as string, req.query.token as string);
    if (!uid) { res.status(401).json({ error: "Unauthorized" }); return; }
    try {
      res.json({ notes: Db.getNotes(uid, 100) });
    } catch (e: any) { res.status(500).json({ error: e.message }); }
  });

  app.post("/api/notes/add", (req, res) => {
    const uid = verifyToken(req.query.uid as string, req.query.token as string);
    if (!uid) { res.status(401).json({ error: "Unauthorized" }); return; }
    try {
      const { title, content, tags } = req.body;
      if (!content) { res.status(400).json({ error: "Missing content" }); return; }
      const id = Db.addNote(uid, title ?? content.slice(0, 50), content, tags ?? "");
      res.json({ ok: true, id });
    } catch (e: any) { res.status(500).json({ error: e.message }); }
  });

  app.post("/api/notes/delete", (req, res) => {
    const uid = verifyToken(req.query.uid as string, req.query.token as string);
    if (!uid) { res.status(401).json({ error: "Unauthorized" }); return; }
    try {
      const { id } = req.body;
      Db.deleteNote(uid, id);
      res.json({ ok: true });
    } catch (e: any) { res.status(500).json({ error: e.message }); }
  });

  app.post("/api/notes/update", (req, res) => {
    const uid = verifyToken(req.query.uid as string, req.query.token as string);
    if (!uid) { res.status(401).json({ error: "Unauthorized" }); return; }
    try {
      const { id, title, content, tags } = req.body;
      Db.updateNote(uid, id, title ?? "", content ?? "", tags ?? "");
      res.json({ ok: true });
    } catch (e: any) { res.status(500).json({ error: e.message }); }
  });

  app.post("/api/notes/pin", (req, res) => {
    const uid = verifyToken(req.query.uid as string, req.query.token as string);
    if (!uid) { res.status(401).json({ error: "Unauthorized" }); return; }
    try {
      const { id, pinned } = req.body;
      Db.pinNote(uid, id, !!pinned);
      res.json({ ok: true });
    } catch (e: any) { res.status(500).json({ error: e.message }); }
  });

  // ── Tasks API ──────────────────────────────────────────────────────────
  app.get("/api/tasks", (req, res) => {
    const uid = verifyToken(req.query.uid as string, req.query.token as string);
    if (!uid) { res.status(401).json({ error: "Unauthorized" }); return; }
    try {
      const all   = Db.getAllTasks(uid);
      const tasks = all.filter((t: any) => t.status !== "done" && t.status !== "cancelled");
      const done  = all.filter((t: any) => t.status === "done").slice(0, 20);
      res.json({ tasks, done });
    } catch (e: any) { res.status(500).json({ error: e.message }); }
  });

  app.post("/api/tasks/add", (req, res) => {
    const uid = verifyToken(req.query.uid as string, req.query.token as string);
    if (!uid) { res.status(401).json({ error: "Unauthorized" }); return; }
    try {
      const { title, description, priority, project, due_at } = req.body;
      if (!title) { res.status(400).json({ error: "Missing title" }); return; }
      const id = Db.addTask(uid, title, description ?? "", project ?? "Inbox", parseInt(priority ?? "2"), due_at ?? null);
      res.json({ ok: true, id });
    } catch (e: any) { res.status(500).json({ error: e.message }); }
  });

  app.post("/api/tasks/status", (req, res) => {
    const uid = verifyToken(req.query.uid as string, req.query.token as string);
    if (!uid) { res.status(401).json({ error: "Unauthorized" }); return; }
    try {
      const { id, status } = req.body;
      Db.updateTaskStatus(uid, id, status);
      res.json({ ok: true });
    } catch (e: any) { res.status(500).json({ error: e.message }); }
  });

  app.post("/api/tasks/delete", (req, res) => {
    const uid = verifyToken(req.query.uid as string, req.query.token as string);
    if (!uid) { res.status(401).json({ error: "Unauthorized" }); return; }
    try {
      const { id } = req.body;
      Db.deleteTask(uid, id);
      res.json({ ok: true });
    } catch (e: any) { res.status(500).json({ error: e.message }); }
  });

  // ── Habits API ─────────────────────────────────────────────────────────
  app.get("/api/habits", (req, res) => {
    const uid = verifyToken(req.query.uid as string, req.query.token as string);
    if (!uid) { res.status(401).json({ error: "Unauthorized" }); return; }
    try {
      const habits  = Db.getHabits(uid);
      const today   = new Date().toISOString().slice(0, 10);
      const result  = habits.map((h: any) => ({
        ...h,
        doneToday: Db.isHabitDoneToday(h.id),
      }));
      res.json({ habits: result });
    } catch (e: any) { res.status(500).json({ error: e.message }); }
  });

  app.post("/api/habits/add", (req, res) => {
    const uid = verifyToken(req.query.uid as string, req.query.token as string);
    if (!uid) { res.status(401).json({ error: "Unauthorized" }); return; }
    try {
      const { name, emoji, frequency } = req.body;
      if (!name) { res.status(400).json({ error: "Missing name" }); return; }
      const id = Db.addHabit(uid, name, emoji ?? "✅", frequency ?? "daily");
      res.json({ ok: true, id });
    } catch (e: any) { res.status(500).json({ error: e.message }); }
  });

  app.post("/api/habits/done", (req, res) => {
    const uid = verifyToken(req.query.uid as string, req.query.token as string);
    if (!uid) { res.status(401).json({ error: "Unauthorized" }); return; }
    try {
      const { habit_id } = req.body;
      if (!habit_id) { res.status(400).json({ error: "Missing habit_id" }); return; }
      Db.logHabit(parseInt(habit_id), uid);
      const h = Db.getHabits(uid).find((x: any) => x.id === parseInt(habit_id));
      res.json({ ok: true, streak: h?.streak ?? 0 });
    } catch (e: any) { res.status(500).json({ error: e.message }); }
  });

  app.post("/api/habits/delete", (req, res) => {
    const uid = verifyToken(req.query.uid as string, req.query.token as string);
    if (!uid) { res.status(401).json({ error: "Unauthorized" }); return; }
    try {
      const { id } = req.body;
      Db.deleteHabit(uid, id);
      res.json({ ok: true });
    } catch (e: any) { res.status(500).json({ error: e.message }); }
  });

  // ── Health check ───────────────────────────────────────────────────────
  app.get("/health", (_req, res) => {
    res.json({ ok: true, ts: new Date().toISOString() });
  });

  app.listen(port, () => {
    log.info(`Web App server on port ${port}`);
  });

  return app;
}
