"""Relay privacy, model, and dictation settings (stdlib only, Python 3.11+).

Two INDEPENDENT controls per V2 "Iki Acik Kontrol":
  cloud_processing  - transcript / action text sent to the remote model?
  context_sharing   - active window / app / title / selection added to the
                     model request?

Stored in ~/.config/relay/settings.toml (kept separate from legacy
config.toml). Empty model overrides mean Auto / Recommended. Direct Right
Ctrl visual context is opt-in and additionally gated by context consent.

"Context sharing ayari Cloud processing ayarini sessizce degistirmez" -
the two are read independently and never mutate each other.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

XDG_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
SETTINGS_PATH = XDG_CONFIG / "relay" / "settings.toml"

DEFAULTS = {
    "cloud_processing": True,
    "context_sharing": True,
    "context_sharing_consented": False,
    "text_model": "",
    "vision_model": "",
    "right_ctrl_visual_context": False,
}

_PRIVACY_KEYS = ("cloud_processing", "context_sharing", "context_sharing_consented")
_MODEL_KEYS = ("text_model", "vision_model")
_DICTATION_KEYS = ("right_ctrl_visual_context",)
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")


def load(path: Path = SETTINGS_PATH) -> dict:
    """Return the privacy settings dict, filling DEFAULTS for anything missing
    or malformed. Never raises."""
    cfg = dict(DEFAULTS)
    if path.exists():
        try:
            import tomllib
            with open(path, "rb") as f:
                data = tomllib.load(f)
            sections = {
                "privacy": _PRIVACY_KEYS,
                "models": _MODEL_KEYS,
                "dictation": _DICTATION_KEYS,
            }
            for section, keys in sections.items():
                sec = data.get(section, {})
                if not isinstance(sec, dict):
                    continue
                for k in keys:
                    v = sec.get(k)
                    if isinstance(DEFAULTS[k], bool) and isinstance(v, bool):
                        cfg[k] = v
                    elif isinstance(DEFAULTS[k], str) and isinstance(v, str):
                        cfg[k] = v if valid_model_id(v, allow_empty=True) else ""
        except Exception:
            pass
    return cfg


def _render(cfg: dict) -> str:
    out = ["# Relay settings (managed by relay-bar Settings).",
           "# cloud_processing  - send transcript/action text to the remote model",
           "# context_sharing   - send active window/app/title/selection/screenshot to the model",
           "# context_sharing_consented - set true after first-use consent",
           "[privacy]"]
    for k in _PRIVACY_KEYS:
        out.append(f"{k} = {'true' if cfg.get(k, DEFAULTS[k]) else 'false'}")
    out.extend([
        "",
        "# Empty model values mean Auto / Recommended.",
        "[models]",
        f'text_model = "{cfg.get("text_model", "")}"',
        f'vision_model = "{cfg.get("vision_model", "")}"',
        "",
        "[dictation]",
        "# Best-effort screenshot after direct Right Ctrl transcription.",
        "# Also requires context_sharing + consent.",
        "right_ctrl_visual_context = "
        f"{'true' if cfg.get('right_ctrl_visual_context', False) else 'false'}",
    ])
    return "\n".join(out) + "\n"


def save(cfg: dict, path: Path = SETTINGS_PATH) -> None:
    """Atomically write managed settings. Unknown keys are dropped;
    missing keys fall back to DEFAULTS. Never raises."""
    clean = {k: bool(cfg.get(k, DEFAULTS[k])) for k in _PRIVACY_KEYS + _DICTATION_KEYS}
    for k in _MODEL_KEYS:
        value = str(cfg.get(k, "")).strip()
        clean[k] = value if valid_model_id(value, allow_empty=True) else ""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".toml.tmp")
        tmp.write_text(_render(clean), encoding="utf-8")
        tmp.replace(path)
    except Exception:
        pass


def cloud_processing_enabled(cfg: dict) -> bool:
    return bool(cfg.get("cloud_processing", DEFAULTS["cloud_processing"]))


def context_sharing_enabled(cfg: dict) -> bool:
    """True only when context_sharing is on AND the user has consented."""
    return (bool(cfg.get("context_sharing", DEFAULTS["context_sharing"]))
            and bool(cfg.get("context_sharing_consented", DEFAULTS["context_sharing_consented"])))


def valid_model_id(value: str, *, allow_empty: bool = False) -> bool:
    """Conservative validation for provider model IDs.

    Allows common IDs such as qwen/qwen3.6-27b while rejecting whitespace,
    quotes, shell metacharacters, and unbounded input. Model output is never
    executed, but validation keeps the settings file and API request safe.
    """
    if not isinstance(value, str):
        return False
    value = value.strip()
    if not value:
        return allow_empty
    return bool(_MODEL_RE.fullmatch(value))


def text_model(cfg: dict) -> str:
    value = str(cfg.get("text_model", "")).strip()
    return value if valid_model_id(value, allow_empty=True) else ""


def vision_model(cfg: dict) -> str:
    value = str(cfg.get("vision_model", "")).strip()
    return value if valid_model_id(value, allow_empty=True) else ""


def right_ctrl_visual_enabled(cfg: dict) -> bool:
    """Direct dictation screenshot is opt-in and also privacy-gated."""
    return (bool(cfg.get("right_ctrl_visual_context", False))
            and context_sharing_enabled(cfg))


def consent_to_context_sharing(path: Path = SETTINGS_PATH) -> dict:
    """Record first-use consent and turn context sharing on. Returns the new cfg."""
    cfg = load(path)
    cfg["context_sharing"] = True
    cfg["context_sharing_consented"] = True
    save(cfg, path)
    return cfg
