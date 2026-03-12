import express from 'express';
import { createServer } from 'http';
import { WebSocketServer, WebSocket } from 'ws';
import path from 'path';
import crypto from 'crypto';
import { config } from '../core/config';
import { db } from '../core/db';

const PUBLIC_DIR = path.join(__dirname, '..', 'public');

// ─── Telegram WebApp auth ──────────────────────────────────────────────────
// Validates initData from Telegram.WebApp.initData
function validateTgInitData(initData: string): number | null {
  try {
    const params = new URLSearchParams(initData);
    const hash = params.get('hash');
    if (!hash) return null;
    params.delete('hash');
    const sorted = Array.from(params.entries()).sort(([a],[b]) => a.localeCompare(b));
    const dataCheckString = sorted.map(([k,v]) => `${k}=${v}`).join('\n');
    const secretKey = crypto.createHmac('sha256', 'WebAppData').update(config.botToken).digest();
    const sig = crypto.createHmac('sha256', secretKey).update(dataCheckString).digest('hex');
    if (sig !== hash) return null;
    const user = JSON.parse(params.get('user') || '{}');
    return user.id || null;
  } catch { return null; }
}

// Middleware: get uid from query param tgUid (Mini App sends it)
// For prod: validate via initData. For simplicity we accept tgUid directly
// (Mini App reads Telegram.WebApp.initDataUnsafe.user.id)
function getUid(req: express.Request): number | null {
  const uid = parseInt((req.query.uid || req.body?.uid || '') as string);
  return isNaN(uid) ? null : uid;
}

