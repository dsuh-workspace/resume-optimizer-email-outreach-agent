"""Offline fixtures: test suites never touch real history, contacts or accounts."""
import tempfile
from pathlib import Path
from unittest.mock import patch


def isolate(test):
    import tracker
    import agent
    import gmail_draft
    import tailor
    temporary = tempfile.TemporaryDirectory()
    test.addCleanup(temporary.cleanup)
    folder = Path(temporary.name)
    (folder / 'contacts.csv').write_text('First Name,Last Name,Company,Status,Email,Resume Path\nAlex,Smith,Example,Pending,,\n')
    patches = [
        patch.object(tracker, 'APPLICATIONS_JSON_FILE', folder / 'applications.json'),
        patch.object(tracker, 'APPLICATIONS_MD_FILE', folder / 'APPLICATIONS.md'),
        patch.object(agent, 'BASE_DIR', folder),
        patch.object(gmail_draft, 'DRAFT_REGISTRY', folder / 'drafts.json'),
        patch.object(tailor, 'JD_CACHE_DIR', folder / 'jd_cache'),
        patch('contact_finder.check_domain_dns', return_value=(True, 'Mocked DNS')),
        patch('requests.sessions.Session.request', side_effect=RuntimeError('Network disabled in tests')),
        patch('copilot.get_genai_client'),
        patch('copilot.notify_pipeline_completion'),
        patch('copilot.send_system_notification'),
        patch('copilot.open_in_file_manager'),
        patch('google.genai.Client', side_effect=RuntimeError('Gemini disabled in tests')),
        patch.object(gmail_draft, 'get_gmail_service', side_effect=RuntimeError('Gmail disabled in tests')),
    ]
    for replacement in patches:
        replacement.start()
        test.addCleanup(replacement.stop)
    test.fixture_dir = folder
