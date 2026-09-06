#!/usr/bin/env bash
# Helper script to launch resume generator with correct Python environment

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check potential Python paths
if [ -f "$DIR/../Emails/.python/python/bin/python3" ]; then
    PYTHON_EXEC="$DIR/../Emails/.python/python/bin/python3"
elif [ -f "$DIR/.python/python/bin/python3" ]; then
    PYTHON_EXEC="$DIR/.python/python/bin/python3"
elif [ -f "$DIR/venv/bin/python3" ]; then
    PYTHON_EXEC="$DIR/venv/bin/python3"
else
    PYTHON_EXEC="python3"
fi

exec "$PYTHON_EXEC" "$DIR/generate_resume.py" "$@"
