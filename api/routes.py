from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import uuid

from agent.orchestrator import run
from memory import (
    get_chats, create_chat, rename_chat, delete_chat,
    get_history, save_message
)
from llm.groq_client import generate

router = APIRouter()


class RunRequest(BaseModel):
    prompt: str
    session_id: Optional[str] = "default"

class NameRequest(BaseModel):
    prompt: str
    session_id: Optional[str] = None

class CreateChatRequest(BaseModel):
    name: Optional[str] = "New Chat"

class RenameChatRequest(BaseModel):
    name: str

@router.post("/agent/run")
async def agent_run(req: RunRequest):
    result = await run(req.prompt, req.session_id)
    return result

@router.post("/name-chat")
async def name_chat(req: NameRequest):
    prompt = (
        f"Generate a short 3-4 word title for a chat that starts with this message: "
        f'"{req.prompt}". Reply with ONLY the title, no punctuation, no quotes.'
    )
    try:
        name = await generate(prompt)
        name = name.strip()[:40]
    except Exception:
        name = req.prompt[:30]


    if req.session_id:
        rename_chat(req.session_id, name)

    return {"name": name}


@router.get("/chats")
def list_chats():
    return get_chats()


@router.post("/chats")
def new_chat(req: CreateChatRequest):
    session_id = str(uuid.uuid4())
    create_chat(session_id, req.name)
    return {"id": session_id, "name": req.name}


@router.delete("/chats/{session_id}")
def remove_chat(session_id: str):
    delete_chat(session_id)
    return {"success": True}


@router.put("/chats/{session_id}/rename")
def rename(session_id: str, req: RenameChatRequest):
    rename_chat(session_id, req.name)
    return {"success": True}


@router.get("/chats/{session_id}/history")
def chat_history(session_id: str):
    history = get_history(session_id, limit=100)
    return [
        {"role": h["role"], "content": h["content"]}
        for h in history
        if h["role"] in ("user", "assistant")
    ]


@router.get("/tools")
def list_tools():
    from tools.registry import registry
    return registry.list_tools()