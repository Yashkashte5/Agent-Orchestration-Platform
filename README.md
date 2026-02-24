# Agent Orchestration Platform

A stateful, tool-orchestrated AI assistant platform built with FastAPI, SQLite, and a React frontend.

This project focuses on an agent runtime that can plan tool calls, execute actions, and persist context across sessions.

## V1 Scope

- Agent orchestration loop with JSON action planning (`tool` or `chat`)
- Persistent memory (chat history, summaries, sessions)
- Tool registry for modular tool execution
- Productivity tools (todos, notes, reminders)
- Habits tracking
- Google integrations (OAuth, Calendar, Tasks sync, Gmail)
- Slack notifications and daily summary delivery

## Architecture

- `agent/orchestrator.py`: Core agent loop and tool-call decision flow
- `tools/registry.py`: Tool registration and execution layer
- `tools/productivity.py`: Productivity, habits, Google, Gmail, Calendar, Slack tools
- `memory.py`: SQLite persistence for sessions/history/summaries
- `api/routes.py`: Chat/session and tool-facing API routes
- `main.py`: FastAPI app bootstrap, tool registration, OAuth routes, static hosting
- `llm/groq_client.py`: Groq Chat Completions client
- `frontend/`: React + Vite UI
- `static/`: Built frontend assets served by FastAPI

## Tech Stack

- Backend: Python, FastAPI, Pydantic
- Agent runtime: custom orchestration loop + tool registry
- LLM provider: Groq API (`llama-3.3-70b-versatile` by default)
- Storage: SQLite (`memory.db`)
- Scheduler: APScheduler
- HTTP client: httpx
- Frontend: React + Vite
- Integrations: Google OAuth/Calendar/Tasks/Gmail, Slack Webhook

## Prerequisites

- Python 3.10+
- Node.js 18+
- A Groq API key
- Optional: Google Cloud OAuth client credentials
- Optional: Slack incoming webhook URL

## Setup

1. Clone and enter the repo.

```bash
git clone https://github.com/Yashkashte5/Agent-Orchestration-Platform.git
cd Agent-Orchestration-Platform
```

2. Create and activate a Python virtual environment.
3. Install dependencies.

```bash
pip install -r requirements.txt
```

4. Configure environment variables.
5. Build frontend assets.

```bash
cd frontend
npm install
npm run build
cd ..
```

6. Run the server.

```bash
uvicorn main:app --reload
```

7. Open `http://localhost:8000`.

## Environment Variables

Create `.env` in project root:

```env
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=llama-3.3-70b-versatile

SLACK_WEBHOOK_URL=

GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback
```

## Google OAuth Setup

1. Create OAuth credentials in Google Cloud Console.
2. Enable APIs: Calendar API, Tasks API, Gmail API.
3. Put your OAuth client JSON in project root as `credentials.json`.
4. Start server and click **Connect Google** in the sidebar, or visit `/auth/google`.

Notes:
- `google_token.json` is generated after successful auth.
- Do not commit `credentials.json` or `google_token.json`.

## Core Endpoints

- `POST /agent/run`: Run agent on a prompt
- `POST /name-chat`: Generate chat title
- `GET /chats`: List chats
- `POST /chats`: Create chat
- `DELETE /chats/{session_id}`: Delete chat
- `PUT /chats/{session_id}/rename`: Rename chat
- `GET /chats/{session_id}/history`: Chat history
- `GET /tools`: List registered tools
- `GET /auth/google`: Start Google OAuth
- `GET /auth/google/callback`: OAuth callback
- `GET /auth/status`: Google auth status
- `GET /health`: Health check

## Example Prompts

- `Add a high priority todo: Finish backend tests due 2026-02-26`
- `Add 3 todos: review PR, write release notes, update docs`
- `Set a reminder for 2026-02-25 09:30 to join standup`
- `Show my daily summary`
- `What should I focus on right now?`
- `Create a calendar event tomorrow at 11:00 called API Review`
- `Show unread emails`
- `Log habit 1`

## Project Status

Current release: `v1.0.0` (see `CHANGELOG.md`).

This v1 is platform-first: orchestration + memory core, with productivity and Google integrations as the first tool domain.

## Security Notes

- Keep `.env`, `credentials.json`, and `google_token.json` out of version control.
- Rotate tokens/keys immediately if committed by mistake.

## License

Add your preferred license in a `LICENSE` file.
