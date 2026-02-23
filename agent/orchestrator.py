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
    save_message(session_id, "user", prompt)

    history = get_history(session_id)
    summary = get_summary(session_id)
    tools = registry.list_tools()

    all_history = get_history(session_id, limit=100)
    if len(all_history) > 0 and len(all_history) % 10 == 0:
        new_summary = await generate(f"Summarize this conversation:\n{all_history}")
        save_summary(session_id, new_summary)

    now = datetime.now()
    current_time_str = now.strftime("%Y-%m-%d %H:%M")
    current_time_readable = now.strftime("%A, %B %d %Y at %I:%M %p")

    system_prompt = f"""You are a helpful AI productivity assistant called Agent Orchestration Platform.

Current date and time: {current_time_readable} (use format YYYY-MM-DD HH:MM for reminder tools, e.g. {current_time_str})

Conversation summary:
{summary}

Recent conversation:
{json.dumps(history, indent=2)}

Available tools:
{json.dumps(tools, indent=2)}

If a tool is needed respond ONLY with valid JSON:
{{
  "action": "tool",
  "tool_name": "...",
  "params": {{}}
}}

Otherwise respond ONLY with valid JSON:
{{
  "action": "chat",
  "response": "your answer"
}}

STRICT RULES:
- NEVER say you did something unless you actually called the tool and got a result back.
- NEVER assume a tool was already called. If the user asks you to do something, call the tool — do not say it was done in a previous turn unless you can see the tool result in this conversation.
- If user asks to complete/delete/update something, you MUST call the appropriate tool. Do not respond with chat until the tool has been called and returned a result.
- If the user refers to a todo/note/reminder by name or says "it" or "that one" and you don't have its ID, call list_todos/get_notes/list_reminders FIRST to find the ID, then call the action tool.
- If the user asks to add multiple items (e.g. "add 3 todos"), call bulk_add_todos with all items in one call.
- Only use tools from the provided list.
- Always respond in valid JSON.
- When user says "in X minutes/hours", calculate the exact datetime using the current time above.
- If the user's request is ambiguous (e.g. "add a todo" with no details), ask for clarification via chat action.

RESPONSE STYLE:
- Respond like a smart, concise assistant — not like a debug log.
- BAD: "Todo with ID 5 has been marked as complete."
- GOOD: "Done — marked that as complete."
- BAD: "Note 'Project Goals' has been saved with the body 'Build a production ready AI agent platform'. The note's ID is 1."
- GOOD: "Saved your Project Goals note."
- Keep confirmations short. Mention IDs only when the user needs them for follow-up actions.
- For lists (todos, notes, reminders), format them clearly and concisely.
- Never expose raw database fields or internal IDs unless asked.
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

            count = tool_call_count.get(tool_name, 0)
            if count >= 10:
                break

            tool_call_count[tool_name] = count + 1
            result = await registry.execute(tool_name, params)

            current_prompt += f"""
Tool: {tool_name}
Result: {json.dumps(result, indent=2)}

If there are more actions needed to fully complete the user's request, continue with the next tool call.
Otherwise respond with a chat action summarizing what was done.
"""
            continue

        if decision.get("action") == "chat":
            final = decision.get("response", response)
            save_message(session_id, "assistant", final)
            return {"response": final}

    save_message(session_id, "assistant", response)
    return {"response": response}