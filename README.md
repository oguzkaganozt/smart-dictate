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

Transcription runs locally. Only the optional cleanup/rephrase/summarize steps
call Groq. Output is copied to the clipboard and pasted into the focused window
with `Ctrl+V`, or `Ctrl+Shift+V` for terminals.

## Features

- Toggle dictation with the configured hotkey, default `RIGHTCTRL`.
- Local Whisper transcription with Vulkan/NVIDIA acceleration.
- Groq LLM cleanup for natural dictation while preserving shell/code snippets.
- Selection rephrase with `Ctrl+Alt+R`.
- Selection summarize with `Ctrl+Alt+S` and a small GTK popup.
- System tray controls for start/stop/restart and microphone calibration.
- Terminal-aware paste for Kitty, Alacritty, Ghostty, WezTerm, Konsole, Ptyxis,
  KGX, Tilix, and common terminal windows.

## Quickstart

```bash
curl -fsSL https://raw.githubusercontent.com/oguzkaganozt/smart-dictate/main/bootstrap.sh | bash
```

The installer prompts for a Groq API key if one is not already configured. Log
out and back in after the first install so the `input` group membership is
active. Then press `RIGHTCTRL`, speak, and press `RIGHTCTRL` again to paste the
cleaned text into the current window.

Non-interactive install:

```bash
export GROQ_API_KEY="gsk_..."
curl -fsSL https://raw.githubusercontent.com/oguzkaganozt/smart-dictate/main/bootstrap.sh | bash -s -- --yes
```

## Commands

```bash
smart-dictate status          # show daemon status and recent logs
smart-dictate check           # verify installed files/services
smart-dictate check-updates   # compare installed version with latest release
smart-dictate upgrade         # download, verify, install, and restart services
smart-dictate calibrate-mic   # run the microphone calibration wizard
smart-dictate uninstall       # remove services, scripts, config, and model data
```

Source checkout commands are still available for development:

```bash
make install
make check
make lint
```

Installer flags, used by the bootstrap script and `smart-dictate install`:

- `./install.sh --yes` runs non-interactively.
- `./install.sh --check` verifies without changing files.
- `./install.sh --dry-run` prints planned actions.
- `./install.sh --uninstall` removes the installation.
- `KEEP_CONFIG=1 make uninstall` preserves user config.
- `KEEP_MODEL=1 make uninstall` preserves the Whisper model.

## Updates

Smart Dictate uses GitHub release bundles for self-managed updates. Users do
not need to clone the repository.

```bash
smart-dictate check-updates
smart-dictate upgrade
```

`smart-dictate upgrade` downloads the latest release tarball, verifies it with
`SHA256SUMS`, runs the bundled installer with `--yes`, and restarts the user
services. The tray app also checks for updates after startup and exposes an
`Upgrade Smart Dictate` menu item.

Install a specific version:

```bash
curl -fsSL https://raw.githubusercontent.com/oguzkaganozt/smart-dictate/main/bootstrap.sh \
  | SMART_DICTATE_VERSION=v0.1.0 bash
```

## Configuration

Runtime config lives in:

- `~/.config/voxtype/config.toml`
- `~/.config/smart-dictate/config.toml`
- `~/.xbindkeysrc`

Source templates live under `config/`. Re-run `./install.sh` after editing repo
templates.

Installed release source is kept at `~/.local/share/smart-dictate/source` so the
`smart-dictate` CLI can run local checks and uninstall commands without a git
checkout.

Groq API key lookup order:

1. `GROQ_API_KEY` environment variable
2. `~/.config/smart-dictate/config.toml`
3. `~/.config/voxtype/groq-api-key`
4. Interactive installer prompt

See [docs/configuration.md](docs/configuration.md) for all knobs.

## Verify

```bash
voxtype setup check
systemctl --user status voxtype
journalctl --user -u voxtype.service -n 30 --no-pager
journalctl --user -u voxtype-tray.service -n 10 --no-pager
voxtype status
```

If transcription works but text does not paste, check the active window type and
`scripts/voxtype-paste-active` terminal detection.

## Repository

```text
smart-dictate/
├── install.sh                    # bootstrap, check, uninstall, calibration
├── Makefile                      # install/check/status/lint aliases
├── config/                       # voxtype, smart-dictate, systemd templates
├── scripts/                      # dictation, paste, rephrase, summarize, tray
├── docs/                         # architecture, configuration, troubleshooting
├── assets/                       # logo
└── .github/workflows/release.yml # tagged release packaging
```

## Release

Create a GitHub release by pushing a version tag:

```bash
git tag v0.1.0
git push origin v0.1.0
```

The release workflow runs `make lint`, builds a source tarball, writes a
`SHA256SUMS` file, and uploads both to the GitHub release.

## Documentation

- [Architecture](docs/architecture.md)
- [Configuration](docs/configuration.md)
- [Troubleshooting](docs/troubleshooting.md)

## License

MIT. See [LICENSE](LICENSE).

VoxType is MIT-licensed by Peter Jackson / Faster Agile. Whisper model weights
are downloaded at install time from the official Hugging Face mirror via
`voxtype setup model`.
