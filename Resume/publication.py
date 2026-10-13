"""Complete packet publication; readers never discover staging directories."""
from contextlib import contextmanager
from pathlib import Path
import os
import shutil
import tempfile
import uuid

@contextmanager
def staged_packet(base, name):
    base = Path(base).resolve()
    base.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.packet-', dir=base))
    destination = base / (name + '_' + uuid.uuid4().hex)
    try:
        yield stage, destination
    finally:
        if stage.exists():
            shutil.rmtree(stage)

def publish_packet(stage, destination):
    stage, destination = Path(stage), Path(destination)
    required = ['tailored_resume.json', 'tailoring_report.md']
    if any(not (stage / name).is_file() for name in required) or any(len(list(stage.glob('*.' + suffix))) != 1 for suffix in ('pdf', 'html')):
        raise ValueError('Resume packet is incomplete; nothing was published.')
    if not any(p.name != 'tailoring_report.md' for p in stage.glob('*.md')):
        raise ValueError('Resume Markdown is missing; nothing was published.')
    if destination.exists():
        raise ValueError('Resume destination already exists; existing packet was preserved.')
    os.rename(stage, destination)
