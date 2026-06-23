.PHONY: help install uninstall check dry-run status clean-api-key lint test

.DEFAULT: help

# Pass-through to install.sh so `make install` works the same as `./install.sh`.
install:           ## install (or upgrade) the pipeline
	@./install.sh

uninstall:         ## remove config, scripts, service
	@./install.sh --uninstall

check:             ## verify install state, no changes
	@./install.sh --check

dry-run:           ## show what install.sh would do, no changes
	@./install.sh --dry-run

# Print daemon state + recent log lines.
status:            ## show systemd status + recent log lines
	@systemctl --user --no-pager --full status voxtype.service || true
	@echo "---"
	@journalctl --user -u voxtype.service -n 30 --no-pager || true

# Remove the locally-stored Groq API key (does not touch the upstream key).
clean-api-key:     ## remove ~/.config/voxtype/groq-api-key
	@rm -f "$${XDG_CONFIG_HOME:-$$HOME/.config}/voxtype/groq-api-key"
	@echo "removed: $${XDG_CONFIG_HOME:-$$HOME/.config}/voxtype/groq-api-key"

# Lightweight syntax / lint sweep. install.sh is the entry point.
lint:              ## bash -n + py_compile + sh -n sweep
	@bash -n install.sh && echo "install.sh: bash -n ok"
	@python3 -m py_compile scripts/_voxtype_groq.py && echo "_voxtype_groq: py_compile ok"
	@python3 -m py_compile scripts/voxtype-clean-dictation && echo "voxtype-clean-dictation: py_compile ok"
	@python3 -m py_compile scripts/voxtype-rephrase && echo "voxtype-rephrase: py_compile ok"
	@python3 -m py_compile scripts/voxtype-summarize && echo "voxtype-summarize: py_compile ok"
	@python3 -m py_compile scripts/voxtype-tray && echo "voxtype-tray: py_compile ok"
	@python3 -m py_compile scripts/voxtype-calibrate-mic && echo "voxtype-calibrate-mic: py_compile ok"
	@python3 -m py_compile scripts/smart-dictate && echo "smart-dictate: py_compile ok"
	@sh -n scripts/voxtype-paste-active && echo "voxtype-paste-active: sh -n ok"

# Stdlib unittest suite (no pip deps). Covers the pure dictation logic.
test:              ## run unit tests (python3 unittest)
	@python3 -m unittest discover -s tests -p 'test_*.py'

help:              ## show this help
	@awk 'BEGIN {FS = ":.*?##"} /^[a-zA-Z_-]+:.*?##/ {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
