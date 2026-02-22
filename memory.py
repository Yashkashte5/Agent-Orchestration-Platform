import sqlite3
from datetime import datetime

DB_PATH = "memory.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            timestamp TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS summary (
            session_id TEXT PRIMARY KEY,
            content TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id TEXT PRIMARY KEY,
            name TEXT,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()


def create_chat(session_id: str, name: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO chats (id, name, created_at) VALUES (?, ?, ?)",
        (session_id, name, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def get_chats():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, name, created_at FROM chats ORDER BY created_at DESC")
    rows = cur.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "created_at": r[2]} for r in rows]


def rename_chat(session_id: str, name: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE chats SET name=? WHERE id=?", (name, session_id))
    conn.commit()
    conn.close()


def delete_chat(session_id: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM chats WHERE id=?", (session_id,))
    cur.execute("DELETE FROM history WHERE session_id=?", (session_id,))
    cur.execute("DELETE FROM summary WHERE session_id=?", (session_id,))
    conn.commit()
    conn.close()


def save_message(session_id: str, role: str, content: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO history (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
        (session_id, role, content, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def get_history(session_id: str, limit: int = 6):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT role, content FROM history WHERE session_id=? ORDER BY id DESC LIMIT ?",
        (session_id, limit),
    )
    rows = cur.fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]


def save_summary(session_id: str, content: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO summary (session_id, content) VALUES (?, ?)
        ON CONFLICT(session_id) DO UPDATE SET content=excluded.content
        """,
        (session_id, content),
    )
    conn.commit()
    conn.close()


def get_summary(session_id: str) -> str:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT content FROM summary WHERE session_id=?", (session_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else ""