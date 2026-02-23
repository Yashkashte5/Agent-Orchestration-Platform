import sqlite3
import asyncio
import os
import httpx
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from llm.groq_client import generate

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DB_PATH = "memory.db"
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")

# ─────────────────────────────────────────
# SLACK
# ─────────────────────────────────────────

def _send_slack(message: str, blocks: list = None) -> bool:
    if not SLACK_WEBHOOK_URL:
        print(f"SLACK_WEBHOOK_URL not set. Reminder: {message}")
        return False
    try:
        payload = {"text": message}
        if blocks:
            payload["blocks"] = blocks
        response = httpx.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"Slack notification failed: {e}")
        return False


def _build_reminder_blocks(reminder_id: int, message: str) -> list:
    now = datetime.now().strftime("%I:%M %p")
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Reminder*\n{message}"}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": f"Fired at {now}  |  ID: `{reminder_id}`"}]},
        {"type": "divider"}
    ]



DB_PATH = "memory.db"

# ─────────────────────────────────────────
# SCHEDULER SETUP
# ─────────────────────────────────────────

scheduler = BackgroundScheduler()


def _fire_reminder(reminder_id: int, message: str):
    """Called by scheduler when a reminder is due. Sends Slack notification."""
    blocks = _build_reminder_blocks(reminder_id, message)
    slack_sent = _send_slack(f"Reminder: {message}", blocks=blocks)
    status = "Slack sent" if slack_sent else "Slack failed"
    print(f"\nREMINDER [{reminder_id}]: {message} | {status}\n")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT recurrence FROM reminders WHERE id=?", (reminder_id,))
    row = cur.fetchone()
    recurrence = row[0] if row else "none"

    if recurrence == "daily":
        next_time = datetime.utcnow() + timedelta(days=1)
        cur.execute("UPDATE reminders SET remind_at=? WHERE id=?", (next_time.isoformat(), reminder_id))
        conn.commit()
        conn.close()
        scheduler.add_job(_fire_reminder, "date", run_date=next_time,
            args=[reminder_id, message], id=f"reminder_{reminder_id}", replace_existing=True)
    elif recurrence == "weekly":
        next_time = datetime.utcnow() + timedelta(weeks=1)
        cur.execute("UPDATE reminders SET remind_at=? WHERE id=?", (next_time.isoformat(), reminder_id))
        conn.commit()
        conn.close()
        scheduler.add_job(_fire_reminder, "date", run_date=next_time,
            args=[reminder_id, message], id=f"reminder_{reminder_id}", replace_existing=True)
    else:
        cur.execute("UPDATE reminders SET done=1 WHERE id=?", (reminder_id,))
        conn.commit()
        conn.close()


def start_scheduler():
    """Start scheduler and reload any pending reminders from DB."""
    scheduler.start()
    _reload_pending_reminders()


def _reload_pending_reminders():
    """On startup, reschedule any reminders that haven't fired yet."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, message, remind_at FROM reminders WHERE done=0")
    rows = cur.fetchall()
    conn.close()

    now = datetime.utcnow()
    for row in rows:
        rid, message, remind_at_str = row
        try:
            remind_at = datetime.fromisoformat(remind_at_str)
            if remind_at > now:
                scheduler.add_job(
                    _fire_reminder,
                    "date",
                    run_date=remind_at,
                    args=[rid, message],
                    id=f"reminder_{rid}",
                    replace_existing=True,
                )
        except Exception as e:
            print(f"Could not reschedule reminder {rid}: {e}")


# ─────────────────────────────────────────
# DB INIT
# ─────────────────────────────────────────

def init_productivity_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task TEXT,
            priority TEXT DEFAULT 'normal',
            due_date TEXT,
            done INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            body TEXT,
            summary TEXT,
            tags TEXT,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT,
            remind_at TEXT,
            recurrence TEXT DEFAULT 'none',
            done INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()


# ─────────────────────────────────────────
# TODOS
# ─────────────────────────────────────────

PRIORITY_ORDER = {"high": 0, "normal": 1, "low": 2}


def add_todo(task: str, priority: str = "normal", due_date: str = "") -> dict:
    """
    Add a todo. priority: low | normal | high
    due_date: optional, format YYYY-MM-DD
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO todos (task, priority, due_date, created_at) VALUES (?, ?, ?, ?)",
        (task, priority, due_date or None, datetime.utcnow().isoformat()),
    )
    conn.commit()
    todo_id = cur.lastrowid
    conn.close()
    msg = f"Todo added: '{task}' | priority: {priority}"
    if due_date:
        msg += f" | due: {due_date}"
    return {"success": True, "message": msg, "id": todo_id}


