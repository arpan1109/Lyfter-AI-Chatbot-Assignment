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