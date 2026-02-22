from fastapi import APIRouter
from pydantic import BaseModel
from agent.orchestrator import run
from tools.registry import registry
from llm.groq_client import generate

router = APIRouter()

class AgentRequest(BaseModel):
    prompt: str
    session_id: str = "default"


class NameRequest(BaseModel):
    prompt: str


@router.post("/agent/run")
async def run_agent(req: AgentRequest):
    return await run(req.prompt, req.session_id)


@router.post("/name-chat")
async def name_chat(req: NameRequest):
    try:
        name = await generate(
            f"Generate a short 3-4 word title for a chat that starts with this message. "
            f"Return ONLY the title, no quotes, no punctuation, no explanation.\n\nMessage: {req.prompt}"
        )
        return {"name": name.strip()[:40]}
    except Exception:
        return {"name": req.prompt[:30]}


@router.get("/tools")
async def list_tools():
    return registry.list_tools()