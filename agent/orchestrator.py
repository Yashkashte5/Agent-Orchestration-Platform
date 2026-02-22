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
    if len(all_history) % 10 == 0 and all_history:
        new_summary = await generate(f"Summarize this conversation:\n{all_history}")
        save_summary(session_id, new_summary)

    now = datetime.now()
    current_time_str = now.strftime("%Y-%m-%d %H:%M")
    current_time_readable = now.strftime("%A, %B %d %Y at %I:%M %p")

    system_prompt = f"""You are a helpful AI assistant with access to tools.

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

Rules:
- Never call the same tool twice.
- Only use tools from the provided list.
- Always respond in JSON.
- When user says "in X minutes/hours", calculate the exact datetime using the current time above.
"""

    current_prompt = system_prompt + f"\nUser: {prompt}"
    max_steps = 3
    used_tools = set()

    for step in range(max_steps):
        response = await generate(current_prompt)
        decision = extract_json(response)

        if not decision:
            save_message(session_id, "assistant", response)
            return {"response": response}

        if decision.get("action") == "tool":
            tool_name = decision.get("tool_name")
            params = decision.get("params", {})

            if not tool_name or tool_name in used_tools:
                break

            used_tools.add(tool_name)
            result = await registry.execute(tool_name, params)

            current_prompt += f"""
Tool: {tool_name}
Result: {json.dumps(result, indent=2)}

Now answer the user using this result.
"""
            continue

        if decision.get("action") == "chat":
            final = decision.get("response", response)
            save_message(session_id, "assistant", final)
            return {"response": final}

    save_message(session_id, "assistant", response)
    return {"response": response}