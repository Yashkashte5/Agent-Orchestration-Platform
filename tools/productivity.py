import sqlite3
import asyncio
import os
import json
import httpx
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from llm.groq_client import generate

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Google OAuth imports
try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import Flow
    from googleapiclient.discovery import build
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False
    print("Google libraries not installed. Run: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")

DB_PATH = "memory.db"
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "google_token.json"

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/gmail.modify",
]


# ─────────────────────────────────────────
# SCHEDULER
# ─────────────────────────────────────────

scheduler = BackgroundScheduler()


def start_scheduler():
    scheduler.start()
    _reload_pending_reminders()


def _reload_pending_reminders():
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
                    _fire_reminder, "date",
                    run_date=remind_at,
                    args=[rid, message],
                    id=f"reminder_{rid}",
                    replace_existing=True,
                )
        except Exception as e:
            print(f"Could not reschedule reminder {rid}: {e}")


# ─────────────────────────────────────────
# SLACK
# ─────────────────────────────────────────

def _send_slack(message: str, blocks: list = None) -> bool:
    if not SLACK_WEBHOOK_URL:
        print(f"SLACK_WEBHOOK_URL not set. Message: {message}")
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


def _fire_reminder(reminder_id: int, message: str):
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
            google_task_id TEXT,
            created_at TEXT
        )
    """)

    # Add google_task_id column if upgrading from old DB
    try:
        cur.execute("ALTER TABLE todos ADD COLUMN google_task_id TEXT")
    except Exception:
        pass

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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            frequency TEXT DEFAULT 'daily',
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS habit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id INTEGER,
            logged_date TEXT,
            created_at TEXT,
            FOREIGN KEY(habit_id) REFERENCES habits(id)
        )
    """)

    conn.commit()
    conn.close()


# ─────────────────────────────────────────
# GOOGLE AUTH
# ─────────────────────────────────────────

def _get_google_creds() -> "Credentials | None":
    """Load and refresh Google credentials from token file."""
    if not GOOGLE_AVAILABLE:
        return None

    creds = None

    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, GOOGLE_SCOPES)
        except Exception:
            pass

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
        except Exception as e:
            print(f"Token refresh failed: {e}")
            return None

    if not creds or not creds.valid:
        return None

    return creds


def get_google_auth_url() -> dict:
    """Generate Google OAuth URL for the user to visit."""
    if not GOOGLE_AVAILABLE:
        return {"success": False, "message": "Google libraries not installed"}

    if not os.path.exists(CREDENTIALS_FILE):
        return {"success": False, "message": "credentials.json not found in project root"}

    try:
        flow = Flow.from_client_secrets_file(
            CREDENTIALS_FILE,
            scopes=GOOGLE_SCOPES,
            redirect_uri=GOOGLE_REDIRECT_URI,
        )
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        return {"success": True, "auth_url": auth_url, "message": f"Visit this URL to connect Google: {auth_url}"}
    except Exception as e:
        return {"success": False, "message": str(e)}


def complete_google_auth(code: str) -> dict:
    """Exchange auth code for token and save it."""
    if not GOOGLE_AVAILABLE:
        return {"success": False, "message": "Google libraries not installed"}

    try:
        flow = Flow.from_client_secrets_file(
            CREDENTIALS_FILE,
            scopes=GOOGLE_SCOPES,
            redirect_uri=GOOGLE_REDIRECT_URI,
        )
        flow.fetch_token(code=code)
        creds = flow.credentials
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        return {"success": True, "message": "Google account connected successfully"}
    except Exception as e:
        return {"success": False, "message": str(e)}


def google_auth_status() -> dict:
    """Check if Google is connected."""
    creds = _get_google_creds()
    if creds and creds.valid:
        return {"success": True, "connected": True, "message": "Google is connected"}
    return {"success": True, "connected": False, "message": "Google not connected. Ask me to connect Google to get started."}


# ─────────────────────────────────────────
# GOOGLE TASKS HELPERS
# ─────────────────────────────────────────

def _get_tasks_service():
    creds = _get_google_creds()
    if not creds:
        return None
    return build("tasks", "v1", credentials=creds)


def _get_default_tasklist_id(service) -> str:
    """Get the ID of the default Google Tasks list."""
    try:
        result = service.tasklists().list().execute()
        lists = result.get("items", [])
        if lists:
            return lists[0]["id"]
    except Exception:
        pass
    return "@default"


