# Lyftr AI Gateway — Resilient Multi-Key LLM Chatbot

A full-stack, fault-tolerant LLM gateway and conversational chatbot built with **FastAPI**, **LiteLLM**, **SQLite**, and **React (Vite)**. Designed for production resilience, it features deterministic multi-key failover, SHA-256 prompt-context response caching, persistent multi-turn session memory, and a deterministic failure-simulation hook for end-to-end verification.

## 1. Live Deployments & Repository

* **Frontend (Vercel):** https://lyfter-ai-chatbot-assignment.vercel.app
* **Backend API (Render):** https://lyfter-ai-chatbot-assignment.onrender.com
* **Interactive API Docs (Swagger UI):** https://lyfter-ai-chatbot-assignment.onrender.com/docs
* **Health Check Endpoint:** https://lyfter-ai-chatbot-assignment.onrender.com/health
* **GitHub Repository:** https://github.com/arpan1109/Lyfter-AI-Chatbot-Assignment

> **Note on Cold Starts:** The backend runs on Render's free tier and spins down after 15 minutes of inactivity. The initial request after idle may take ~30–50 seconds while the container wakes; subsequent requests complete in ~250 ms (live inference) or <15 ms (cached).

---

## 2. System Architecture & Request Lifecycle

```text
┌─────────────────────────┐       HTTPS / CORS        ┌──────────────────────────────────────────┐
│   React + Vite Client   │ ────────────────────────▶ │           FastAPI Gateway (/chat)        │
│        (Vercel)         │ ◀──────────────────────── │                 (Render)                 │
└─────────────────────────┘   Reply + Telemetry Meta  └────────────────────┬─────────────────────┘
                                                                           │
                                                      1. Load Session History & System Prompt
                                                                           ▼
                                                      ┌──────────────────────────────────────────┐
                                                      │     SQLite Persistence (local_app.db)    │
                                                      │   • sessions (session_id, system_prompt) │
                                                      │   • messages (role, content, metadata)   │
                                                      │   • llm_cache (prompt_hash, response)    │
                                                      └────────────────────┬─────────────────────┘
                                                                           │
                                                      2. Compute SHA-256 Prompt Context Hash
                                                                ┌──────────┴──────────┐
                                                          [Cache Hit]           [Cache Miss]
                                                                │                     │
                                                                ▼                     ▼
                                                      Return Instant Reply   ┌───────────────────┐
                                                      (`LLM_CACHE`, 0 tok)   │  LiteLLM Router   │
                                                                             │  Key Rotation:    │
                                                                             │  key_1 ──▶ key_2  │
                                                                             └─────────┬─────────┘
                                                                                       │
                                                                            Groq Inference API
                                                                         (openai/gpt-oss-120b)

```

## API Reference:
| Method | Endpoint | Description | Success Status |
|---|---|---|---|
| GET | `/` | Service metadata and navigation pointers | 200 OK |
| GET | `/health` | Readiness probe reporting configured key count & cache state | 200 OK |
| POST | `/chat` | Submit a message with session memory, caching, and failover | 200 OK (503 if all keys fail) |
| GET | `/sessions/{session_id}/messages` | Retrieve chronological message history for an existing session | 200 OK (404 if unknown) |

## 5.Local Setup and Running Instructions:
- Clone this repo. using:
```
git clone [https://github.com/arpan1109/Lyfter-AI-Chatbot-Assignment.git](https://github.com/arpan1109/Lyfter-AI-Chatbot-Assignment.git)
cd Lyfter-AI-Chatbot-Assignment
cp .env.example .env

```

- Add your Groq API keys in the .env files:
  
 ```
LLM_API_KEYS=gsk_your_primary_key,gsk_your_backup_key
LLM_MODEL=groq/openai/gpt-oss-120b
DATABASE_URL=/data/app.db
ENABLE_FAILURE_SIMULATION=true
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173
VITE_API_BASE_URL=http://localhost:8000
```
- Build your containers:

```
docker compose up --build
```
## 6. Run Tests:
```
cd backend
python -m pytest
```
