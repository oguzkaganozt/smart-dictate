# AGENTS.md — smart-dictate

Ubuntu 24.04 push-to-talk voice-to-text pipeline (VoxType + Whisper large-v3-turbo + Groq LLM cleanup + xdotool paste).

## Entry points

- `./install.sh` — single bootstrap entry point. Flags: `--check` (verify), `--dry-run`, `--yes`, `--uninstall`, `--no-model`.
- `Makefile` — aliases: `make install|uninstall|check|dry-run|status|clean-api-key|lint`.
- `uninstall.sh` — delegates to `install.sh --uninstall`. Env knobs: `KEEP_CONFIG=1`, `KEEP_MODEL=1` (default), `PURGE_DEB=1`.

## API key auth order

`GROQ_API_KEY` env var → `~/.config/smart-dictate/config.toml` → `~/.config/voxtype/groq-api-key` → interactive prompt. Installer writes key to `~/.config/voxtype/groq-api-key` (mode 0600).

## Config deployment

`config/voxtype.toml` contains `${HOME}` placeholders — `install.sh` sed-substitutes them to `$HOME` before placing at `~/.config/voxtype/config.toml`. Scripts go to `~/.local/bin/`, systemd unit to `~/.config/systemd/user/`. All paths respect `XDG_*` vars.

## Config file

`config/smart-dictate.toml` is deployed to `~/.config/smart-dictate/config.toml` with model, endpoint, and system prompts for both dictation cleanup and rephrase. Env vars (`GROQ_MODEL`, `GROQ_ENDPOINT`, `GROQ_API_KEY`, `REPHRASE_STYLE`) override config values at runtime — config file overrides script defaults.

## Pipeline flow

1. evdev hotkey (RIGHT CTRL, toggle mode) → VoxType daemon
2. Silero VAD → whisper.cpp (Vulkan, large-v3-turbo, ~1.6 GB model)
3. `voxtype-clean-dictation` (Groq LLM, 3.5s HTTP timeout, 6s daemon timeout, model: `openai/gpt-oss-120b`) — short snippets <90 chars / <14 words pass through; shell/code patterns (`sudo`, `git`, `&&`, `--`, `~/`, etc.) skip LLM
4. xclip → clipboard → `voxtype-paste-active` fires Ctrl+V or Ctrl+Shift+V (terminal detection by window class)

## GPU selection

Systemd drop-in `config/systemd/voxtype.service.d/gpu.conf` sets `VOXTYPE_VULKAN_DEVICE=nvidia`. Verify with `voxtype info variants`.

## Required groups

User must be in `input` group (hotkey evdev + modifier-release guard). Takes effect after logout/login.

## Output delivery

`mode = "clipboard"` with `driver_order = ["ydotool", "clipboard"]`. `post_output_command` fires `voxtype-paste-active` after clipboard write. Terminal match list in `scripts/voxtype-paste-active:31`.

## Text rephrase

`voxtype-rephrase` (`~/.local/bin/voxtype-rephrase`) rewrites selected text in place using Groq LLM. Select text in any text field, trigger the script via a compositor keybinding, and the selection is replaced with a rephrased version.

Script reuses `GROQ_API_KEY`, `GROQ_MODEL`, `GROQ_ENDPOINT` from the dictation pipeline. Reads from PRIMARY selection via `xclip`, writes rephrased text to clipboard, and pastes via `voxtype-paste-active` (handles terminal Ctrl+Shift+V vs GUI Ctrl+V). Short snippets <40 chars or code patterns skip the LLM. System prompt overridable via `REPHRASE_STYLE` env var.

GNOME shortcut (set via gsettings or Settings → Keyboard → Custom Shortcuts): Super+R.
Hyprland equivalent:
```
bind = $main R, exec, ~/.local/bin/voxtype-rephrase
```

## Lint

```sh
make lint   # bash -n + py_compile + sh -n sweep
```

## Running state verification

```
voxtype setup check
systemctl --user status voxtype
journalctl --user -u voxtype.service -n 30 --no-pager
voxtype status
```
