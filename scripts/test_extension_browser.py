#!/usr/bin/env python3
"""Run synthetic DOM tests in a separate headless Chrome profile; no accounts or network."""
import html
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from Resume.render_pdf import find_chrome_binary


def main():
    chrome = find_chrome_binary()
    if not chrome:
        raise SystemExit('Install Chrome to run the browser integration tests.')
    for portal in ('controls', 'greenhouse', 'lever', 'panel'):
        with tempfile.TemporaryDirectory(prefix='copilot-extension-test-') as temporary:
            folder = Path(temporary)
            page = ROOT / 'extension/tests' / (portal + '.html')
            if portal == 'panel':
                # Load the actual panel markup/scripts with test-only Chrome APIs.
                text = (ROOT / 'extension/panel.html').read_text()
                text = text.replace('<script src="core.js"', '<script src="' + (ROOT / 'extension/tests/panel-harness.js').as_uri() + '"></script><script src="core.js"')
                for filename in ('panel.css', 'core.js', 'panel.js'):
                    text = text.replace('"' + filename + '"', '"' + (ROOT / 'extension' / filename).as_uri() + '"')
                text = text.replace('</head>', '<script defer src="' + (ROOT / 'extension/tests/panel.test.js').as_uri() + '"></script></head>')
                page = folder / 'panel.html'
                page.write_text(text)
            output = folder / 'dom.html'
            with output.open('w') as stdout, (folder / 'chrome.log').open('w') as stderr:
                process = subprocess.Popen([chrome, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
                    '--disable-background-networking', '--disable-component-update', '--password-store=basic', '--use-mock-keychain',
                    '--user-data-dir=' + str(folder / 'profile'), '--virtual-time-budget=120000', '--dump-dom',
                    page.as_uri()], stdout=stdout, stderr=stderr, start_new_session=True)
                try:
                    deadline = time.monotonic() + 30
                    result = None
                    while time.monotonic() < deadline:
                        text = output.read_text()
                        match = re.search(r'<pre id="results">(.*?)</pre>', text, re.S)
                        if match and ('PASS:' in match[1] or 'FAIL:' in match[1]):
                            result = html.unescape(match[1])
                            break
                        if process.poll() is not None:
                            break
                        time.sleep(.1)
                    if not result or not result.startswith('PASS:'):
                        raise RuntimeError(f'{portal}: {result or "Chrome did not complete the test"}\n' + (folder / 'chrome.log').read_text()[-1500:])
                    print(portal + ': ' + result, flush=True)
                finally:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGTERM)
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.wait()
    print('Browser integration tests passed; no live application pages opened.')


if __name__ == '__main__':
    main()
