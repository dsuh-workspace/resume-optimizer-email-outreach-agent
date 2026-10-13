"""Local review and extension bridge. AI calls occur only on explicit answer requests."""
import copy
import hashlib
import json
import os
import re
import secrets
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from Emails.reliability_store import read_json, store_lock

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / 'review_ui'


class ReviewStore:
    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.output = self.root / 'Resume' / 'output'

    def packet_path(self, packet_id):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', packet_id):
            raise ValueError('Invalid packet identifier.')
        # IDs are opaque: callers cannot turn an HTTP path into a filesystem path.
        for path in self.output.glob('*/tailored_resume.json'):
            if path.parent.name.startswith('.') or path.is_symlink() or path.parent.is_symlink():
                continue
            if self.packet_id(path) == packet_id:
                return path
        raise FileNotFoundError('Application packet was not found.')

    @staticmethod
    def packet_id(path):
        return hashlib.sha256(path.parent.name.encode()).hexdigest()[:24]

    @staticmethod
    def revision(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def list_packets(self):
        packets = []
        for path in sorted(self.output.glob('*/tailored_resume.json'), key=lambda p: p.stat().st_mtime, reverse=True):
            if path.parent.name.startswith('.') or path.is_symlink() or path.parent.is_symlink():
                continue
            try:
                data = read_json(path, {})
                report = data.get('tailoring_report', {})
                packets.append({'id': self.packet_id(path), 'company': report.get('target_company') or data.get('target_company', 'Unknown company'),
                                'role': report.get('target_role') or data.get('target_role', 'Unknown role'),
                                'version': path.parent.name, 'edited': bool(data.get('review_revision'))})
            except (RuntimeError, AttributeError):
                packets.append({'id': self.packet_id(path), 'company': 'Unreadable packet', 'role': path.parent.name, 'version': path.parent.name})
        return packets

    @staticmethod
    def pdf_path(path):
        pdfs = [p for p in path.parent.glob('*.pdf') if not p.is_symlink()]
        if len(pdfs) != 1:
            raise ValueError('This packet must contain exactly one resume PDF.')
        return pdfs[0]

    def context(self, path, data):
        """Join only exact local packet paths or draft IDs, never fuzzy company matches."""
        inherited = read_json(path.parent / 'review_context.json', {})
        contacts = copy.deepcopy(inherited.get('contacts', []))
        messages = copy.deepcopy(inherited.get('messages', []))
        errors = []
        draft_ids = set()
        def same_folder(value):
            if not value:
                return False
            p = Path(value)
            if not p.is_absolute():
                p = self.root / p
            return p.resolve() == path.parent.resolve()
        try:
            apps = read_json(self.root / 'applications.json', [])
            if not isinstance(apps, list):
                raise ValueError('Application history is invalid.')
            for app in apps:
                if not (same_folder(app.get('output_dir')) or same_folder(str(Path(app['pdf_path']).parent) if app.get('pdf_path') else '')):
                    continue
                contacts.extend(dict(record, kind=kind) for kind, record in app.get('contact_verifications', {}).items())
                draft_ids.update(str(app[k]) for k in ('touch1_draft_id', 'recruiter_draft_id', 'touch2_draft_id') if app.get(k))
                for sequence in app.get('outreach_sequences', []):
                    draft_ids.update(str(sequence[k]) for k in ('touch1_draft_id', 'touch2_draft_id') if sequence.get(k))
        except (RuntimeError, ValueError, TypeError, AttributeError) as exc:
            errors.append('Could not load contact history: ' + str(exc))
        try:
            registry = read_json(self.root / '.draft_registry.json', {})
            if not isinstance(registry, dict):
                raise ValueError('Draft registry is invalid.')
            for entry in registry.values():
                snapshot = entry.get('review_snapshot') or {}
                attachment = snapshot.get('attachment_path')
                draft_id = str((entry.get('draft') or {}).get('id', ''))
                if same_folder(str(Path(attachment).parent) if attachment else '') or (draft_id and draft_id in draft_ids):
                    messages.append(dict(snapshot, draft_id=draft_id, state=entry.get('state', 'unknown')))
        except (RuntimeError, ValueError, TypeError, AttributeError) as exc:
            errors.append('Could not load draft snapshots: ' + str(exc))
        # Local text is shown literally, not rendered as untrusted HTML.
        notes = []
        for name in ('review_packet.md', 'outreach_review_packet.md'):
            p = path.parent / name
            if p.is_file() and not p.is_symlink():
                notes.append(p.read_text(encoding='utf-8'))
        unique = lambda records: list({json.dumps(x, sort_keys=True): x for x in records}.values())
        return {'contacts': unique(contacts), 'messages': unique(messages), 'notes': '\n\n'.join(notes) or inherited.get('notes', ''), 'errors': errors}

    def load_packet(self, packet_id, *, allow_view_only=False):
        """Capture, validate and export one snapshot; detect concurrent replacement."""
        path = self.packet_path(packet_id)
        profile_path = self.root / 'Resume' / 'master_profile.json'
        captures = {}
        def capture(file):
            before = file.stat()
            content = file.read_bytes()
            after = file.stat()
            stamp = lambda st: (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
            if stamp(before) != stamp(after):
                raise ValueError('Packet changed while reading. Reload it before continuing.')
            captures[file] = (stamp(after), content)
            return content
        raw = capture(path)
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError('Packet JSON must be an object.')
        problems, evidence, pdf, content, profile = [], {}, None, b'', {}
        try:
            pdf = self.pdf_path(path)
            content = capture(pdf)
            if data.get('artifact_sha256') != hashlib.sha256(content).hexdigest():
                raise ValueError('PDF checksum is missing or differs from the saved packet. Regenerate this packet.')
            if data.get('evidence_version') != 1:
                raise ValueError('This older packet has no source evidence. Regenerate this packet.')
            from Resume.evidence import validate_saved_resume
            profile = json.loads(capture(profile_path))
            evidence = validate_saved_resume(data, profile)
        except (ValueError, RuntimeError, KeyError, TypeError, OSError) as exc:
            problems.append(str(exc))
        for file, (stamp, original) in captures.items():
            st = file.stat()
            if stamp != (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns) or file.read_bytes() != original:
                raise ValueError('Packet changed while reading. Reload it before continuing.')
        if pdf and self.pdf_path(path) != pdf:
            raise ValueError('Packet changed while reading. Reload it before continuing.')
        if problems and not allow_view_only:
            raise ValueError('Packet unavailable for autofill: ' + '\n'.join(problems))
        return dict(path=path, data=data, revision=hashlib.sha256(raw).hexdigest(),
                    pdf=pdf, pdf_bytes=content, evidence=evidence, profile=profile, problems=problems)

    def detail(self, packet_id, snapshot=None):
        snapshot = snapshot or self.load_packet(packet_id, allow_view_only=True)
        path, data = snapshot['path'], snapshot['data']
        report = data.get('tailoring_report', {})
        problems, pdf, evidence = snapshot['problems'], snapshot['pdf'], snapshot['evidence']
        bullets = []
        evidence_rows = iter(evidence.get('bullets', []))
        for ei, exp in enumerate(data.get('experiences', [])):
            for bi, bullet in enumerate(exp.get('bullets', [])):
                row = next(evidence_rows, {}) if not problems else {}
                bullets.append({'experience': ei, 'index': bi, 'company': exp.get('company', ''), 'role': exp.get('role', ''),
                                'text': bullet if isinstance(bullet, str) else bullet.get('text', ''),
                                'original': row.get('original', []), 'source_refs': row.get('source_refs', [])})
        return {'id': packet_id, 'revision': snapshot['revision'], 'company': report.get('target_company') or data.get('target_company', ''),
                'role': report.get('target_role') or data.get('target_role', ''), 'folder': path.parent.name,
                'editable': not problems, 'problems': problems, 'pdf_url': f'/api/packets/{packet_id}/pdf' if pdf else None,
                'bullets': bullets, 'skills': evidence.get('skills', []) if not problems else [],
                'review_revision': data.get('review_revision'), 'context': self.context(path, data)}

    def save(self, packet_id, payload):
        from Resume.evidence import validate_resume_evidence
        from Resume.render_pdf import save_resume_artifacts
        # tailor uses sibling imports in its existing CLI implementation.
        if str(ROOT / 'Resume') not in sys.path:
            sys.path.insert(0, str(ROOT / 'Resume'))
        from Resume.tailor import generate_report_markdown
        with store_lock(self.output / '.review-save'):
            snapshot = self.load_packet(packet_id, allow_view_only=True)
            detail = self.detail(packet_id, snapshot)
            if payload.get('revision') != detail['revision']:
                raise ValueError('The source packet changed. Reload it before saving.')
            if not detail['editable']:
                raise ValueError('\n'.join(detail['problems']))
            edits = payload.get('bullets')
            if not isinstance(edits, list) or len(edits) != len(detail['bullets']):
                raise ValueError('Provide every bullet; adding or removing bullets is not supported.')
            if any(not isinstance(s, str) or not s.strip() or len(s) > 2000 for s in edits):
                raise ValueError('Each bullet must contain between 1 and 2,000 characters.')
            if edits == [b['text'] for b in detail['bullets']]:
                raise ValueError('No bullet changes to save.')
            path = snapshot['path']
            data = copy.deepcopy(snapshot['data'])
            for row, text in zip(detail['bullets'], edits):
                data['experiences'][row['experience']]['bullets'][row['index']] = text.strip()
            validate_resume_evidence(data, read_json(self.root / 'Resume' / 'master_profile.json', {}))
            # The original score and narrative were computed before these manual edits.
            report = data['tailoring_report']
            for key in ('score_breakdown', 'matched_keywords', 'key_strengths_highlighted', 'interview_talking_points', 'core_pain_points_addressed'):
                report.pop(key, None)
            report['ats_match_score'] = 'Not recalculated after manual editing'
            data['review_revision'] = {'parent_id': packet_id, 'saved_at': datetime.now(timezone.utc).isoformat(),
                                       'note': 'Manual bullet edits. Existing Gmail drafts and attachments retain their original contents.'}
            folder = 'Review_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + secrets.token_hex(4)
            from Resume.publication import staged_packet, publish_packet
            with staged_packet(self.output, folder) as (stage, destination):
                artifacts = save_resume_artifacts(data, stage)
                data['artifact_sha256'] = hashlib.sha256(Path(artifacts['pdf']).read_bytes()).hexdigest()
                (stage / 'tailored_resume.json').write_text(json.dumps(data, indent=2), encoding='utf-8')
                (stage / 'tailoring_report.md').write_text(generate_report_markdown(report), encoding='utf-8')
                (stage / 'review_context.json').write_text(json.dumps(detail['context'], indent=2), encoding='utf-8')
                # Recheck the source immediately before publishing a manual revision.
                if self.load_packet(packet_id)['revision'] != snapshot['revision']:
                    raise ValueError('The source packet changed. Reload it before saving.')
                publish_packet(stage, destination)
            return self.detail(self.packet_id(destination / 'tailored_resume.json'))


def make_server(store=None, port=8765):
    from extension_api import ExtensionAPI
    store = store or ReviewStore()
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Do not put personal packet contents or cookies in logs.

        def respond(self, status, content, kind='application/json', cookie=False):
            if kind == 'application/json':
                content = json.dumps(content).encode()
            elif isinstance(content, str):
                content = content.encode()
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            if self.path.startswith('/extension/v1/') and extension.origin_id(self.headers.get('Origin')):
                self.send_header('Access-Control-Allow-Origin', self.headers['Origin'])
                self.send_header('Vary', 'Origin')
                self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
                self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type, X-Extension-Id')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; frame-src 'self'; object-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'none'")
            if cookie:
                self.send_header('Set-Cookie', f'review_session={token}; HttpOnly; SameSite=Strict; Path=/')
            self.end_headers()
            self.wfile.write(content)

        def authorized(self, mutation=False):
            host = f'127.0.0.1:{self.server.server_port}'
            if self.headers.get('Host') != host:
                return False
            if self.headers.get('Origin') not in (None, f'http://{host}'):
                return False
            if mutation or self.path.startswith('/api/'):
                cookie = SimpleCookie()
                try:
                    cookie.load(self.headers.get('Cookie', ''))
                except Exception:
                    return False
                if not cookie.get('review_session') or not secrets.compare_digest(cookie['review_session'].value, token):
                    return False
            return not mutation or secrets.compare_digest(self.headers.get('X-Review-Token', ''), token)

        def do_GET(self):
            if self.path.startswith('/extension/v1/'):
                return self.extension_request('GET')
            if not self.authorized():
                return self.respond(403, {'error': 'Open the review screen from its local URL.'})
            route = urlsplit(self.path).path
            try:
                if route == '/health':
                    from native_bridge import instance_id
                    return self.respond(200, {'product': 'ApplyPilot', 'api_version': 1, 'native_version': 1, 'instance': instance_id(store.root)})
                if route == '/api/setup/status':
                    from native_bridge import status
                    return self.respond(200, status(store.root))
                if route == '/setup':
                    return self.respond(200, (STATIC / 'setup.html').read_text().replace('__REVIEW_TOKEN__', token), 'text/html; charset=utf-8', True)
                if route == '/logo.svg':
                    return self.respond(200, (ROOT / 'extension/icons/logo.svg').read_bytes(), 'image/svg+xml')
                if route == '/':
                    return self.respond(200, (STATIC / 'index.html').read_text().replace('__REVIEW_TOKEN__', token), 'text/html; charset=utf-8', True)
                if route in ('/app.js', '/style.css', '/setup.js', '/setup.css'):
                    return self.respond(200, (STATIC / route[1:]).read_bytes(), 'text/javascript; charset=utf-8' if route.endswith('.js') else 'text/css; charset=utf-8')
                if route == '/api/packets':
                    return self.respond(200, store.list_packets())
                match = re.fullmatch(r'/api/packets/([a-f0-9]{24})(/pdf)?', route)
                if match:
                    if match[2]:
                        return self.respond(200, store.pdf_path(store.packet_path(match[1])).read_bytes(), 'application/pdf')
                    return self.respond(200, store.detail(match[1]))
                self.respond(404, {'error': 'Not found.'})
            except FileNotFoundError as exc:
                self.respond(404, {'error': str(exc)})
            except (ValueError, RuntimeError, OSError, TypeError, KeyError, AttributeError, IndexError) as exc:
                self.respond(400, {'error': str(exc)})

        def do_POST(self):
            if self.path.startswith('/extension/v1/'):
                return self.extension_request('POST')
            if not self.authorized(mutation=True):
                return self.respond(403, {'error': 'Review session expired or request came from another site. Reload the local screen.'})
            try:
                if self.path == '/api/setup/install':
                    self.read_payload()
                    from native_bridge import install
                    return self.respond(200, install(store.root))
                if self.path in ('/api/extension/pair-code', '/api/extension/revoke'):
                    payload = self.read_payload()
                    result = extension.create_code(payload.get('extension_id')) if self.path.endswith('pair-code') else extension.revoke()
                    return self.respond(200, result)
                match = re.fullmatch(r'/api/packets/([a-f0-9]{24})/save', self.path)
                if not match:
                    return self.respond(404, {'error': 'Not found.'})
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 100000 or self.headers.get('Content-Type') != 'application/json':
                    raise ValueError('Expected a JSON request under 100 KB.')
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise ValueError('Expected a JSON object.')
                self.respond(200, store.save(match[1], payload))
            except (ValueError, RuntimeError, OSError, TypeError, KeyError, AttributeError, IndexError) as exc:
                self.respond(400, {'error': str(exc)})
            except Exception:
                self.respond(500, {'error': 'PDF regeneration failed. The original packet was preserved. Check that Chrome is installed and retry.'})

        def read_payload(self):
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 150000 or self.headers.get('Content-Type') != 'application/json':
                raise ValueError('Expected a JSON request under 150 KB.')
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError('Expected a JSON object.')
            return payload

        def do_OPTIONS(self):
            if (self.path.startswith('/extension/v1/') and extension.origin_id(self.headers.get('Origin'))
                    and self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'):
                return self.respond(200, {})
            self.respond(403, {'error': 'Origin is not allowed.'})

        def extension_request(self, method):
            try:
                # Privileged extension GETs can omit Origin. The explicit ID is
                # still bound to the pairing code/token; ordinary web Origins
                # must never be replaced or trusted through this header.
                origin = self.headers.get('Origin') or ('chrome-extension://' + self.headers.get('X-Extension-Id', ''))
                if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}' or not extension.origin_id(origin):
                    raise PermissionError('Extension origin is not allowed.')
                route = self.path.removeprefix('/extension/v1')
                pairing = route == '/pair' and method == 'POST'
                if not pairing and not extension.authorized(origin, self.headers.get('Authorization', '')):
                    raise PermissionError('Extension is not paired. Connect from the local review screen.')
                payload = self.read_payload() if method == 'POST' else {}
                result = extension.pair(origin, payload.get('code')) if pairing else extension.dispatch(method, route, payload)
                self.respond(200, result)
            except PermissionError as exc:
                self.respond(403, {'error': str(exc)})
            except (ValueError, RuntimeError, OSError, TypeError, KeyError, AttributeError) as exc:
                self.respond(400, {'error': str(exc)})
            except Exception:
                self.respond(500, {'error': 'Answer service failed. No application fields were changed. Check local AI configuration and retry.'})

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    try:
        extension = ExtensionAPI(store)
    except Exception:
        server.server_close()
        raise
    original_close = server.server_close
    def close():
        original_close()
        extension.state.close()
    server.server_close = close
    server.daemon_threads = True
    return server


def serve(port=8765):
    server = make_server(port=port)
    print(f'Application review: http://127.0.0.1:{server.server_port}\nPress Ctrl+C to stop. All review data stays on this computer.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    serve(parser.parse_args().port)
