# Configuration

The shipped config (`config/voxtype.toml`) is the exact file currently
running on the reference machine. Everything below is **off by default
in the shipped file**; uncomment + edit to change.

## Hotkey

```toml
[hotkey]
key = "RIGHTCTRL"        # evdev key name
mode = "toggle"          # "push_to_talk" or "toggle"
modifiers = []           # required companion keys, e.g. ["LEFTCTRL"]
# model_modifier = "LEFTSHIFT"   # hold + hotkey -> secondary model
# enabled = false          # disable for compositor-driven keybindings
```

Find your key name with `sudo evtest` (look in `/dev/input/event*`).

## Audio

```toml
[audio]
device = "default"       # pactl list sources short for a specific name
sample_rate = 16000      # Whisper's native rate; don't change
max_duration_secs = 180  # safety cap; daemon aborts past this
# pause_media = false    # auto-pause Spotify via MPRIS
```

## Whisper engine

```toml
[whisper]
backend = "local"        # "local" or "remote" (HTTP)
model = "large-v3-turbo"
language = ["tr", "en"]  # array constrains detection; single string or "auto"
translate = false        # translate to English (local model only)
# threads = 4
gpu_device = 1           # overridden by VOXTYPE_VULKAN_DEVICE=nvidia
# flash_attention = false
# initial_prompt = ""    # bias the model toward domain vocabulary

# Multi-model (advanced)
# secondary_model = "large-v3-turbo"
# available_models = ["large-v3-turbo", "medium.en"]
# max_loaded_models = 2
# cold_model_timeout_secs = 300

# Streaming / eager
eager_processing = false
eager_chunk_secs = 3.0
# eager_overlap_secs = 0.5
```

### Switching engines

The Vulkan binary is shipped and active by default. To switch:

```bash
voxtype setup onnx --enable   # install ONNX runtime, switch binary
voxtype setup gpu --enable    # auto-pick best GPU EP
```

Available engines (after switching): `whisper`, `parakeet`,
`moonshine`, `sensevoice`, `paraformer`, `dolphin`, `omnilingual`.

### Remote backend (instead of local)

```toml
[whisper]
backend = "remote"
remote_endpoint = "http://192.168.1.100:8080"   # whisper.cpp server
# remote_endpoint = "https://api.openai.com"
# remote_model = "whisper-1"
# remote_api_key = ""                          # or $VOXTYPE_WHISPER_API_KEY
remote_timeout_secs = 30
```

## Output

```toml
[output]
mode = "clipboard"        # "type" | "clipboard"
fallback_to_clipboard = true
driver_order = ["ydotool", "clipboard"]
type_delay_ms = 0         # increase if chars are dropped
# auto_submit = true      # press Enter after dictation
# shift_enter_newlines = false  # for apps where Enter submits
# restore_clipboard = false    # paste mode only
wait_for_modifier_release = true
modifier_release_timeout_ms = 750
post_output_command = "~/.local/bin/voxtype-paste-active"

[output.post_process]
command = "~/.local/bin/voxtype-clean-dictation"
timeout_ms = 6000          # daemon-side timeout for the post-process pipe
trim = true
fallback_on_empty = true

[output.notification]
on_recording_start = false
on_recording_stop = false
on_transcription = true
# urgency = "normal"
```

### Post-process override

The cleanup script (`scripts/voxtype-clean-dictation`) honors:

| Env var | Default | Effect |
|---|---|---|
| `GROQ_API_KEY` | — | required, falls back to `~/.config/voxtype/groq-api-key` |
| `GROQ_MODEL` | `qwen/qwen3.6-27b` | any Groq chat-completion model id |
| `GROQ_ENDPOINT` | `https://api.groq.com/openai/v1/chat/completions` | any OpenAI-compatible endpoint |

For local LLMs instead of Groq, point `GROQ_ENDPOINT` at an Ollama
OpenAI-compatible server (`http://localhost:11434/v1/chat/completions`)
and `GROQ_MODEL` at the local tag (`llama3.2:1b`).

### Profiles (per-context cleanup)

```toml
[profiles.slack]
post_process_command = "ollama run llama3.2:1b 'Rewrite as a casual Slack message, no greetings, no signature.'"
output_mode = "clipboard"

[profiles.code]
post_process_command = "ollama run llama3.2:1b 'Output a Python comment block, no prose.'"
output_mode = "clipboard"
```

Use with: `voxtype record start --profile code`.

## VAD

```toml
[vad]
enabled = true
threshold = 0.5           # 0.0 = sensitive, 1.0 = aggressive
min_speech_duration_ms = 250

```

Disable VAD only if you're recording in noisy environments where
silence is short — the model will hallucinate on truly silent audio.

## OSD

```toml
[osd]
enabled = false           # GTK4 floating waveform
```

## Status (Waybar / polybar)

```toml
# [status]
# icon_theme = "emoji"
# [status.icons]
# idle = "🎙️"
# recording = "🎤"
# transcribing = "⏳"
# stopped = ""
```

Then a Waybar module can read `$XDG_RUNTIME_DIR/voxtype/state` and pick
an icon. VoxType ships snippets via `voxtype setup waybar`.

## Text processing

```toml
# [text]
# spoken_punctuation = false     # "period" -> "."
# replacements = { "vox type" = "voxtype" }
# smart_auto_submit = false      # say "submit" -> press Enter
# filter_filler_words = true
# filler_words = ["uh", "um", "er", "ah", "eh", "hmm", "hm", "mm", "mhm"]
```

## Summarize

The `voxtype-summarize` script (Ctrl+Alt+S) reads selected text and shows a summary in a GTK3 popup near the cursor.

| Env var | Default | Effect |
|---|---|---|
| `SUMMARIZE_MODEL` | `qwen/qwen3.6-27b` | any Groq chat-completion model id |
| `SUMMARIZE_ENDPOINT` | `https://api.groq.com/openai/v1/chat/completions` | any OpenAI-compatible endpoint |
| `SUMMARIZE_STYLE` | (see `config/relay.toml`) | custom system prompt for summarization |

The popup auto-closes after 30 seconds. Click, Escape, or `q` dismiss it immediately.

## Validation

After any edit:

```bash
voxtype setup check         # sanity check the binary
make check                  # verify the repo's installed state
journalctl --user -u voxtype.service -n 50 --no-pager  # recent logs
```
