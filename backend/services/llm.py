import os
import json
import time
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional

# Default system Groq API credentials provided by user
DEFAULT_GROQ_API_KEY = os.environ.get(
    "GROQ_API_KEY",
    "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"
)
DEFAULT_GROQ_MODEL = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b")
DEFAULT_OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
DEFAULT_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")

# Active runtime configuration in memory
_RUNTIME_CONFIG: Dict[str, Any] = {
    "provider": "groq",  # 'groq' | 'ollama'
    "custom_api_key": DEFAULT_GROQ_API_KEY,
    "model": DEFAULT_GROQ_MODEL,
    "ollama_url": DEFAULT_OLLAMA_URL,
    "ollama_model": DEFAULT_OLLAMA_MODEL
}


def get_llm_config() -> Dict[str, Any]:
    """Returns the current active LLM configuration and masked key."""
    active_key = _RUNTIME_CONFIG.get("custom_api_key") or DEFAULT_GROQ_API_KEY
    masked = ""
    if active_key:
        if len(active_key) > 12:
            masked = active_key[:8] + "..." + active_key[-4:]
        else:
            masked = "***"

    return {
        "provider": _RUNTIME_CONFIG.get("provider", "groq"),
        "model": _RUNTIME_CONFIG.get("model", DEFAULT_GROQ_MODEL),
        "has_api_key": bool(active_key),
        "masked_api_key": masked,
        "raw_api_key": active_key,
        "default_model": DEFAULT_GROQ_MODEL,
        "supported_models": [
            "qwen/qwen3.8-27b",
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "llama3.2"
        ]
    }


def update_llm_config(provider: Optional[str] = None, api_key: Optional[str] = None, model: Optional[str] = None) -> Dict[str, Any]:
    """Updates runtime LLM configuration."""
    if provider:
        _RUNTIME_CONFIG["provider"] = provider.lower().strip()
    if api_key is not None:
        key_clean = api_key.strip()
        _RUNTIME_CONFIG["custom_api_key"] = key_clean if key_clean else DEFAULT_GROQ_API_KEY
    if model:
        _RUNTIME_CONFIG["model"] = model.strip()
    return get_llm_config()


def test_groq_api_key(api_key: Optional[str] = None, model: Optional[str] = None) -> Dict[str, Any]:
    """Tests connection to Groq Cloud API with the specified or active API key."""
    key = api_key.strip() if api_key else (_RUNTIME_CONFIG.get("custom_api_key") or DEFAULT_GROQ_API_KEY)
    mod = model.strip() if model else (_RUNTIME_CONFIG.get("model") or DEFAULT_GROQ_MODEL)
    
    if not key:
        return {"valid": False, "error": "No Groq API key provided."}

    t0 = time.time()
    payload = json.dumps({
        "model": mod,
        "messages": [
            {"role": "system", "content": "You are a test probe."},
            {"role": "user", "content": "Reply with ONE word: OK"}
        ],
        "max_tokens": 5,
        "temperature": 0.0
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "VERDANT-AI-Copilot/1.0"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            elapsed_ms = round((time.time() - t0) * 1000)
            reply = data["choices"][0]["message"]["content"].strip()
            return {
                "valid": True,
                "latency_ms": elapsed_ms,
                "model": mod,
                "reply": reply,
                "message": f"Groq LPU verified successfully ({elapsed_ms}ms response time)."
            }
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="ignore")
        return {"valid": False, "status_code": e.code, "error": f"HTTP {e.code}: {err_msg}"}
    except Exception as e:
        return {"valid": False, "error": str(e)}


def call_groq_chat(
    prompt: str,
    system_prompt: str,
    history: Optional[List[Dict[str, str]]] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    timeout: float = 12.0
) -> Optional[Dict[str, Any]]:
    """Calls Groq Cloud API endpoint for lightning-fast inference."""
    key = api_key.strip() if (api_key and api_key.strip()) else (_RUNTIME_CONFIG.get("custom_api_key") or DEFAULT_GROQ_API_KEY)
    mod = model.strip() if (model and model.strip()) else (_RUNTIME_CONFIG.get("model") or DEFAULT_GROQ_MODEL)

    if not key:
        return None

    messages: List[Dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    if history:
        for h in history[-6:]:
            role = "user" if h.get("role") in ["user", "Facility Director"] else "assistant"
            content = h.get("content", "").strip()
            if content:
                messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": prompt})

    payload = json.dumps({
        "model": mod,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 400
    }).encode("utf-8")

    t0 = time.time()
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "VERDANT-AI-Copilot/1.0"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            elapsed_ms = round((time.time() - t0) * 1000)
            reply = data["choices"][0]["message"]["content"].strip()
            usage = data.get("usage", {})
            return {
                "reply": reply,
                "mode": f"Groq Cloud LPU ({mod})",
                "provider": "groq",
                "model": mod,
                "latency_ms": elapsed_ms,
                "usage": usage
            }
    except Exception:
        return None


def call_ollama_chat(
    prompt: str,
    system_prompt: str,
    history: Optional[List[Dict[str, str]]] = None,
    model: Optional[str] = None,
    timeout: float = 4.5
) -> Optional[Dict[str, Any]]:
    """Calls local Ollama instance if available."""
    mod = model or _RUNTIME_CONFIG.get("ollama_model", DEFAULT_OLLAMA_MODEL)
    url = _RUNTIME_CONFIG.get("ollama_url", DEFAULT_OLLAMA_URL)

    payload = {
        "model": mod,
        "system": system_prompt,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 250}
    }

    t0 = time.time()
    try:
        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            reply = data.get("response", "").strip()
            elapsed_ms = round((time.time() - t0) * 1000)
            if reply:
                return {
                    "reply": reply,
                    "mode": f"Local Ollama GPU ({mod})",
                    "provider": "ollama",
                    "model": mod,
                    "latency_ms": elapsed_ms
                }
    except Exception:
        pass
    return None


def generate_llm_response(
    prompt: str,
    system_prompt: str,
    history: Optional[List[Dict[str, str]]] = None,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Unified LLM router:
    1. If provider is 'groq' or not specified, tries Groq Cloud LPU first using custom/default key.
    2. If Groq fails or provider is 'ollama', tries local Ollama.
    3. Returns None if both LLM endpoints fail (triggering grounded knowledge fallback).
    """
    pref_provider = (provider or _RUNTIME_CONFIG.get("provider", "groq")).lower().strip()

    if pref_provider == "ollama":
        res = call_ollama_chat(prompt, system_prompt, history, model=model)
        if res:
            return res
        # Fallback to Groq if Ollama fails
        return call_groq_chat(prompt, system_prompt, history, api_key=api_key, model=model)

    # Default: Groq First (snappy LPU)
    res = call_groq_chat(prompt, system_prompt, history, api_key=api_key, model=model)
    if res:
        return res

    # Fallback to local Ollama if Groq fails
    return call_ollama_chat(prompt, system_prompt, history, model=model)
