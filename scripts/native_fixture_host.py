"""Test-only native host: runs the production protocol against isolated fixture data."""
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from native_bridge import main, instance_id


def start(root):
    config = json.loads((root / 'fixture-native.json').read_text())
    url = 'http://127.0.0.1:' + str(config['port'])
    def healthy():
        try:
            with urllib.request.urlopen(url + '/health', timeout=1) as response:
                return json.load(response).get('instance') == instance_id(root)
        except OSError:
            return False
    if not healthy():
        process = subprocess.Popen([sys.executable, str(ROOT / 'scripts/extension_fixture_server.py'), '--serve', str(root), '--port', str(config['port'])], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        (root / 'fixture-server.pid').write_text(str(process.pid))
        for _ in range(60):
            if healthy():
                break
            if process.poll() is not None:
                raise RuntimeError('Fixture backend exited.')
            time.sleep(.1)
        else:
            raise RuntimeError('Fixture backend did not start.')
    return url


if __name__ == '__main__':
    main(root=Path(sys.argv[1]), starter=start, origin=sys.argv[2])
