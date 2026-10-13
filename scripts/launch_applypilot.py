#!/usr/bin/env python3
"""Start the local review app on demand, or reconnect to an existing instance."""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
URL = 'http://127.0.0.1:8765'


def health(root=ROOT):
    try:
        with urllib.request.urlopen(URL + '/health', timeout=2) as response:
            value = json.load(response)
            from native_bridge import instance_id
            if value.get('product') != 'ApplyPilot' or value.get('api_version') != 1 or value.get('instance') != instance_id(root) or value.get('native_version') != 1:
                raise RuntimeError('Port 8765 belongs to another app or an older review server. Stop that server and launch ApplyPilot again.')
            return True
    except urllib.error.HTTPError as exc:
        raise RuntimeError('Port 8765 is occupied by another app or an older server. Stop it before launching ApplyPilot.') from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, ConnectionRefusedError):
            return False
        raise RuntimeError(f'Cannot inspect local port 8765: {exc.reason}') from exc


def ensure_service(root=ROOT):
    from Emails.reliability_store import store_lock
    with store_lock(root / '.applypilot_startup'):
        if not health(root):
            python = root / 'Emails/.python/python/bin/python3'
            if not python.exists():
                raise RuntimeError('Bundled Python is missing. Follow the repository setup instructions.')
            with (root / '.applypilot.log').open('ab') as log:
                process = subprocess.Popen([str(python), str(root / 'review_app.py')], cwd=root,
                                           stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
            for _ in range(40):
                time.sleep(.25)
                if health(root):
                    break
                if process.poll() is not None:
                    raise RuntimeError('ApplyPilot could not start. Read .applypilot.log in the project folder.')
            else:
                raise RuntimeError('ApplyPilot startup timed out. Read .applypilot.log before trying again.')
    return URL


def main():
    ensure_service()
    if not webbrowser.open(URL + '/setup'):
        raise RuntimeError('The browser could not open. Visit ' + URL + '/setup in Chrome.')
    print('ApplyPilot setup is open. After setup, use the Chrome extension on a job application.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('ApplyPilot: ' + str(exc), file=sys.stderr)
        sys.exit(1)
