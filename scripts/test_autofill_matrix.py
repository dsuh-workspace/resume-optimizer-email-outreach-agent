#!/usr/bin/env python3
"""Run isolated real-extension acceptance scenarios; never opens live forms."""
import concurrent.futures
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = [('greenhouse', mode) for mode in ('robinhood', 'modern', 'alias', 'missing-school', 'legacy', 'classic', 'challenge', 'dependent-rerender', 'conditional', 'extension-reload', 'late')] + [('lever', mode) for mode in ('modern', 'delayed', 'rerender', 'workflow')]

def run(scenario):
    node = shutil.which('node') or '/Applications/Visual Studio Code.app/Contents/MacOS/Code'
    result = subprocess.run([node, 'scripts/test_autofill_loaded.cjs', *scenario], cwd=ROOT,
                            env=dict(os.environ, ELECTRON_RUN_AS_NODE='1'), capture_output=True, text=True, timeout=160)
    return scenario, result

if __name__ == '__main__':
    if len(sys.argv) > 1:
        SCENARIOS = [tuple(value.split('/', 1)) for value in sys.argv[1:]]
    failed = False
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for future in concurrent.futures.as_completed([pool.submit(run, s) for s in SCENARIOS]):
            scenario, result = future.result()
            print('/'.join(scenario) + ': ' + ('PASS' if result.returncode == 0 else 'FAIL'), flush=True)
            if result.returncode:
                failed = True
                print(result.stdout + result.stderr, flush=True)
    sys.exit(1 if failed else 0)
