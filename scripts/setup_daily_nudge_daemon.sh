#!/bin/bash
# ==============================================================================
# Automated Daily Follow-Up Daemon Setup (macOS launchd)
# Runs copilot.py --auto-nudge every weekday at 9:00 AM automatically.
# ==============================================================================

PLIST_NAME="com.danielsuh.copilot.autonudge"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
PROJECT_DIR="/Users/danielsuh/Documents/Coding Stuff/Job Applications"
PYTHON_BIN="${PROJECT_DIR}/Emails/.python/python/bin/python3"
LOG_DIR="${PROJECT_DIR}/logs"

mkdir -p "$LOG_DIR"
mkdir -p "$HOME/Library/LaunchAgents"

echo "⚙️ Installing automated background daily follow-up daemon..."

cat << EOF > "$PLIST_PATH"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_BIN}</string>
        <string>${PROJECT_DIR}/copilot.py</string>
        <string>--auto-nudge</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>
    <key>StartCalendarInterval</key>
    <array>
        <dict>
            <key>Weekday</key>
            <integer>1</integer>
            <key>Hour</key>
            <integer>9</integer>
            <key>Minute</key>
            <integer>0</integer>
        </dict>
        <dict>
            <key>Weekday</key>
            <integer>2</integer>
            <key>Hour</key>
            <integer>9</integer>
            <key>Minute</key>
            <integer>0</integer>
        </dict>
        <dict>
            <key>Weekday</key>
            <integer>3</integer>
            <key>Hour</key>
            <integer>9</integer>
            <key>Minute</key>
            <integer>0</integer>
        </dict>
        <dict>
            <key>Weekday</key>
            <integer>4</integer>
            <key>Hour</key>
            <integer>9</integer>
            <key>Minute</key>
            <integer>0</integer>
        </dict>
        <dict>
            <key>Weekday</key>
            <integer>5</integer>
            <key>Hour</key>
            <integer>9</integer>
            <key>Minute</key>
            <integer>0</integer>
        </dict>
    </array>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/autonudge.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/autonudge_error.log</string>
</dict>
</plist>
EOF

# Unload previous instance if exists, then load new
launchctl unload "$PLIST_PATH" 2>/dev/null
launchctl load "$PLIST_PATH"

echo "✅ SUCCESS: Daily Follow-Up Daemon installed and active!"
echo "📅 Schedule: Monday–Friday at 9:00 AM"
echo "📄 Logs: ${LOG_DIR}/autonudge.log"
