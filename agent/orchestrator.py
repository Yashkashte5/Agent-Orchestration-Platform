import json
import re
from datetime import datetime
from llm.groq_client import generate
from tools.registry import registry
from memory import save_message, get_history, save_summary, get_summary


def extract_json(text: str):
    text = re.sub(r"```json|```", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    return None


async def run(prompt: str, session_id: str = "default"):
    # Fetch history BEFORE saving current message to avoid duplication in prompt
    history = get_history(session_id, limit=6)
    summary = get_summary(session_id)
    tools = registry.list_tools()

    # Save current message after fetching history
    save_message(session_id, "user", prompt)

    # Summarize every 20 messages instead of 10
    all_history = get_history(session_id, limit=100)
    if len(all_history) > 0 and len(all_history) % 20 == 0:
        new_summary = await generate(f"Summarize this conversation in 3 sentences max:\n{all_history}")
        save_summary(session_id, new_summary)

    now = datetime.now()
    current_time_str = now.strftime("%Y-%m-%d %H:%M")
    current_time_readable = now.strftime("%A, %B %d %Y at %I:%M %p")

    # Compact tool list — name + description + exact param names
    compact_tools = [
        {"name": t["name"], "desc": t["description"], "params": t.get("params", {})}
        for t in tools
    ]

    system_prompt = f"""You are a concise AI productivity assistant called Agent Orchestration Platform.
Current time: {current_time_readable} (reminder format: {current_time_str})

Summary: {summary or "None"}

Recent conversation:
{json.dumps(history, indent=2)}

Tools:
{json.dumps(compact_tools, indent=2)}

Respond ONLY with valid JSON:
Tool call: {{"action":"tool","tool_name":"...","params":{{}}}}
Chat reply: {{"action":"chat","response":"..."}}

RULES:
- Never claim to do something without calling the tool first.
- If you need an ID (complete/delete/update), call list_todos/get_notes/list_reminders first, then immediately act — no chat in between.
- For multiple items, use bulk_add_todos.
- For ambiguous requests, ask for clarification.
- Always use tools — never answer from memory when a tool exists.
- remind_at format: YYYY-MM-DD HH:MM

STYLE: Be concise. "Done — marked complete." not "Todo with ID 5 has been marked as complete."
"""

    current_prompt = system_prompt + f"\nUser: {prompt}"
    max_steps = 8
    tool_call_count = {}

    for step in range(max_steps):
        response = await generate(current_prompt, json_mode=True)
        decision = extract_json(response)

        if not decision:
            save_message(session_id, "assistant", response)
            return {"response": response}

        if decision.get("action") == "tool":
            tool_name = decision.get("tool_name")
            params = decision.get("params", {})

            if not tool_name:
                break

            # Allow same tool up to 10 times (for bulk operations)
            count = tool_call_count.get(tool_name, 0)
            if count >= 10:
                break

            tool_call_count[tool_name] = count + 1
            result = await registry.execute(tool_name, params)

            current_prompt += f"""
Tool: {tool_name}
Result: {json.dumps(result, indent=2)}

If this was a list result (list_todos, get_notes, list_reminders) and the user asked to complete/delete/update an item, extract the correct ID from the result above and IMMEDIATELY call the appropriate action tool next. Do not respond with chat yet.
If the task is fully complete, respond with a chat action summarizing what was done.
"""
            continue

        if decision.get("action") == "chat":
            final = decision.get("response", response)
            save_message(session_id, "assistant", final)
            return {"response": final}

    save_message(session_id, "assistant", response)
    return {"response": response}