def _create_google_task(task: str, due_date: str = "") -> str | None:
    """Create a task in Google Tasks, return the task ID."""
    service = _get_tasks_service()
    if not service:
        return None
    try:
        tasklist_id = _get_default_tasklist_id(service)
        body = {"title": task}
        if due_date:
            try:
                dt = datetime.fromisoformat(due_date)
                body["due"] = dt.strftime("%Y-%m-%dT00:00:00.000Z")
            except Exception:
                pass
        result = service.tasks().insert(tasklist=tasklist_id, body=body).execute()
        return result.get("id")
    except Exception as e:
        print(f"Google Tasks create failed: {e}")
        return None


def _complete_google_task(google_task_id: str) -> bool:
    """Mark a Google Task as complete."""
    service = _get_tasks_service()
    if not service:
        return False
    try:
        task = service.tasks().get(tasklist="@default", task=google_task_id).execute()
        task["status"] = "completed"
        task["completed"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
        service.tasks().update(tasklist="@default", task=google_task_id, body=task).execute()
        return True
    except Exception as e:
        print(f"Google Tasks complete failed: {e}")
        return False


def _delete_google_task(google_task_id: str) -> bool:
    """Delete a Google Task."""
    service = _get_tasks_service()
    if not service:
        return False
    try:
        service.tasks().delete(tasklist="@default", task=google_task_id).execute()
        return True
    except Exception as e:
        print(f"Google Tasks delete failed: {e}")
        return False


# ─────────────────────────────────────────
# TODOS (with Google Tasks two-way sync)
# ─────────────────────────────────────────

PRIORITY_ORDER = {"high": 0, "normal": 1, "low": 2}


def add_todo(task: str, priority: str = "normal", due_date: str = "") -> dict:
    """Add a todo and sync to Google Tasks if connected."""
    # Try Google Tasks sync
    google_task_id = _create_google_task(task, due_date)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO todos (task, priority, due_date, google_task_id, created_at) VALUES (?, ?, ?, ?, ?)",
        (task, priority, due_date or None, google_task_id, datetime.utcnow().isoformat()),
    )
    conn.commit()
    todo_id = cur.lastrowid
    conn.close()

    msg = f"Todo added: '{task}' | priority: {priority}"
    if due_date:
        msg += f" | due: {due_date}"
    if google_task_id:
        msg += " | synced to Google Tasks"

    return {"success": True, "message": msg, "id": todo_id, "google_synced": bool(google_task_id)}


def bulk_add_todos(tasks: list) -> dict:
    """Add multiple todos at once, each synced to Google Tasks."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    added = []

    for item in tasks:
        if isinstance(item, str):
            task, priority, due_date = item, "normal", ""
        else:
            task = item.get("task", "")
            priority = item.get("priority", "normal")
            due_date = item.get("due_date", "") or ""

        if not task:
            continue

        google_task_id = _create_google_task(task, due_date)
        cur.execute(
            "INSERT INTO todos (task, priority, due_date, google_task_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (task, priority, due_date or None, google_task_id, datetime.utcnow().isoformat()),
        )
        added.append({"id": cur.lastrowid, "task": task, "priority": priority, "google_synced": bool(google_task_id)})

    conn.commit()
    conn.close()

    synced = sum(1 for t in added if t["google_synced"])
    msg = f"Added {len(added)} todos"
    if synced:
        msg += f" ({synced} synced to Google Tasks)"

    return {"success": True, "message": msg, "todos": added}


def list_todos() -> dict:
    """List all pending todos sorted by priority then due date."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, task, priority, due_date, google_task_id, created_at FROM todos WHERE done=0")
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return {"success": True, "todos": [], "message": "No pending todos"}

    now = datetime.utcnow().date()
    todos = []
    for r in rows:
        tid, task, priority, due_date, google_task_id, created_at = r
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
            "google_task_id": google_task_id,
            "created_at": created_at,
        })

    todos.sort(key=lambda x: (
        PRIORITY_ORDER.get(x["priority"], 1),
        x["due_date"] if x["due_date"] != "none" else "9999",
    ))

    overdue_count = sum(1 for t in todos if t["overdue"])
    return {"success": True, "todos": todos, "overdue_count": overdue_count}


