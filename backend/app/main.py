import os
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .database import (
    get_connection,
    get_or_create_session,
    get_session_messages,
    init_db,
    save_turn,
    session_exists,
)
from .llm_service import DEFAULT_SYSTEM_PROMPT, generate_chat_reply, get_configured_keys
from .models import ChatRequest, ChatResponse, HealthResponse, MessagesResponse

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Lyftr AI LLM Chatbot", lifespan=lifespan)

# Configure CORS cleanly for local Docker, custom origins, and Vercel deployments
raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
if raw_origins.strip() == "*":
    allow_origins = ["*"]
    allow_origin_regex = None
else:
    allow_origins = [o.strip().rstrip("/") for o in raw_origins.split(",") if o.strip()]
    allow_origin_regex = r"https://.*\.vercel\.app"

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_origin_regex=allow_origin_regex,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.get("/")
def root():
    return {
        "service": "Lyftr AI Gateway",
        "status": "running",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health", response_model=HealthResponse)
def health_check():
    keys = get_configured_keys()
    return HealthResponse(
        status="ok",
        keys_configured=len(keys),
        cache_enabled=True,
    )


@app.get("/sessions/{session_id}/messages", response_model=MessagesResponse)
def fetch_session_messages(session_id: str):
    if not session_exists(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    messages = get_session_messages(session_id)
    return MessagesResponse(session_id=session_id, messages=messages)


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(
    payload: ChatRequest,
    x_simulate_failure: Optional[str] = Header(default=None, alias="X-Simulate-Failure"),
):
    history = get_session_messages(payload.session_id) if session_exists(payload.session_id) else []

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT system_prompt FROM sessions WHERE session_id = ?",
            (payload.session_id,),
        ).fetchone()
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

    get_or_create_session(payload.session_id, payload.system_prompt)
    save_turn(payload.session_id, payload.message, reply_text, metadata)

    return ChatResponse(
        session_id=payload.session_id,
        reply=reply_text,
        metadata=metadata,
    )