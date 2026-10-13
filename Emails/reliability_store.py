"""Small locked, atomic stores for local application and draft state."""
import json
import hashlib
import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
import fcntl

_LOCKS = {}
_GUARD = threading.Lock()

@contextmanager
def store_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _GUARD:
        lock = _LOCKS.setdefault(str(path.resolve()), threading.RLock())
    with lock:
        with path.with_suffix(path.suffix + '.lock').open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

def read_json(path, default):
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f'Cannot read {path}; history was preserved. Restore or repair it before continuing.') from exc

def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def application_operation_key(company, role, attempt=''):
    """Share the same operation identity across every outreach entry point."""
    labels = [str(value).strip().casefold() for value in (company, role, attempt)]
    return hashlib.sha256(json.dumps(labels).encode()).hexdigest()
