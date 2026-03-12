import express from 'express';
import { createServer } from 'http';
import { WebSocketServer, WebSocket } from 'ws';
import path from 'path';
import { fileURLToPath } from 'url';
import { config } from '../core/config.ts';
import { db } from '../core/db.ts';
import crypto from 'crypto';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PUBLIC_DIR = path.join(__dirname, '..', '..', 'src', 'public');

export function startServer(bot?: any) {
  const app = express();
  app.use(express.json());

  // Health check
  app.get('/health', (_req, res) => res.json({ ok: true, version: '6.0.0' }));

  // Serve mini apps
  app.get('/', (_req, res) => res.sendFile(path.join(PUBLIC_DIR, 'hub.html')));
  app.get('/hub', (_req, res) => res.sendFile(path.join(PUBLIC_DIR, 'hub.html')));
  app.get('/finance', (_req, res) => res.sendFile(path.join(PUBLIC_DIR, 'finance.html')));
  app.get('/notes', (_req, res) => res.sendFile(path.join(PUBLIC_DIR, 'notes.html')));
  app.get('/tasks', (_req, res) => res.sendFile(path.join(PUBLIC_DIR, 'tasks.html')));
  app.get('/habits', (_req, res) => res.sendFile(path.join(PUBLIC_DIR, 'habits.html')));

  // API: Finance
  app.get('/api/finance/:uid', (req, res) => {
    const uid = parseInt(req.params.uid);
    const month = (req.query.month as string) || new Date().toISOString().substring(0, 7);
    const txs = db.prepare(`SELECT * FROM finance WHERE uid = ? AND created_at >= ? ORDER BY created_at DESC`).all(uid, `${month}-01`);
    res.json({ ok: true, data: txs });
  });

  app.post('/api/finance', (req, res) => {
    const { uid, type, amount, category, note } = req.body;
    if (!uid || !type || !amount) return res.status(400).json({ ok: false, error: 'Missing fields' });
    const r = db.prepare('INSERT INTO finance (uid, type, amount, category, note) VALUES (?, ?, ?, ?, ?)').run(uid, type, amount, category || 'Other', note || '');
    res.json({ ok: true, id: r.lastInsertRowid });
  });

  // API: Notes
  app.get('/api/notes/:uid', (req, res) => {
    const uid = parseInt(req.params.uid);
    const notes = db.prepare('SELECT * FROM notes WHERE uid = ? ORDER BY pinned DESC, updated_at DESC').all(uid);
    res.json({ ok: true, data: notes });
  });

  app.post('/api/notes', (req, res) => {
    const { uid, title, content } = req.body;
    if (!uid || !content) return res.status(400).json({ ok: false, error: 'Missing fields' });
    const r = db.prepare('INSERT INTO notes (uid, title, content) VALUES (?, ?, ?)').run(uid, title || '', content);
    res.json({ ok: true, id: r.lastInsertRowid });
  });

  app.delete('/api/notes/:id', (req, res) => {
    db.prepare('DELETE FROM notes WHERE id = ?').run(parseInt(req.params.id));
    res.json({ ok: true });
  });

  // API: Tasks
  app.get('/api/tasks/:uid', (req, res) => {
    const uid = parseInt(req.params.uid);
    const tasks = db.prepare('SELECT * FROM tasks WHERE uid = ? ORDER BY priority DESC, created_at DESC').all(uid);
    res.json({ ok: true, data: tasks });
  });

  app.post('/api/tasks', (req, res) => {
    const { uid, title, project, priority, due_date } = req.body;
    if (!uid || !title) return res.status(400).json({ ok: false, error: 'Missing fields' });
    const r = db.prepare('INSERT INTO tasks (uid, title, project, priority, due_date) VALUES (?, ?, ?, ?, ?)').run(uid, title, project || 'General', priority || 'medium', due_date || null);
    res.json({ ok: true, id: r.lastInsertRowid });
  });

  app.patch('/api/tasks/:id', (req, res) => {
    const { status } = req.body;
    db.prepare('UPDATE tasks SET status = ?, updated_at = datetime(\'now\') WHERE id = ?').run(status, parseInt(req.params.id));
    res.json({ ok: true });
  });

  // API: Habits
  app.get('/api/habits/:uid', (req, res) => {
    const uid = parseInt(req.params.uid);
    const habits = db.prepare('SELECT * FROM habits WHERE uid = ? ORDER BY streak DESC').all(uid);
    res.json({ ok: true, data: habits });
  });

  app.post('/api/habits/:id/done', (req, res) => {
    const id = parseInt(req.params.id);
    const habit = db.prepare('SELECT * FROM habits WHERE id = ?').get(id) as any;
    if (!habit) return res.status(404).json({ ok: false });
    const today = new Date().toISOString().split('T')[0];
    if (habit.last_done?.startsWith(today)) {
      // Undo
      db.prepare('UPDATE habits SET streak = MAX(0, streak - 1), last_done = NULL WHERE id = ?').run(id);
    } else {
      const newStreak = habit.streak + 1;
      const bestStreak = Math.max(habit.best_streak || 0, newStreak);
      db.prepare('UPDATE habits SET streak = ?, best_streak = ?, last_done = ? WHERE id = ?').run(newStreak, bestStreak, new Date().toISOString(), id);
    }
    res.json({ ok: true });
  });

  // WebSocket server for PC Agent
  const httpServer = createServer(app);
  const wss = new WebSocketServer({ server: httpServer, path: '/ws' });

  const pcClients = new Map<string, WebSocket>(); // device_id -> ws
  const pendingResults = new Map<string, (data: any) => void>();

  wss.on('connection', (ws) => {
    let deviceId: string | null = null;
    let uid: number | null = null;

    ws.on('message', async (raw) => {
      try {
        const msg = JSON.parse(raw.toString());

        if (msg.type === 'register' && msg.uid) {
          uid = msg.uid;
          deviceId = msg.device_id;
          if (deviceId) pcClients.set(deviceId, ws);
          db.prepare(`INSERT INTO pc_agents (uid, device_id, platform, ws_id, last_seen)
            VALUES (?, ?, ?, ?, ?) ON CONFLICT(uid) DO UPDATE SET device_id=?, platform=?, ws_id=?, last_seen=?`)
            .run(uid, deviceId, msg.platform || '', deviceId, new Date().toISOString(),
                 deviceId, msg.platform || '', deviceId, new Date().toISOString());
          ws.send(JSON.stringify({ type: 'registered', ok: true }));
        }

        if (msg.type === 'request_link') {
          deviceId = msg.device_id;
          const code = crypto.randomBytes(3).toString('hex').toUpperCase();
          db.prepare('DELETE FROM link_codes WHERE device_id = ?').run(deviceId);
          db.prepare('INSERT INTO link_codes (code, device_id, platform) VALUES (?, ?, ?)').run(code, deviceId, msg.platform || '');
          if (deviceId) pcClients.set(deviceId, ws);
          ws.send(JSON.stringify({ type: 'link_code', code }));
        }

        if (msg.type === 'linked') {
          uid = msg.uid;
          if (deviceId) db.prepare('UPDATE pc_agents SET uid = ?, last_seen = ? WHERE device_id = ?').run(uid, new Date().toISOString(), deviceId);
        }

        if (msg.type === 'screenshot_result' || msg.type === 'result') {
          const resolve = pendingResults.get(msg.reqId);
          if (resolve) {
            resolve(msg);
            pendingResults.delete(msg.reqId);
          }

          // If screenshot, send to Telegram
          if (msg.type === 'screenshot_result' && msg.data && msg.chatId && bot) {
            const imgBuf = Buffer.from(msg.data, 'base64');
            try {
              await bot.api.sendPhoto(msg.chatId, new (await import('grammy')).InputFile(imgBuf, 'screenshot.png'), { caption: '📸 Скриншот' });
            } catch (e) { console.error('[ws] screenshot send error:', e); }
          }

          if (msg.type === 'result' && msg.chatId && bot) {
            try {
              await bot.api.sendMessage(msg.chatId, `\`\`\`\n${msg.data || '(no output)'}\n\`\`\``, { parse_mode: 'Markdown' });
            } catch (e) { console.error('[ws] result send error:', e); }
          }
        }

        if (msg.type === 'ping') {
          ws.send(JSON.stringify({ type: 'pong' }));
        }
      } catch (e) { console.error('[ws] message error:', e); }
    });

    ws.on('close', () => {
      if (deviceId) pcClients.delete(deviceId);
      if (uid) db.prepare('UPDATE pc_agents SET ws_id = NULL WHERE uid = ?').run(uid);
    });
  });

  // Helper to send command to PC agent
  global.sendToPCAgent = async (uid: number, msg: any): Promise<any> => {
    const agent = db.prepare('SELECT * FROM pc_agents WHERE uid = ?').get(uid) as any;
    if (!agent?.ws_id) throw new Error('PC Agent not connected');
    const ws = pcClients.get(agent.ws_id);
    if (!ws || ws.readyState !== WebSocket.OPEN) throw new Error('PC Agent disconnected');

    const reqId = crypto.randomUUID();
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        pendingResults.delete(reqId);
        reject(new Error('PC Agent timeout (30s)'));
      }, 30000);

      pendingResults.set(reqId, (data) => {
        clearTimeout(timeout);
        resolve(data);
      });

      ws.send(JSON.stringify({ ...msg, reqId }));
    });
  };

  const port = config.port;
  httpServer.listen(port, () => {
    console.log(`[server] running on port ${port}`);
    console.log(`[server] mini apps: ${config.webappUrl || `http://localhost:${port}`}`);
  });

  return httpServer;
}