def complete_todo(todo_id: int) -> dict:
    """Mark todo complete and sync to Google Tasks."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT google_task_id FROM todos WHERE id=?", (todo_id,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return {"success": False, "message": f"No todo found with id {todo_id}"}

    google_task_id = row[0]
    cur.execute("UPDATE todos SET done=1 WHERE id=?", (todo_id,))
    conn.commit()
    conn.close()

    google_synced = False
    if google_task_id:
        google_synced = _complete_google_task(google_task_id)

    msg = f"Todo {todo_id} marked complete"
    if google_synced:
        msg += " (synced to Google Tasks)"

    return {"success": True, "message": msg, "google_synced": google_synced}


def bulk_complete_todos(todo_ids: list) -> dict:
    """Mark multiple todos complete and sync to Google Tasks."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    google_synced = 0
    for tid in todo_ids:
        cur.execute("SELECT google_task_id FROM todos WHERE id=?", (tid,))
        row = cur.fetchone()
        if row and row[0]:
            if _complete_google_task(row[0]):
                google_synced += 1
        cur.execute("UPDATE todos SET done=1 WHERE id=?", (tid,))

    conn.commit()
    conn.close()

    msg = f"Completed {len(todo_ids)} todos"
    if google_synced:
        msg += f" ({google_synced} synced to Google Tasks)"

    return {"success": True, "message": msg}


def delete_todo(todo_id: int) -> dict:
    """Delete todo and remove from Google Tasks."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT google_task_id FROM todos WHERE id=?", (todo_id,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return {"success": False, "message": f"No todo found with id {todo_id}"}

    google_task_id = row[0]
    cur.execute("DELETE FROM todos WHERE id=?", (todo_id,))
    conn.commit()
    conn.close()

    google_synced = False
    if google_task_id:
        google_synced = _delete_google_task(google_task_id)

    msg = f"Todo {todo_id} deleted"
    if google_synced:
        msg += " (removed from Google Tasks)"

    return {"success": True, "message": msg}


# ─────────────────────────────────────────
# NOTES
# ─────────────────────────────────────────

async def add_note(title: str, body: str, tags: str = "") -> dict:
    """Save a note. Auto-summarizes if body is long."""
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
        {"id": r[0], "title": r[1], "body": r[2], "summary": r[3] or "", "tags": r[4] or "", "created_at": r[5]}
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
    return {"success": True, "message": f"Note updated"}


def delete_note(note_id: int) -> dict:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM notes WHERE id=?", (note_id,))
    conn.commit()
    affected = cur.rowcount
    conn.close()
    if affected == 0:
        return {"success": False, "message": f"No note found with id {note_id}"}
    return {"success": True, "message": "Note deleted"}


# ─────────────────────────────────────────
# REMINDERS
# ─────────────────────────────────────────

def set_reminder(message: str, remind_at: str, recurrence: str = "none") -> dict:
    """Set a reminder. remind_at: YYYY-MM-DD HH:MM. recurrence: none | daily | weekly"""
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
        _fire_reminder, "date",
        run_date=remind_dt,
        args=[reminder_id, message],
        id=f"reminder_{reminder_id}",
        replace_existing=True,
    )

    result = {"success": True, "message": f"Reminder set for {remind_at}", "id": reminder_id}
    if recurrence != "none":
        result["recurrence"] = recurrence
    return result


def list_reminders() -> dict:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, message, remind_at, recurrence FROM reminders WHERE done=0 ORDER BY remind_at ASC")
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return {"success": True, "reminders": [], "message": "No upcoming reminders"}

    return {"success": True, "reminders": [
        {"id": r[0], "message": r[1], "remind_at": r[2], "recurrence": r[3]}
        for r in rows
    ]}


def snooze_reminder(reminder_id: int, minutes: int = 15) -> dict:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT message, remind_at FROM reminders WHERE id=?", (reminder_id,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return {"success": False, "message": f"No reminder found with id {reminder_id}"}

    message, remind_at_str = row
    new_time = datetime.fromisoformat(remind_at_str) + timedelta(minutes=minutes)
    cur.execute("UPDATE reminders SET remind_at=? WHERE id=?", (new_time.isoformat(), reminder_id))
    conn.commit()
    conn.close()

    job_id = f"reminder_{reminder_id}"
    if scheduler.get_job(job_id):
        scheduler.reschedule_job(job_id, trigger="date", run_date=new_time)
    else:
        scheduler.add_job(_fire_reminder, "date", run_date=new_time,
            args=[reminder_id, message], id=job_id, replace_existing=True)

    return {"success": True, "message": f"Snoozed to {new_time.strftime('%Y-%m-%d %H:%M')}"}


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
    return {"success": True, "message": "Reminder deleted"}


# ─────────────────────────────────────────
# HABITS
# ─────────────────────────────────────────

def add_habit(name: str, frequency: str = "daily") -> dict:
    """Track a new habit. frequency: daily | weekly"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO habits (name, frequency, created_at) VALUES (?, ?, ?)",
        (name, frequency, datetime.utcnow().isoformat()),
    )
    conn.commit()
    habit_id = cur.lastrowid
    conn.close()
    return {"success": True, "message": f"Now tracking habit: '{name}' ({frequency})", "id": habit_id}


