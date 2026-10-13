#!/usr/bin/env python3
"""Optional macOS background checks, gated to 09:10 Pacific on weekdays."""
import argparse
import datetime
import os
from pathlib import Path
import plistlib
import subprocess
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'Emails'))
from reliability_store import atomic_write, read_json, store_lock

PACIFIC = ZoneInfo('America/Los_Angeles')
LABEL = 'com.danielsuh.copilot.autonudge'
STATE = ROOT / 'logs' / 'daily_nudge_state.json'


def is_check_time(now):
    local = now.astimezone(PACIFIC)
    return local.weekday() < 5 and local.time() >= datetime.time(9, 10)


def build_plist():
    return {
        'Label': LABEL,
        'ProgramArguments': [sys.executable, str(Path(__file__).resolve())],
        'WorkingDirectory': str(ROOT),
        'StartInterval': 300,
        # The interval plus Pacific gate keeps the job correct if macOS changes time zones.
        'RunAtLoad': True,
        'StartCalendarInterval': [{'Weekday': d, 'Hour': 9, 'Minute': 10} for d in range(1, 6)],
        'StandardOutPath': str(ROOT / 'logs' / 'autonudge.log'),
        'StandardErrorPath': str(ROOT / 'logs' / 'autonudge_error.log'),
        'EnvironmentVariables': {'COPILOT_NONINTERACTIVE': '1'},
    }


def run_daily_check(now=None):
    now = now or datetime.datetime.now(PACIFIC)
    if not is_check_time(now):
        return False
    day = now.astimezone(PACIFIC).date().isoformat()
    with store_lock(STATE):
        state = read_json(STATE, {})
        if state.get('completed_date') == day:
            return False
        os.environ['COPILOT_NONINTERACTIVE'] = '1'
        from tracker import process_due_touch2_nudges, load_applications
        process_due_touch2_nudges()
        sequences = [seq for app in load_applications() for seq in (app.get('outreach_sequences') or [app])]
        if any(str(seq.get('touch2_status', '')).startswith('Paused:') for seq in sequences):
            print('One or more contact sequences are paused; the next check will retry.', flush=True)
            return False
        import json
        atomic_write(STATE, json.dumps({'completed_date': day}))
        print(f'{day}: draft-only follow-up check completed.', flush=True)
        return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install', action='store_true')
    parser.add_argument('--dry-run', action='store_true', help='Print the launchd configuration without installing or running it')
    args = parser.parse_args()
    if args.dry_run:
        print(plistlib.dumps(build_plist()).decode())
        return
    if args.install:
        destination = Path.home() / 'Library' / 'LaunchAgents' / f'{LABEL}.plist'
        destination.parent.mkdir(parents=True, exist_ok=True)
        (ROOT / 'logs').mkdir(exist_ok=True)
        destination.write_bytes(plistlib.dumps(build_plist()))
        domain = f'gui/{os.getuid()}'
        subprocess.run(['launchctl', 'bootout', f'{domain}/{LABEL}'], capture_output=True)
        subprocess.run(['launchctl', 'bootstrap', domain, str(destination)], check=True)
        print('Installed: one successful weekday check from 9:10 AM Pacific, with a five-minute retry/catch-up interval. Drafts only.')
        return
    run_daily_check()


if __name__ == '__main__':
    main()
