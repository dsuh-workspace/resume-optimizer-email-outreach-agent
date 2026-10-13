#!/bin/zsh
# Chrome passes the calling extension origin as the first argument.
PROJECT_ROOT="${0:A:h:h}"
cd "$PROJECT_ROOT" || exit 1
exec "$PROJECT_ROOT/Emails/.python/python/bin/python3" "$PROJECT_ROOT/native_bridge.py" "$@"
