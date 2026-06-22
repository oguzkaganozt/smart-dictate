"""Shared Groq helpers for smart-dictate scripts (stdlib only, Python 3.11+).

Centralizes config loading, API-key resolution, model/endpoint precedence,
the chat-completions HTTP call, reasoning_effort selection, and the Groq
free-tier token-budget math so the three calling scripts
(voxtype-clean-dictation, voxtype-rephrase, voxtype-summarize) can't drift.

Imported by sibling scripts that prepend their own directory to sys.path.
"""
import json
import os
import urllib.request
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "smart-dictate" / "config.toml"
KEY_FILE = Path.home() / ".config" / "voxtype" / "groq-api-key"
DEFAULT_MODEL = "qwen/qwen3.6-27b"
DEFAULT_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"


def load_config(*sections: str) -> dict:
    """Return {section: dict} for each requested [section] of config.toml.

    A missing file, a parse error, or a missing/non-table section all yield
    an empty dict for that section (never raises).
    """
    cfg = {s: {} for s in sections}
    if CONFIG_PATH.exists():
        try:
            import tomllib
            with open(CONFIG_PATH, "rb") as f:
                data = tomllib.load(f)
            for s in sections:
                val = data.get(s)
                if isinstance(val, dict):
                    cfg[s] = val
        except Exception:
            pass
    return cfg


def _first(*values: str) -> str:
    for v in values:
        if v:
            return v
    return ""


def resolve_model(groq_cfg: dict, section_cfg: dict = None, env_prefix: str = None) -> str:
    """Model precedence: <PREFIX>_MODEL env > [section].model > GROQ_MODEL env
    > [groq].model > built-in default."""
    section_cfg = section_cfg or {}
    return _first(
        os.environ.get(f"{env_prefix}_MODEL") if env_prefix else "",
        section_cfg.get("model"),
        os.environ.get("GROQ_MODEL"),
        groq_cfg.get("model"),
        DEFAULT_MODEL,
    )


def resolve_endpoint(groq_cfg: dict, section_cfg: dict = None, env_prefix: str = None) -> str:
    """Endpoint precedence mirrors resolve_model (ENDPOINT instead of MODEL)."""
    section_cfg = section_cfg or {}
    return _first(
        os.environ.get(f"{env_prefix}_ENDPOINT") if env_prefix else "",
        section_cfg.get("endpoint"),
        os.environ.get("GROQ_ENDPOINT"),
        groq_cfg.get("endpoint"),
        DEFAULT_ENDPOINT,
    )


def get_api_key(groq_cfg: dict = None) -> str:
    """GROQ_API_KEY env > [groq].api_key > key file > '' (never raises)."""
    key = os.environ.get("GROQ_API_KEY")
    if key:
        return key
    if groq_cfg:
        key = groq_cfg.get("api_key", "")
        if key:
            return key
    if KEY_FILE.exists():
        return KEY_FILE.read_text(encoding="utf-8").strip()
    return ""


def reasoning_effort(model: str):
    """Groq reasoning_effort for a model, or None when the field should be omitted."""
    if model.startswith("openai/gpt-oss"):
        return "low"
    if model.startswith("qwen/"):
        return "none"
    return None


def token_budget(input_text: str, system_prompt: str, *,
                 tpm: int = 8000, overhead: int = 600,
                 floor: int = 512, ceiling: int = 4096) -> int:
    """max_completion_tokens that fits the Groq free-tier TPM budget.

    Rough char/4 token estimate for input + system prompt, clamped to
    [floor, ceiling].
    """
    input_tokens = len(input_text) // 4 + len(system_prompt) // 4 + 20
    return min(max(floor, tpm - input_tokens - overhead), ceiling)


def build_payload(model: str, system_prompt: str, user_content: str, *,
                  temperature: float, max_completion_tokens: int) -> dict:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
        "max_completion_tokens": max_completion_tokens,
    }
    effort = reasoning_effort(model)
    if effort is not None:
        payload["reasoning_effort"] = effort
    return payload


def call_groq(endpoint: str, api_key: str, payload: dict, *,
              timeout: float, user_agent: str) -> str:
    """POST a chat-completions payload; return first choice content, stripped
    of surrounding whitespace and wrapping quotes. Empty string if no choice."""
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": user_agent,
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    choices = data.get("choices") or []
    if not choices:
        return ""
    content = choices[0].get("message", {}).get("content", "").strip()
    return content.strip('"').strip()
