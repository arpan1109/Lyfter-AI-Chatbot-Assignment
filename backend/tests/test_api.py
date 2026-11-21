import os
import tempfile
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

# Configure test environment before importing app
tmp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{tmp_db.name}"
os.environ["LLM_API_KEYS"] = "fake_key_1,fake_key_2"
os.environ["ENABLE_FAILURE_SIMULATION"] = "true"

from app.main import app
from app.database import init_db

init_db()
client = TestClient(app)

def mock_litellm_success(content="Hello world", cache_hit=False, prompt_tokens=15, completion_tokens=5):
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content=content))]
    mock_resp._hidden_params = {"cache_hit": cache_hit}
    mock_resp.usage = MagicMock(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    return mock_resp

def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "keys_configured": 2, "cache_enabled": True}

def test_validation_422():
    res = client.post("/chat", json={"session_id": "", "message": "hi"})
    assert res.status_code == 422
    res2 = client.post("/chat", json={"session_id": "s-1", "message": "   "})
    assert res2.status_code == 422

@patch("app.llm_service.litellm.completion")
def test_chat_and_failover(mock_comp):
    mock_comp.return_value = mock_litellm_success("Paris", cache_hit=False)
    res = client.post(
        "/chat",
        json={"session_id": "s-test-1", "message": "Capital of France?"},
        headers={"X-Simulate-Failure": "key_1=429"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["reply"] == "Paris"
    assert data["metadata"]["key_id"] == "key_2"
    assert data["metadata"]["fallback_attempts"] == 1
    assert data["metadata"]["resolution_source"] == "LIVE_INFERENCE"

@patch("app.llm_service.litellm.completion")
def test_all_keys_fail_503(mock_comp):
    res = client.post(
        "/chat",
        json={"session_id": "s-fail", "message": "Hello"},
        headers={"X-Simulate-Failure": "*=429"}
    )
    assert res.status_code == 503
    assert res.json() == {"detail": "all providers unavailable"}
    # Verify nothing added to history
    hist = client.get("/sessions/s-fail/messages")
    assert hist.status_code == 404