export function startServer(bot?: any) {
  const app = express();
  app.use(express.json());
  app.use((_req, res, next) => {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    next();
  });

  // ── Static Mini Apps ────────────────────────────────────────────────────
  app.get('/',        (_req, res) => res.sendFile(path.join(PUBLIC_DIR, 'hub.html')));
  app.get('/hub',     (_req, res) => res.sendFile(path.join(PUBLIC_DIR, 'hub.html')));
  app.get('/finance', (_req, res) => res.sendFile(path.join(PUBLIC_DIR, 'finance.html')));
  app.get('/notes',   (_req, res) => res.sendFile(path.join(PUBLIC_DIR, 'notes.html')));
  app.get('/tasks',   (_req, res) => res.sendFile(path.join(PUBLIC_DIR, 'tasks.html')));
  app.get('/habits',  (_req, res) => res.sendFile(path.join(PUBLIC_DIR, 'habits.html')));
  app.get('/health',  (_req, res) => res.json({ ok: true, version: '7.0.0' }));
  app.get('/sites',   (_req, res) => res.sendFile(path.join(PUBLIC_DIR, 'sites.html')));
  app.get('/tools-app', (_req, res) => res.sendFile(path.join(PUBLIC_DIR, 'tools.html')));

  // ── Site viewer — AI-generated websites ──────────────────────────────────
  app.get('/site/:id', (req, res) => {
    const id = parseInt(req.params.id);
    const site = db.prepare('SELECT * FROM websites WHERE id = ?').get(id) as any;
    if (!site) return res.status(404).send('<h1>Site not found</h1>');
    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    res.send(site.html);
  });

  // ── API: Websites ─────────────────────────────────────────────────────────
  app.get('/api/websites', (req, res) => {
    const uid = getUid(req);
    if (!uid) return res.status(400).json({ ok: false, error: 'No uid' });
    const sites = db.prepare('SELECT id, uid, name, created_at FROM websites WHERE uid = ? ORDER BY created_at DESC').all(uid);
    res.json({ ok: true, data: sites });
  });

  app.delete('/api/websites/:id', (req, res) => {
    db.prepare('DELETE FROM websites WHERE id = ?').run(parseInt(req.params.id));
    res.json({ ok: true });
  });

  // ── API: Custom Tools ─────────────────────────────────────────────────────
  app.get('/api/tools', (req, res) => {
    const uid = getUid(req);
    if (!uid) return res.status(400).json({ ok: false, error: 'No uid' });
    const tools = db.prepare('SELECT id, name, description, trigger_pattern, usage_count, active, created_at FROM custom_tools WHERE (uid = ? OR uid = 0) ORDER BY usage_count DESC').all(uid);
    res.json({ ok: true, data: tools });
  });

  app.delete('/api/tools/:id', (req, res) => {
    db.prepare('UPDATE custom_tools SET active = 0 WHERE id = ?').run(parseInt(req.params.id));
    res.json({ ok: true });
  });



  // ── API: Finance ─────────────────────────────────────────────────────────
  app.get('/api/finance', (req, res) => {
    const uid = getUid(req);
    if (!uid) return res.status(400).json({ ok: false, error: 'No uid' });
    const month = (req.query.month as string) || new Date().toISOString().substring(0, 7);
    const txs = db.prepare(
      `SELECT * FROM finance WHERE uid = ? AND created_at >= ? ORDER BY created_at DESC`
    ).all(uid, `${month}-01`);
    res.json({ ok: true, data: txs });
  });

  app.post('/api/finance', (req, res) => {
    const { uid, type, amount, category, note } = req.body;
    if (!uid || !type || !amount) return res.status(400).json({ ok: false, error: 'Missing' });
    const r = db.prepare(
      'INSERT INTO finance (uid, type, amount, category, note) VALUES (?, ?, ?, ?, ?)'
    ).run(uid, type, parseFloat(amount), category || 'Other', note || '');
    res.json({ ok: true, id: r.lastInsertRowid });
  });

  app.delete('/api/finance/:id', (req, res) => {
    db.prepare('DELETE FROM finance WHERE id = ?').run(parseInt(req.params.id));
    res.json({ ok: true });
  });

  // ── API: Notes ────────────────────────────────────────────────────────────
  app.get('/api/notes', (req, res) => {
    const uid = getUid(req);
    if (!uid) return res.status(400).json({ ok: false, error: 'No uid' });
    const notes = db.prepare(
      'SELECT * FROM notes WHERE uid = ? ORDER BY pinned DESC, updated_at DESC'
    ).all(uid);
    res.json({ ok: true, data: notes });
  });

  app.post('/api/notes', (req, res) => {
    const { uid, title, content, pinned } = req.body;
    if (!uid || !content) return res.status(400).json({ ok: false, error: 'Missing' });
    const r = db.prepare(
      'INSERT INTO notes (uid, title, content, pinned) VALUES (?, ?, ?, ?)'
    ).run(uid, title || '', content, pinned ? 1 : 0);
    res.json({ ok: true, id: r.lastInsertRowid });
  });

  app.put('/api/notes/:id', (req, res) => {
    const { title, content, pinned } = req.body;
    db.prepare(
      `UPDATE notes SET title=?, content=?, pinned=?, updated_at=datetime('now') WHERE id=?`
    ).run(title || '', content || '', pinned ? 1 : 0, parseInt(req.params.id));
    res.json({ ok: true });
  });

  app.delete('/api/notes/:id', (req, res) => {
    db.prepare('DELETE FROM notes WHERE id = ?').run(parseInt(req.params.id));
    res.json({ ok: true });
  });

  // ── API: Tasks ────────────────────────────────────────────────────────────
  app.get('/api/tasks', (req, res) => {
    const uid = getUid(req);
    if (!uid) return res.status(400).json({ ok: false, error: 'No uid' });
    const tasks = db.prepare(
      `SELECT * FROM tasks WHERE uid = ? ORDER BY
        CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
        created_at DESC`
    ).all(uid);
    res.json({ ok: true, data: tasks });
  });

  app.post('/api/tasks', (req, res) => {
    const { uid, title, description, project, priority, due_date } = req.body;
    if (!uid || !title) return res.status(400).json({ ok: false, error: 'Missing' });
    const r = db.prepare(
      `INSERT INTO tasks (uid, title, description, project, priority, due_date)
       VALUES (?, ?, ?, ?, ?, ?)`
    ).run(uid, title, description || '', project || 'General', priority || 'medium', due_date || null);
    res.json({ ok: true, id: r.lastInsertRowid });
  });

  app.put('/api/tasks/:id', (req, res) => {
    const { title, status, priority, project, due_date } = req.body;
    db.prepare(
      `UPDATE tasks SET title=COALESCE(?,title), status=COALESCE(?,status),
       priority=COALESCE(?,priority), project=COALESCE(?,project),
       due_date=COALESCE(?,due_date), updated_at=datetime('now') WHERE id=?`
    ).run(title||null, status||null, priority||null, project||null, due_date||null, parseInt(req.params.id));
    res.json({ ok: true });
  });

  app.delete('/api/tasks/:id', (req, res) => {
    db.prepare('DELETE FROM tasks WHERE id = ?').run(parseInt(req.params.id));
    res.json({ ok: true });
  });

  // ── API: Habits ───────────────────────────────────────────────────────────
  app.get('/api/habits', (req, res) => {
    const uid = getUid(req);
    if (!uid) return res.status(400).json({ ok: false, error: 'No uid' });
    const habits = db.prepare('SELECT * FROM habits WHERE uid = ? ORDER BY created_at').all(uid);
    const today = new Date().toISOString().split('T')[0];
    // Attach weekly logs
    const result = habits.map((h: any) => {
      const logs = db.prepare(
        `SELECT date(done_at) as d FROM habit_logs WHERE habit_id = ? AND done_at >= date('now','-7 days')
         GROUP BY date(done_at)`
      ).all(h.id).map((r: any) => r.d);
      return { ...h, logs, done_today: logs.includes(today) };
    });
    res.json({ ok: true, data: result });
  });

  app.post('/api/habits', (req, res) => {
    const { uid, name, emoji } = req.body;
    if (!uid || !name) return res.status(400).json({ ok: false, error: 'Missing' });
    const r = db.prepare(
      'INSERT INTO habits (uid, name, emoji) VALUES (?, ?, ?)'
    ).run(uid, name, emoji || '🎯');
    res.json({ ok: true, id: r.lastInsertRowid });
  });

  // Toggle habit done for today
  app.post('/api/habits/:id/toggle', (req, res) => {
    const id = parseInt(req.params.id);
    const today = new Date().toISOString().split('T')[0];
    const existing = db.prepare(
      `SELECT id FROM habit_logs WHERE habit_id = ? AND date(done_at) = ?`
    ).get(id, today);

    if (existing) {
      db.prepare('DELETE FROM habit_logs WHERE id = ?').run((existing as any).id);
      db.prepare(`UPDATE habits SET streak = MAX(0, streak-1) WHERE id = ?`).run(id);
    } else {
      db.prepare('INSERT INTO habit_logs (habit_id, uid, done_at) VALUES (?, ?, datetime(?))').run(
        id, req.body.uid || 0, today + 'T12:00:00'
      );
      // Recalculate streak
      const yesterday = new Date();
      yesterday.setDate(yesterday.getDate() - 1);
      const yd = yesterday.toISOString().split('T')[0];
      const hadYesterday = db.prepare(
        `SELECT id FROM habit_logs WHERE habit_id = ? AND date(done_at) = ?`
      ).get(id, yd);
      const habit = db.prepare('SELECT * FROM habits WHERE id = ?').get(id) as any;
      const newStreak = hadYesterday ? (habit?.streak || 0) + 1 : 1;
      const bestStreak = Math.max(habit?.best_streak || 0, newStreak);
      db.prepare(
        `UPDATE habits SET streak=?, best_streak=?, last_done=? WHERE id=?`
      ).run(newStreak, bestStreak, today, id);
    }
    res.json({ ok: true });
  });

  app.delete('/api/habits/:id', (req, res) => {
    db.prepare('DELETE FROM habit_logs WHERE habit_id = ?').run(parseInt(req.params.id));
    db.prepare('DELETE FROM habits WHERE id = ?').run(parseInt(req.params.id));
    res.json({ ok: true });
  });

  // ── WebSocket (PC Agent) ──────────────────────────────────────────────────
  const httpServer = createServer(app);
  const wss = new WebSocketServer({ server: httpServer, path: '/ws' });
  const linkCodes = new Map<string, { deviceId: string; platform: string; ws: WebSocket }>();
  const agents    = new Map<number, WebSocket>();
  const pending   = new Map<string, { resolve: Function; reject: Function }>();

  wss.on('connection', (ws) => {
    let wsUid: number | null = null;

    ws.on('message', (raw) => {
      try {
        const msg = JSON.parse(raw.toString());
        const type = msg.type;

        if (type === 'request_link') {
          const code = Math.random().toString(36).slice(2, 8).toUpperCase();
          linkCodes.set(code, { deviceId: msg.device_id, platform: msg.platform || 'Unknown', ws });
          ws.send(JSON.stringify({ type: 'link_code', code }));

        } else if (type === 'register') {
          wsUid = msg.uid;
          if (wsUid) {
            agents.set(wsUid, ws);
            db.prepare(`INSERT INTO pc_agents (uid, device_id, platform, last_seen)
              VALUES (?, ?, ?, datetime('now'))
              ON CONFLICT(uid) DO UPDATE SET device_id=excluded.device_id,
              platform=excluded.platform, last_seen=excluded.last_seen`
            ).run(wsUid, msg.device_id, msg.platform || 'Unknown');
            ws.send(JSON.stringify({ type: 'registered' }));
          }

        } else if (type === 'result' || type === 'screenshot_result') {
          const reqId = msg.reqId;
          const p = pending.get(reqId);
          if (p) { p.resolve(msg); pending.delete(reqId); }

        } else if (type === 'ping') {
          ws.send(JSON.stringify({ type: 'pong' }));
        }
      } catch {}
    });

    ws.on('close', () => {
      if (wsUid) agents.delete(wsUid);
    });
  });

  // Expose for bot commands
  (app as any).sendToAgent = async (uid: number, msg: object): Promise<any> => {
    const ws = agents.get(uid);
    if (!ws || ws.readyState !== WebSocket.OPEN) throw new Error('Agent offline');
    const reqId = crypto.randomUUID();
    return new Promise((resolve, reject) => {
      pending.set(reqId, { resolve, reject });
      setTimeout(() => { pending.delete(reqId); reject(new Error('Timeout')); }, 20000);
      ws.send(JSON.stringify({ ...msg, reqId }));
    });
  };

  (app as any).linkAgent = (code: string, uid: number): boolean => {
    const entry = linkCodes.get(code.toUpperCase());
    if (!entry) return false;
    entry.ws.send(JSON.stringify({ type: 'linked', uid }));
    agents.set(uid, entry.ws);
    linkCodes.delete(code.toUpperCase());
    return true;
  };

  (app as any).isAgentOnline = (uid: number): boolean => {
    const ws = agents.get(uid);
    return !!ws && ws.readyState === WebSocket.OPEN;
  };

  const port = parseInt(process.env.PORT || '3000');
  httpServer.listen(port, () => {
    console.log(`[server] ✅ Running on port ${port}`);
  });

  return httpServer;
}
