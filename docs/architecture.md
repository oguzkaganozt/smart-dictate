# Architecture

End-to-end view of what runs when you press **RIGHT CTRL** to toggle
recording, then release (or press again) to transcribe.

```
┌─────────────────────────────────────────────────────────────────────┐
│                          User Space                                  │
│                                                                     │
│   ┌──────────┐    SIGUSR1/2    ┌──────────────────────────────┐    │
│   │ evdev    │ ──────────────► │ voxtype daemon (systemd user) │    │
│   │ RIGHT    │                 │                              │    │
│   │ CTRL     │ ◄────────────── │   state_file: $XDG_RUNTIME…  │    │
│   └──────────┘  hotkey events  │                              │    │
│                                │   1. record 16kHz PCM        │    │
│                                │      pipewire-alsa           │    │
│                                │   2. Silero VAD (filter)      │    │
│                                │   3. whisper.cpp (Vulkan)     │    │
│                                │      ggml-large-v3-turbo.bin  │    │
│                                │   4. post-process (stdin pipe)│    │
│                                │      voxtype-clean-dictation  │    │
│                                │   5. xclip (clipboard)        │    │
│                                │   6. post_output hook         │    │
│                                │      voxtype-paste-active     │    │
│                                └──────────────────────────────┘    │
│                                          │                           │
└──────────────────────────────────────────│──────────────────────────┘
                                           │  HTTPS (Groq API)
                                           ▼
                                  ┌──────────────────┐
                                  │   Groq Cloud     │
                                   │   openai/gpt-oss-120b   │
                                   │   (chat)               │
                                  └──────────────────┘
```

## Components

### 1. VoxType daemon
- Systemd user unit (`config/systemd/voxtype.service`), starts on
  graphical login, restarts on crash.
- Drop-in (`config/systemd/voxtype.service.d/gpu.conf`) exports
  `VOXTYPE_VULKAN_DEVICE=nvidia` so the Vulkan ICD loader resolves the
  NVIDIA GPU instead of any iGPU or software rasterizer.
- The `state_file = "auto"` setting gives Waybar / scripts a way to
  poll current state via `$XDG_RUNTIME_DIR/voxtype/state`.

### 2. Audio capture
- `pipewire-alsa` provides the ALSA compatibility shim.
- VoxType opens the default source at 16 kHz mono (Whisper's native
  format). `max_duration_secs = 45` is a safety cap.
- Voice Activity Detection (`[vad]`, Silero ONNX) drops recordings
  that contain no speech — this prevents Whisper hallucinations on
  silent clips.

### 3. Whisper transcription
- Local backend. The `large-v3-turbo` model (1.6 GB) is loaded once
  and kept warm by the daemon.
- Vulkan binary selected at install time (`voxtype info variants`
  shows `Whisper (Vulkan)` as the active variant).
- `language = ["tr", "en"]` constrains detection so the model won't
  pick Portuguese when you're code-switching between Turkish and
  English.

### 4. Post-processing (`voxtype-clean-dictation`)
- VoxType pipes the raw transcription into this script on stdin.
- `should_skip()` short-circuits on:
  - Short snippets (<90 chars, <14 words) — no point cleaning "yes
    please" through an LLM.
  - Anything that looks like a shell command (`sudo`, `git`, `&&`,
    `~/`, `--`, …).
- Otherwise: HTTPS POST to Groq OpenAI-compatible endpoint with
  temperature 0.0, max 256 completion tokens.
- The system prompt asks the model to behave like an experienced
  bilingual Turkish/English editor that fixes ASR artifacts while
  preserving code, commands, and proper nouns verbatim.
- Three fallback paths keep the daemon from ever blocking:
  - HTTP / parse / timeout error → original text out
  - empty model response → original text out
  - response dramatically longer than input → original text out

### 5. Output delivery
- `mode = "clipboard"` puts the cleaned text on X11 clipboard via
  `xclip`.
- `driver_order = ["ydotool", "clipboard"]` — ydotool is the type
  driver; on X11 we don't actually use it because `mode = "clipboard"`
  but the fallback chain is there in case mode flips to `"type"`.
- `post_output_command = voxtype-paste-active` runs after the daemon
  finishes writing to the clipboard.
- `voxtype-paste-active` reads the focused window's `WM_CLASS` /
  `getwindowname` and:
  - Sends **Ctrl+Shift+V** if the window name matches a terminal
    (kitty, alacritty, ghostty, wezterm, konsole, ptyxis, kgx, tilix,
    …) — terminals treat bare ^V as literal input.
  - Sends **Ctrl+V** otherwise (browsers, IDEs, etc.).
- `wait_for_modifier_release = true` (the default) reads evdev to
  make sure Ctrl / Alt / Super / Shift are not still held when the
  first character is typed; this prevents accidental keychords from
  firing on the first letter of your dictation.

## Why these choices

| Choice | Reason |
|---|---|
| Local Whisper, not OpenAI API | Audio never leaves the box; works offline; no per-minute cost. |
| `large-v3-turbo` (not `large-v3`) | ~3× faster, ~1% accuracy loss; the cleanup pass would paper over it anyway. |
| Vulkan (not CUDA) variant | One binary covers NVIDIA + AMD + Intel; on NVIDIA it talks through the proprietary Vulkan ICD (`nvidia_icd.json`). |
| Groq for cleanup | Sub-second latency on a 3-billion-token model; OpenAI-compatible API; cheap. |
| Clipboard + post-hook paste | Decouples "text ready" from "where to send it"; survives window switches mid-recording. |
| `toggle` mode, not `push_to_talk` | Long dictations (multiple sentences) don't fatigue the hand. |

## Files that the running system touches

| Path | Owner | Purpose |
|---|---|---|
| `~/.config/voxtype/config.toml` | 644 | VoxType config |
| `~/.config/voxtype/groq-api-key` | 600 | Groq auth (created at install) |
| `~/.config/systemd/user/voxtype.service` | 644 | daemon unit |
| `~/.config/systemd/user/voxtype.service.d/gpu.conf` | 644 | Vulkan device env |
| `~/.local/bin/voxtype-clean-dictation` | 755 | LLM cleanup pipe |
| `~/.local/bin/voxtype-paste-active` | 755 | auto-paste hook |
| `~/.local/share/voxtype/models/ggml-large-v3-turbo.bin` | 644 | Whisper weights |
| `$XDG_RUNTIME_DIR/voxtype/state` | 664 | state for Waybar/scripts |
| `$XDG_RUNTIME_DIR/voxtype/audio.sock` | 660 | daemon IPC |