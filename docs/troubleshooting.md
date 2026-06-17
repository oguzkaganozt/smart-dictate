# Troubleshooting

Run `voxtype setup check` first — it walks every dependency and prints
what's missing.

## Hotkey doesn't fire

1. **Are you in the `input` group?**
   ```bash
   groups | tr ' ' '\n' | grep input
   ```
   If not, log out and back in (or `newgrp input` for the current shell).

2. **Is `udevadm` exposing the key?**
   ```bash
   sudo evtest
   ```
   Pick the event device for your keyboard, press **RIGHT CTRL**, look
   for `KEY_RIGHTCTRL`. If you don't see it, your keymap is wrong;
   change `[hotkey] key = "RIGHTCTRL"` to whatever evtest reports.

3. **Wayland conflict.** If you're on GNOME / KDE with a desktop
   shortcut bound to RIGHT CTRL (rare), VoxType's evdev grab loses.
   Move the desktop shortcut or pick a different hotkey
   (`SCROLLLOCK`, `PAUSE`, `F13`–`F24`).

4. **Daemon not running.**
   ```bash
   systemctl --user status voxtype.service
   journalctl --user -u voxtype.service -n 100 --no-pager
   ```
   Look for "Permission denied" on `/dev/input/event*` — fix the group
   (see step 1).

## Vulkan picks the wrong GPU

If you have both an iGPU and a discrete NVIDIA (or AMD + NVIDIA), the
Vulkan ICD loader may default to the iGPU. Two knobs:

- **Easiest**: the shipped drop-in at
  `config/systemd/voxtype.service.d/gpu.conf` already sets
  `VOXTYPE_VULKAN_DEVICE=nvidia`. Verify:
  ```bash
  systemctl --user show voxtype.service -p Environment
  ```
- **Index-based**: in `config/voxtype.toml`, set
  `[whisper] gpu_device = 1` (or whatever index `vulkaninfo --summary`
  shows for your discrete GPU).

Verify the active GPU:
```bash
voxtype info variants
journalctl --user -u voxtype.service -n 50 | grep -i vulkan
```

## Transcription takes > 5 s on a fast machine

- Confirm Vulkan is selected (not AVX-512):
  `voxtype info variants` → "Active: Whisper (Vulkan)".
- Confirm the right GPU is in use: `nvidia-smi` should show
  `voxtype-vulkan` running during a recording.
- Try `eager_processing = true` for streaming-style typing.
- Try `flash_attention = true` if you have a CUDA build.

## Post-process (Groq) keeps timing out

The daemon waits up to `timeout_ms = 6000` (set in
`config/voxtype.toml`). Anything longer and the daemon falls back to
the un-cleaned text and logs a warning.

```bash
# Run the script standalone to see the actual error:
echo "test dictation sentence" | ~/.local/bin/voxtype-clean-dictation
```

Common causes:
- `GROQ_API_KEY` missing → "GROQ_API_KEY is not configured".
- Network/DNS broken → `curl https://api.groq.com/openai/v1/models`
- Wrong model id → 404. Check Groq's docs for current model names.

## First character of typed text triggers a keychord

You're holding Ctrl / Alt / Super / Shift when recording starts.
VoxType's `wait_for_modifier_release = true` (the default) reads evdev
to wait for the modifier to clear before typing. If `/dev/input` is
unreadable (sandbox, container, etc.), the wait silently disables and
you'll see this problem.

Workarounds:
- Make sure you're in the `input` group (see above).
- On Hyprland, the docs recommend a `submap` block; see the commented
  `[output] pre_output_command` in `config/voxtype.toml`.

## Terminal eats the paste

The `voxtype-paste-active` hook sends Ctrl+Shift+V in terminals
because raw ^V is the literal-input character. If your terminal still
eats it:

1. Check the focused window's class:
   ```bash
   xdotool getactivewindow getwindowname
   xprop WM_CLASS
   ```
2. If the lowercase substring doesn't match any of the patterns in
   `scripts/voxtype-paste-active` (kitty, alacritty, ghostty,
   wezterm, konsole, ptyxis, kgx, tilix, terminal, console, …),
   add yours to the `case` glob.

## State file is empty / Waybar doesn't update

```bash
ls -la "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/voxtype/"
cat  "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/voxtype/state"
```

If the dir doesn't exist, VoxType isn't running as a user service.
Check `systemctl --user status voxtype.service`.

## Service won't start: "Failed to determine user credentials"

`$XDG_RUNTIME_DIR` isn't set. The systemd unit sets it explicitly
(`Environment=XDG_RUNTIME_DIR=%t`) — if you've overridden it, undo.

## Removing it all

```bash
./install.sh --uninstall
sudo apt remove voxtype
sudo apt autoremove
# Optionally (DESTRUCTIVE):
rm -rf ~/.local/share/voxtape ~/.config/voxtype
```

## Getting help

- VoxType docs: https://voxtype.io/docs
- VoxType issues: https://github.com/peteonrails/voxtype/issues
- Whisper model docs: https://github.com/openai/whisper
- Groq API console: https://console.groq.com