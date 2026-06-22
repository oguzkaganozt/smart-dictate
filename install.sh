#!/usr/bin/env bash
# install.sh — bootstrap the smart-dictate pipeline on Ubuntu 24.04+.
#
# Idempotent: re-running skips steps that already succeeded.
#
# Usage:
#   ./install.sh                  install (interactive for missing API key)
#   ./install.sh --check          verify install state, no changes
#   ./install.sh --dry-run        print what would be done, no changes
#   ./install.sh --yes            non-interactive: assume --yes to prompts
#   ./install.sh --uninstall      remove config + scripts + service
#   ./install.sh --no-model       skip Whisper model download
#   ./install.sh --calibrate-mic  run microphone gain calibration
#
# Auth (in priority order):
#   1. $GROQ_API_KEY already set in the environment
#   2. ./.env file with GROQ_API_KEY=...
#   3. ~/.config/voxtype/groq-api-key file
#   4. prompt (skipped if --yes and none of the above)

set -Eeuo pipefail

# ---------- paths ----------
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null && pwd)"
CONFIG_SRC="$SCRIPT_DIR/config/voxtype.toml"
SMART_DICTATE_CONFIG_SRC="$SCRIPT_DIR/config/smart-dictate.toml"
SYSTEMD_DIR="$SCRIPT_DIR/config/systemd"
SCRIPT_SRC_DIR="$SCRIPT_DIR/scripts"

VOXTYPE_CONFIG_DST="${XDG_CONFIG_HOME:-$HOME/.config}/voxtype/config.toml"
SMART_DICTATE_CONFIG_DST="${XDG_CONFIG_HOME:-$HOME/.config}/smart-dictate/config.toml"
VOXTYPE_KEY_DST="${XDG_CONFIG_HOME:-$HOME/.config}/voxtype/groq-api-key"
SYSTEMD_DST_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
SCRIPT_DST_DIR="${XDG_LOCAL_BIN:-$HOME/.local/bin}"

VOXTYPE_DEB_URL="https://github.com/peteonrails/voxtype/releases/download/v0.7.5/voxtype_0.7.5-1_amd64.deb"
VOXTYPE_DEB_TMP="/tmp/voxtype-install.deb"

# ---------- flags ----------
MODE="install"
ASSUME_YES=0
SKIP_MODEL=0

# ---------- hotkey defaults (overridable interactively at install) ----------
# Dictation key uses VoxType/evdev names (e.g. RIGHTCTRL, RIGHTALT, F12).
# Rephrase/summarize use xbindkeys syntax (e.g. "control + alt + r").
DICTATION_KEY="RIGHTCTRL"
REPHRASE_BIND="control + alt + r"
SUMMARIZE_BIND="control + alt + s"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check)      MODE="check"; shift ;;
    --dry-run)    MODE="dry-run"; shift ;;
    --yes|-y)     ASSUME_YES=1; shift ;;
    --uninstall)  MODE="uninstall"; shift ;;
    --no-model)   SKIP_MODEL=1; shift ;;
    --calibrate-mic) MODE="calibrate-mic"; shift ;;
    -h|--help)
      sed -n '2,16p' "$0"
      exit 0
      ;;
    *) echo "install.sh: unknown flag: $1" >&2; exit 2 ;;
  esac
done

