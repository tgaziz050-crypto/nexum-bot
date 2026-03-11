/**
 * NEXUM WebApp Server — Finance + Notes + Tasks + Habits mini-apps
 */
import express from "express";
import * as path from "path";
import * as fs from "fs";
import * as url from "url";
import { Db } from "../core/db.js";
import { log } from "../core/logger.js";
import { Config } from "../core/config.js";

const __dirname = path.dirname(url.fileURLToPath(import.meta.url));
const authTokens = new Map<number, string>();

export function generateWebAppToken(uid: number): string {
  const token = Math.random().toString(36).slice(2) + Date.now().toString(36);
  authTokens.set(uid, token);
  return token;
}
function validateToken(uid: number, token: string): boolean {
  return authTokens.get(uid) === token;
}
function startOfMonth(): Date {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

export function startWebAppServer(port: number) {
  const app = express();
  app.use(express.json());

  // ── Static files ──────────────────────────────────────────────
  const webDir = __dirname;
  app.get("/", (_req, res) => serveFile(res, path.join(webDir, "index.html")));
  app.get("/notes", (_req, res) => serveFile(res, path.join(webDir, "notes.html")));
  app.get("/tasks", (_req, res) => serveFile(res, path.join(webDir, "tasks.html")));
  app.get("/habits", (_req, res) => serveFile(res, path.join(webDir, "habits.html")));

  function serveFile(res: express.Response, filePath: string) {
    if (fs.existsSync(filePath)) res.sendFile(filePath);
    else res.status(404).send("Not found");
  }

  // ── Auth middleware ───────────────────────────────────────────
  function auth(req: express.Request, res: express.Response, next: express.NextFunction) {
    const uid = parseInt(req.query.uid as string || (req.body?.uid ?? "0"));
    const token = (req.query.token as string) || req.body?.token || "";
    if (!uid || !validateToken(uid, token)) { res.status(403).json({ error: "Unauthorized" }); return; }
    (req as any).uid = uid;
    next();
  }

  // ── FINANCE ───────────────────────────────────────────────────
  /** Combined data endpoint for Finance webapp */
  app.get("/api/data", auth, async (req, res) => {
    const uid = (req as any).uid;
    try {
      Db.finEnsureDefaults(uid);
      const accounts = Db.finGetAccounts(uid);
      const now = new Date(), from = startOfMonth();
      const { income, expense } = Db.finGetTotalByPeriod(uid, from, now);
      const txs = Db.finGetTxs(uid, 50);
      const categoryBreakdown = Db.finGetByCategory(uid, from);
      const budgets = Db.finGetBudgets(uid);
      // Rates from CBU
      let rates: Record<string, number> = { usd: 12900, eur: 14100, rub: 142, cny: 1780 };
      try {
        const r = await fetch("https://cbu.uz/uz/arkhiv-kursov-valyut/json/", { signal: AbortSignal.timeout(3000) });
        if (r.ok) {
          const data = await r.json() as any[];
          const map: Record<string, string> = { USD: "usd", EUR: "eur", RUB: "rub", CNY: "cny" };
          for (const item of data) { if (map[item.Ccy]) rates[map[item.Ccy]!] = parseFloat(item.Rate); }
        }
      } catch {}
      res.json({ accounts, income, expense, txs, categoryBreakdown, budgets, rates });
    } catch(e: any) { res.status(500).json({ error: e.message }); }
  });

  app.post("/api/add", auth, (req, res) => {
    const uid = (req as any).uid;
    const { type, amount, category, note, accountId } = req.body;
    try {
      if (!type || !amount || amount <= 0) { res.status(400).json({ error: "Invalid" }); return; }
      const id = Db.finAddTransaction(uid, type, amount, category || "Прочее", accountId || null, note || "", "", "UZS", null);
      res.json({ ok: true, id });
    } catch(e: any) { res.status(500).json({ error: e.message }); }
  });

  // ── NOTES ─────────────────────────────────────────────────────
  app.get("/api/notes", auth, (req, res) => {
    const uid = (req as any).uid;
    try { res.json(Db.getNotes(uid, 100)); } catch(e: any) { res.status(500).json({ error: e.message }); }
  });
  app.post("/api/notes/add", auth, (req, res) => {
    const uid = (req as any).uid;
    const { title, content, tags } = req.body;
    try {
      if (!content) { res.status(400).json({ error: "No content" }); return; }
      const id = Db.addNote(uid, title || content.slice(0, 40), content, tags || "");
      res.json({ ok: true, id });
    } catch(e: any) { res.status(500).json({ error: e.message }); }
  });
  app.post("/api/notes/edit", auth, (req, res) => {
    const uid = (req as any).uid;
    const { id, title, content, tags } = req.body;
    try {
      Db.updateNote(uid, id, title || "", content || "", tags || "");
      res.json({ ok: true });
    } catch(e: any) { res.status(500).json({ error: e.message }); }
  });
  app.post("/api/notes/pin", auth, (req, res) => {
    const uid = (req as any).uid;
    const { id, pin } = req.body;
    try { Db.pinNote(uid, id, pin); res.json({ ok: true }); } catch(e: any) { res.status(500).json({ error: e.message }); }
  });
  app.post("/api/notes/delete", auth, (req, res) => {
    const uid = (req as any).uid;
    const { id } = req.body;
    try { Db.deleteNote(uid, id); res.json({ ok: true }); } catch(e: any) { res.status(500).json({ error: e.message }); }
  });

  // ── TASKS ─────────────────────────────────────────────────────
  app.get("/api/tasks", auth, (req, res) => {
    const uid = (req as any).uid;
    try { res.json(Db.getAllTasks(uid)); } catch(e: any) { res.status(500).json({ error: e.message }); }
  });
  app.post("/api/tasks/add", auth, (req, res) => {
    const uid = (req as any).uid;
    const { title, description, project, priority } = req.body;
    try {
      if (!title) { res.status(400).json({ error: "No title" }); return; }
      const id = Db.addTask(uid, title, description || "", project || "Inbox", priority || 2, null);
      res.json({ ok: true, id });
    } catch(e: any) { res.status(500).json({ error: e.message }); }
  });
  app.post("/api/tasks/status", auth, (req, res) => {
    const uid = (req as any).uid;
    const { id, status } = req.body;
    try { Db.updateTaskStatus(uid, id, status); res.json({ ok: true }); } catch(e: any) { res.status(500).json({ error: e.message }); }
  });

  // ── HABITS ────────────────────────────────────────────────────
  app.get("/api/habits", auth, (req, res) => {
    const uid = (req as any).uid;
    try {
      const habits = Db.getHabits(uid);
      const today = new Date().toISOString().slice(0, 10);
      const enriched = habits.map((h: any) => ({
        ...h,
        doneToday: !!Db.getHabitLog(h.id, today),
      }));
      res.json(enriched);
    } catch(e: any) { res.status(500).json({ error: e.message }); }
  });
  app.post("/api/habits/add", auth, (req, res) => {
    const uid = (req as any).uid;
    const { name, emoji } = req.body;
    try {
      if (!name) { res.status(400).json({ error: "No name" }); return; }
      const id = Db.addHabit(uid, name, emoji || "✅", "daily", "");
      res.json({ ok: true, id });
    } catch(e: any) { res.status(500).json({ error: e.message }); }
  });
  app.post("/api/habits/done", auth, (req, res) => {
    const uid = (req as any).uid;
    const { id } = req.body;
    try {
      const today = new Date().toISOString().slice(0, 10);
      Db.logHabit(id, uid, today);
      const streakRes = Db.getHabitStreak(id) as any;
      Db.updateHabitStreak(id, streakRes?.n || 0);
      res.json({ ok: true });
    } catch(e: any) { res.status(500).json({ error: e.message }); }
  });

  app.listen(port, () => {
    log.info(`WebApp server on port ${port} ✅`);
    log.info(`  Finance:  /`);
    log.info(`  Notes:    /notes`);
    log.info(`  Tasks:    /tasks`);
    log.info(`  Habits:   /habits`);
  });

  return app;
}
