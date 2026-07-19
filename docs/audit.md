# Public-Readiness Audit

> Historical snapshot from before the Relay rename. References to
> `smart-dictate` are legacy evidence, and several findings have since been
> resolved. Use executable sources and `AGENTS.md` for current behavior.

Read-only review of the smart-dictate repository for gaps and issues that
should be addressed before treating it as a public-facing product. Findings
are ordered by severity, each with file:line evidence, impact, and a concrete
recommendation.

Last updated: 2026-06-22.

---

## Findings

### Critical

#### 1. Paste path is X11-only on a Wayland-first OS
- **Evidence**: `scripts/voxtype-paste-active:19,25,27,34,37` (xdotool
  only); `scripts/voxtype-rephrase:174,175,189,199,204` (xdotool/xclip);
  `scripts/voxtype-summarize:142` (`xdotool getmouselocation`).
  `install.sh:169` lists `ydotool wtype wl-clipboard` as required packages
  but no script ever invokes them. `config/voxtype.toml:30` sets
  `driver_order = ["ydotool", "clipboard"]`, which is misleading because
  `mode = "clipboard"` bypasses the type drivers and goes straight to the
  X11-only `post_output_command`.
- **Impact**: Default Ubuntu 24.04 ships GNOME on Wayland. After
  dictation, text lands on the clipboard but the auto-paste silently fails
  for the majority of public users. Re-paste (`Ctrl+Alt+R` / `Ctrl+Alt+S`)
  and the summarize popup window positioning are also X11-only.
- **Recommendation**: Detect session (`echo $XDG_SESSION_TYPE`) and branch
  `voxtype-paste-active` between `xdotool` (X11/XWayland) and
  `ydotool`/`wtype` (Wayland). For summarize popup, replace
  `xdotool getmouselocation` with a Wayland-safe equivalent (e.g. reading
  the cursor via `wlr-cursor` / `swaymsg -t get_cursor` / DBus
  `org.gnome.Mutter.IdleMonitor`); if not possible, center the popup on the
  active output instead. Remove `ydotool`/`wtype` from `REQUIRED_PACKAGES`
  or actually use them.

#### 2. No tests for any of the critical paths
- **Evidence**: `make lint` only does `bash -n` + `py_compile` + `sh -n`.
  No `tests/` dir, no `pytest`/`unittest` invocation. `Makefile:30-39`.
- **Impact**: The `should_skip` short-circuit
  (`voxtype-clean-dictation:76-86`), TPM-budget math
  (`voxtype-rephrase:101-112`, `voxtype-summarize:105-116`),
  `reasoning_effort` selection (`voxtype-clean-dictation:129-132`, mirrored
  in the other two scripts), terminal-detection case list
  (`voxtype-paste-active:33`, `voxtype-rephrase:162-165`), and the "output
  too long" guard (`voxtype-clean-dictation:194`) all ship with zero
  regression coverage. Any refactor will break these silently.
- **Recommendation**: Add `tests/` with stdlib `unittest` (no new deps,
  matches existing stdlib-only constraint). Cover at minimum: `should_skip`
  boundaries (89/90 chars, 13/14 words, each code marker), model-prefix →
  `reasoning_effort` mapping, terminal list match logic, output-length
  guard, `_is_terminal` (mock `xdotool`/`xprop`). Wire `make test` into the
  same target as lint.

#### 3. World-readable API key in `config.toml`
- **Evidence**: `install.sh:258` installs
  `~/.config/smart-dictate/config.toml` mode 0644.
  `config/smart-dictate.toml:43-45` and `.env.example:11-12` both document
  `api_key = "gsk_..."` as an option. By contrast, the dedicated
  `groq-api-key` file is written under `umask 077` (`install.sh:347`).
- **Impact**: Any user who follows the documented `api_key = "gsk_..."`
  shortcut in `config.toml` exposes their Groq key to every other account
  on a multi-user system. The current docs imply either path is fine.
- **Recommendation**: Either (a) remove the `api_key` field from
  `config.toml` entirely and tell users to use the key file, or (b)
  install the config as `chmod 0600` if a key is set, and warn loudly
  during install. Make the `.env.example` comment match.

---

### High

