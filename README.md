<p align="center">
  <img src="assets/smart-dictate-logo.svg" alt="smart-dictate logo" width="160">
</p>

# smart-dictate

<p align="center">
  <a href="https://github.com/oguzkaganozt/smart-dictate/actions/workflows/release.yml"><img alt="Release" src="https://github.com/oguzkaganozt/smart-dictate/actions/workflows/release.yml/badge.svg"></a>
  <img alt="Ubuntu 24.04" src="https://img.shields.io/badge/Ubuntu-24.04-E95420?logo=ubuntu&logoColor=white">
  <img alt="Python 3.11+" src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white">
  <img alt="License MIT" src="https://img.shields.io/badge/License-MIT-green.svg">
</p>

Push-to-talk dictation for Ubuntu 24.04: VoxType + Whisper large-v3-turbo +
Groq cleanup + terminal-aware paste.

```text
mic  ──►  VoxType daemon  ──►  OpenAI Whisper (large-v3-turbo, Vulkan/NVIDIA)
                                  │
                                  ▼
                          post-process (Groq LLM)
                                  │
                                  ▼
                          xdotool auto-paste
```

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/oguzkaganozt/smart-dictate/main/bootstrap.sh | bash
```

The installer prompts for a Groq API key if one is not already configured.
Log out and back in so the `input` group membership is active, then press
`RIGHTCTRL`, speak, and press `RIGHTCTRL` again to paste the cleaned text.

Non-interactive:

```bash
export GROQ_API_KEY="gsk_..."
curl -fsSL https://raw.githubusercontent.com/oguzkaganozt/smart-dictate/main/bootstrap.sh | bash -s -- --yes
```

Pin a specific version:

```bash
curl -fsSL https://raw.githubusercontent.com/oguzkaganozt/smart-dictate/main/bootstrap.sh \
  | SMART_DICTATE_VERSION=v0.2.2 bash
```

## Features

- Toggle dictation (`RIGHTCTRL`), selection rephrase (`Ctrl+Alt+R`), selection
  summarize (`Ctrl+Alt+S`).
- Local Whisper transcription with Vulkan/NVIDIA acceleration.
- Groq LLM cleanup that preserves shell/code snippets.
- System tray with start/stop/restart and microphone calibration.
- Terminal-aware paste for Kitty, Alacritty, Ghostty, WezTerm, Konsole, Ptyxis,
  KGX, Tilix, and common terminal windows.

## Usage

```bash
smart-dictate status          # daemon status + recent logs
smart-dictate check           # verify installed files/services
smart-dictate check-updates   # compare installed version with latest release
smart-dictate upgrade         # download, verify, install, restart services
smart-dictate calibrate-mic   # run the microphone calibration wizard
smart-dictate uninstall       # remove services, scripts, config, and model data
```

Install a development checkout with the Makefile:

```bash
make install
make check
make lint
```

## Updates

```bash
smart-dictate check-updates
smart-dictate upgrade
```

`smart-dictate upgrade` downloads the latest release tarball, verifies it with
`SHA256SUMS`, runs the bundled installer with `--yes`, and restarts the user
services. The tray app also checks for updates after startup and exposes an
`Upgrade Smart Dictate` menu item.

## Configuration

| File | Purpose |
| --- | --- |
| `~/.config/voxtype/config.toml` | VoxType daemon config (hotkey, model, paste hook) |
| `~/.config/smart-dictate/config.toml` | Groq model, endpoint, prompts |
| `~/.config/smart-dictate/version` | Installed version marker |
| `~/.local/share/smart-dictate/source` | Local installer copy for `smart-dictate check/uninstall` |
| `~/.xbindkeysrc` | Rephrase / summarize bindings |

Groq API key lookup order: `GROQ_API_KEY` env var → `~/.config/smart-dictate/config.toml`
→ `~/.config/voxtype/groq-api-key` → interactive installer prompt.

See [docs/configuration.md](docs/configuration.md) for all knobs.

## Release

```bash
git tag v0.x.y
git push origin v0.x.y
```

The release workflow runs `make lint`, builds a source tarball, writes
`SHA256SUMS`, and uploads both to the GitHub release.

## Documentation

- [Architecture](docs/architecture.md)
- [Configuration](docs/configuration.md)
- [Troubleshooting](docs/troubleshooting.md)

## License

MIT. See [LICENSE](LICENSE).
