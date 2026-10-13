"""Isolated fixture backend; no production profile, AI calls, or Chrome registration."""
import argparse
import json
import hashlib
import shlex
import shutil
import sys
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from test_copilot import TestLocalReview
from extension_api import ExtensionAPI
from review_app import make_server, ReviewStore

parser = argparse.ArgumentParser()
parser.add_argument('--native-profile')
parser.add_argument('--state-root')
parser.add_argument('--serve')
parser.add_argument('--pdf')
parser.add_argument('--port', type=int, default=0)
parser.add_argument('--expanded', action='store_true')
parser.add_argument('--workflow', action='store_true')
args = parser.parse_args()
fixture = None
if args.serve:
    store = ReviewStore(Path(args.serve))
else:
    fixture = TestLocalReview('test_review_shows_original_rewrite_and_skill_evidence')
    fixture.setUp()
    store = fixture.store
    if args.state_root:
        shutil.copytree(store.root, args.state_root)
        store = ReviewStore(Path(args.state_root))

if args.pdf:
    packet = next(store.output.glob('*/tailored_resume.json'))
    content = Path(args.pdf).read_bytes()
    (packet.parent / 'resume.pdf').write_bytes(content)
    data = json.loads(packet.read_text())
    data['artifact_sha256'] = hashlib.sha256(content).hexdigest()
    packet.write_text(json.dumps(data))

if args.expanded:
    profile_path = store.root / 'Resume/master_profile.json'
    profile = json.loads(profile_path.read_text())
    profile['experiences'].append({'company': 'Omitted Employer', 'role': 'Intern'})
    profile_path.write_text(json.dumps(profile))
    (store.root / '.application_answers.json').write_text((ROOT / 'extension/tests/application-profile.json').read_text())
    (store.root / 'fixture-fast').write_text('synthetic answers only')

if args.workflow:
    # Enrich only the disposable synthetic profile and revalidate its packet.
    from Resume.evidence import validate_resume_evidence
    profile_path = store.root / 'Resume/master_profile.json'
    profile = json.loads(profile_path.read_text())
    profile['personal_info'].update(email='sample@example.test', phone='202-555-0123',
                                    linkedin='linkedin.com/in/sample', github='github.com/sample')
    profile['experiences'][0]['date_range'] = 'January 2020 – March 2021'
    profile['experiences'].append({'id': 'beta', 'company': 'Beta', 'role': 'Analyst',
        'location': 'Berkeley', 'date_range': 'June 2022 – August 2023',
        'bullets': [{'text': 'Built Python tools.', 'tags': ['python']}]})
    profile_path.write_text(json.dumps(profile))
    packet_path = next(store.output.glob('*/tailored_resume.json'))
    data = json.loads(packet_path.read_text())
    data['experiences'][0]['date_range'] = profile['experiences'][0]['date_range']
    data['experiences'].append({'company': 'Beta', 'role': 'Analyst', 'location': 'Berkeley',
        'date_range': 'June 2022 – August 2023', 'bullets': ['Built Python tools.'],
        'bullet_source_refs': [['beta:bullet:0']]})
    data.pop('profile_evidence_sha256', None)
    packet_path.write_text(json.dumps(validate_resume_evidence(data, profile)))
    preference_path = store.root / '.application_answers.json'
    preferences = json.loads(preference_path.read_text())
    preferences['facts'].update(address='123 Example Street', city='Berkeley', state='California', postal_code='94704')
    preference_path.write_text(json.dumps(preferences))

def generate(prompt):
    time.sleep(.05 if (store.root / 'fixture-fast').exists() else 32)
    return {'answer': 'I saved 50 hours weekly using Python automation.', 'citations': ['experience:0:0']}

ExtensionAPI.generate_answer = staticmethod(generate)
server = make_server(store, port=args.port)
if args.native_profile:
    from native_bridge import install, HOST
    (store.root / 'extension').mkdir()
    shutil.copy(ROOT / 'extension/manifest.json', store.root / 'extension/manifest.json')
    python = store.root / 'Emails/.python/python/bin/python3'
    python.parent.mkdir(parents=True)
    python.symlink_to(sys.executable)
    host = store.root / 'scripts/native_host.sh'
    host.parent.mkdir()
    host.write_text('#!/bin/zsh\nexec ' + shlex.quote(sys.executable) + ' ' + shlex.quote(str(ROOT / 'scripts/native_fixture_host.py')) + ' ' + shlex.quote(str(store.root)) + ' "$@"\n')
    (store.root / 'fixture-native.json').write_text(json.dumps({'port': server.server_port}))
    install(store.root, Path(args.native_profile) / 'NativeMessagingHosts' / (HOST + '.json'))
print(server.server_port, flush=True)
try:
    server.serve_forever()
finally:
    server.server_close()
    if fixture:
        fixture.doCleanups()