def log_habit(habit_id: int) -> dict:
    """Mark a habit as done for today."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT name FROM habits WHERE id=?", (habit_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return {"success": False, "message": f"No habit found with id {habit_id}"}

    name = row[0]
    today = datetime.utcnow().date().isoformat()

    # Check if already logged today
    cur.execute("SELECT id FROM habit_logs WHERE habit_id=? AND logged_date=?", (habit_id, today))
    if cur.fetchone():
        conn.close()
        return {"success": True, "message": f"'{name}' already logged for today"}

    cur.execute(
        "INSERT INTO habit_logs (habit_id, logged_date, created_at) VALUES (?, ?, ?)",
        (habit_id, today, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    return {"success": True, "message": f"Logged '{name}' for today"}


def get_habits() -> dict:
    """Show all habits with streaks and recent completion."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, name, frequency, created_at FROM habits")
    habits = cur.fetchall()

    if not habits:
        conn.close()
        return {"success": True, "habits": [], "message": "No habits tracked yet"}

    result = []
    today = datetime.utcnow().date()

    for h in habits:
        hid, name, frequency, created_at = h

        # Get last 30 logs
        cur.execute(
            "SELECT logged_date FROM habit_logs WHERE habit_id=? ORDER BY logged_date DESC LIMIT 30",
            (hid,)
        )
        logs = [row[0] for row in cur.fetchall()]
        log_dates = set(logs)

        # Calculate streak
        streak = 0
        check_date = today
        while check_date.isoformat() in log_dates:
            streak += 1
            check_date = check_date - timedelta(days=1)

        done_today = today.isoformat() in log_dates

        result.append({
            "id": hid,
            "name": name,
            "frequency": frequency,
            "streak": streak,
            "done_today": done_today,
            "total_logs": len(logs),
        })

    conn.close()
    return {"success": True, "habits": result}


