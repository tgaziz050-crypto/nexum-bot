import sqlite3
from datetime import datetime
DB = "nexum_memory.db"

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid INTEGER,
            role TEXT,
            content TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid INTEGER,
            category TEXT,
            fact TEXT,
            importance INTEGER DEFAULT 5,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()

def save_message(uid:int, role:str, content:str):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT INTO conversations(uid,role,content,created_at) VALUES(?,?,?,?)",
              (uid, role, content, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def get_history(uid:int, limit:int=30):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT role,content,created_at FROM conversations WHERE uid=? ORDER BY id DESC LIMIT ?",
              (uid, limit))
    rows = c.fetchall()
    conn.close()
    rows.reverse()
    return [{"role":r[0],"content":r[1],"time":r[2]} for r in rows]

def add_memory(uid:int, category:str, fact:str, importance:int=5):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT INTO memories(uid,category,fact,importance,created_at) VALUES(?,?,?,?,?)",
              (uid, category, fact, importance, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
