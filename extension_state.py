"""Private, bounded local progress and asynchronous work for ApplyPilot."""
import fcntl
import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from Emails.reliability_store import atomic_write, read_json, store_lock

RETENTION = 30 * 86400


class ExtensionState:
    def __init__(self, root, clock=time.time):
        self.path = root / '.applypilot_state.json'
        self.clock = clock
        root.mkdir(parents=True, exist_ok=True)
        self.owner = (root / '.applypilot_worker.lock').open('a')
        try:
            fcntl.flock(self.owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.owner.close()
            raise RuntimeError('ApplyPilot preparation worker is already running for this project.') from exc
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='applypilot')
        self.guard = threading.RLock()
        self.closed = False
        try:
            with self.guard, store_lock(self.path):
                data = self._read()
                for job in data['jobs'].values():
                    if job['status'] in ('queued', 'running'):
                        job.update(status='interrupted', error='Local app restarted. Review and start a new request.')
                self._write(data)
        except BaseException:
            self.close()
            raise

    def close(self):
        """Drain work before releasing ownership; another worker may then recover."""
        with self.guard:
            self.closed = True
        self.pool.shutdown(wait=True)
        if not self.owner.closed:
            fcntl.flock(self.owner, fcntl.LOCK_UN)
            self.owner.close()

    def _read(self):
        data = read_json(self.path, {'sessions': {}, 'jobs': {}})
        cutoff = self.clock() - RETENTION
        for kind in ('sessions', 'jobs'):
            data[kind] = {k: v for k, v in data[kind].items() if v.get('updated', 0) > cutoff}
        return data

    def _write(self, data):
        atomic_write(self.path, json.dumps(data))

    def session(self, payload):
        key = payload.get('key')
        if not isinstance(key, str) or not 1 <= len(key) <= 500:
            raise ValueError('Invalid posting identity.')
        with self.guard, store_lock(self.path):
            if self.closed:
                raise RuntimeError('Preparation worker is shutting down.')
            data = self._read()
            action = payload.get('action', 'get')
            if action == 'save':
                value = payload.get('value')
                if not isinstance(value, dict) or len(json.dumps(value)) > 100000:
                    raise ValueError('Application progress exceeds the local storage limit.')
                data['sessions'][key] = {'value': value, 'updated': self.clock()}
                if len(data['sessions']) > 200:
                    oldest = min(data['sessions'], key=lambda k: data['sessions'][k]['updated'])
                    del data['sessions'][oldest]
            elif action == 'clear':
                data['sessions'].pop(key, None)
                data['jobs'] = {k: v for k, v in data['jobs'].items() if v.get('posting_key') != key}
            elif action == 'clear-all':
                data['sessions'] = {}
                data['jobs'] = {}
            elif action != 'get':
                raise ValueError('Unknown progress action.')
            self._write(data)
            return data['sessions'].get(key, {}).get('value', {})

    def job(self, payload, operation):
        action = payload.get('action', 'create')
        with self.guard, store_lock(self.path):
            if self.closed:
                raise RuntimeError('Preparation worker is shutting down.')
            data = self._read()
            if action in ('status', 'cancel'):
                identity = payload.get('id')
                if not identity and isinstance(payload.get('request_id'), str):
                    identity = hashlib.sha256(payload['request_id'].encode()).hexdigest()[:32]
                job = data['jobs'].get(identity)
                if not job:
                    raise ValueError('Job expired or does not exist.')
                if action == 'cancel' and job['status'] in ('queued', 'running'):
                    job.update(status='cancelled', updated=self.clock())
                self._write(data)
                return job
            if action != 'create':
                raise ValueError('Unknown job action.')
            key = payload.get('request_id')
            if not isinstance(key, str) or not 8 <= len(key) <= 100:
                raise ValueError('A stable request ID is required.')
            job_id = hashlib.sha256(key.encode()).hexdigest()[:32]
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            if job_id in data['jobs']:
                existing = data['jobs'][job_id]
                if existing['digest'] != digest:
                    raise ValueError('Request ID already belongs to different content.')
                return existing
            if sum(j['status'] in ('queued', 'running') for j in data['jobs'].values()) >= 4:
                raise ValueError('Four jobs are already active. Wait or cancel one.')
            job = {'id': job_id, 'digest': digest, 'status': 'queued', 'updated': self.clock(), 'kind': payload.get('kind'), 'posting_key': payload.get('posting_key')}
            data['jobs'][job_id] = job
            self._write(data)
        self.pool.submit(self._run, job_id, payload, operation)
        return job

    def _run(self, job_id, payload, operation):
        def publish(callback):
            # Cancellation and publication share one lock, so cancellation that wins
            # the race can never expose a resume packet.
            with self.guard, store_lock(self.path):
                data = self._read()
                if data['jobs'].get(job_id, {}).get('status') != 'running':
                    raise ValueError('Job cancelled.')
                result = callback()
                data['jobs'][job_id].update(status='complete', result=result, updated=self.clock())
                self._write(data)
                return result
        with self.guard, store_lock(self.path):
            data = self._read()
            job = data['jobs'].get(job_id)
            if not job or job['status'] != 'queued':
                return
            job.update(status='running', updated=self.clock())
            self._write(data)
        try:
            result = operation(payload, publish)
            update = {'status': 'complete', 'result': result}
        except Exception as exc:
            update = {'status': 'failed', 'error': str(exc)}
        with self.guard, store_lock(self.path):
            data = self._read()
            job = data['jobs'].get(job_id)
            if job and job['status'] == 'running':
                job.update(update, updated=self.clock())
                self._write(data)