def bulk_add_todos(tasks: list) -> dict:
    """
    Add multiple todos at once.
    tasks: list of strings or dicts with keys: task, priority (optional), due_date (optional)
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    added = []
    for item in tasks:
        if isinstance(item, str):
            task, priority, due_date = item, "normal", None
        else:
            task = item.get("task", "")
            priority = item.get("priority", "normal")
            due_date = item.get("due_date", None) or None
        if not task:
            continue
        cur.execute(
            "INSERT INTO todos (task, priority, due_date, created_at) VALUES (?, ?, ?, ?)",
            (task, priority, due_date, datetime.utcnow().isoformat()),
        )
        added.append({"id": cur.lastrowid, "task": task, "priority": priority})
    conn.commit()
    conn.close()
    return {"success": True, "message": f"Added {len(added)} todos", "todos": added}


def list_todos() -> dict:
    """List all pending todos sorted by priority then due date. Flags overdue items."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, task, priority, due_date, created_at FROM todos WHERE done=0")
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return {"success": True, "todos": [], "message": "No pending todos"}

    now = datetime.utcnow().date()
    todos = []
    for r in rows:
        tid, task, priority, due_date, created_at = r
        overdue = False
        if due_date:
            try:
                overdue = datetime.fromisoformat(due_date).date() < now
            except Exception:
                pass
        todos.append({
            "id": tid,
            "task": task,
            "priority": priority,
            "due_date": due_date or "none",
            "overdue": overdue,
            "created_at": created_at,
        })

    todos.sort(key=lambda x: (
        PRIORITY_ORDER.get(x["priority"], 1),
        x["due_date"] if x["due_date"] != "none" else "9999",
    ))

    overdue_count = sum(1 for t in todos if t["overdue"])
    return {"success": True, "todos": todos, "overdue_count": overdue_count}


def complete_todo(todo_id: int) -> dict:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE todos SET done=1 WHERE id=?", (todo_id,))
    conn.commit()
    affected = cur.rowcount
    conn.close()
    if affected == 0:
        return {"success": False, "message": f"No todo found with id {todo_id}"}
    return {"success": True, "message": f"Todo {todo_id} marked complete"}


def bulk_complete_todos(todo_ids: list) -> dict:
    """Mark multiple todos complete in one shot."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executemany("UPDATE todos SET done=1 WHERE id=?", [(i,) for i in todo_ids])
    conn.commit()
    conn.close()
    return {"success": True, "message": f"Completed todos: {todo_ids}"}


def delete_todo(todo_id: int) -> dict:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM todos WHERE id=?", (todo_id,))
    conn.commit()
    affected = cur.rowcount
    conn.close()
    if affected == 0:
        return {"success": False, "message": f"No todo found with id {todo_id}"}
    return {"success": True, "message": f"Todo {todo_id} deleted"}


# ─────────────────────────────────────────
# NOTES
# ─────────────────────────────────────────

async def add_note(title: str, body: str, tags: str = "") -> dict:
    """
    Save a note. Auto-summarizes if body is long.
    tags: comma separated e.g. 'work,ideas,ai'
    """
    summary = ""
    if len(body.split()) > 40:
        try:
            summary = await generate(f"Summarize in one sentence:\n\n{body}")
            summary = summary.strip()
        except Exception:
            summary = ""

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO notes (title, body, summary, tags, created_at) VALUES (?, ?, ?, ?, ?)",
        (title, body, summary, tags, datetime.utcnow().isoformat()),
    )
    conn.commit()
    note_id = cur.lastrowid
    conn.close()

    result = {"success": True, "message": f"Note saved: '{title}'", "id": note_id}
    if summary:
        result["auto_summary"] = summary
    return result


def get_notes(keyword: str = "", tag: str = "") -> dict:
    """Retrieve notes. Filter by keyword or tag."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    if tag:
        cur.execute(
            "SELECT id, title, body, summary, tags, created_at FROM notes WHERE tags LIKE ? ORDER BY id DESC",
            (f"%{tag}%",),
        )
    elif keyword:
        cur.execute(
            "SELECT id, title, body, summary, tags, created_at FROM notes WHERE title LIKE ? OR body LIKE ? ORDER BY id DESC",
            (f"%{keyword}%", f"%{keyword}%"),
        )
    else:
        cur.execute("SELECT id, title, body, summary, tags, created_at FROM notes ORDER BY id DESC")

    rows = cur.fetchall()
    conn.close()

    if not rows:
        return {"success": True, "notes": [], "message": "No notes found"}

    notes = [
        {
            "id": r[0],
            "title": r[1],
            "body": r[2],
            "summary": r[3] or "",
            "tags": r[4] or "",
            "created_at": r[5],
        }
        for r in rows
    ]
    return {"success": True, "notes": notes}


