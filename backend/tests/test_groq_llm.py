from fastapi.testclient import TestClient
from backend.app.main import app
from backend.services.llm import test_groq_api_key as run_test_groq_api_key, get_llm_config, update_llm_config

client = TestClient(app)

GROQ_KEY = "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"

def test_service_groq_api_key():
    res = run_test_groq_api_key(GROQ_KEY)
    assert res["valid"] is True
    assert "latency_ms" in res


def test_groq_config_endpoints():
    # 1. Get current config
    res = client.get("/intelligence/llm/config")
    assert res.status_code == 200
    data = res.json()
    assert "provider" in data
    assert "model" in data
    assert data["has_api_key"] is True
    assert "masked_api_key" in data

    # 2. Update config with custom model
    update_res = client.post("/intelligence/llm/config", json={
        "provider": "groq",
        "api_key": GROQ_KEY,
        "model": "qwen/qwen3.8-27b"
    })
    assert update_res.status_code == 200
    cfg = update_res.json()
    assert cfg["provider"] == "groq"
    assert cfg["model"] == "qwen/qwen3.8-27b"


def test_groq_live_test_endpoint():
    res = client.post("/intelligence/llm/test", json={
        "api_key": GROQ_KEY,
        "model": "qwen/qwen3.8-27b"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["valid"] is True
    assert "latency_ms" in data
    assert data["latency_ms"] < 5000


def test_copilot_chat_with_groq():
    res = client.post("/intelligence/copilot/chat", json={
        "query": "What is our rooftop solar PV capacity and daily generation?",
        "api_key": GROQ_KEY,
        "provider": "groq",
        "model": "qwen/qwen3.8-27b"
    })
    assert res.status_code == 200
    data = res.json()
    assert "reply" in data
    assert len(data["reply"]) > 10
    assert "Groq Cloud" in data["mode"]


def test_advisor_explain_with_groq():
    res = client.post("/advisor/explain", json={
        "api_key": GROQ_KEY,
        "provider": "groq",
        "model": "qwen/qwen3.8-27b"
    })
    assert res.status_code == 200
    data = res.json()
    assert "summary" in data
    assert "key_findings" in data
    assert "Groq Cloud" in data["mode"]
