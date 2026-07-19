<p align="center">
  <img src="assets/relay-logo.svg" alt="Relay logo" width="160">
</p>

# Relay

<p align="center">
  <a href="https://github.com/oguzkaganozt/relay/actions/workflows/release.yml"><img alt="Release" src="https://github.com/oguzkaganozt/relay/actions/workflows/release.yml/badge.svg"></a>
  <img alt="Ubuntu 24.04" src="https://img.shields.io/badge/Ubuntu-24.04-E95420?logo=ubuntu&logoColor=white">
  <img alt="Python 3.11+" src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white">
  <img alt="License MIT" src="https://img.shields.io/badge/License-MIT-green.svg">
</p>

Context-aware productivity companion for Ubuntu 24.04. The current release
provides push-to-talk dictation with VoxType, Whisper, Groq cleanup, and
terminal-aware paste.

```text
mic  ──►  VoxType ──► Whisper ──► Groq LLM ──► auto-paste
```

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/oguzkaganozt/relay/main/install.sh | bash
```

Prompts for a Groq API key if none is configured. Pass `--yes` and set
`GROQ_API_KEY` to skip prompts. Log out and back in for `input` group
membership, then press `RIGHTCTRL`, speak, press `RIGHTCTRL` again.

## Usage

```bash
relay status          # daemon status + recent logs
relay check           # verify installed files/services
relay check-updates   # compare with latest release
relay upgrade         # download, verify SHA256SUMS, install, restart
relay calibrate-mic   # microphone gain wizard
relay uninstall       # remove everything
```

`relay upgrade` downloads the latest release tarball, verifies it with
`SHA256SUMS`, re-runs the installer, and restarts services. The tray app also
shows an `Upgrade` item when an update is available.

The legacy `smart-dictate` command remains as a temporary compatibility alias.

| Hotkey | Action |
| --- | --- |
| `RIGHTCTRL` | Toggle dictation |
| `Ctrl+Alt+R` | Rewrite selected text (Groq) |
| `Ctrl+Alt+S` | Summarize selected text (Groq) |

## Configuration

Key files under `~/.config/`:

| File | Purpose |
| --- | --- |
| `voxtype/config.toml` | VoxType daemon (hotkey, model, paste) |
| `relay/config.toml` | Groq model, prompts |
| `xbindkeysrc` | Rephrase / summarize key bindings |

API key lookup: `GROQ_API_KEY` env -> `relay/config.toml` ->
`voxtype/groq-api-key` -> installer prompt.

See [docs/configuration.md](docs/configuration.md) and
[docs/architecture.md](docs/architecture.md) for details.

## License

MIT.
