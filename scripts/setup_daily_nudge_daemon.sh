#!/bin/bash
# Install only when explicitly invoked; --dry-run prints the configuration.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="$PROJECT_DIR/Emails/.python/python/bin/python3"
if [[ ! -x "$PYTHON_BIN" ]]; then
    PYTHON_BIN="$(command -v python3)"
fi
exec "$PYTHON_BIN" "$SCRIPT_DIR/daily_nudge.py" --install "$@"
