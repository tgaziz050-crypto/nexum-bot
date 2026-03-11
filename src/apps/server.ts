/**
 * NEXUM v5 — Web App Server
 * Serves mini-apps and REST API for Finance, Notes, Tasks, Habits
 */
import express from "express";
import * as path from "path";
import * as fs from "fs";
import * as crypto from "crypto";
import { Db, DbV5 } from "../core/db.js";
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

  // ── HTML pages ─────────────────────────────────────────────────────
  app.get("/",       (_req, res) => serveFile(res, path.join(webDir, "index.html")));
  app.get("/hub",    (_req, res) => serveFile(res, path.join(webDir, "hub.html")));
  app.get("/notes",  (_req, res) => serveFile(res, path.join(webDir, "notes.html")));
  app.get("/tasks",  (_req, res) => serveFile(res, path.join(webDir, "tasks.html")));
  app.get("/habits", (_req, res) => serveFile(res, path.join(webDir, "habits.html")));

  // ── /api/data — Finance dashboard ──────────────────────────────────
  app.get("/api/data", async (req, res) => {
    const uid = verifyToken(req.query.uid as string, req.query.token as string);
    if (!uid) { res.status(401).json({ error: "Unauthorized" }); return; }
    try {
      const now  = new Date();
      const from = new Date(now.getFullYear(), now.getMonth(), 1);
      const accounts = Db.finGetAccounts(uid);
      const { income, expense } = Db.finGetTotalByPeriod(uid, from, now);
      const txs = Db.finGetTxs(uid, 30);
      const categoryBreakdown = Db.finGetByCategory(uid, from);
      const budgets = Db.finGetBudgets(uid);
      const user = Db.getUser(uid);
      const habits = Db.getHabits(uid);
      const today = now.toISOString().slice(0, 10);
      const todayDone = habits.filter((h: any) => {
        try { return DbV5.getLinkedDevices && false; } catch { return false; }
      }).length;

      // CBU rates
      let rates: any = {};
      try {
        const r = await fetch("https://cbu.uz/uz/arkhiv-kursov-valyut/json/");
        if (r.ok) {
          const raw = await r.json() as any[];
          for (const c of raw.slice(0, 10)) rates[c.Ccy] = c.Rate;
        }
      } catch {}

      res.json({
        accounts, income, expense, txs: txs.slice(0, 20),
        categoryBreakdown, budgets, rates,
        userName: user?.name ?? "",
        totalMsgs: user?.total_msgs ?? 0,
        todayHabits: habits.length,
        todayDone,
      });
    } catch (e: any) { res.status(500).json({ error: e.message }); }
  });

  // ── /api/add — Add finance transaction ─────────────────────────────
  app.post("/api/add", (req, res) => {
    const uid = verifyToken(req.query.uid as string, req.query.token as string);
    if (!uid) { res.status(401).json({ error: "Unauthorized" }); return; }
    try {
      const { type, amount, category, note, account_id } = req.body;
      if (!type || !amount || !category) { res.status(400).json({ error: "Missing fields" }); return; }
      const accs = Db.finGetAccounts(uid);
      const accId = account_id ?? accs[0]?.id;
      if (!accId) { res.status(400).json({ error: "No account" }); return; }
      Db.finAddTx(uid, accId, type, parseFloat(amount), category, note ?? "");
      res.json({ ok: true });
    } catch (e: any) { res.status(500).json({ error: e.message }); }
  });

  // ── Notes API ────────────────────────────────────────────────────────
  app.get("/api/notes", (req, res) => {
    const uid = verifyToken(req.query.uid as string, req.query.token as string);
    if (!uid) { res.status(401).json({ error: "Unauthorized" }); return; }
    try {
      const notes = Db.getNotes(uid, 100);
      res.json({ notes });
    } catch (e: any) { res.status(500).json({ error: e.message }); }
  });

  app.post("/api/notes/add", (req, res) => {
    const uid = verifyToken(req.query.uid as string, req.query.token as string);
    if (!uid) { res.status(401).json({ error: "Unauthorized" }); return; }
    try {
      const { content, icon } = req.body;
      if (!content) { res.status(400).json({ error: "Missing content" }); return; }
      Db.addNote(uid, content, icon ?? "📝");
      res.json({ ok: true });
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

  app.post("/api/notes/pin", (req, res) => {
    const uid = verifyToken(req.query.uid as string, req.query.token as string);
    if (!uid) { res.status(401).json({ error: "Unauthorized" }); return; }
    try {
      const { id, pinned } = req.body;
      Db.pinNote(uid, id, pinned);
      res.json({ ok: true });
    } catch (e: any) { res.status(500).json({ error: e.message }); }
  });

  // ── Tasks API ────────────────────────────────────────────────────────
  app.get("/api/tasks", (req, res) => {
    const uid = verifyToken(req.query.uid as string, req.query.token as string);
    if (!uid) { res.status(401).json({ error: "Unauthorized" }); return; }
    try {
      const tasks = Db.getTasks(uid);
      res.json({ tasks });
    } catch (e: any) { res.status(500).json({ error: e.message }); }
  });

  app.post("/api/tasks/add", (req, res) => {
    const uid = verifyToken(req.query.uid as string, req.query.token as string);
    if (!uid) { res.status(401).json({ error: "Unauthorized" }); return; }
    try {
      const { title, description, priority, project } = req.body;
      if (!title) { res.status(400).json({ error: "Missing title" }); return; }
      Db.addTask(uid, title, description ?? "", priority ?? 2, project ?? "");
      res.json({ ok: true });
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

  // ── Habits API ────────────────────────────────────────────────────────
  app.get("/api/habits", (req, res) => {
    const uid = verifyToken(req.query.uid as string, req.query.token as string);
    if (!uid) { res.status(401).json({ error: "Unauthorized" }); return; }
    try {
      const habits = Db.getHabits(uid);
      const today = new Date().toISOString().slice(0, 10);
      const withDone = habits.map((h: any) => {
        let doneToday = false;
        try {
          const log = Db.getHabitLog(h.id, today);
          doneToday = !!log;
        } catch {}
        return { ...h, doneToday };
      });
      res.json({ habits: withDone });
    } catch (e: any) { res.status(500).json({ error: e.message }); }
  });

  app.post("/api/habits/add", (req, res) => {
    const uid = verifyToken(req.query.uid as string, req.query.token as string);
    if (!uid) { res.status(401).json({ error: "Unauthorized" }); return; }
    try {
      const { name, icon, frequency } = req.body;
      if (!name) { res.status(400).json({ error: "Missing name" }); return; }
      Db.addHabit(uid, name, icon ?? "🎯", frequency ?? "daily");
      res.json({ ok: true });
    } catch (e: any) { res.status(500).json({ error: e.message }); }
  });

  app.post("/api/habits/done", (req, res) => {
    const uid = verifyToken(req.query.uid as string, req.query.token as string);
    if (!uid) { res.status(401).json({ error: "Unauthorized" }); return; }
    try {
      const { habit_id } = req.body;
      Db.logHabit(habit_id, uid);
      res.json({ ok: true });
    } catch (e: any) { res.status(500).json({ error: e.message }); }
  });

  app.listen(port, () => {
    log.info(`Web App server running on port ${port}`);
  });

  return app;
}
