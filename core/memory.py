import sqlite3

DB = "memory.db"


def init_db():
    conn = sqlite3.connect(DB)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid INTEGER,
        role TEXT,
        text TEXT
    )
    """)

    conn.commit()
    conn.close()


def save(uid, role, text):

    conn = sqlite3.connect(DB)

    conn.execute(
        "INSERT INTO messages(uid,role,text) VALUES(?,?,?)",
        (uid, role, text)
    )

    conn.commit()
    conn.close()


def load(uid, limit=20):

    conn = sqlite3.connect(DB)

    rows = conn.execute(
        "SELECT role,text FROM messages WHERE uid=? ORDER BY id DESC LIMIT ?",
        (uid, limit)
    ).fetchall()

    conn.close()

    rows.reverse()

    history = []

    for r in rows:
        history.append({
            "role": r[0],
            "content": r[1]
        })

    return history