def update_note(note_id: int, title: str = "", body: str = "") -> dict:
    """Update an existing note's title or body."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    if title and body:
        cur.execute("UPDATE notes SET title=?, body=? WHERE id=?", (title, body, note_id))
    elif title:
        cur.execute("UPDATE notes SET title=? WHERE id=?", (title, note_id))
    elif body:
        cur.execute("UPDATE notes SET body=? WHERE id=?", (body, note_id))
    else:
        conn.close()
        return {"success": False, "message": "Provide title or body to update"}

    conn.commit()
    affected = cur.rowcount
    conn.close()

    if affected == 0:
        return {"success": False, "message": f"No note found with id {note_id}"}
    return {"success": True, "message": f"Note {note_id} updated"}


def delete_note(note_id: int) -> dict:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM notes WHERE id=?", (note_id,))
    conn.commit()
    affected = cur.rowcount
    conn.close()
    if affected == 0:
        return {"success": False, "message": f"No note found with id {note_id}"}
    return {"success": True, "message": f"Note {note_id} deleted"}


# ─────────────────────────────────────────
# REMINDERS
# ─────────────────────────────────────────

def set_reminder(message: str, remind_at: str, recurrence: str = "none") -> dict:
    """
    Set a reminder.
    remind_at: 'YYYY-MM-DD HH:MM'
    recurrence: none | daily | weekly
    """
    try:
        remind_dt = datetime.fromisoformat(remind_at)
    except ValueError:
        return {"success": False, "message": "Invalid datetime format. Use: YYYY-MM-DD HH:MM"}

    if remind_dt <= datetime.utcnow():
        return {"success": False, "message": "Reminder time must be in the future"}

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO reminders (message, remind_at, recurrence, created_at) VALUES (?, ?, ?, ?)",
        (message, remind_at, recurrence, datetime.utcnow().isoformat()),
    )
    conn.commit()
    reminder_id = cur.lastrowid
    conn.close()

    scheduler.add_job(
        _fire_reminder,
        "date",
        run_date=remind_dt,
        args=[reminder_id, message],
        id=f"reminder_{reminder_id}",
        replace_existing=True,
    )

    result = {"success": True, "message": f"Reminder set: '{message}' at {remind_at}", "id": reminder_id}
    if recurrence != "none":
        result["recurrence"] = recurrence
    return result


def list_reminders() -> dict:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, message, remind_at, recurrence, created_at FROM reminders WHERE done=0 ORDER BY remind_at ASC"
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return {"success": True, "reminders": [], "message": "No upcoming reminders"}

    reminders = [
        {
            "id": r[0],
            "message": r[1],
            "remind_at": r[2],
            "recurrence": r[3],
            "created_at": r[4],
        }
        for r in rows
    ]
    return {"success": True, "reminders": reminders}


def snooze_reminder(reminder_id: int, minutes: int = 15) -> dict:
    """Push a reminder forward by X minutes."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT message, remind_at FROM reminders WHERE id=?", (reminder_id,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return {"success": False, "message": f"No reminder found with id {reminder_id}"}

    message, remind_at_str = row
    try:
        new_time = datetime.fromisoformat(remind_at_str) + timedelta(minutes=minutes)
    except Exception:
        conn.close()
        return {"success": False, "message": "Could not parse reminder time"}

    cur.execute("UPDATE reminders SET remind_at=? WHERE id=?", (new_time.isoformat(), reminder_id))
    conn.commit()
    conn.close()

    job_id = f"reminder_{reminder_id}"
    if scheduler.get_job(job_id):
        scheduler.reschedule_job(job_id, trigger="date", run_date=new_time)
    else:
        scheduler.add_job(
            _fire_reminder,
            "date",
            run_date=new_time,
            args=[reminder_id, message],
            id=job_id,
            replace_existing=True,
        )

    return {"success": True, "message": f"Reminder {reminder_id} snoozed to {new_time.strftime('%Y-%m-%d %H:%M')}"}


def delete_reminder(reminder_id: int) -> dict:
    job_id = f"reminder_{reminder_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM reminders WHERE id=?", (reminder_id,))
    conn.commit()
    affected = cur.rowcount
    conn.close()

    if affected == 0:
        return {"success": False, "message": f"No reminder found with id {reminder_id}"}
    return {"success": True, "message": f"Reminder {reminder_id} deleted"}


