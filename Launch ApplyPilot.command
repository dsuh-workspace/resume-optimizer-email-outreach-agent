#!/bin/zsh
cd -- "${0:A:h}" || exit 1
Emails/.python/python/bin/python3 scripts/launch_applypilot.py
if [[ $? -ne 0 ]]; then
  read '?Press Return to close…'
fi
