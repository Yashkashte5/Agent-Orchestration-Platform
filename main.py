from fastapi import FastAPI
from api.routes import router
from memory import init_db
from tools.registry import registry
from tools.summarizer import summarize_text
from tools.productivity import (
    init_productivity_db, start_scheduler,
    add_todo, list_todos, complete_todo, bulk_complete_todos, delete_todo,
    add_note, get_notes, update_note, delete_note,
    set_reminder, list_reminders, snooze_reminder, delete_reminder,
    get_daily_summary, clear_completed,
    send_slack_message, send_slack_daily_summary,
)

app = FastAPI(title="AI Agent Platform")

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
    description="Add a new todo task with optional priority (low/normal/high) and due date (YYYY-MM-DD)",
    func=add_todo,
    schema={"task": "string", "priority": "string (optional)", "due_date": "string YYYY-MM-DD (optional)"},
)
registry.register(
    name="list_todos",
    description="List all pending todos sorted by priority and due date. Flags overdue items.",
    func=list_todos,
    schema={},
)
registry.register(
    name="complete_todo",
    description="Mark a single todo as complete by its ID",
    func=complete_todo,
    schema={"todo_id": "integer"},
)
registry.register(
    name="bulk_complete_todos",
    description="Mark multiple todos complete at once by providing a list of IDs",
    func=bulk_complete_todos,
    schema={"todo_ids": "list of integers"},
)
registry.register(
    name="delete_todo",
    description="Delete a todo by its ID",
    func=delete_todo,
    schema={"todo_id": "integer"},
)

# ── Notes ──────────────────────────────────────────────
registry.register(
    name="add_note",
    description="Save a note with title, body, and optional tags. Auto-summarizes long notes.",
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
    description="Update an existing note's title or body by its ID",
    func=update_note,
    schema={"note_id": "integer", "title": "string (optional)", "body": "string (optional)"},
)
registry.register(
    name="delete_note",
    description="Delete a note by its ID",
    func=delete_note,
    schema={"note_id": "integer"},
)

# ── Reminders ──────────────────────────────────────────
registry.register(
    name="set_reminder",
    description="Set a reminder that actually fires at the given time. remind_at: YYYY-MM-DD HH:MM. recurrence: none | daily | weekly",
    func=set_reminder,
    schema={"message": "string", "remind_at": "string YYYY-MM-DD HH:MM", "recurrence": "string (optional)"},
)
registry.register(
    name="list_reminders",
    description="List all upcoming reminders",
    func=list_reminders,
    schema={},
)
registry.register(
    name="snooze_reminder",
    description="Push a reminder forward by X minutes",
    func=snooze_reminder,
    schema={"reminder_id": "integer", "minutes": "integer (optional, default 15)"},
)
registry.register(
    name="delete_reminder",
    description="Delete a reminder by its ID",
    func=delete_reminder,
    schema={"reminder_id": "integer"},
)

# ── Cross-tool ─────────────────────────────────────────
registry.register(
    name="get_daily_summary",
    description="Get a full picture of your day: pending todos with overdue flags, upcoming reminders, and recent notes. Use when user asks what's on their plate, their day summary, or what they have planned.",
    func=get_daily_summary,
    schema={},
)
registry.register(
    name="clear_completed",
    description="Clean up by deleting all completed todos and fired reminders",
    func=clear_completed,
    schema={},
)

# ── Slack ──────────────────────────────────────────────
registry.register(
    name="send_slack_message",
    description="Send a custom message to the user's Slack. Use when user says 'notify me on Slack', 'send to Slack', or wants to push an important update.",
    func=send_slack_message,
    schema={"message": "string"},
)
registry.register(
    name="send_slack_daily_summary",
    description="Push the full daily summary (todos, reminders, notes) to Slack as a rich formatted message. Use when user asks to send their summary to Slack.",
    func=send_slack_daily_summary,
    schema={},
)

app.include_router(router)

@app.get("/health")
async def health():
    return {"status": "ok"}