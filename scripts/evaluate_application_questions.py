#!/usr/bin/env python3
"""Explicit real-model evaluation with synthetic candidate data, never live form writes."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from extension_api import ExtensionAPI
from test_copilot import TestLocalReview


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--repeats', type=int, default=5)
    parser.add_argument('--writing', action='store_true', help='Evaluate grounded prose and missing qualifications instead of question interpretation.')
    args = parser.parse_args()
    if not 1 <= args.repeats <= 5:
        parser.error('Use one to five independent repetitions.')
    cases = json.loads((ROOT / 'extension/tests/preparation-questions.json').read_text())
    records = []
    fixture = TestLocalReview('test_review_shows_original_rewrite_and_skill_evidence')
    fixture.setUp()
    bridge = ExtensionAPI(fixture.store)
    try:
        if args.writing:
            cases = [
                {'question': 'Why does this analytics internship interest you? Connect your answer to an evidenced project.', 'needs_input': False},
                {'question': 'Describe a process improvement you made, preserving the timeframe of any result.', 'needs_input': False},
                {'question': 'Describe your professional nursing license and your clinical patient-care experience.', 'needs_input': True},
            ]
            for iteration in range(args.repeats):
                for case in cases:
                    payload = {'packet_id': fixture.id, 'url': 'https://job-boards.greenhouse.io/example/jobs/1',
                               'question': case['question'], 'description': 'An analytics internship using Python to improve business processes.',
                               'limit': 1000, 'word_limit': 80, 'evidence_scope': 'profile'}
                    try:
                        result = bridge.answer(payload)
                        records.append({'iteration': iteration + 1, 'question': case['question'], 'passed': not case['needs_input'], 'result': result})
                    except ValueError as exc:
                        records.append({'iteration': iteration + 1, 'question': case['question'],
                                        'passed': case['needs_input'] and str(exc).startswith('Your input is needed:'), 'error': str(exc)})
                    except Exception as exc:
                        records.append({'iteration': iteration + 1, 'passed': False, 'blocked': str(exc)})
                        break
                    finally:
                        args.output.parent.mkdir(parents=True, exist_ok=True)
                        args.output.write_text(json.dumps({'synthetic_only': True, 'cases': cases, 'runs': records}, indent=2))
                    print(f'Writing repetition {iteration + 1}: {"PASS" if records[-1]["passed"] else "FAIL"}', flush=True)
                if records[-1].get('blocked'):
                    break
            return 0 if len(records) == args.repeats * len(cases) and all(r['passed'] for r in records) else 1
        profile_path = fixture.store.root / 'Resume/master_profile.json'
        profile = json.loads(profile_path.read_text())
        profile['personal_info']['linkedin'] = 'linkedin.com/in/example'
        profile_path.write_text(json.dumps(profile))
        bridge.preferences({'facts': {'first_name': 'Alex', 'last_name': 'Example', 'city': 'Example City'},
                            'application_profile': {'education': [{'institution': 'Example University',
                            'degree': 'Bachelor of Science', 'major': 'Business Administration',
                            'status': 'expected', 'end': '2028-05'}]}})
        fields = [dict({k: v for k, v in case.items() if not k.startswith('expected')}, id=str(i), type='textarea') for i, case in enumerate(cases)]
        for iteration in range(args.repeats):
            raw = []
            def generate(prompt):
                response = ExtensionAPI.generate_answer(prompt)
                raw.append(response)
                return response
            bridge.generate = generate
            try:
                results = bridge.interpret_fields({'url': 'https://job-boards.greenhouse.io/example/jobs/1',
                                                  'company': 'Example', 'fields': fields}, lambda callback: callback())
                failures = []
                for i, case in enumerate(cases):
                    result = results[str(i)]
                    valid = (result.get('value') == case['expected']) if 'expected' in case else (
                        bool(result.get('written')) if case['expected_kind'] == 'written' else 'value' not in result and not result.get('written'))
                    if not valid:
                        failures.append({'case': i, 'expected': case, 'actual': result})
                records.append({'iteration': iteration + 1, 'passed': not failures, 'failures': failures,
                                'raw': raw, 'results': results})
                print(f'Repetition {iteration + 1}: {len(cases) - len(failures)}/{len(cases)}', flush=True)
            except Exception as exc:
                records.append({'iteration': iteration + 1, 'passed': False, 'blocked': str(exc)})
                print(f'Repetition {iteration + 1}: blocked: {exc}', flush=True)
                break
            finally:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps({'synthetic_only': True, 'cases': cases, 'runs': records}, indent=2))
    finally:
        bridge.state.pool.shutdown(wait=True)
        fixture.doCleanups()
    return 0 if len(records) == args.repeats and all(r['passed'] for r in records) else 1


if __name__ == '__main__':
    raise SystemExit(main())
