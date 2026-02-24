from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.requests import Request
from api.routes import router
from memory import init_db
from tools.registry import registry
from tools.summarizer import summarize_text
from tools.productivity import (
    init_productivity_db, start_scheduler,
    # Todos
    add_todo, bulk_add_todos, list_todos, complete_todo,
    bulk_complete_todos, delete_todo,
    # Notes
    add_note, get_notes, update_note, delete_note,
    # Reminders
    set_reminder, list_reminders, snooze_reminder, delete_reminder,
    # Habits
    add_habit, log_habit, get_habits, delete_habit,
    # Google Auth
    get_google_auth_url, complete_google_auth, google_auth_status,
    # Google Calendar
    list_events, create_event, delete_event, update_event,
    # Gmail
    get_unread_emails, send_email, get_email_summary,
    # Cross-tool
    get_daily_summary, get_priority_inbox, get_weekly_review, clear_completed,
    # Slack
    send_slack_message, send_slack_daily_summary,
)
import os

app = FastAPI(title="Agent Orchestration Platform")

init_db()
init_productivity_db()
start_scheduler()

# ── Summarization ──────────────────────────────────────
registry.register(
    name="summarize_text",
    description="Summarizes a long piece of text concisely",
    func=summarize_text,
    schema={"text": "string"},
)

# ── Todos ──────────────────────────────────────────────
registry.register(
    name="add_todo",
    description="Add a single todo. Automatically syncs to Google Tasks if connected.",
    func=add_todo,
    schema={"task": "string", "priority": "string low/normal/high (optional)", "due_date": "string YYYY-MM-DD (optional)"},
)
registry.register(
    name="bulk_add_todos",
    description="Add multiple todos at once. Use when user lists 2 or more tasks. Each syncs to Google Tasks if connected.",
    func=bulk_add_todos,
    schema={"tasks": "list of strings or objects with task/priority/due_date"},
)
registry.register(
    name="list_todos",
    description="List all pending todos sorted by priority and due date. Flags overdue items.",
    func=list_todos,
    schema={},
)
registry.register(
    name="complete_todo",
    description="Mark a single todo as complete. Syncs to Google Tasks if connected.",
    func=complete_todo,
    schema={"todo_id": "integer"},
)
registry.register(
    name="bulk_complete_todos",
    description="Mark multiple todos complete at once. Syncs to Google Tasks if connected.",
    func=bulk_complete_todos,
    schema={"todo_ids": "list of integers"},
)
registry.register(
    name="delete_todo",
    description="Delete a todo. Also removes from Google Tasks if connected.",
    func=delete_todo,
    schema={"todo_id": "integer"},
)

# ── Notes ──────────────────────────────────────────────
registry.register(
    name="add_note",
    description="Save a note with title, body, optional tags. Auto-summarizes long notes.",
    func=add_note,
    schema={"title": "string", "body": "string", "tags": "string comma separated (optional)"},
)
registry.register(
    name="get_notes",
    description="Retrieve notes. Optionally filter by keyword or tag.",
    func=get_notes,
    schema={"keyword": "string (optional)", "tag": "string (optional)"},
)
registry.register(
    name="update_note",
    description="Update an existing note's title or body by its ID.",
    func=update_note,
    schema={"note_id": "integer", "title": "string (optional)", "body": "string (optional)"},
)
registry.register(
    name="delete_note",
    description="Delete a note by its ID.",
    func=delete_note,
    schema={"note_id": "integer"},
)

# ── Reminders ──────────────────────────────────────────
registry.register(
    name="set_reminder",
    description="Set a reminder that fires at the given time with optional Slack notification. remind_at: YYYY-MM-DD HH:MM. recurrence: none | daily | weekly",
    func=set_reminder,
    schema={"message": "string", "remind_at": "string YYYY-MM-DD HH:MM", "recurrence": "string (optional)"},
)
registry.register(
    name="list_reminders",
    description="List all upcoming reminders.",
    func=list_reminders,
    schema={},
)
registry.register(
    name="snooze_reminder",
    description="Push a reminder forward by X minutes.",
    func=snooze_reminder,
    schema={"reminder_id": "integer", "minutes": "integer (optional, default 15)"},
)
registry.register(
    name="delete_reminder",
    description="Delete a reminder by its ID.",
    func=delete_reminder,
    schema={"reminder_id": "integer"},
)