# ---------- helpers ----------
log()  { printf '\033[1;34m[install]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*" >&2; }
err()  { printf '\033[1;31m[err ]\033[0m %s\n' "$*" >&2; }
ok()   { printf '\033[1;32m[ ok ]\033[0m %s\n' "$*"; }

run() {
  if [[ "$MODE" == "dry-run" ]]; then
    printf '  would run: %s\n' "$*"
  else
    "$@"
  fi
}

# Wrap commands that may need sudo. In check/dry-run we never elevate.
maybe_sudo() {
  if [[ "$MODE" == "dry-run" || "$MODE" == "check" ]]; then
    "$@"
    return
  fi
  if [[ $EUID -eq 0 ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

# ---------- env loading ----------
load_env() {
  if [[ -z "${GROQ_API_KEY:-}" && -f "$SCRIPT_DIR/.env" ]]; then
    # shellcheck disable=SC1091
    set -a; . "$SCRIPT_DIR/.env"; set +a
  fi
}

# ---------- interactive hotkey selection ----------
# Prompt for the three hotkeys, keeping the default when the user presses
# Enter. Skipped entirely under --yes / --check / --dry-run so automated and
# non-interactive runs keep the defaults.
prompt_shortcuts() {
  if [[ "$MODE" != "install" || "$ASSUME_YES" -eq 1 ]]; then
    return 0
  fi
  log "Configure hotkeys — press Enter to keep the [default] shown."
  log "  Dictation uses evdev names (RIGHTCTRL, RIGHTALT, F12, ...)."
  log "  Rephrase/summarize use xbindkeys syntax (e.g. 'control + alt + r')."
  local ans
  read -r -p "  Dictation push-to-talk key [$DICTATION_KEY]: " ans
  [[ -n "$ans" ]] && DICTATION_KEY="$ans"
  read -r -p "  Rephrase binding [$REPHRASE_BIND]: " ans
  [[ -n "$ans" ]] && REPHRASE_BIND="$ans"
  read -r -p "  Summarize binding [$SUMMARIZE_BIND]: " ans
  [[ -n "$ans" ]] && SUMMARIZE_BIND="$ans"
  ok "Hotkeys: dictation=$DICTATION_KEY  rephrase='$REPHRASE_BIND'  summarize='$SUMMARIZE_BIND'"
}

# ---------- preflight ----------
require_cmd() {
  local cmd="$1"
  if command -v "$cmd" >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

preflight() {
  if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    if [[ "${ID:-}" != "ubuntu" && "${ID:-}" != "debian" ]]; then
      warn "Detected ${ID:-unknown} ${VERSION_ID:-}. This script targets Ubuntu 24.04+ / Debian Trixie+."
    fi
  else
    warn "Cannot read /etc/os-release; proceeding anyway."
  fi

  if [[ "$MODE" == "check" || "$MODE" == "dry-run" ]]; then
    return 0
  fi

  if ! require_cmd apt-get; then
    err "apt-get not found. This installer assumes a Debian-family distro."
    exit 1
  fi
  if ! require_cmd sudo; then
    err "sudo not found. Run as root or install sudo."
    exit 1
  fi
}

# ---------- steps ----------
# All packages we need (binary or runtime). Used both to detect "already
# installed" and to know what apt-get to install on a fresh box.
#
# vulkan-tools (provides vulkaninfo / vkcube) is intentionally omitted:
# it's diagnostics only and VoxType doesn't link against it.
# mesa-vulkan-drivers is the Mesa ICD loader (Intel/AMD); for NVIDIA
# systems the nvidia-driver package provides the Vulkan ICD instead.
REQUIRED_PACKAGES=(voxtype xdotool xclip ydotool wtype wl-clipboard
                   libnotify-bin pipewire-alsa playerctl libvulkan1
                   mesa-vulkan-drivers
                   gir1.2-ayatanaappindicator3-0.1 xbindkeys)

missing_packages() {
  local miss=()
  local p
  for p in "${REQUIRED_PACKAGES[@]}"; do
    if ! dpkg -s "$p" >/dev/null 2>&1; then
      miss+=("$p")
    fi
  done
  printf '%s\n' "${miss[@]}"
}

step_apt_deps() {
  local missing
  missing="$(missing_packages)"

  if [[ -z "$missing" ]]; then
    ok "all required packages already installed"
    return 0
  fi

  # shellcheck disable=SC2086 # intentional: word-split multi-line package list into args
  log "Missing packages:" $'\n'"$(printf '  - %s\n' $missing)"

  # Install the voxtype .deb first if voxtype itself is missing.
  if ! require_cmd voxtype; then
    log "Downloading voxtype .deb"
    run bash -c "wget -q -O '$VOXTYPE_DEB_TMP' '$VOXTYPE_DEB_URL'"
    run maybe_sudo apt-get install -y "$VOXTYPE_DEB_TMP"
    run rm -f "$VOXTYPE_DEB_TMP"
    # Re-check after installing voxtype
    missing="$(missing_packages)"
  fi

  if [[ -n "$missing" ]]; then
    log "Installing runtime dependencies via apt-get"
    # shellcheck disable=SC2086 # intentional: word-split multi-line package list into args
    run maybe_sudo apt-get install -y $missing
  fi
}

step_input_group() {
  if id -nG "$USER" 2>/dev/null | tr ' ' '\n' | grep -qx input; then
    ok "user $USER is already in 'input' group"
  else
    log "Adding $USER to 'input' group (hotkey detection + modifier-release guard)"
    run maybe_sudo usermod -aG input "$USER"
    warn "Group change requires a logout/login to take effect."
  fi
}

step_config() {
  log "Deploying config: $VOXTYPE_CONFIG_DST"
  run mkdir -p "$(dirname "$VOXTYPE_CONFIG_DST")"
  if [[ "$MODE" == "dry-run" || "$MODE" == "check" ]]; then
    : # nothing
  else
    # Template-substitute ${HOME} so paths point at this user's home.
    local rendered
    rendered="$(mktemp)"
    sed -e "s|\${HOME}|$HOME|g" -e "s|\${DICTATION_KEY}|$DICTATION_KEY|g" "$CONFIG_SRC" > "$rendered"
    install -m 0644 "$rendered" "$VOXTYPE_CONFIG_DST"
    rm -f "$rendered"
  fi

  log "Deploying systemd units: $SYSTEMD_DST_DIR/"
  run mkdir -p "$SYSTEMD_DST_DIR/voxtype.service.d"
  if [[ "$MODE" != "dry-run" && "$MODE" != "check" ]]; then
    install -m 0644 "$SYSTEMD_DIR/voxtype.service" "$SYSTEMD_DST_DIR/voxtype.service"
    install -m 0644 "$SYSTEMD_DIR/voxtype-tray.service" \
      "$SYSTEMD_DST_DIR/voxtype-tray.service"
    install -m 0644 "$SYSTEMD_DIR/voxtype.service.d/gpu.conf" \
      "$SYSTEMD_DST_DIR/voxtype.service.d/gpu.conf"
    local rendered
    rendered="$(mktemp)"
    sed "s|\${DISPLAY_PLACEHOLDER}|${DISPLAY:-:0}|g" "$SYSTEMD_DIR/xbindkeys.service" > "$rendered"
    install -m 0644 "$rendered" "$SYSTEMD_DST_DIR/xbindkeys.service"
    rm -f "$rendered"
  fi
}

step_smart_dictate_config() {
  log "Deploying smart-dictate config: $SMART_DICTATE_CONFIG_DST"
  run mkdir -p "$(dirname "$SMART_DICTATE_CONFIG_DST")"
  if [[ "$MODE" != "dry-run" && "$MODE" != "check" ]]; then
    install -m 0644 "$SMART_DICTATE_CONFIG_SRC" "$SMART_DICTATE_CONFIG_DST"
  fi
}

step_scripts() {
  log "Installing scripts to $SCRIPT_DST_DIR/"
  run mkdir -p "$SCRIPT_DST_DIR"
  if [[ "$MODE" != "dry-run" && "$MODE" != "check" ]]; then
    local rendered
    install -m 0755 "$SCRIPT_SRC_DIR/voxtype-clean-dictation" \
      "$SCRIPT_DST_DIR/voxtype-clean-dictation"
    install -m 0755 "$SCRIPT_SRC_DIR/voxtype-paste-active" \
      "$SCRIPT_DST_DIR/voxtype-paste-active"
    install -m 0755 "$SCRIPT_SRC_DIR/voxtype-rephrase" \
      "$SCRIPT_DST_DIR/voxtype-rephrase"
    install -m 0755 "$SCRIPT_SRC_DIR/voxtype-summarize" \
      "$SCRIPT_DST_DIR/voxtype-summarize"
    install -m 0755 "$SCRIPT_SRC_DIR/voxtype-tray" \
      "$SCRIPT_DST_DIR/voxtype-tray"
    install -m 0755 "$SCRIPT_SRC_DIR/voxtype-calibrate-mic" \
      "$SCRIPT_DST_DIR/voxtype-calibrate-mic"
    rendered="$(mktemp)"
    sed -e "s|\${REPHRASE_BIND}|$REPHRASE_BIND|g" \
         -e "s|\${SUMMARIZE_BIND}|$SUMMARIZE_BIND|g" \
         "$SCRIPT_DIR/config/xbindkeysrc" > "$rendered"
    install -m 0644 "$rendered" "$HOME/.xbindkeysrc"
    rm -f "$rendered"
  fi
}

step_api_key() {
  if [[ -n "${GROQ_API_KEY:-}" ]]; then
    ok "GROQ_API_KEY already set in environment"
    return 0
  fi
  if [[ -f "$VOXTYPE_KEY_DST" ]]; then
    ok "API key already present at $VOXTYPE_KEY_DST"
    return 0
  fi

  if [[ "$MODE" == "check" || "$MODE" == "dry-run" ]]; then
    warn "no GROQ_API_KEY and no key file (would prompt at install)"
    return 0
  fi

  if [[ "$ASSUME_YES" -eq 1 ]]; then
    warn "GROQ_API_KEY missing and --yes passed; skipping key write."
    warn "voxtype-clean-dictation will fall back to original text on every call."
    return 0
  fi

  log "No GROQ_API_KEY found. Get one at https://console.groq.com/keys"
  local key
  read -r -s -p "Paste your Groq API key (input hidden): " key
  echo
  if [[ -z "$key" ]]; then
    warn "Empty key; skipping. The cleanup step will be a pass-through."
    return 0
  fi
  mkdir -p "$(dirname "$VOXTYPE_KEY_DST")"
  umask 077
  printf '%s' "$key" > "$VOXTYPE_KEY_DST"
  ok "wrote $VOXTYPE_KEY_DST (mode 0600)"
}

step_model() {
  if [[ "$SKIP_MODEL" -eq 1 ]]; then
    log "Skipping model download (--no-model)"
    return 0
  fi

  local model_dir="$HOME/.local/share/voxtype/models"
  local model_file="$model_dir/ggml-large-v3-turbo.bin"
  if [[ -f "$model_file" ]]; then
    ok "Whisper model already present: $model_file ($(du -h "$model_file" | cut -f1))"
    return 0
  fi

  if [[ "$MODE" == "check" || "$MODE" == "dry-run" ]]; then
    warn "Whisper model not present (would download ~1.6 GB)"
    return 0
  fi

  log "Downloading whisper large-v3-turbo (~1.6 GB) via 'voxtype setup model'"
  run mkdir -p "$model_dir"
  run voxtype setup model --quiet --model large-v3-turbo
}

step_service() {
  if [[ "$MODE" == "check" || "$MODE" == "dry-run" ]]; then
    log "Would: systemctl --user daemon-reload && enable --now voxtype + voxtype-tray + xbindkeys"
    return 0
  fi

  log "Reloading systemd user manager + enabling services"
  systemctl --user daemon-reload
  systemctl --user enable --now voxtype.service voxtype-tray.service xbindkeys.service
  sleep 1
  systemctl --user --no-pager --full status voxtype.service || true
}

# ---------- verify ----------
verify() {
  local fail=0

  if require_cmd voxtype; then ok "voxtype: $(command -v voxtype)"; else err "voxtype: MISSING"; fail=1; fi
  if require_cmd xdotool;  then ok "xdotool:  $(command -v xdotool)";  else err "xdotool:  MISSING"; fail=1; fi
  if require_cmd xclip;    then ok "xclip:    $(command -v xclip)";    else err "xclip:    MISSING"; fail=1; fi
  if require_cmd ydotool;  then ok "ydotool:  $(command -v ydotool)";  else err "ydotool:  MISSING"; fail=1; fi

  if [[ -x "$SCRIPT_DST_DIR/voxtype-clean-dictation" ]]; then
    ok "script:   $SCRIPT_DST_DIR/voxtype-clean-dictation"
  else
    err "script:   $SCRIPT_DST_DIR/voxtype-clean-dictation MISSING"; fail=1
  fi
  if [[ -x "$SCRIPT_DST_DIR/voxtype-paste-active" ]]; then
    ok "script:   $SCRIPT_DST_DIR/voxtype-paste-active"
  else
    err "script:   $SCRIPT_DST_DIR/voxtype-paste-active MISSING"; fail=1
  fi
  if [[ -x "$SCRIPT_DST_DIR/voxtype-rephrase" ]]; then
    ok "script:   $SCRIPT_DST_DIR/voxtype-rephrase"
  else
    err "script:   $SCRIPT_DST_DIR/voxtype-rephrase MISSING"; fail=1
  fi
  if [[ -x "$SCRIPT_DST_DIR/voxtype-summarize" ]]; then
    ok "script:   $SCRIPT_DST_DIR/voxtype-summarize"
  else
    err "script:   $SCRIPT_DST_DIR/voxtype-summarize MISSING"; fail=1
  fi
  if [[ -x "$SCRIPT_DST_DIR/voxtype-tray" ]]; then
    ok "script:   $SCRIPT_DST_DIR/voxtype-tray"
  else
    err "script:   $SCRIPT_DST_DIR/voxtype-tray MISSING"; fail=1
  fi
  if [[ -x "$SCRIPT_DST_DIR/voxtype-calibrate-mic" ]]; then
    ok "script:   $SCRIPT_DST_DIR/voxtype-calibrate-mic"
  else
    err "script:   $SCRIPT_DST_DIR/voxtype-calibrate-mic MISSING"; fail=1
  fi

  if [[ -f "$VOXTYPE_CONFIG_DST" ]]; then
    ok "config:   $VOXTYPE_CONFIG_DST"
  else
    err "config:   $VOXTYPE_CONFIG_DST MISSING"; fail=1
  fi
  if [[ -f "$SMART_DICTATE_CONFIG_DST" ]]; then
    ok "config:   $SMART_DICTATE_CONFIG_DST"
  else
    err "config:   $SMART_DICTATE_CONFIG_DST MISSING"; fail=1
  fi
  if [[ -f "$HOME/.xbindkeysrc" ]]; then
    ok "config:   $HOME/.xbindkeysrc"
  else
    err "config:   $HOME/.xbindkeysrc MISSING"; fail=1
  fi

  if [[ -f "$SYSTEMD_DST_DIR/voxtype.service" ]]; then
    ok "service:  $SYSTEMD_DST_DIR/voxtype.service"
  else
    err "service:  $SYSTEMD_DST_DIR/voxtype.service MISSING"; fail=1
  fi
  if [[ -f "$SYSTEMD_DST_DIR/voxtype.service.d/gpu.conf" ]]; then
    ok "drop-in:  $SYSTEMD_DST_DIR/voxtype.service.d/gpu.conf"
  else
    err "drop-in:  $SYSTEMD_DST_DIR/voxtype.service.d/gpu.conf MISSING"; fail=1
  fi
  if [[ -f "$SYSTEMD_DST_DIR/voxtype-tray.service" ]]; then
    ok "service:  $SYSTEMD_DST_DIR/voxtype-tray.service"
  else
    err "service:  $SYSTEMD_DST_DIR/voxtype-tray.service MISSING"; fail=1
  fi
  if [[ -f "$SYSTEMD_DST_DIR/xbindkeys.service" ]]; then
    ok "service:  $SYSTEMD_DST_DIR/xbindkeys.service"
  else
    err "service:  $SYSTEMD_DST_DIR/xbindkeys.service MISSING"; fail=1
  fi
  if systemctl --user is-active --quiet xbindkeys.service 2>/dev/null; then
    ok "service:  xbindkeys.service (active)"
  elif [[ "$MODE" != "check" && "$MODE" != "dry-run" ]]; then
    warn "service:  xbindkeys.service NOT active"
  fi

  local model="$HOME/.local/share/voxtype/models/ggml-large-v3-turbo.bin"
  if [[ -f "$model" ]]; then
    ok "model:    $model ($(du -h "$model" | cut -f1))"
  else
    warn "model:    $model NOT YET DOWNLOADED"
  fi

  if id -nG "$USER" 2>/dev/null | tr ' ' '\n' | grep -qx input; then
    ok "group:    $USER is in 'input'"
  else
    warn "group:    $USER NOT in 'input' (logout/login needed)"
  fi

  if systemctl --user is-active --quiet voxtype.service 2>/dev/null; then
    ok "service:  active"
  elif [[ "$MODE" != "check" && "$MODE" != "dry-run" ]]; then
    warn "service:  NOT active"
  fi

  echo
  if [[ "$fail" -eq 0 ]]; then
    ok "verify: ok"
    exit 0
  else
    err  "verify: FAIL ($fail missing)"
    exit 1
  fi
}

# ---------- uninstall ----------
do_uninstall() {
  log "Stopping + disabling services"
  systemctl --user disable --now voxtype.service 2>/dev/null || true
  systemctl --user disable --now voxtype-tray.service 2>/dev/null || true
  systemctl --user disable --now xbindkeys.service 2>/dev/null || true

  log "Removing config, scripts, systemd units"
  rm -f  "$SYSTEMD_DST_DIR/voxtype.service"
  rm -f  "$SYSTEMD_DST_DIR/voxtype-tray.service"
  rm -rf "$SYSTEMD_DST_DIR/voxtype.service.d"
  rm -f  "$SCRIPT_DST_DIR/voxtype-clean-dictation"
  rm -f  "$SCRIPT_DST_DIR/voxtype-paste-active"
  rm -f  "$SCRIPT_DST_DIR/voxtype-rephrase"
  rm -f  "$SCRIPT_DST_DIR/voxtype-summarize"
  rm -f  "$SCRIPT_DST_DIR/voxtype-tray"
  rm -f  "$SCRIPT_DST_DIR/voxtype-calibrate-mic"
  rm -f  "$HOME/.xbindkeysrc"
  rm -f  "$SYSTEMD_DST_DIR/xbindkeys.service"

  if [[ "${KEEP_CONFIG:-0}" != "1" ]]; then
    rm -f "$VOXTYPE_CONFIG_DST"
    rm -rf "${XDG_CONFIG_HOME:-$HOME/.config}/smart-dictate"
  else
    warn "KEEP_CONFIG=1: leaving voxtype config + smart-dictate config"
  fi

  if [[ "${KEEP_MODEL:-0}" == "1" ]]; then
    warn "Keeping ~/.local/share/voxtype/ (model + meetings) — set KEEP_MODEL=0 to remove"
  else
    rm -rf "${HOME}/.local/share/voxtype"
  fi

  warn "Not removing the voxtype .deb itself. Run:  sudo apt remove voxtype"
  ok "uninstall complete"
}

# ---------- main ----------
load_env
preflight

case "$MODE" in
  install)
    prompt_shortcuts
    step_apt_deps
    step_input_group
    step_config
    step_smart_dictate_config
    step_source_tree
    step_scripts
    step_api_key
    step_model
    step_service
    echo
    log "Installation finished. Running verify:"
    verify
    ;;
  dry-run)
    echo "[DRY-RUN] no changes will be made"
    step_apt_deps
    step_input_group
    step_config
    step_smart_dictate_config
    step_source_tree
    step_scripts
    step_api_key
    step_model
    step_service
    echo
    log "Dry-run complete. Re-run without --dry-run to apply."
    exit 0
    ;;
  check)
    echo "[CHECK] verifying existing install state"
    verify
    ;;
  calibrate-mic)
    "${SCRIPT_DST_DIR}/voxtype-calibrate-mic"
    ;;
  uninstall)
    do_uninstall
    ;;
esac