#### 4. No CI on pull requests
- **Evidence**: `.github/workflows/` contains only `release.yml`, which is
  `on: push: tags: v*` plus manual dispatch. No `pull_request` trigger, no
  `push: branches: [main]` trigger.
- **Impact**: Public contributors can land PRs that break `make lint` (or
  any other invariant). The only gate is the tag-time release job, so
  defects ship to a real GitHub release without any CI signal. There is no
  PR template either (`.github/ISSUE_TEMPLATE/` is missing).
- **Recommendation**: Add a `ci.yml` workflow running on PR and
  push-to-main: `make lint` + `make test` + `shellcheck install.sh
  bootstrap.sh scripts/voxtype-paste-active`. Optionally add
  `.github/dependabot.yml` for GitHub Actions updates.

#### 5. VoxType .deb is hard-pinned to v0.7.5 with no override
- **Evidence**: `install.sh:40` sets `VOXTYPE_DEB_URL` to a single pinned
  URL. No `VOXTYPE_VERSION` env knob, no apt repo, no GPG-checked source
  list.
- **Impact**: Public users on a different VoxType release can't opt in.
  When VoxType ships a breaking config change, smart-dictate install breaks
  for everyone until a new release. Also no integrity check on the
  downloaded `.deb` (no `SHA256SUMS` verification, no `dpkg-sig`).
- **Recommendation**: Accept `VOXTYPE_VERSION` (default `0.7.5`), build the
  URL from it, and add a `.sha256` next to the .deb URL (or check
  `dpkg --info` signature) so the .deb is verified before install.

#### 6. Major code duplication across the three LLM-calling scripts
- **Evidence**: `_load_config` is byte-identical in
  `voxtype-clean-dictation:40-53`, `voxtype-rephrase:24-37`,
  `voxtype-summarize:26-39`. `get_api_key` is byte-identical in
  `voxtype-clean-dictation:89-98`, `voxtype-rephrase:84-93`,
  `voxtype-summarize:89-98`. The MODEL/ENDPOINT env-precedence chain is
  duplicated in all three (e.g. `voxtype-clean-dictation:58-61`,
  `voxtype-rephrase:42-53`, `voxtype-summarize:44-55`). The urllib Groq
  POST boilerplate is repeated three times
  (`voxtype-clean-dictation:134-145`, `voxtype-rephrase:118-128`,
  `voxtype-summarize:122-132`). `get_selected_text` is duplicated
  (`voxtype-rephrase:71-81`, `voxtype-summarize:76-86`). Total duplicated
  LOC: ~200.
