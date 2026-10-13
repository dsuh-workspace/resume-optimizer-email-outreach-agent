"""Narrow Chrome native handshake. Installation is an explicit local setup action."""
import base64
import hashlib
import json
import secrets
import struct
import sys
import time
from pathlib import Path
from Emails.reliability_store import atomic_write, read_json, store_lock

HOST = 'com.applypilot.companion'
ROOT = Path(__file__).resolve().parent


def extension_id(root=ROOT):
    key = json.loads((root / 'extension/manifest.json').read_text())['key']
    digest = hashlib.sha256(base64.b64decode(key, validate=True)).hexdigest()[:32]
    return ''.join(chr(ord('a') + int(char, 16)) for char in digest)


def instance_id(root):
    return hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:24]


def registration_path():
    return Path.home() / 'Library/Application Support/Google/Chrome/NativeMessagingHosts' / (HOST + '.json')


def status(root=ROOT, registration=None):
    identity = extension_id(root)
    access = read_json(root / '.extension_access.json', {})
    grant = access.get('_native', {})
    registration = registration or registration_path()
    installed = read_json(registration, {})
    expected_path = str(root / 'scripts/native_host.sh')
    valid = (installed.get('path') == expected_path and installed.get('allowed_origins') == ['chrome-extension://' + identity + '/'])
    return {'installed': valid, 'enabled': valid and bool(grant.get('token')) and grant.get('id') == identity and secrets.compare_digest(access.get(identity, ''), hashlib.sha256(grant.get('token', '').encode()).hexdigest()),
            'extension_id': identity, 'extension_path': str(root / 'extension'),
            'last_connected': grant.get('last_connected'), 'relocated': bool(installed) and not valid}


def install(root=ROOT, registration=None):
    """No caller-controlled executable, origin or installation path in the HTTP API."""
    identity = extension_id(root)
    host = root / 'scripts/native_host.sh'
    python = root / 'Emails/.python/python/bin/python3'
    if not host.is_file() or not python.is_file():
        raise RuntimeError('ApplyPilot helper or bundled Python is missing. Repair the project installation first.')
    host.chmod(0o700)
    registration = registration or registration_path()
    access = root / '.extension_access.json'
    with store_lock(access):
        entries = read_json(access, {})
        token = secrets.token_urlsafe(32)
        atomic_write(registration, json.dumps({'name': HOST, 'description': 'ApplyPilot on-demand companion',
                     'path': str(host), 'type': 'stdio', 'allowed_origins': ['chrome-extension://' + identity + '/']}, indent=2))
        entries[identity] = hashlib.sha256(token.encode()).hexdigest()
        entries['_native'] = {'id': identity, 'token': token}
        atomic_write(access, json.dumps(entries))
    return status(root, registration)


def connect(message, origin, root=ROOT, starter=None):
    identity = extension_id(root)
    if origin != 'chrome-extension://' + identity + '/':
        raise PermissionError('This Chrome extension is not allowed.')
    if message != {'action': 'connect', 'version': 1}:
        raise ValueError('Only the ApplyPilot connection handshake is supported.')
    access = root / '.extension_access.json'
    def grant():
        entries = read_json(access, {})
        current = entries.get('_native', {})
        token = current.get('token', '')
        if current.get('id') != identity or not token or not secrets.compare_digest(entries.get(identity, ''), hashlib.sha256(token.encode()).hexdigest()):
            raise PermissionError('Connection is disabled. Open ApplyPilot.app and click Enable Chrome connection.')
        return entries, current
    with store_lock(access):
        grant()
    if starter is None:
        from scripts.launch_applypilot import ensure_service
        starter = ensure_service
    url = starter(root)
    # Re-check after startup so revocation racing the launch cannot issue credentials.
    with store_lock(access):
        entries, current = grant()
        current['last_connected'] = time.time()
        atomic_write(access, json.dumps(entries))
        return {'server': url, 'token': current['token'], 'version': 1}


def main(root=ROOT, starter=None, origin=None, source=None, sink=None):
    source = source or sys.stdin.buffer
    sink = sink or sys.stdout.buffer
    try:
        header = source.read(4)
        if len(header) != 4:
            raise ValueError('Missing native message.')
        size = struct.unpack('=I', header)[0]
        if not 0 < size <= 4096:
            raise ValueError('Invalid native message size.')
        body = source.read(size)
        if len(body) != size:
            raise ValueError('Incomplete native message.')
        result = connect(json.loads(body), origin if origin is not None else (sys.argv[1] if len(sys.argv) > 1 else ''), root, starter)
    except Exception as exc:
        result = {'error': str(exc)}
    encoded = json.dumps(result).encode()
    sink.write(struct.pack('=I', len(encoded)) + encoded)
    sink.flush()


if __name__ == '__main__':
    main()
