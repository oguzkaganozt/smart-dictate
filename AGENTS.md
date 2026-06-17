# AGENTS.md — smart-dictate

Ubuntu 24.04 push-to-talk voice-to-text pipeline (VoxType + Whisper large-v3-turbo + Groq LLM cleanup + xdotool paste).

## Entry points

- `./install.sh` — single bootstrap. Flags: `--check` (verify), `--dry-run`, `--yes`, `--uninstall`, `--no-model`.
- `make install|uninstall|check|dry-run|status|clean-api-key|lint` — pass-through aliases.
- `make uninstall` → `./install.sh --uninstall`. Env knobs: `KEEP_CONFIG=1`, `KEEP_MODEL=1` (default), `PURGE_DEB=1`.

## API key auth order

`GROQ_API_KEY` env var → `~/.config/smart-dictate/config.toml` → `~/.config/voxtype/groq-api-key` → interactive prompt (install only). Installer writes key to `~/.config/voxtype/groq-api-key` (mode 0600). Scripts also source `.env` from the repo root if `GROQ_API_KEY` is unset.

## Pipeline flow

1. evdev hotkey (RIGHT CTRL, toggle mode) → VoxType daemon
2. Silero VAD → whisper.cpp (Vulkan, large-v3-turbo, ~1.6 GB model)
3. `voxtype-clean-dictation` (Groq LLM, model: `qwen/qwen3.6-27b`, reasoning: `none`) — short snippets <90 chars / <14 words pass through; shell/code patterns (`sudo`, `git`, `&&`, `--`, `~/`, etc.) skip LLM
4. xclip → clipboard → `voxtype-paste-active` fires Ctrl+V or Ctrl+Shift+V (terminal detection)
5. `voxtype-clean-dictation` shows notification via `notify-send` (icon: `audio-input-microphone`)

## Notification system

Voxtype's built-in `on_transcription` notification is **disabled**
(`config/voxtype.toml`).  Instead, smart-dictate owns its own notifications:

| Action | Source | Icon | Summary |
|--------|--------|------|---------|
| Dictation | `voxtype-clean-dictation` | `audio-input-microphone` | "Dikte edildi" |
| Rephrase | `voxtype-rephrase` | `edit-paste` | "Düzeltildi" |

Both show the first ~100 chars of the output text as the notification body.
Notifications are fire-and-forget (failures silently ignored).

## Python scripts

- `scripts/voxtype-clean-dictation` — stdin/stdout LLM cleanup pipe. Called by VoxType daemon.
- `scripts/voxtype-rephrase` — reads PRIMARY/CLIPBOARD selection via xclip, rewrites via Groq, pastes via `xdotool key ctrl+v`.
- Both use **stdlib only** (no pip dependencies). Require **Python 3.11+** (`tomllib`).
- Model-specific payload fields: if model starts with `openai/gpt-oss`, payload uses `reasoning_effort: "low"`. If starts with `qwen/`, uses `reasoning_effort: "none"`. See `voxtype-clean-dictation:129-132`.
- Config file `~/.config/smart-dictate/config.toml` is read at import time by both. Env vars (`GROQ_MODEL`, `GROQ_ENDPOINT`, `GROQ_API_KEY`, `REPHRASE_MODEL`, `REPHRASE_ENDPOINT`, `REPHRASE_STYLE`) override config values at runtime.
- `max_completion_tokens` is computed dynamically to fit within Groq free-tier 8000 TPM limit (`rephrase`:96-104). Caps at 4096, floor 512.

## Text rephrase

`voxtype-rephrase` — binds to **Ctrl+Alt+R** (via xbindkeys). Reads PRIMARY/CLIPBOARD selection, rewrites via Groq (5s timeout, temp 0.3, max 20000 chars input), pastes via `xdotool key ctrl+v`. Shows "Düzeltildi" notification on success. System prompt overridable via `REPHRASE_STYLE` env var. Model defaults to `qwen/qwen3.6-27b` (overridable via `[rephrase].model` or `REPHRASE_MODEL`).

Keybinding is handled by xbindkeys (systemd user service, autostarted). GNOME custom shortcut is also set during install for fallback.

## Terminal detection

`scripts/voxtype-paste-active:31` maintains a terminal match list (`kitty`, `alacritty`, `ghostty`, `wezterm`, `konsole`, `ptyxis`, `kgx`, `tilix`, `terminal`, `console`). Add new terminals here if they need `ctrl+shift+v` instead of `ctrl+v`.

## Output delivery

`mode = "clipboard"` with `driver_order = ["ydotool", "clipboard"]`. `post_output_command` fires `voxtype-paste-active` after clipboard write.

## GPU selection

Systemd drop-in `config/systemd/voxtype.service.d/gpu.conf` sets `VOXTYPE_VULKAN_DEVICE=nvidia`. Verify with `voxtype info variants`.

## Required groups

User must be in `input` group (hotkey evdev + modifier-release guard). Takes effect after logout/login.

## Lint

```sh
make lint   # bash -n + py_compile + sh -n sweep
```

## System tray indicator

`scripts/voxtype-tray` — autostarted via `voxtype-tray.service`. Shows a
microphone icon in the system tray: green when voxtype is active (listening),
gray when inactive. Left-click toggles the service; right-click opens a menu
(Start / Stop / Restart / Quit). Uses GTK StatusIcon on X11 and Ayatana
AppIndicator3 on Wayland.

Requires `gir1.2-ayatanaappindicator3-0.1` (installed by install.sh).

## Running state verification

```
voxtype setup check
systemctl --user status voxtype
journalctl --user -u voxtype.service -n 30 --no-pager
journalctl --user -u voxtype-tray.service -n 10 --no-pager
voxtype status
```
