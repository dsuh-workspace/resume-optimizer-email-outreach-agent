"""Explicitly invoked three-question live-model smoke test with synthetic evidence only."""
import json
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from test_copilot import TestLocalReview
from extension_api import ExtensionAPI


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--question-index', type=int, choices=range(3))
    args = parser.parse_args()
    fixture = TestLocalReview()
    fixture.setUp()
    bridge = ExtensionAPI(fixture.store)
    try:
        results = []
        questions = [
            ('Briefly describe your key skills or areas of expertise.', 180),
            ('Describe your relevant automation experience.', 300),
            ('How does your experience relate to this Python automation role?', 450),
        ]
        if args.question_index is not None:
            questions = [questions[args.question_index]]
        for question, limit in questions:
            result = bridge.answer({'packet_id': fixture.id, 'revision': fixture.store.revision(fixture.path),
                                    'url': 'https://jobs.lever.co/example/synthetic/apply',
                                    'question': question, 'description': 'Synthetic role: automate business operations with Python.',
                                    'limit': limit})
            results.append({'question': question, 'limit': limit, **result})
        print(json.dumps(results, indent=2))
    finally:
        bridge.state.pool.shutdown(wait=True)
        fixture.doCleanups()


if __name__ == '__main__':
    main()