# ── Habits ──────────────────────────────────────────────
registry.register(
    name="add_habit",
    description="Start tracking a new habit. frequency: daily | weekly",
    func=add_habit,
    schema={"name": "string", "frequency": "string daily/weekly (optional, default daily)"},
)
registry.register(
    name="log_habit",
    description="Mark a habit as done for today by its ID.",
    func=log_habit,
    schema={"habit_id": "integer"},
)
registry.register(
    name="get_habits",
    description="Show all tracked habits with current streaks and today's completion status.",
    func=get_habits,
    schema={},
)
registry.register(
    name="delete_habit",
    description="Stop tracking a habit by its ID.",
    func=delete_habit,
    schema={"habit_id": "integer"},
)

# ── Google Auth ────────────────────────────────────────
registry.register(
    name="get_google_auth_url",
    description="Get the Google OAuth URL so the user can connect their Google account. Use when user says 'connect Google' or Google tools fail.",
    func=get_google_auth_url,
    schema={},
)
registry.register(
    name="google_auth_status",
    description="Check if Google account is connected.",
    func=google_auth_status,
    schema={},
)

# ── Google Calendar ────────────────────────────────────
registry.register(
    name="list_events",
    description="List upcoming Google Calendar events. days_ahead: how many days to look ahead (default 7).",
    func=list_events,
    schema={"days_ahead": "integer (optional, default 7)"},
)
registry.register(
    name="create_event",
    description="Create a Google Calendar event. date: YYYY-MM-DD, time: HH:MM, duration_minutes: optional.",
    func=create_event,
    schema={"title": "string", "date": "string YYYY-MM-DD", "time": "string HH:MM (optional)", "duration_minutes": "integer (optional)", "description": "string (optional)"},
)
registry.register(
    name="delete_event",
    description="Delete a Google Calendar event by its ID.",
    func=delete_event,
    schema={"event_id": "string"},
)
registry.register(
    name="update_event",
    description="Update a Google Calendar event's title, date, or time.",
    func=update_event,
    schema={"event_id": "string", "title": "string (optional)", "date": "string YYYY-MM-DD (optional)", "time": "string HH:MM (optional)", "duration_minutes": "integer (optional)"},
)

# ── Gmail ──────────────────────────────────────────────
registry.register(
    name="get_unread_emails",
    description="Get unread emails from Gmail inbox.",
    func=get_unread_emails,
    schema={"max_results": "integer (optional, default 5)"},
)
registry.register(
    name="get_email_summary",
    description="Get a quick summary of unread emails — who they're from and subjects.",
    func=get_email_summary,
    schema={},
)
registry.register(
    name="send_email",
    description="Send an email via Gmail.",
    func=send_email,
    schema={"to": "string email address", "subject": "string", "body": "string"},
)

# ── Cross-tool ─────────────────────────────────────────
registry.register(
    name="get_daily_summary",
    description="Full picture of the day: todos, reminders, calendar events, habits, recent notes. Use when user asks what's on their plate or what they have today.",
    func=get_daily_summary,
    schema={},
)
registry.register(
    name="get_priority_inbox",
    description="What should I focus on right now? Returns top 5 items ranked by urgency, overdue status, and priority.",
    func=get_priority_inbox,
    schema={},
)
registry.register(
    name="get_weekly_review",
    description="Summary of the past 7 days: completed todos, notes created, habits tracked.",
    func=get_weekly_review,
    schema={},
)
registry.register(
    name="clear_completed",
    description="Clean up by deleting all completed todos and fired reminders.",
    func=clear_completed,
    schema={},
)

# ── Slack ──────────────────────────────────────────────
registry.register(
    name="send_slack_message",
    description="Send a custom message to Slack.",
    func=send_slack_message,
    schema={"message": "string"},
)
registry.register(
    name="send_slack_daily_summary",
    description="Push the full daily summary including calendar events and habits to Slack.",
    func=send_slack_daily_summary,
    schema={},
)

app.include_router(router)


# ── Google OAuth Routes ────────────────────────────────
@app.get("/auth/google")
async def google_auth():
    result = get_google_auth_url()
    if result["success"]:
        return RedirectResponse(url=result["auth_url"])
    return {"error": result["message"]}


@app.get("/auth/google/callback")
async def google_callback(request: Request):
    code = request.query_params.get("code")
    if not code:
        return {"error": "No code provided"}
    result = complete_google_auth(code)
    if result["success"]:
        return RedirectResponse(url="/?google=connected")
    return {"error": result["message"]}


@app.get("/auth/status")
async def auth_status():
    return google_auth_status()


@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Serve React Frontend ───────────────────────────────
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="assets")

    @app.get("/")
    async def serve_frontend():
        return FileResponse(os.path.join(static_dir, "index.html"))

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        return FileResponse(os.path.join(static_dir, "index.html"))