def delete_habit(habit_id: int) -> dict:
    """Remove a habit from tracking."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM habit_logs WHERE habit_id=?", (habit_id,))
    cur.execute("DELETE FROM habits WHERE id=?", (habit_id,))
    conn.commit()
    affected = cur.rowcount
    conn.close()
    if affected == 0:
        return {"success": False, "message": f"No habit found with id {habit_id}"}
    return {"success": True, "message": "Habit removed"}


# ─────────────────────────────────────────
# GOOGLE CALENDAR
# ─────────────────────────────────────────

def _get_calendar_service():
    creds = _get_google_creds()
    if not creds:
        return None
    return build("calendar", "v3", credentials=creds)


def list_events(days_ahead: int = 7) -> dict:
    """List upcoming Google Calendar events."""
    service = _get_calendar_service()
    if not service:
        return {"success": False, "message": "Google not connected. Say 'connect Google' to get started."}

    try:
        now = datetime.utcnow().isoformat() + "Z"
        end = (datetime.utcnow() + timedelta(days=days_ahead)).isoformat() + "Z"

        result = service.events().list(
            calendarId="primary",
            timeMin=now,
            timeMax=end,
            singleEvents=True,
            orderBy="startTime",
            maxResults=20,
        ).execute()

        events = result.get("items", [])
        if not events:
            return {"success": True, "events": [], "message": f"No events in the next {days_ahead} days"}

        formatted = []
        for e in events:
            start = e["start"].get("dateTime", e["start"].get("date", ""))
            end_time = e["end"].get("dateTime", e["end"].get("date", ""))
            formatted.append({
                "id": e["id"],
                "title": e.get("summary", "Untitled"),
                "start": start,
                "end": end_time,
                "location": e.get("location", ""),
                "description": e.get("description", ""),
            })

        return {"success": True, "events": formatted}
    except Exception as e:
        return {"success": False, "message": f"Calendar error: {str(e)}"}


def create_event(title: str, date: str, time: str = "09:00", duration_minutes: int = 60, description: str = "") -> dict:
    """Create a Google Calendar event. date: YYYY-MM-DD, time: HH:MM"""
    service = _get_calendar_service()
    if not service:
        return {"success": False, "message": "Google not connected. Say 'connect Google' to get started."}

    try:
        start_dt = datetime.fromisoformat(f"{date}T{time}:00")
        end_dt = start_dt + timedelta(minutes=duration_minutes)

        event = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": "UTC"},
        }

        result = service.events().insert(calendarId="primary", body=event).execute()
        return {
            "success": True,
            "message": f"Event created: '{title}' on {date} at {time}",
            "event_id": result.get("id"),
            "link": result.get("htmlLink", ""),
        }
    except Exception as e:
        return {"success": False, "message": f"Calendar error: {str(e)}"}


def delete_event(event_id: str) -> dict:
    """Delete a Google Calendar event by ID."""
    service = _get_calendar_service()
    if not service:
        return {"success": False, "message": "Google not connected"}

    try:
        service.events().delete(calendarId="primary", eventId=event_id).execute()
        return {"success": True, "message": "Event deleted"}
    except Exception as e:
        return {"success": False, "message": f"Calendar error: {str(e)}"}


def update_event(event_id: str, title: str = "", date: str = "", time: str = "", duration_minutes: int = 0) -> dict:
    """Update an existing Google Calendar event."""
    service = _get_calendar_service()
    if not service:
        return {"success": False, "message": "Google not connected"}

    try:
        event = service.events().get(calendarId="primary", eventId=event_id).execute()

        if title:
            event["summary"] = title
        if date and time:
            start_dt = datetime.fromisoformat(f"{date}T{time}:00")
            mins = duration_minutes or 60
            end_dt = start_dt + timedelta(minutes=mins)
            event["start"] = {"dateTime": start_dt.isoformat(), "timeZone": "UTC"}
            event["end"] = {"dateTime": end_dt.isoformat(), "timeZone": "UTC"}

        result = service.events().update(calendarId="primary", eventId=event_id, body=event).execute()
        return {"success": True, "message": f"Event updated: '{result.get('summary')}'"}
    except Exception as e:
        return {"success": False, "message": f"Calendar error: {str(e)}"}


# ─────────────────────────────────────────
# GMAIL
# ─────────────────────────────────────────

def _get_gmail_service():
    creds = _get_google_creds()
    if not creds:
        return None
    return build("gmail", "v1", credentials=creds)


def get_unread_emails(max_results: int = 5) -> dict:
    """Get unread emails from Gmail inbox."""
    service = _get_gmail_service()
    if not service:
        return {"success": False, "message": "Google not connected. Say 'connect Google' to get started."}

    try:
        result = service.users().messages().list(
            userId="me",
            labelIds=["INBOX", "UNREAD"],
            maxResults=max_results,
        ).execute()

        messages = result.get("messages", [])
        if not messages:
            return {"success": True, "emails": [], "message": "No unread emails"}

        emails = []
        for msg in messages:
            full = service.users().messages().get(userId="me", id=msg["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"]).execute()

            headers = {h["name"]: h["value"] for h in full["payload"]["headers"]}
            snippet = full.get("snippet", "")

            emails.append({
                "id": msg["id"],
                "from": headers.get("From", ""),
                "subject": headers.get("Subject", ""),
                "date": headers.get("Date", ""),
                "snippet": snippet[:150],
            })

        return {"success": True, "emails": emails, "count": len(emails)}
    except Exception as e:
        return {"success": False, "message": f"Gmail error: {str(e)}"}


def send_email(to: str, subject: str, body: str) -> dict:
    """Send an email via Gmail."""
    service = _get_gmail_service()
    if not service:
        return {"success": False, "message": "Google not connected. Say 'connect Google' to get started."}

    try:
        import base64
        from email.mime.text import MIMEText

        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        result = service.users().messages().send(userId="me", body={"raw": raw}).execute()

        return {"success": True, "message": f"Email sent to {to}", "message_id": result.get("id")}
    except Exception as e:
        return {"success": False, "message": f"Gmail error: {str(e)}"}


def get_email_summary() -> dict:
    """Get a summary of unread emails — count, senders, subjects."""
    result = get_unread_emails(max_results=10)
    if not result["success"]:
        return result

    emails = result.get("emails", [])
    if not emails:
        return {"success": True, "message": "Inbox is clear — no unread emails"}

    lines = [f"- {e['from'].split('<')[0].strip()}: {e['subject']}" for e in emails]
    return {
        "success": True,
        "message": f"You have {len(emails)} unread emails",
        "emails": emails,
        "summary": "\n".join(lines),
    }


# ─────────────────────────────────────────
# CROSS-TOOL
# ─────────────────────────────────────────

def get_daily_summary() -> dict:
    """Full picture: todos, reminders, notes, habits, calendar events."""
    todos_result = list_todos()
    reminders_result = list_reminders()
    habits_result = get_habits()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, title, summary, tags, created_at FROM notes ORDER BY id DESC LIMIT 5")
    note_rows = cur.fetchall()
    conn.close()

    recent_notes = [
        {"id": r[0], "title": r[1], "summary": r[2] or "", "tags": r[3] or "", "created_at": r[4]}
        for r in note_rows
    ]

    todos = todos_result.get("todos", [])
    overdue = [t for t in todos if t.get("overdue")]

    # Try to get today's calendar events
    calendar_events = []
    cal_result = list_events(days_ahead=1)
    if cal_result.get("success"):
        calendar_events = cal_result.get("events", [])

    # Habits not done today
    habits = habits_result.get("habits", [])
    pending_habits = [h for h in habits if not h.get("done_today")]

    return {
        "success": True,
        "daily_summary": {
            "pending_todos": len(todos),
            "overdue_todos": len(overdue),
            "todos": todos,
            "upcoming_reminders": reminders_result.get("reminders", []),
            "recent_notes": recent_notes,
            "calendar_events": calendar_events,
            "pending_habits": pending_habits,
        }
    }


def get_priority_inbox() -> dict:
    """What should I work on right now? Ranks by overdue > high priority > due today."""
    todos = list_todos().get("todos", [])
    if not todos:
        return {"success": True, "message": "Nothing on your plate — all clear!"}

    today = datetime.utcnow().date().isoformat()

    def score(t):
        s = 0
        if t["overdue"]: s += 100
        if t["priority"] == "high": s += 50
        if t["due_date"] == today: s += 30
        if t["priority"] == "normal": s += 10
        return s

    ranked = sorted(todos, key=score, reverse=True)[:5]
    return {"success": True, "priority_inbox": ranked, "message": f"Top {len(ranked)} things to focus on"}


def get_weekly_review() -> dict:
    """Summary of the week — completed todos, notes created, habits logged."""
    week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT task, priority FROM todos WHERE done=1 AND created_at >= ?", (week_ago,))
    completed_todos = [{"task": r[0], "priority": r[1]} for r in cur.fetchall()]

    cur.execute("SELECT title, created_at FROM notes WHERE created_at >= ?", (week_ago,))
    new_notes = [{"title": r[0], "created_at": r[1]} for r in cur.fetchall()]

    cur.execute("""
        SELECT h.name, COUNT(hl.id) as logs
        FROM habits h
        LEFT JOIN habit_logs hl ON h.id = hl.habit_id AND hl.logged_date >= ?
        GROUP BY h.id
    """, (week_ago[:10],))
    habit_summary = [{"habit": r[0], "logs_this_week": r[1]} for r in cur.fetchall()]

    conn.close()

    return {
        "success": True,
        "weekly_review": {
            "completed_todos": completed_todos,
            "completed_count": len(completed_todos),
            "new_notes": new_notes,
            "habit_summary": habit_summary,
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
    events = d["calendar_events"]
    pending_habits = d["pending_habits"]

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

    if events:
        event_lines = [f"{e['title']} - {e['start']}" for e in events[:5]]
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": "*Today's Calendar*\n" + "\n".join(event_lines)}})
        blocks.append({"type": "divider"})

    if reminders:
        rem_lines = [f"{r['message']} - {r['remind_at']}" for r in reminders[:5]]
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": "*Upcoming Reminders*\n" + "\n".join(rem_lines)}})
    else:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Reminders* Nothing scheduled"}})

    blocks.append({"type": "divider"})

    if pending_habits:
        habit_lines = [f"- {h['name']} (streak: {h['streak']})" for h in pending_habits]
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": "*Habits to complete today*\n" + "\n".join(habit_lines)}})

    if notes:
        note_lines = [f"*{n['title']}*" + (f" - {n['summary'][:80]}" if n['summary'] else "") for n in notes[:3]]
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": "*Recent Notes*\n" + "\n".join(note_lines)}})

    sent = _send_slack("Your Daily Summary", blocks=blocks)
    if sent:
        return {"success": True, "message": "Daily summary sent to Slack"}
    return {"success": False, "message": "Failed to send. Check SLACK_WEBHOOK_URL in .env"}