- **Impact**: Drift risk. The same TPM-budget logic exists in two files
  and is at risk of drifting (e.g. one updates `PROMPT_OVERHEAD`, the
  other doesn't). The `reasoning_effort` model-prefix mapping is also
  duplicated 3x — a new model family requires three edits.
- **Recommendation**: Extract a `scripts/_voxtype_groq.py` (or even just a
  `lib/` module) with: `load_config()`, `get_api_key()`, MODEL/ENDPOINT
  resolution helper, `call_groq(payload, timeout) -> str`, and
  `add_reasoning_effort(payload, model_name)`. Each calling script becomes
  ~50 lines.

#### 7. No paste-failure feedback to the user
- **Evidence**: `voxtype-paste-active:34,37` swallow all xdotool errors.
  `install.sh:507-511` exits 0 from `verify` if only warnings exist;
  nothing checks that `xdotool` actually works on the user's session.
- **Impact**: When auto-paste fails (most common on Wayland, or when
  `DISPLAY` is unset under `systemd --user`), the user sees the
  "Dikte edildi" notification and the text lands on the clipboard, but
  nothing types. There is no retry, no fallback, and no error notification.
  This is a silent UX failure.
- **Recommendation**: After firing the paste key, check
  `xdotool getactivewindow` again to verify focus is still on the same
  window. On failure, post a `notify-send` "Text on clipboard — press
  Ctrl+V to paste" so the user knows to do it manually.

#### 8. The `max_completion_tokens` constraint is enforced AFTER the LLM call
- **Evidence**: `voxtype-clean-dictation:194` —
  `if len(output) > max(len(text) * 1.5, len(text) + 120):` runs *after* the
  request returns. The `max_completion_tokens=512` cap in the payload (line
  126) is a Groq-side cap on output, not on input.
- **Impact**: The daemon always pays the full Groq roundtrip latency
  (~0.6 s) even when the input text is so long that any reasonable cleanup
  is going to be rejected. For inputs > 1.5× the source, this is wasted
  work and a worse UX (notification of "fallback" instead of LLM-cleaned
  text).
- **Recommendation**: Add an input-side precheck: if input is already >
  some upper bound, skip the LLM call (e.g. 4 000 chars for dictation;
  rephrase/summarize already have explicit limits). The fallback path
  becomes `notify-send "text too long, kept original"`.

#### 9. No version-pinned dependencies, no integrity check on downloaded model or .deb
- **Evidence**: `install.sh:372` calls
  `voxtype setup model --quiet --model large-v3-turbo` which downloads the
  model. There is no SHA verification of the Whisper model. Same for the
  VoxType .deb (line 200). The Whisper model is a ~1.6 GB binary execute
  target for end users.
- **Impact**: A compromised mirror (or a future VoxType repo compromise)
  silently distributes malicious binaries to every installer run. There is
  also no `apt-transport-https` enforcement or GPG check on the model.
- **Recommendation**: At minimum, SHA256-verify the VoxType .deb. Document
  the model source (`huggingface.co/ggerganov/whisper.cpp`) and add an
  integrity note in the README. For maximum safety, ship the model via
  apt (VoxType already does this for the daemon).

---

### Medium

#### 10. Unbounded log growth in `/tmp`
- **Evidence**: `voxtype-rephrase:13` and `voxtype-summarize:14` open
  `/tmp/voxtype-rephrase.log` and `/tmp/voxtype-summarize.log` in append
  mode on every invocation. No rotation, no size cap.
- **Impact**: Power users will see these grow without bound. On a
  long-running desktop this is a small but real disk-pressure issue. They
  also live in `/tmp`, which is wiped on reboot, so debugging a
  session-spanning issue is impossible.
- **Recommendation**: Move logs to `~/.local/state/smart-dictate/` (XDG
  state dir) and rotate at 1 MB. Truncate on startup if older than 7 days.

#### 11. Turkish-only user-facing strings
- **Evidence**: `voxtype-clean-dictation:161` ("Dikte edildi"),
  `voxtype-rephrase:144` ("D\xfczeltildi"),
  `voxtype-summarize:386,397,413` ("Özet Hatası", "Özetleniyor...",
  "Özet"). The `notify-send` summaries are all in Turkish.
- **Impact**: The LLM correctly preserves input language, but the tray and
  notification chrome is Turkish. For a public product, this excludes the
  majority of English-speaking users even when the tool otherwise works.
- **Recommendation**: Either add an `LANG=tr|en` switch in
  `config/smart-dictate.toml`, or move all user-visible strings into a
  single i18n module with `tr` (default) and `en` translations.

#### 12. `voxtype-tray.service` Documentation URL points at the upstream repo, not smart-dictate
- **Evidence**: `config/systemd/voxtype-tray.service:3` —
  `Documentation=https://github.com/peteonrails/voxtype`.
- **Impact**: `systemctl --user status voxtype-tray` shows the upstream
  URL. Confusing for users filing smart-dictate issues.
- **Recommendation**: Change to
  `https://github.com/oguzkaganozt/smart-dictate` (or remove).

#### 13. Hardcoded timeout in `voxtype-clean-dictation` cannot be overridden
- **Evidence**: `voxtype-clean-dictation:144` —
  `urllib.request.urlopen(req, timeout=5.0)`. The script's docstring
  (lines 1-25) advertises env-var overrides for `GROQ_MODEL` /
  `GROQ_ENDPOINT` but not for the timeout. The daemon-level timeout is
  `timeout_ms = 6000` in `config/voxtype.toml:36`.
- **Impact**: Power users with a slow Groq endpoint or large models see
  the script silently swallow the call and paste the original text, with
  no way to tune it. The daemon-side 6 000 ms is also tight for the
  larger models (`openai/gpt-oss-120b` at ~0.85 s with prompts).
- **Recommendation**: Read `GROQ_TIMEOUT` (or `DICTATION_TIMEOUT`) env var
  with default 5. Bump daemon `timeout_ms` to 8 000 in the default config.

#### 14. The "short snippet" pass-through has an inconsistent boundary
- **Evidence**: `voxtype-clean-dictation:78` —
  `if len(text) < 90 and len(words) < 14: return True`. The conditions are
  AND, so a 14-word text of 200 chars does go through the LLM, but a
  13-word text of 5 000 chars also passes through unchanged. The intent
  ("don't waste LLM on trivial input") is partially defeated.
- **Impact**: Long log lines that happen to have <14 words (e.g. URLs,
  file paths, stack-trace fragments) skip cleanup. The code-marker
  fallback (line 81) catches many of these, but not all.
- **Recommendation**: Make the short-circuit OR (`< 90 chars OR < 14
  words`), and consider adding a hard upper bound ("if input > 4 000 chars,
  skip LLM") as in finding 8.

#### 15. `xbindkeys` xbindkeysrc deployment overwrites the user's existing file
- **Evidence**: `install.sh:312` —
  `install -m 0644 "$rendered" "$HOME/.xbindkeysrc"`. There is no check
  whether the user already had an `~/.xbindkeysrc`.
- **Impact**: A user with their own xbindkeys bindings loses them silently
  on install. The uninstall correctly removes the file (`install.sh:532`),
  so the user's bindings are gone forever if they later uninstall
  smart-dictate.
- **Recommendation**: If `~/.xbindkeysrc` exists and does not already
  contain the smart-dictate bindings, append them or back up the file.
  Mention this in the install summary.

#### 16. The `make uninstall` target bypasses the prompt by default
- **Evidence**: `Makefile:10` runs `./install.sh --uninstall`
  unconditionally. `install.sh:515` (`do_uninstall`) deletes the user's
  `~/.xbindkeysrc`, `~/.config/smart-dictate/`, and
  `~/.config/voxtype/config.toml` (unless `KEEP_CONFIG=1`).
- **Impact**: `make uninstall` and `smart-dictate uninstall` are
  destructive by default. A typo or muscle-memory alias can wipe the user's
  config + xbindkeysrc without a confirmation prompt. Not catastrophic
  (re-installable), but painful.
- **Recommendation**: Add a `--yes` requirement for the destructive path,
  or print a clear summary of what will be removed and ask for
  confirmation. Document the `KEEP_CONFIG=1` knob in the README (currently
  it's only in the Makefile comment).

#### 17. The installer has no `--no-systemd` or "user-only" path
- **Evidence**: `install.sh` always writes systemd units, always tries
  `usermod -aG input`, always runs `systemctl --user enable --now`. There
  is no opt-out.
- **Impact**: Power users on minimal systems (no systemd, no audio,
  container-only) cannot use the installer. The preflight only checks for
  `apt-get` + `sudo` (`install.sh:151-158`).
- **Recommendation**: Document the supported environments at the top of
  the README, and either error out clearly with a helpful message on
  unsupported systems, or add a `--no-systemd` flag that only deploys
  scripts + config.

#### 18. AGENTS.md and docs/architecture.md disagree on the dictation token cap
- **Evidence**: `docs/architecture.md:73` says `max 256 completion tokens`
  for the cleanup step; the code (`voxtype-clean-dictation:126`) actually
  uses 512. AGENTS.md was corrected in commit `e897c7c`.
- **Impact**: This is the kind of drift a public user could trip over.
- **Recommendation**: Update `docs/architecture.md:73` to "max 512
  completion tokens". Add a CI check (or a `make lint-docs` target) that
  fails the build if any doc claims a number that disagrees with a script
  default — at minimum a regex sweep.

#### 19. No CHANGELOG, SECURITY, CONTRIBUTING, or CODE_OF_CONDUCT
- **Evidence**: `git ls-files` shows none of these at the repo root.
- **Impact**: Public users have no place to report security issues
  privately (no `SECURITY.md`), no contribution guide, no code of conduct,
  and no human-readable changelog between releases. `VERSION` is the only
  release marker. For a public product, all four are baseline
  expectations.
- **Recommendation**: Add at minimum a `SECURITY.md` (with private
  disclosure instructions) and a `CHANGELOG.md` populated from git log on
  each release. `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md` can follow the
  standard GitHub templates.

#### 20. No demo, screenshot, or animated GIF in the README
- **Evidence**: `README.md` has only a logo SVG
  (`assets/smart-dictate-logo.svg`). No `docs/demo.gif` or section showing
  the tray, the notification, or a sample cleanup.
- **Impact**: A new visitor can't see the product in action. The current
  README is heavy on text and install commands.
- **Recommendation**: Add a short terminal recording (or screenshot of tray
  + notification) to the README. Even a 10-second screen capture
  dramatically improves conversion.

---

### Low

#### 21. `voxtype-clean-dictation` uses an exact-string match for the `< 14 words` heuristic that doesn't handle Turkish suffix patterns well
- **Evidence**: `voxtype-clean-dictation:77` —
  `words = re.findall(r"\S+", text)`. The count is whitespace-tokenized.
- **Impact**: Turkish often concatenates suffixes (e.g. "geliyorum",
  "etmiyordur"). The "word" count is technically correct but the LLM is
  the one cleaning morphology, so this is mostly cosmetic.
- **Recommendation**: No change needed; this is a behaviour choice, not a
  bug.

#### 22. `__pycache__` lives in the working tree
- **Evidence**: `scripts/__pycache__/` is present and currently untracked
  (in `.gitignore`).
- **Impact**: The release tarball excludes it via `release.yml:47-48`, so
  users don't see it, but contributors running `make lint` will have it
  appear in `git status`. Minor noise.
- **Recommendation**: Add `find . -name __pycache__ -type d -exec rm -rf
  {} +` to `make lint`, or just `rm -rf scripts/__pycache__`.

#### 23. The Python scripts read config at import time, not at call time
- **Evidence**: `voxtype-clean-dictation:56` and `voxtype-rephrase:40` and
  `voxtype-summarize:42` do `MODEL = os.environ.get(...)` at module
  import.
- **Impact**: If a user changes their model in
  `~/.config/smart-dictate/config.toml` at runtime, the daemon needs a
  restart for it to take effect (because the post-process pipe is `exec`'d
  per dictation, this is fine for the daemon; for the rephrase/summarize
  scripts run by xbindkeys, every invocation re-imports, so it actually
  works there). Cosmetic only.
- **Recommendation**: Document this in `docs/configuration.md` so users
  know to restart the daemon after editing `[dictation]` / `[rephrase]`
  settings.

#### 24. `voxtype-paste-active` has a 50 ms `sleep` for no documented reason
- **Evidence**: `voxtype-paste-active:17` — `sleep 0.05`.
- **Impact**: Fragile race-condition guard. On a slow system the clipboard
  write may not be done; on a fast system it's wasted latency.
- **Recommendation**: Replace with a verify-read of the clipboard after
  writing, or document the race in the script header.

---

## Coverage

- **Architecture & structure**: Full file tree + all 7 Python/shell
  scripts reviewed. The three LLM-calling scripts have heavy duplication
  (finding 6).
- **Security**: API-key storage paths, file modes, log file contents,
  env-var precedence, sudo usage. Found 1 critical (finding 3).
- **Reliability**: Error handling, fallbacks, timeouts, race conditions,
  log growth. Found 1 critical (finding 1) and several high/medium.
- **Wayland / X11 split**: Reviewed every script that touches input or
  windows. Found the X11-only paste path (finding 1) and the Wayland
  packages that are installed but unused.
- **CI / release**: `.github/workflows/release.yml`, `Makefile`,
  `bootstrap.sh`, `install.sh` reviewed. Found missing PR CI (finding 4)
  and hard-pinned VoxType .deb (finding 5).
- **Documentation**: `README.md`, `docs/architecture.md`,
  `docs/configuration.md`, `docs/troubleshooting.md`, `AGENTS.md`,
  `.env.example` reviewed. Found stale 256-token claim (finding 18) and
  missing governance files (finding 19).
- **Tests**: None. `Makefile` only runs `bash -n` / `py_compile` / `sh -n`
  (finding 2).

## Commands run

- `git status --short`, `git log --oneline -5`, `git ls-files` (clean tree
  post-push; only release bundle files tracked)
- `make lint` (passes; 9 ok lines)
- File-by-file reads of all 7 scripts, 4 config files, 3 systemd units,
  `install.sh`, `bootstrap.sh`, `release.yml`, `Makefile`, `README.md`, all
  3 docs, `.env.example`, `.gitignore`
- Targeted `grep` for: `xdotool`/`xclip`/`Wayland`/`DISPLAY`/xbindkeysrc/
  `install -m`/`VOXTYPE_DEB`/`api_key` (confirmed the modes and hardcoded
  URL findings)

## Gaps and recommended next checks

- **No runtime verification**: I cannot run the installer on a live Wayland
  session to confirm the xdotool-paste failure mode end-to-end. The paste
  path should be tested on a default Ubuntu 24.04 GNOME Wayland install
  before any public release.
- **No load test on the LLM calls**: The 5 s timeout in
  `voxtype-clean-dictation` and the 8000 TPM cap should be exercised with
  a synthetic 4 000-character dictation to confirm fallback behaves.
- **No model-version matrix**: I did not check which VoxType releases are
  still API-compatible with the current `config/voxtype.toml` keys. If a
  new VoxType release renames `[vad].min_silence_duration_ms` or similar,
  the installer will silently miss it.
- **No fuzz testing on `should_skip`**: Worth adding a small property test
  that any string with one of the 8 code markers short-circuits regardless
  of length.
- **No SBOM / dependency manifest**: Even though everything is stdlib +
  system packages, a public release should ship a pinned apt-list for
  reproducibility.

## Feature gaps a public product should have

1. **In-product update check inside the dictation tray** — the tray
   already runs `smart-dictate check-updates` every 20 s
   (`voxtype-tray:128`) and posts a notification, but the user has to
   remember to run `upgrade`. A one-click "Upgrade Now" menu item that
   forks a terminal (like the existing "Calibrate Microphone" menu at
   `voxtype-tray:174-177`) would close the loop. This is partially there
   — `voxtype-tray:179-181` — but only if the menu is opened; no
   auto-prompt.
2. **First-run onboarding** — after install, the user is told to log out
   and back in, but not where to find the tray, what the keys are, or how
   to test the microphone. A one-time welcome notification with a link to
   a `docs/getting-started.md` would help.
3. **A "test the pipeline" command** — `smart-dictate test` that pipes a
   known string through `voxtype-clean-dictation` and reports the result,
   no microphone needed. Useful for diagnosing Groq / model / key issues
   without recording audio.
4. **Recording indicator on the tray icon** — the tray is dim when
   "active" and bright when "idle", which is the inverse of what most
   users expect (intuitive UX is bright when recording, dim when idle).
   Worth re-checking the icon convention in `voxtype-tray:61-89`.
5. **Multi-mic / source selector in the tray** — `[audio] device =
   "default"` is hardcoded. Power users on PulseAudio/PipeWire with
   multiple sources (e.g. USB headset + laptop mic) can't switch from the
   tray.
6. **Local-only mode** — the installer + config currently assume Groq.
   Users without a Groq account or with privacy requirements cannot use
   the dictation cleanup at all. A "disable cleanup" toggle in
   `config/voxtype.toml` (set `post_process.command = ""`) would let the
   rest of the pipeline work without Groq; this works today but isn't
   documented.
7. **Snap / Flatpak packaging** — Ubuntu's snap store would dramatically
   increase reach. The installer is `apt-get`-coupled, which is the right
   choice for power users but blocks `snap install` discoverability.
8. **Health-check endpoint** — the daemon already writes
   `$XDG_RUNTIME_DIR/voxtype/state` (`config/voxtype.toml:6` →
   `state_file = "auto"`). A `smart-dictate health` subcommand that reads
   this file and reports a structured JSON would help monitoring tools
   and packaging CI.

## Recommended priority order

1. **Finding 1 (Wayland paste)** — biggest user-facing gap.
2. **Finding 3 (config.toml key mode)** — security default.
3. **Finding 2 (test suite scaffolding)** — safety net for future work.
4. **Finding 4 (PR CI)** — gates everything below.
5. **Finding 6 (dedupe scripts)** — reduces drift risk for the rest.
6. **Findings 5, 7–9** — reliability and integrity.
7. **Findings 10–20** — polish, docs, governance.
8. **Findings 21–24** — low-hanging cleanup.
