# smart-dictate

Reproducible bootstrap for a local push-to-talk voice-to-text pipeline with
LLM text rephrasing on Ubuntu 24.04:

```
mic  ──►  VoxType daemon  ──►  OpenAI Whisper (large-v3-turbo, Vulkan/NVIDIA)
                                  │
                                  ▼
                          post-process (Groq LLM)
                                  │
                                  ▼
                          xdotool auto-paste
```

The transcription runs entirely on your machine; only the cleanup step (a
small, latency-bounded Groq call) touches the network. Output is auto-pasted
into the focused window with terminal-aware shortcuts.

Select any text and press Super+R to rephrase it in-place via the same Groq
LLM — a separate shortcut for text refinement without leaving your keyboard.

## Quickstart

```bash
git clone <this-repo> smart-dictate
cd smart-dictate

# 1. Put your Groq API key somewhere (choose one):
export GROQ_API_KEY="gsk_..."
# or:
cp .env.example .env && $EDITOR .env

# 2. Install (idempotent: safe to re-run)
./install.sh

# 3. Log out / back in (so the `input` group change takes effect),
#    then press RIGHT CTRL to toggle recording.
```

`install.sh` will:
- install VoxType v0.7.5 (.deb) and its recommended runtime deps
- ensure your user is in the `input` group (for hotkey + modifier-release)
- drop the config + systemd unit + Vulkan drop-in into `~/.config/`
- install `voxtype-clean-dictation`, `voxtype-paste-active`, and `voxtype-rephrase` into `~/.local/bin/`
- download the `large-v3-turbo` Whisper model into `~/.local/share/voxtype/models/`
- enable and start the user service

## Verify

```bash
voxtype setup check                # system check
systemctl --user status voxtype    # daemon should be active
voxtype status                     # should print state (idle/recording/...)

# Hold RIGHT CTRL, speak Turkish or English for a few seconds, release.
# The cleaned text should appear in the focused window via Ctrl+V (or
# Ctrl+Shift+V if it's a terminal).
```

## Repository layout

```
smart-dictate/
├── README.md                       # this file
├── LICENSE                         # MIT
├── install.sh                      # one-shot bootstrap
├── install.sh --uninstall          # reverse of install
├── Makefile                        # make install / uninstall / status / check
├── .env.example                    # GROQ_API_KEY template
├── config/
│   ├── voxtype.toml                # ~/.config/voxtype/config.toml
│   └── systemd/
│       ├── voxtype.service         # user-level systemd unit
│       └── voxtype.service.d/
│           └── gpu.conf            # VOXTYPE_VULKAN_DEVICE=nvidia drop-in
├── scripts/
│   ├── voxtype-clean-dictation     # Groq LLM cleanup (post-process)
│   ├── voxtype-paste-active        # auto-paste hook (terminal-aware)
│   └── voxtype-rephrase            # Groq LLM text rephrase (selection)
└── docs/
    ├── architecture.md
    ├── configuration.md
    └── troubleshooting.md
```

## Customizing

See [docs/configuration.md](docs/configuration.md) for the full list of knobs.
The interesting ones for tweaking the pipeline:

- **Hotkey**: `[hotkey] key` and `[hotkey] mode` (`push_to_talk` vs `toggle`).
- **Languages**: `[whisper] language` accepts a list like `["tr", "en"]` so
  Whisper constrains its language detection.
- **Engine swap**: comment out Vulkan, switch to a Cohere / Parakeet /
  Moonshine engine with `voxtype setup onnx`.
- **Profiles**: the commented `[profiles.*]` section in `config/voxtype.toml`
  lets you trigger different LLM cleanup prompts per app
  (`voxtype record start --profile code`).

## Architecture details

See [docs/architecture.md](docs/architecture.md). Why each piece is here,
what the LLM cleanup prompt is trying to do, and how the auto-paste hook
chooses Ctrl+V vs Ctrl+Shift+V.

## Troubleshooting

See [docs/troubleshooting.md](docs/troubleshooting.md). Common issues:
hotkey not firing, Vulkan picking the wrong GPU, post-process timing out,
modifiers interfering with typed text.

## License

MIT. See [LICENSE](LICENSE).

VoxType itself is MIT-licensed by Peter Jackson / Faster Agile
(https://voxtype.io). The OpenAI Whisper model weights are downloaded at
install time from the official HuggingFace mirror via `voxtype setup model`.