# ─────────────────────────────────────────
# CROSS-TOOL
# ─────────────────────────────────────────

def get_daily_summary() -> dict:
    """One call: pending todos with overdue flags, upcoming reminders, recent notes."""
    todos_result = list_todos()
    reminders_result = list_reminders()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, title, summary, tags, created_at FROM notes ORDER BY id DESC LIMIT 5"
    )
    note_rows = cur.fetchall()
    conn.close()

    recent_notes = [
        {"id": r[0], "title": r[1], "summary": r[2] or "", "tags": r[3] or "", "created_at": r[4]}
        for r in note_rows
    ]

    todos = todos_result.get("todos", [])
    overdue = [t for t in todos if t.get("overdue")]

    return {
        "success": True,
        "daily_summary": {
            "pending_todos": len(todos),
            "overdue_todos": len(overdue),
            "todos": todos,
            "upcoming_reminders": reminders_result.get("reminders", []),
            "recent_notes": recent_notes,
        }
    }


def clear_completed() -> dict:
    """Wipe all completed todos and fired reminders."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM todos WHERE done=1")
    todos_deleted = cur.rowcount
    cur.execute("DELETE FROM reminders WHERE done=1")
    reminders_deleted = cur.rowcount
    conn.commit()
    conn.close()
    return {
        "success": True,
        "message": f"Cleared {todos_deleted} completed todos and {reminders_deleted} fired reminders",
    }

# ─────────────────────────────────────────
# SLACK TOOLS
# ─────────────────────────────────────────

def send_slack_message(message: str) -> dict:
    """Send a custom message to Slack."""
    if not SLACK_WEBHOOK_URL:
        return {"success": False, "message": "SLACK_WEBHOOK_URL not configured in .env"}
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": message}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": f"Sent via Agent · {datetime.now().strftime('%b %d, %I:%M %p')}"}]}
    ]
    sent = _send_slack(message, blocks=blocks)
    if sent:
        return {"success": True, "message": "Message sent to Slack"}
    return {"success": False, "message": "Failed to send. Check SLACK_WEBHOOK_URL in .env"}


def send_slack_daily_summary() -> dict:
    """Push daily summary to Slack."""
    summary = get_daily_summary()
    if not summary["success"]:
        return {"success": False, "message": "Could not fetch daily summary"}

    d = summary["daily_summary"]
    todos = d["todos"]
    reminders = d["upcoming_reminders"]
    notes = d["recent_notes"]

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"Daily Summary - {datetime.now().strftime('%b %d, %Y')}"}},
        {"type": "divider"},
    ]

    if todos:
        todo_lines = []
        for t in todos[:8]:
            tag = "[overdue]" if t["overdue"] else ("[high]" if t["priority"] == "high" else "-")
            due = f" (due {t['due_date']})" if t["due_date"] != "none" else ""
            todo_lines.append(f"{tag} {t['task']}{due}")
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": f"*Todos ({len(todos)} pending, {d['overdue_todos']} overdue)*\n" + "\n".join(todo_lines)}})
    else:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Todos* All clear!"}})

    blocks.append({"type": "divider"})

    if reminders:
        rem_lines = [f"{r['message']} - {r['remind_at']}" for r in reminders[:5]]
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": "*Upcoming Reminders*\n" + "\n".join(rem_lines)}})
    else:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Reminders* Nothing scheduled"}})

    blocks.append({"type": "divider"})

    if notes:
        note_lines = [f"*{n['title']}*" + (f" - {n['summary'][:80]}" if n['summary'] else "") for n in notes[:3]]
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": "*Recent Notes*\n" + "\n".join(note_lines)}})

    sent = _send_slack("Your Daily Summary", blocks=blocks)
    if sent:
        return {"success": True, "message": "Daily summary sent to Slack"}
    return {"success": False, "message": "Failed to send. Check SLACK_WEBHOOK_URL in .env"}