import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Optional

from .database import (
    init_db,
    get_or_create_session,
    session_exists,
    get_session_messages,
    save_turn,
)
from .schemas import ChatRequest, ChatResponse, SessionHistoryResponse
from .llm_service import get_configured_keys, generate_chat_reply, DEFAULT_SYSTEM_PROMPT

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="Lyftr AI LLM Chatbot", lifespan=lifespan)

allowed_origins_raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
allowed_origins = [o.strip() for o in allowed_origins_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if allowed_origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return JSONResponse(status_code=500, content={"detail": "internal server error"})

@app.get("/health")
def health_check():
    keys = get_configured_keys()
    # Verify DB is reachable
    session_exists("__health_probe__")
    return {
        "status": "ok",
        "keys_configured": len(keys),
        "cache_enabled": True
    }

@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(
    payload: ChatRequest,
    x_simulate_failure: Optional[str] = Header(default=None, alias="X-Simulate-Failure")
):
    # Read existing history/system prompt without creating the session yet
    history = get_session_messages(payload.session_id) if session_exists(payload.session_id) else []
    
    # Determine effective system prompt without writing to DB before LLM succeeds
    from .database import get_connection
    conn = get_connection()
    try:
        row = conn.execute("SELECT system_prompt FROM sessions WHERE session_id = ?", (payload.session_id,)).fetchone()
        existing_sys = row["system_prompt"] if row else None
    finally:
        conn.close()

    active_sys_prompt = payload.system_prompt if payload.system_prompt is not None else existing_sys
    effective_sys_prompt = active_sys_prompt if active_sys_prompt is not None else DEFAULT_SYSTEM_PROMPT

    llm_messages = []
    if effective_sys_prompt.strip():
        llm_messages.append({"role": "system", "content": effective_sys_prompt.strip()})
    for msg in history:
        llm_messages.append({"role": msg["role"], "content": msg["content"]})
    llm_messages.append({"role": "user", "content": payload.message})

    try:
        reply_text, metadata = generate_chat_reply(llm_messages, x_simulate_failure)
    except RuntimeError:
        raise HTTPException(status_code=503, detail="all providers unavailable")

    # Persist session & turn ONLY after successful generation
    get_or_create_session(payload.session_id, payload.system_prompt)
    save_turn(payload.session_id, payload.message, reply_text, metadata)

    return ChatResponse(
        session_id=payload.session_id,
        reply=reply_text,
        metadata=metadata
    )
@app.get("/sessions/{session_id}/messages", response_model=SessionHistoryResponse)
def get_messages_endpoint(session_id: str):
    if not session_exists(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    messages = get_session_messages(session_id)
    return SessionHistoryResponse(
        session_id=session_id,
        messages=messages
    )