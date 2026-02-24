# Changelog

All notable changes to this project are documented in this file.

## [1.0.0] - 2026-02-24

### Added
- Agent orchestration loop with JSON-only action planning (`tool` vs `chat`) and bounded multi-step execution.
- Session-based memory with persistent SQLite chat history, summaries, and chat management.
- Tool registry with dynamic tool registration and runtime execution.
- Productivity toolset: todos, bulk todo operations, notes, reminders, daily summary, and cleanup actions.
- Habit tracking tools: add habit, log habit completion, list habits with streaks, and delete habit.
- Google OAuth support with connect flow and auth status endpoint.
- Google integrations:
  - Google Tasks sync for todo add/complete/delete.
  - Google Calendar tools: list/create/update/delete events.
  - Gmail tools: unread inbox fetch, summary, and send email.
- Slack integrations for custom messages, reminder notifications, and daily summary delivery.
- New cross-tool intelligence endpoints/tools:
  - Priority inbox (ranked focus list).
  - Weekly review summary.
- Frontend updates for Google connect status/action in sidebar.
- FastAPI OAuth routes:
  - `/auth/google`
  - `/auth/google/callback`
  - `/auth/status`

### Changed
- Orchestrator prompt rules tightened for reliable list->ID->action flows (especially complete/delete/update flows).
- Orchestrator step budget increased to support multi-action requests.
- LLM client updated to support JSON response mode (`response_format: json_object`).
- Daily summary expanded to include calendar events and pending habits.
- Static frontend build refreshed with new asset bundles.

### Notes
- This v1 establishes a platform-first architecture: tool orchestration + memory core, with productivity/Google as the first tool domain.
