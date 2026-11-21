import os
import time
import json
import hashlib
from typing import List, Dict, Any, Tuple, Optional
from dotenv import load_dotenv
import litellm
from litellm.caching.caching import Cache
from litellm.exceptions import (
    RateLimitError,
    APIError,
    ServiceUnavailableError,
    AuthenticationError,
    Timeout,
)

load_dotenv(override=True)

# Initialize LiteLLM built-in cache
litellm.cache = Cache(type="local")
litellm.drop_params = True

# Fast, deterministic in-memory cache store keyed by model + full message list
_RESPONSE_CACHE: Dict[str, Dict[str, Any]] = {}

_raw_model = os.getenv("LLM_MODEL", "").strip() or "groq/openai/gpt-oss-120b"
DEFAULT_MODEL = _raw_model if _raw_model.startswith("groq/") else f"groq/{_raw_model}"
DEFAULT_SYSTEM_PROMPT = os.getenv(
    "DEFAULT_SYSTEM_PROMPT", "You are a helpful, concise AI assistant."
)


def get_configured_keys() -> List[Tuple[str, str]]:
    load_dotenv(override=True)
    raw = os.getenv("LLM_API_KEYS", "")
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    return [(f"key_{i+1}", key) for i, key in enumerate(keys)]


def parse_simulated_failures(header_val: Optional[str]) -> Dict[str, int]:
    if os.getenv("ENABLE_FAILURE_SIMULATION", "false").lower() != "true":
        return {}
    if not header_val:
        return {}
    failures: Dict[str, int] = {}
    for pair in header_val.split(","):
        pair = pair.strip()
        if "=" in pair:
            k, code_str = pair.split("=", 1)
            k = k.strip()
            try:
                code = int(code_str.strip())
                if code in (429, 500, 502, 503):
                    failures[k] = code
            except ValueError:
                continue
    return failures


def _build_cache_key(model: str, messages: List[Dict[str, str]]) -> str:
    payload = json.dumps({"model": model, "messages": messages}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def generate_chat_reply(
    messages: List[Dict[str, str]],
    simulate_failure_header: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    start_time = time.perf_counter()
    cache_key = _build_cache_key(DEFAULT_MODEL, messages)

    # 1. Check cache first (keyed by model + system prompt + history + new message)
    cached_entry = _RESPONSE_CACHE.get(cache_key)
    if cached_entry is not None:
        elapsed_ms = max(1, int((time.perf_counter() - start_time) * 1000))
        metadata = {
            "resolution_source": "LLM_CACHE",
            "model": DEFAULT_MODEL,
            "latency_ms": elapsed_ms,
            "input_tokens": cached_entry["input_tokens"],
            "output_tokens": cached_entry["output_tokens"],
            "key_id": None,
            "fallback_attempts": 0,
        }
        return cached_entry["reply"], metadata

    # 2. Cache miss -> run live inference across configured keys with failover
    keys = get_configured_keys()
    if not keys:
        raise RuntimeError("No API keys configured")

    simulated = parse_simulated_failures(simulate_failure_header)
    fallback_attempts = 0

    for key_id, api_key in keys:
        sim_status = simulated.get("*") or simulated.get(key_id)
        if sim_status is not None:
            print(f"[SIMULATION] Simulating HTTP {sim_status} failure on {key_id}")
            fallback_attempts += 1
            continue

        try:
            response = litellm.completion(
                model=DEFAULT_MODEL,
                messages=messages,
                api_key=api_key,
                num_retries=0,
            )

            elapsed_ms = max(1, int((time.perf_counter() - start_time) * 1000))
            reply_text = response.choices[0].message.content or ""

            usage = getattr(response, "usage", None)
            input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)

            # Save reply + exact token counts to cache
            _RESPONSE_CACHE[cache_key] = {
                "reply": reply_text,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            }

            metadata = {
                "resolution_source": "LIVE_INFERENCE",
                "model": DEFAULT_MODEL,
                "latency_ms": elapsed_ms,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "key_id": key_id,
                "fallback_attempts": fallback_attempts,
            }
            return reply_text, metadata

        except (
            RateLimitError,
            ServiceUnavailableError,
            APIError,
            Timeout,
            AuthenticationError,
        ) as e:
            print(f"[FAILOVER] {key_id} ({DEFAULT_MODEL}) error: {type(e).__name__} - {e}")
            fallback_attempts += 1
            continue
        except Exception as e:
            print(f"[FAILOVER] {key_id} ({DEFAULT_MODEL}) unexpected error: {type(e).__name__} - {e}")
            fallback_attempts += 1
            continue

    raise RuntimeError("all providers unavailable")