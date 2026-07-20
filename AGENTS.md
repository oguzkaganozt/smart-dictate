# AGENTS.md

## Repository Shape

- This is an Ubuntu/Debian installer plus executable scripts, not a Python package. There is no dependency lockfile; Python code must remain stdlib-only and requires Python 3.11+ (`tomllib`).
- `install.sh` is both the local installer and the curl bootstrap. Without `config/voxtype.toml` beside it, it downloads a GitHub release, verifies `SHA256SUMS`, and re-execs the bundled installer.
- `scripts/_voxtype_groq.py` owns config loading, API-key lookup, model/endpoint precedence, payload construction, token budgeting, and HTTP calls shared by the three Groq scripts. Keep this logic centralized.
- Runtime dictation flow is `voxtype daemon -> voxtype-clean-dictation -> clipboard -> voxtype-paste-active`. Rephrase and summarize are separate xbindkeys actions.
- V2 surface: `scripts/relay-bar` is the GTK3 Relay Bar (Ctrl+Alt+Space). It owns the V2 product surface and is a transient process launched by xbindkeys. `scripts/_relay_actions.py` (action registry + prompts + runner), `scripts/_relay_context.py` (context snapshot/sidecar/stale-target), and `scripts/_relay_settings.py` (privacy/model/dictation settings) are stdlib-only and unit-tested. The bar captures a context snapshot to `~/.config/relay/context/active.json` BEFORE taking focus and clears it on exit (atexit + SIGTERM + startup sweep); temp context must never persist.
- V2 privacy is two independent controls in `~/.config/relay/settings.toml` `[privacy]`: `cloud_processing` (send text to remote model) and `context_sharing` (send app/title/selection/screenshot to model), gated by `context_sharing_consented` (first-use consent). Context sharing off does NOT change cloud processing. `[models]` holds optional `text_model`/`vision_model` UI overrides (empty = Auto/Recommended); `[dictation].right_ctrl_visual_context` is opt-in, defaults off, and is additionally gated by context sharing + consent. Context (app/title/selection/screenshot) is always UNTRUSTED DATA, never an instruction. When context sharing is on and a screenshot was captured, a vision-capable model (`resolve_vision_model`, default `meta-llama/llama-4-scout-17b-16e-instruct`) is used with an OpenAI-compatible image_url block; temp PNGs live in `~/.local/share/relay/shots/` and are deleted on exit alongside the snapshot sidecar. Direct Right Ctrl screenshots are captured best-effort after transcription (VoxType has no pre-record hook) and deleted immediately after the model call.
- Treat `config/*.toml`, `config/systemd/`, `scripts/`, and `install.sh` as source of truth. Some examples in `docs/architecture.md` and `docs/configuration.md` lag executable defaults (notably model, token cap, and notification settings).

## Verification

```sh
make lint
make test
shellcheck install.sh scripts/voxtype-paste-active
```

- CI runs those checks in that order on Ubuntu 24.04. `make lint` is only `bash -n`, `py_compile`, and `sh -n`; it does not run ShellCheck.
- Run one test class with `python3 -m unittest tests.test_groq.TokenBudgetTests`; use the same dotted form for a single method.
- Tests are pure stdlib unit tests. They cover `_voxtype_groq.py` and cleanup decisions, not installer side effects, desktop integration, systemd, GTK, or live Groq calls.
- `make check` is `./install.sh --check`: it validates the current machine's installed files and services, not the checkout. Use `./install.sh --dry-run` to inspect installation work without applying it.

## Installer And Deployed State

- A real install invokes apt/sudo, may download a roughly 1.6 GB model, adds the user to `input`, deploys systemd user units, and enables services. Do not use it as routine source verification.
- Installation renders `${HOME}`/`${DICTATION_KEY}` in `config/voxtype.toml`, key bindings in `config/xbindkeysrc`, and `${DISPLAY_PLACEHOLDER}` in the xbindkeys unit. Do not deploy these templates by copying them directly.
- Reinstalling overwrites deployed VoxType config and the Relay-owned `~/.config/relay/xbindkeysrc`, but preserves an existing Relay `config.toml` and never writes or removes the user's `~/.xbindkeysrc`. It snapshots source into `~/.local/share/relay/source`; installed CLI commands use that snapshot, not necessarily this checkout.
- Only the installer sources repo-root `.env`, and only when `GROQ_API_KEY` is unset. Runtime scripts read process env, `~/.config/relay/config.toml`, and the key file; they never source `.env`.
- API key order is `GROQ_API_KEY` -> `[groq].api_key` -> `~/.config/voxtype/groq-api-key`. Model order is action-specific env -> Settings UI override -> action section -> generic env -> `[groq]` -> built-in default. Endpoint order remains action-specific env -> action section -> generic env -> `[groq]` -> built-in default.
- Uninstall removes config and model data by default. `KEEP_CONFIG=1` and `KEEP_MODEL=1` preserve them; the VoxType deb itself is intentionally retained.

## Cross-File Constraints

- `voxtype-clean-dictation` must fail open: short text, code-like text, missing auth, API errors, empty responses, or oversized output return the original transcription. Its completion cap is intentionally fixed at 512 for latency.
- Rephrase and summarize use `_voxtype_groq.token_budget()` for the Groq 8000 TPM limit; rephrase additionally caps completion at 1536. Do not replace dictation's fixed cap with this larger dynamic budget.
- Keep terminal detection markers synchronized between `scripts/voxtype-paste-active` and the fallback in `scripts/voxtype-rephrase`; terminals require Ctrl+Shift+V rather than Ctrl+V.
- Wayland paste tries `ydotool` then `wtype`; X11 uses `xdotool`. Ubuntu's `ydotool` package lacks `ydotoold`, so the installer deploys the daemon unit and uinput rule only when a `ydotoold` binary already exists.
- The `input` group is required for evdev hotkeys and uinput access, and new membership needs logout/login. The Vulkan systemd drop-in deliberately forces `VOXTYPE_VULKAN_DEVICE=nvidia`.
- Release CI runs lint and tests, excludes `.git`, `.github`, env files, Python caches, and `dist`, then overwrites bundled `VERSION`, creates the Relay tarball, and writes `SHA256SUMS`.
