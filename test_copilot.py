import os
import unittest
import sys
from pathlib import Path

from copilot import ROOT_DIR, RESUME_DIR, EMAILS_DIR
import tailor
import render_pdf
import agent
import gmail_draft
import resume_finder

def _run_coro(coro):
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)

class TestCopilotSupervisorSuite(unittest.TestCase):

    def setUp(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent if Path(__file__).parent.name in ('Emails', 'Resume') else Path(__file__).parent))
        from testing_support import isolate
        isolate(self)


    @staticmethod
    def render_fixture(data, folder):
        result = {'page_count': 1}
        for suffix in ('pdf', 'md', 'html'):
            path = Path(folder) / ('resume.' + suffix)
            path.write_text('mock rendered artifact')
            result[suffix] = str(path)
        return result

    def test_paths_and_subdirectories_exist(self):
        """Verifies that Root, Resume, and Emails project directories are present and resolved."""
        self.assertTrue(ROOT_DIR.exists())
        self.assertTrue(RESUME_DIR.exists())
        self.assertTrue(EMAILS_DIR.exists())
        self.assertTrue((RESUME_DIR / "master_profile.json").exists())
        self.assertTrue((EMAILS_DIR / "email-agent-context.md").exists())

    def test_subagent_modules_loaded(self):
        """Verifies that all worker specialist subagents and tools are loaded and callable."""
        self.assertTrue(callable(tailor.tailor_resume))
        self.assertTrue(callable(render_pdf.save_resume_artifacts))
        self.assertTrue(callable(agent.generate_email_draft_async))
        self.assertTrue(callable(gmail_draft.create_gmail_draft))
        self.assertTrue(callable(resume_finder.find_tailored_resume))

    def test_tracker_record_and_render(self):
        """Verifies that tracker records application entries and renders APPLICATIONS.md dashboard."""
        import tracker
        sample_app = {
            "company": "TestCompanyCorp",
            "role": "Product Specialist",
            "stage": "Draft Staged",
            "ats_score": 92,
            "pdf_path": "/fake/path/resume.pdf",
            "recruiter_name": "Alex Smith",
            "touch2_due_date": "2026-09-02"
        }
        entry = tracker.record_application(sample_app)
        self.assertEqual(entry["company"], "TestCompanyCorp")
        self.assertTrue(tracker.APPLICATIONS_JSON_FILE.exists())
        self.assertTrue(tracker.APPLICATIONS_MD_FILE.exists())

        # Verify update stage (standard and role-specific)
        updated = tracker.update_application_stage("TestCompanyCorp", "Interviewing")
        self.assertTrue(updated)

        # Verify role-specific match
        updated_role = tracker.update_application_stage("TestCompanyCorp", "Offer", role_query="Product Specialist")
        self.assertTrue(updated_role)

        # Cleanup test entry
        apps = tracker.load_applications()
        cleaned = [a for a in apps if a.get("company") != "TestCompanyCorp"]
        tracker.save_applications(cleaned)

    def test_agents_manifest_exists(self):
        """Verifies that AGENTS.md exists and contains the multi-agent specification."""
        manifest = ROOT_DIR / "AGENTS.md"
        self.assertTrue(manifest.exists())
        content = manifest.read_text(encoding="utf-8")
        self.assertIn("Multi-Agent System Manifest", content)
        self.assertIn("Fail-Fast", content)
        self.assertIn("Resume Specialist", content)
        self.assertIn("Outreach & Email Specialist", content)

    def test_contact_finder_xray_and_ranking(self):
        """Verifies Google X-Ray links and ranked contact discovery functions."""
        from contact_finder import generate_xray_search_links, discover_ranked_contacts, verify_or_synthesize_email
        xrays = generate_xray_search_links("Stripe", "Associate Product Manager")
        self.assertIn("hiring_manager_xray", xrays)
        self.assertIn("linkedin.com", xrays["hiring_manager_xray"])
        self.assertIn("hiring_beacon_posts", xrays)

        from unittest.mock import patch
        with patch('agent.find_email_via_hunter', return_value=('john.doe@stripe.com', 90)):
            email, score = verify_or_synthesize_email("John", "Doe", "Stripe")
        self.assertEqual(email, 'john.doe@stripe.com')
        self.assertEqual(score, 90)

    def test_hunter_failsafe_loop_simulation(self):
        """Verifies prompt_hunter_failsafe_loop handles exit and candidate iteration cleanly."""
        from contact_finder import prompt_hunter_failsafe_loop
        from unittest.mock import patch

        # Test stop/exit trigger - returns (None, None, None) to end workflow without fallback alias
        inputs_stop = iter(["stop"])
        name, email, pos = prompt_hunter_failsafe_loop("Stripe", "APM", "Hiring Manager", input_func=lambda _: next(inputs_stop))
        self.assertIsNone(name)
        self.assertIsNone(email)
        self.assertIsNone(pos)

        # Test valid candidate entry with mocked Hunter finder
        inputs_candidate = iter(["David Song", "Group PM"])
        with patch("agent.find_email_via_hunter", return_value=("david.song@stripe.com", 90)):
            name, email, pos = prompt_hunter_failsafe_loop("Stripe", "APM", "Hiring Manager", input_func=lambda _: next(inputs_candidate))
        self.assertEqual(name, "David Song")
        self.assertIn("@stripe.com", email)

    def test_process_due_touch2_nudges_logic(self):
        """Verifies process_due_touch2_nudges detects past-due follow-ups and reply status."""
        import tracker

        # Insert a simulated past-due application
        test_app = {
            "company": "NudgeTestCo",
            "role": "Product Lead",
            "stage": "Draft Staged",
            "hiring_manager_name": "Taylor Swift",
            "hiring_manager_email": "taylor@nudgetestco.com",
            "touch2_due_date": "2020-01-01",  # Past date
            "touch2_status": "Scheduled",
            "touch2_subject": "Following up: Product Lead — Daniel Suh",
            "touch2_body": "Hi Taylor, following up in case my note got buried."
        }
        tracker.record_application(test_app)

        # Process with auto_send=False and stage_draft=False to simulate without making live network calls
        processed = tracker.process_due_touch2_nudges(auto_send=False, stage_draft=False)

        # Cleanup
        apps = tracker.load_applications()
        cleaned = [a for a in apps if a.get("company") != "NudgeTestCo"]
        tracker.save_applications(cleaned)

    def test_reauthorize_gmail_callable(self):
        """Verifies that reauthorize_gmail and check_thread_for_replies are present and callable."""
        from gmail_draft import reauthorize_gmail, check_thread_for_replies, SCOPES
        self.assertTrue(callable(reauthorize_gmail))
        self.assertTrue(callable(check_thread_for_replies))
        self.assertIn("gmail.modify", SCOPES[0])

    def test_supervisor_imports_email_validator(self):
        """Verifies that email_validator functions are imported and accessible from supervisor."""
        from copilot import is_valid_email, validate_email, sanitize_and_validate_email
        self.assertTrue(callable(is_valid_email))
        self.assertTrue(callable(validate_email))
        self.assertTrue(callable(sanitize_and_validate_email))
        self.assertTrue(is_valid_email("recruiter@stripe.com"))
        self.assertFalse(is_valid_email("bad-email"))

    def test_orchestrate_job_application_fails_fast_on_invalid_email(self):
        """Verifies orchestrate_job_application raises ValueError immediately when given an invalid contact email."""
        from copilot import orchestrate_job_application
        import asyncio

        sample_jd = "Company: Stripe\nRole: Associate Product Manager\nWe are looking for an APM with Python and product skills."

        # Test invalid HM email
        with self.assertRaises(ValueError) as ctx_hm:
            _run_coro(orchestrate_job_application(
                jd_text=sample_jd,
                hm_name="Alex Smith",
                hm_email="invalid-hm-email",
                stage_gmail=False,
                run_tests=False
            ))
        self.assertIn("Critical Failure", str(ctx_hm.exception))
        self.assertIn("Primary Contact email", str(ctx_hm.exception))

        # Test invalid Recruiter email
        with self.assertRaises(ValueError) as ctx_rec:
            _run_coro(orchestrate_job_application(
                jd_text=sample_jd,
                hm_name="Alex Smith",
                hm_email="alex@stripe.com",
                recruiter_name="Sarah Jenkins",
                recruiter_email="not-an-email@",
                stage_gmail=False,
                run_tests=False
            ))
        self.assertIn("Critical Failure", str(ctx_rec.exception))
        self.assertIn("Secondary Contact email", str(ctx_rec.exception))

    def test_orchestrate_job_application_single_contact_hm_only(self):
        """Verifies orchestrate_job_application succeeds when only Primary Contact (HM) is provided."""
        from copilot import orchestrate_job_application
        from unittest.mock import patch, AsyncMock
        import asyncio
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
            tf.write(b"%PDF-1.4 mock")
            mock_pdf = tf.name

        with tempfile.TemporaryDirectory() as tmp_out:
            try:
                sample_jd = "Company: Stripe\nRole: Associate Product Manager\nWe are looking for an APM."
                mock_tailored = {
                    "tailoring_report": {
                        "target_company": "Stripe",
                        "target_role": "Associate Product Manager",
                        "ats_match_score": 85,
                        "score_breakdown": {"matched_tech_skills": ["Python"]}
                    }
                }
                with patch("copilot.verify_gmail_access", return_value={"authenticated": True, "email_address": "test@berkeley.edu"}), \
                     patch("copilot.tailor_resume", return_value=mock_tailored), \
                     patch("copilot.save_resume_artifacts", side_effect=self.render_fixture), \
                     patch("copilot.discover_ranked_contacts", return_value={"candidates": []}), \
                     patch("copilot.run_seniority_sanity_audit", return_value={"recommended_p1": {}, "recommended_p2": {}}), \
                     patch("copilot.generate_email_draft_async", new=AsyncMock(return_value=("Subject", "This is a mock email body with sufficient text for the preview."))), \
                     patch("copilot.record_application", return_value={}):

                    result = _run_coro(orchestrate_job_application(
                        jd_text=sample_jd,
                        hm_name="David Song",
                        hm_email="david.song@stripe.com",
                        recruiter_name=None,
                        recruiter_email=None,
                        stage_gmail=False,
                        run_tests=False,
                        output_base_dir=Path(tmp_out)
                    ))
                    self.assertEqual(result["company"], "Stripe")
                    self.assertEqual(result["hiring_manager_email"], "david.song@stripe.com")
                    self.assertIsNone(result.get("recruiter_email"))
            finally:
                if os.path.exists(mock_pdf):
                    os.unlink(mock_pdf)

    def test_orchestrate_job_application_single_contact_recruiter_only(self):
        """Verifies orchestrate_job_application succeeds when only Secondary Contact (Recruiter) is provided."""
        from copilot import orchestrate_job_application
        from unittest.mock import patch, AsyncMock
        import asyncio
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
            tf.write(b"%PDF-1.4 mock")
            mock_pdf = tf.name

        with tempfile.TemporaryDirectory() as tmp_out:
            try:
                sample_jd = "Company: Stripe\nRole: Associate Product Manager\nWe are looking for an APM."
                mock_tailored = {
                    "tailoring_report": {
                        "target_company": "Stripe",
                        "target_role": "Associate Product Manager",
                        "ats_match_score": 85,
                        "score_breakdown": {"matched_tech_skills": ["Python"]}
                    }
                }
                with patch("copilot.verify_gmail_access", return_value={"authenticated": True, "email_address": "test@berkeley.edu"}), \
                     patch("copilot.tailor_resume", return_value=mock_tailored), \
                     patch("copilot.save_resume_artifacts", side_effect=self.render_fixture), \
                     patch("copilot.discover_ranked_contacts", return_value={"candidates": []}), \
                     patch("copilot.run_seniority_sanity_audit", return_value={"recommended_p1": {}, "recommended_p2": {}}), \
                     patch("copilot.generate_email_draft_async", new=AsyncMock(return_value=("Subject", "This is a mock email body with sufficient text for the preview."))), \
                     patch("copilot.record_application", return_value={}):

                    result = _run_coro(orchestrate_job_application(
                        jd_text=sample_jd,
                        hm_name=None,
                        hm_email=None,
                        recruiter_name="Sarah Jenkins",
                        recruiter_email="sarah.jenkins@stripe.com",
                        stage_gmail=False,
                        run_tests=False,
                        notify=False,
                        output_base_dir=Path(tmp_out)
                    ))
                    self.assertEqual(result["company"], "Stripe")
                    self.assertEqual(result["recruiter_email"], "sarah.jenkins@stripe.com")
                    self.assertIsNone(result.get("hiring_manager_email"))
            finally:
                if os.path.exists(mock_pdf):
                    os.unlink(mock_pdf)

    def test_notifier_module_functions(self):
        """Verifies that notifier functions (system notifications, sounds, pipeline completion) execute cleanly."""
        import notifier
        from unittest.mock import patch, MagicMock

        self.assertTrue(callable(notifier.play_alert_sound))
        self.assertTrue(callable(notifier.send_system_notification))
        self.assertTrue(callable(notifier.notify_pipeline_completion))

        # Test send_system_notification on macOS simulation
        with patch("platform.system", return_value="Darwin"), \
             patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_run, \
             patch("notifier.play_alert_sound", return_value=True):
            res = notifier.send_system_notification(
                title="Test Title",
                message="Test Message",
                subtitle="Test Subtitle",
                sound_name="Glass",
                play_sound=True
            )
            self.assertTrue(res)
            mock_run.assert_called_once()
            args, _ = mock_run.call_args
            self.assertIn("osascript", args[0])
            self.assertIn("Test Title", args[0][3:])

        # Test notify_pipeline_completion helper
        with patch("notifier.send_system_notification", return_value=True) as mock_send:
            res_comp = notifier.notify_pipeline_completion(
                company="Anthropic",
                role="Research Engineer",
                ats_score=95,
                contact_name="Dario Amodei",
                draft_staged=True
            )
            self.assertTrue(res_comp)
            mock_send.assert_called_once()
            call_kwargs = mock_send.call_args[1]
            self.assertEqual(call_kwargs["title"], "👑 Job Application Co-Pilot")
            self.assertIn("Anthropic", call_kwargs["subtitle"])
            self.assertIn("95/100", call_kwargs["message"])
            self.assertIn("Dario Amodei", call_kwargs["message"])

    def test_orchestrate_job_application_calls_notifier(self):
        """Verifies orchestrate_job_application triggers notify_pipeline_completion when notify=True."""
        from copilot import orchestrate_job_application
        from unittest.mock import patch, AsyncMock
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
            tf.write(b"%PDF-1.4 mock")
            mock_pdf = tf.name

        with tempfile.TemporaryDirectory() as tmp_out:
            try:
                sample_jd = "Company: Stripe\nRole: Associate Product Manager\nWe are looking for an APM."
                mock_tailored = {
                    "tailoring_report": {
                        "target_company": "Stripe",
                        "target_role": "Associate Product Manager",
                        "ats_match_score": 88,
                        "score_breakdown": {"matched_tech_skills": ["Python"]}
                    }
                }
                with patch("copilot.verify_gmail_access", return_value={"authenticated": True, "email_address": "test@berkeley.edu"}), \
                     patch("copilot.tailor_resume", return_value=mock_tailored), \
                     patch("copilot.save_resume_artifacts", side_effect=self.render_fixture), \
                     patch("copilot.discover_ranked_contacts", return_value={"candidates": []}), \
                     patch("copilot.run_seniority_sanity_audit", return_value={"recommended_p1": {}, "recommended_p2": {}}), \
                     patch("copilot.generate_email_draft_async", new=AsyncMock(return_value=("Subject", "This is a mock email body with sufficient text for the preview."))), \
                     patch("copilot.record_application", return_value={}), \
                     patch("copilot.notify_pipeline_completion") as mock_notify:

                    # 1. notify=True (default)
                    _run_coro(orchestrate_job_application(
                        jd_text=sample_jd,
                        hm_name="David Song",
                        hm_email="david.song@stripe.com",
                        recruiter_name=None,
                        recruiter_email=None,
                        stage_gmail=False,
                        run_tests=False,
                        notify=True,
                        output_base_dir=Path(tmp_out)
                    ))
                    mock_notify.assert_called_once_with(
                        company="Stripe",
                        role="Associate Product Manager",
                        ats_score=88,
                        contact_name="David Song",
                        draft_staged=False
                    )

                    # 2. notify=False
                    mock_notify.reset_mock()
                    _run_coro(orchestrate_job_application(
                        jd_text=sample_jd,
                        hm_name="David Song",
                        hm_email="david.song@stripe.com",
                        recruiter_name=None,
                        recruiter_email=None,
                        stage_gmail=False,
                        run_tests=False,
                        notify=False,
                        output_base_dir=Path(tmp_out)
                    ))
                    mock_notify.assert_not_called()
            finally:
                if os.path.exists(mock_pdf):
                    os.unlink(mock_pdf)

    def test_file_navigation_utilities(self):
        """Verifies open_in_file_manager and get_latest_output_packet behavior."""
        import notifier
        from unittest.mock import patch, MagicMock
        import tempfile

        # Test non-existent path
        self.assertFalse(notifier.open_in_file_manager("/path/does/not/exist/for/test"))

        # Test valid path macOS reveal
        with tempfile.NamedTemporaryFile(suffix=".pdf") as tf:
            with patch("platform.system", return_value="Darwin"), \
                 patch("subprocess.Popen") as mock_popen:
                res = notifier.open_in_file_manager(tf.name, reveal=True)
                self.assertTrue(res)
                mock_popen.assert_called_once_with(["open", "-R", tf.name])

        # Test get_latest_output_packet
        with tempfile.TemporaryDirectory() as td:
            p1 = Path(td) / "Folder1"
            p1.mkdir()
            (p1 / "test1.pdf").write_text("mock pdf")

            packet = notifier.get_latest_output_packet(output_base_dir=td)
            self.assertIsNotNone(packet)
            self.assertEqual(packet["folder_name"], "Folder1")
            self.assertTrue(packet["pdf"].endswith("test1.pdf"))

    def test_orchestrate_job_application_open_folder(self):
        """Verifies orchestrate_job_application triggers open_in_file_manager when open_folder=True."""
        from copilot import orchestrate_job_application
        from unittest.mock import patch, AsyncMock
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
            tf.write(b"%PDF-1.4 mock")
            mock_pdf = tf.name

        with tempfile.TemporaryDirectory() as tmp_out:
            try:
                sample_jd = "Company: Stripe\nRole: Associate Product Manager\nWe are looking for an APM."
                mock_tailored = {
                    "tailoring_report": {
                        "target_company": "Stripe",
                        "target_role": "Associate Product Manager",
                        "ats_match_score": 90,
                        "score_breakdown": {}
                    }
                }
                with patch("copilot.verify_gmail_access", return_value={"authenticated": True, "email_address": "test@berkeley.edu"}), \
                     patch("copilot.tailor_resume", return_value=mock_tailored), \
                     patch("copilot.save_resume_artifacts", side_effect=self.render_fixture), \
                     patch("copilot.discover_ranked_contacts", return_value={"candidates": []}), \
                     patch("copilot.run_seniority_sanity_audit", return_value={"recommended_p1": {}, "recommended_p2": {}}), \
                     patch("copilot.generate_email_draft_async", new=AsyncMock(return_value=("Subject", "Email content with sufficient length."))), \
                     patch("copilot.record_application", return_value={}), \
                     patch("copilot.notify_pipeline_completion"), \
                     patch("copilot.open_in_file_manager") as mock_open:

                    _run_coro(orchestrate_job_application(
                        jd_text=sample_jd,
                        hm_name="David Song",
                        hm_email="david.song@stripe.com",
                        recruiter_name=None,
                        recruiter_email=None,
                        stage_gmail=False,
                        run_tests=False,
                        notify=False,
                        open_folder=True,
                        output_base_dir=Path(tmp_out)
                    ))
                    mock_open.assert_called_once()
                    self.assertTrue(Path(mock_open.call_args.args[0]).is_file())
                    self.assertEqual(mock_open.call_args.kwargs, {'reveal': True})
            finally:
                if os.path.exists(mock_pdf):
                    os.unlink(mock_pdf)


class TestTrackerReliability(unittest.TestCase):
    def setUp(self):
        from testing_support import isolate
        isolate(self)

    def test_legacy_contact_migrates_before_new_contact(self):
        import tracker
        first = tracker.record_application({'company': 'Acme', 'role': 'PM', 'touch1_thread_id': 'old-thread', 'hiring_manager_email': 'old@acme.org', 'touch2_status': 'Awaiting Follow-Up'})
        tracker.record_application({'company': 'Acme', 'role': 'PM', 'outreach_sequences': [{'id': 'new', 'touch1_thread_id': 'new-thread', 'hiring_manager_email': 'new@acme.org'}]})
        sequences = tracker.load_applications()[0]['outreach_sequences']
        self.assertEqual(len(sequences), 2)
        self.assertEqual(sequences[0]['id'], first['id'])
        self.assertEqual(sequences[0]['touch1_thread_id'], 'old-thread')

    def test_staged_followup_monitoring_and_parent_outcomes(self):
        import tracker
        from unittest.mock import patch
        sequence = {'id': 'one', 'touch1_thread_id': 'thread', 'hiring_manager_email': 'alex@acme.org', 'touch2_status': 'Draft Staged', 'touch2_draft_id': 'draft', 'touch2_message_id': 'old-draft-message', 'touch2_operation_id': 'stable-operation'}
        tracker.record_application({'company': 'Acme', 'role': 'PM', 'outreach_sequences': [sequence]})
        status = {'touch1_sent': True, 'sent_at': '2020-01-03T20:00:00+00:00', 'sent_messages': [{'id': 'new-sent-message', 'operation_id': 'stable-operation', 'sent_at': '2020-01-07T20:00:00+00:00'}]}
        with patch('gmail_draft.check_thread_for_replies', return_value=status), patch('gmail_draft.create_gmail_draft') as create:
            tracker.process_due_touch2_nudges()
            self.assertEqual(tracker.load_applications()[0]['stage'], 'Touch 2 Sent')
            status['has_reply'] = True
            tracker.process_due_touch2_nudges()
            self.assertEqual(tracker.load_applications()[0]['stage'], 'Replied / In Conversation')
            create.assert_not_called()
        parent = {'stage': 'Interviewing'}
        tracker.aggregate_outreach(parent, [{'touch2_status': 'Draft Staged'}])
        self.assertEqual(parent['stage'], 'Interviewing')

    def test_outreach_history_preflight_before_external_work(self):
        import tracker
        import copilot
        from unittest.mock import patch
        tracker.APPLICATIONS_JSON_FILE.write_text('{corrupt')
        with patch('copilot.extract_name_from_input') as resolve, self.assertRaises(RuntimeError):
            _run_coro(copilot.outreach_from_linkedin_contact('Alex Example', company='Acme', role='PM'))
        resolve.assert_not_called()

    def test_corrupt_history_is_preserved(self):
        import tracker
        tracker.APPLICATIONS_JSON_FILE.write_text('{broken')
        with self.assertRaises(RuntimeError):
            tracker.record_application({'company': 'Acme', 'role': 'PM'})
        self.assertEqual(tracker.APPLICATIONS_JSON_FILE.read_text(), '{broken')

    def test_idempotent_records_and_explicit_attempt(self):
        import tracker
        first = tracker.record_application({'company': 'Acme', 'role': 'PM', 'notes': 'first'})
        second = tracker.record_application({'company': 'acme', 'role': 'pm', 'notes': 'second'})
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(len(tracker.load_applications()), 1)
        tracker.record_application({'company': 'Acme', 'role': 'PM', 'attempt': 'next-year'})
        self.assertEqual(len(tracker.load_applications()), 2)

    def test_interrupted_write_preserves_history(self):
        import tracker
        from unittest.mock import patch
        tracker.record_application({'company': 'Acme', 'role': 'PM'})
        original = tracker.APPLICATIONS_JSON_FILE.read_bytes()
        with patch('Emails.reliability_store.os.replace', side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):
                tracker.record_application({'company': 'Other', 'role': 'PM'})
        self.assertEqual(tracker.APPLICATIONS_JSON_FILE.read_bytes(), original)

    def test_concurrent_records_keep_both_updates(self):
        import tracker
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda company: tracker.record_application({'company': company, 'role': 'PM'}), ['One', 'Two']))
        self.assertEqual({a['company'] for a in tracker.load_applications()}, {'One', 'Two'})
        self.assertTrue(tracker.APPLICATIONS_JSON_FILE.with_suffix('.json.bak').exists())

    def followup(self, status):
        import tracker
        from unittest.mock import patch
        tracker.record_application({'company': 'Acme', 'role': 'PM', 'hiring_manager_email': 'alex@acme.org', 'touch1_thread_id': 'thread'})
        with patch('gmail_draft.check_thread_for_replies', return_value=status), patch('gmail_draft.create_gmail_draft', return_value={'id': 'draft'}) as create:
            result = tracker.process_due_touch2_nudges()
            calls = create.call_count
        return result, calls, tracker.load_applications()[0]

    def test_unsent_draft_never_stages_followup(self):
        result, calls, app = self.followup({'touch1_sent': False})
        self.assertEqual(calls, 0)
        self.assertEqual(app['touch2_due_date'], '')

    def test_gmail_error_pauses_followup(self):
        result, calls, app = self.followup({'error': 'expired token', 'touch1_sent': True})
        self.assertEqual(calls, 0)
        self.assertEqual(app['touch2_status'], 'Paused: Gmail Inspection Failed')
        self.assertEqual(result[0]['error'], 'expired token')
        import tracker
        self.assertIn('expired token', tracker.render_dashboard_markdown([app]))

    def test_sent_friday_uses_tuesday_and_stages_once(self):
        import tracker
        from unittest.mock import patch
        status = {'touch1_sent': True, 'has_reply': False, 'sent_at': '2020-01-03T20:00:00+00:00', 'first_message_id': '<sent>'}
        result, calls, app = self.followup(status)
        self.assertEqual(calls, 1)
        self.assertEqual(app['touch2_due_date'], '2020-01-07')
        with patch('gmail_draft.check_thread_for_replies', return_value=status), patch('gmail_draft.create_gmail_draft') as create:
            tracker.process_due_touch2_nudges()
            create.assert_not_called()

    def test_reply_cancels_followup(self):
        result, calls, app = self.followup({'touch1_sent': True, 'has_reply': True, 'sent_at': '2020-01-03T20:00:00+00:00'})
        self.assertEqual(calls, 0)
        self.assertEqual(app['touch2_status'], 'Replied (Sequence Cancelled)')

    def test_readonly_cli_does_not_process_nudges(self):
        from unittest.mock import patch
        import copilot
        with patch('sys.argv', ['copilot.py', '--tracker']), patch('copilot.process_due_touch2_nudges') as process:
            copilot.main()
            process.assert_not_called()

    def test_send_due_cli_is_rejected(self):
        from unittest.mock import patch
        import copilot
        with patch('sys.argv', ['copilot.py', '--auto-nudge', '--send-due']), self.assertRaises(SystemExit) as exc:
            copilot.main()
        self.assertEqual(exc.exception.code, 2)

    def test_review_packet_contains_evidence_and_verification(self):
        from copilot import render_review_packet
        report = {'ats_match_score': 80, 'evidence_review': {'bullets': [{'company': 'Acme', 'source_refs': ['exp:bullet:0'], 'original': ['Saved 50 hours'], 'rewritten': 'Automated work saving 50 hours'}], 'skills': []}}
        text = render_review_packet('Acme', 'PM', '/tmp/resume.pdf', report, {'recruiter': {'email': 'alex@acme.org', 'source': 'user-provided', 'status': 'unverified', 'checked_at': '2026-10-04'}}, [('alex@acme.org', 'Subject', 'Body')])
        for expected in ('Saved 50 hours', 'Automated work saving 50 hours', 'user-provided', '2026-10-04', 'Body', 'resume.pdf'):
            self.assertIn(expected, text)


class TestBackgroundAndPreservation(unittest.TestCase):
    def setUp(self):
        from testing_support import isolate
        isolate(self)

    def test_partial_update_preserves_packet_fields(self):
        import tracker
        tracker.record_application({'company': 'Acme', 'role': 'PM', 'pdf_path': '/tmp/existing.pdf', 'hiring_manager_email': 'alex@acme.org', 'touch1_staged': True})
        tracker.record_application({'company': 'Acme', 'role': 'PM', 'notes': 'Reviewed'})
        app = tracker.load_applications()[0]
        self.assertEqual(app['pdf_path'], '/tmp/existing.pdf')
        self.assertEqual(app['hiring_manager_email'], 'alex@acme.org')
        self.assertTrue(app['touch1_staged'])

    def test_separate_contacts_do_not_share_reply_state(self):
        import tracker
        from unittest.mock import patch
        seqs = [{'id': email, 'company': 'Acme', 'role': 'PM', 'hiring_manager_email': email, 'touch1_thread_id': email} for email in ('manager@acme.org', 'recruiter@acme.org')]
        tracker.record_application({'company': 'Acme', 'role': 'PM', 'outreach_sequences': seqs})
        def inspect(thread, recipient, **kwargs):
            return {'touch1_sent': True, 'sent_at': '2020-01-03T20:00:00+00:00', 'first_message_id': '<sent>', 'has_reply': recipient.startswith('manager')}
        with patch('gmail_draft.check_thread_for_replies', side_effect=inspect), patch('gmail_draft.create_gmail_draft', return_value={'id': 'draft'}) as create:
            tracker.process_due_touch2_nudges()
        self.assertEqual(create.call_count, 1)
        self.assertEqual(create.call_args.args[0], 'recruiter@acme.org')
        states = [seq['touch2_status'] for seq in tracker.load_applications()[0]['outreach_sequences']]
        self.assertEqual(states, ['Replied (Sequence Cancelled)', 'Draft Staged'])

    def test_background_pacific_weekday_and_dst_gate(self):
        import datetime
        from scripts.daily_nudge import is_check_time
        utc = datetime.timezone.utc
        self.assertFalse(is_check_time(datetime.datetime(2026, 10, 5, 16, 9, tzinfo=utc)))
        self.assertTrue(is_check_time(datetime.datetime(2026, 10, 5, 16, 10, tzinfo=utc)))
        self.assertFalse(is_check_time(datetime.datetime(2026, 10, 4, 18, 0, tzinfo=utc)))
        self.assertFalse(is_check_time(datetime.datetime(2026, 11, 2, 17, 9, tzinfo=utc)))
        self.assertTrue(is_check_time(datetime.datetime(2026, 11, 2, 17, 10, tzinfo=utc)))

    def test_background_runs_once_per_day_and_keeps_paths_portable(self):
        import datetime
        from scripts import daily_nudge
        from unittest.mock import patch
        now = datetime.datetime(2026, 10, 5, 16, 10, tzinfo=datetime.timezone.utc)
        with patch.object(daily_nudge, 'STATE', self.fixture_dir / 'daily.json'), patch('tracker.process_due_touch2_nudges') as process, patch.dict(os.environ, {}):
            self.assertTrue(daily_nudge.run_daily_check(now))
            self.assertFalse(daily_nudge.run_daily_check(now))
            self.assertEqual(process.call_count, 1)
        config = daily_nudge.build_plist()
        self.assertEqual(config['WorkingDirectory'], str(ROOT_DIR))
        self.assertEqual(config['StartInterval'], 300)
        self.assertEqual(config['EnvironmentVariables']['COPILOT_NONINTERACTIVE'], '1')

    def test_background_pauses_retry_without_marking_success(self):
        import datetime
        import tracker
        from scripts import daily_nudge
        from unittest.mock import patch
        tracker.record_application({'company': 'Acme', 'role': 'PM', 'outreach_sequences': [{'id': 'one', 'touch2_status': 'Paused: Gmail Inspection Failed'}]})
        now = datetime.datetime(2026, 10, 5, 16, 10, tzinfo=datetime.timezone.utc)
        with patch.object(daily_nudge, 'STATE', self.fixture_dir / 'daily.json'), patch('tracker.process_due_touch2_nudges'), patch.dict(os.environ, {}):
            self.assertFalse(daily_nudge.run_daily_check(now))
        self.assertFalse((self.fixture_dir / 'daily.json').exists())

    def test_readonly_commands_do_not_rewrite_real_history(self):
        from unittest.mock import patch
        import copilot
        with patch('sys.argv', ['copilot.py', '--tracker']), patch('copilot.process_due_touch2_nudges') as nudge, patch('tracker.save_applications') as save:
            copilot.main()
        nudge.assert_not_called()
        save.assert_not_called()

class TestLocalReview(unittest.TestCase):
    def setUp(self):
        import copy
        import hashlib
        import json
        import tempfile
        from Resume.test_resume import TestResumeEvidence
        from Resume.evidence import validate_resume_evidence
        from review_app import ReviewStore
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.folder = self.root / 'Resume/output/Example_PM_20260101'
        self.folder.mkdir(parents=True)
        fixture = TestResumeEvidence()
        fixture.setUp()
        self.profile = fixture.profile
        self.data = validate_resume_evidence(copy.deepcopy(fixture.data), self.profile)
        self.data['tailoring_report'].update(target_company='Example', target_role='PM', ats_match_score=90)
        self.pdf = self.folder / 'resume.pdf'
        self.pdf.write_bytes(b'original pdf fixture')
        self.data['artifact_sha256'] = hashlib.sha256(self.pdf.read_bytes()).hexdigest()
        self.path = self.folder / 'tailored_resume.json'
        self.path.write_text(json.dumps(self.data))
        (self.root / 'Resume/master_profile.json').write_text(json.dumps(self.profile))
        self.store = ReviewStore(self.root)
        self.id = self.store.packet_id(self.path)

    def payload(self, text='Saved 50 hours per week using Python automation.'):
        return {'revision': self.store.revision(self.path), 'bullets': [text]}

    def mock_render(self, data, folder):
        from Resume.render_pdf import generate_resume_html, generate_resume_markdown
        pdf = Path(folder) / 'resume.pdf'
        pdf.write_bytes(b'regenerated pdf fixture')
        (Path(folder) / 'resume.html').write_text(generate_resume_html(data))
        (Path(folder) / 'resume.md').write_text(generate_resume_markdown(data))
        return {'pdf': str(pdf), 'page_count': 1}

    def test_saved_factual_tampering_is_view_only(self):
        import copy, json
        for section, key, value in [('personal_info', 'full_name', 'Wrong Person'),
                                    ('education', 'degree', 'Doctorate'),
                                    ('education', 'gpa', '4.99')]:
            with self.subTest(key=key):
                changed = copy.deepcopy(self.data)
                target = changed[section] if section == 'personal_info' else changed[section][0]
                target[key] = value
                self.path.write_text(json.dumps(changed))
                self.assertFalse(self.store.detail(self.id)['editable'])

    def test_notification_text_is_never_script_source(self):
        from unittest.mock import patch
        import notifier
        text = "quotes\" \\ ' & $(echo bad)\nnew line"
        for platform in ('Darwin', 'Windows'):
            with patch('notifier.platform.system', return_value=platform), patch('notifier.subprocess.run') as run:
                notifier.send_system_notification(text, text, subtitle=text, sound_name=text, play_sound=False)
                command = run.call_args.args[0]
                self.assertNotIn(text, command[2])
                if platform == 'Darwin':
                    self.assertEqual(command[3], '--')
                    self.assertIn(text, command[4:])
                else:
                    self.assertEqual(run.call_args.kwargs['env']['APPLYPILOT_NOTIFICATION_MESSAGE'], text)

    def test_packet_rejects_changes_during_snapshot_capture(self):
        from unittest.mock import patch
        from Resume.evidence import validate_saved_resume
        def mutate(data, profile):
            result = validate_saved_resume(data, profile)
            self.path.write_text(self.path.read_text() + ' ')
            return result
        with patch('Resume.evidence.validate_saved_resume', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'changed while reading'):
                self.store.load_packet(self.id)

    def test_review_shows_original_rewrite_and_skill_evidence(self):
        detail = self.store.detail(self.id)
        self.assertTrue(detail['editable'])
        self.assertEqual(detail['bullets'][0]['original'], ['Saved 50 hours per week with Python automation.'])
        self.assertEqual(detail['bullets'][0]['source_refs'], ['exp:bullet:0'])
        self.assertEqual(detail['skills'][0]['rewritten'], 'Python')

    def test_old_packets_and_changed_pdfs_are_view_only(self):
        import json
        self.pdf.write_bytes(b'changed')
        self.assertFalse(self.store.detail(self.id)['editable'])
        self.data.pop('evidence_version')
        self.path.write_text(json.dumps(self.data))
        with self.assertRaisesRegex(ValueError, 'no source evidence|PDF checksum'):
            self.store.save(self.id, self.payload())

    def test_profile_changes_block_editing(self):
        import json
        self.profile['experiences'][0]['bullets'][0]['text'] = 'Saved 100 hours per week.'
        (self.root / 'Resume/master_profile.json').write_text(json.dumps(self.profile))
        self.assertFalse(self.store.detail(self.id)['editable'])

    def test_unsupported_claim_is_blocked_before_rendering(self):
        from unittest.mock import patch
        with patch('Resume.render_pdf.save_resume_artifacts') as render:
            with self.assertRaisesRegex(ValueError, 'Unsupported metric'):
                self.store.save(self.id, self.payload('Saved 90 hours per week.'))
            render.assert_not_called()
        self.assertEqual(len(self.store.list_packets()), 1)

    def test_revision_preserves_original_and_rebuilds_evidence(self):
        import hashlib
        import json
        from unittest.mock import patch
        original = self.path.read_bytes()
        with patch('Resume.render_pdf.save_resume_artifacts', side_effect=self.mock_render):
            result = self.store.save(self.id, self.payload())
        self.assertTrue(result['editable'])
        self.assertNotEqual(result['id'], self.id)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.pdf.read_bytes(), b'original pdf fixture')
        new_path = self.store.packet_path(result['id'])
        saved = json.loads(new_path.read_text())
        self.assertEqual(saved['artifact_sha256'], hashlib.sha256(b'regenerated pdf fixture').hexdigest())
        self.assertEqual(saved['tailoring_report']['evidence_review']['bullets'][0]['rewritten'], self.payload()['bullets'][0])
        self.assertIn('Not recalculated', saved['tailoring_report']['ats_match_score'])
        self.assertIn(self.payload()['bullets'][0], (new_path.parent / 'tailoring_report.md').read_text())
        self.assertFalse((self.root / 'applications.json').exists())
        self.assertFalse((self.root / '.draft_registry.json').exists())

    def test_failed_pdf_render_keeps_original_and_cleans_staging(self):
        from unittest.mock import patch
        with patch('Resume.render_pdf.save_resume_artifacts', side_effect=ValueError('Resume must be exactly one page')):
            with self.assertRaisesRegex(ValueError, 'exactly one page'):
                self.store.save(self.id, self.payload())
        self.assertEqual(self.pdf.read_bytes(), b'original pdf fixture')
        self.assertEqual([p for p in self.store.output.glob('.review-*') if p.is_dir()], [])
        self.assertEqual(len(self.store.list_packets()), 1)

    def test_stale_empty_and_structurally_changed_edits_rejected(self):
        payloads = [dict(self.payload(), revision='stale'), self.payload(''), dict(self.payload(), bullets=[]), self.payload('x' * 2001), self.payload(self.data['experiences'][0]['bullets'][0])]
        for payload in payloads:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.store.save(self.id, payload)

    def test_packet_paths_cannot_escape_output(self):
        for identifier in ('../master_profile.json', '%2e%2e', '/etc/passwd'):
            with self.assertRaises(ValueError):
                self.store.packet_path(identifier)
        linked = self.store.output / 'linked'
        linked.symlink_to(self.folder, target_is_directory=True)
        self.assertEqual(len(self.store.list_packets()), 1)

    def test_context_uses_exact_packet_and_keeps_original_snapshot(self):
        import json
        from unittest.mock import patch
        contact = {'email': 'alex@example.org', 'source': 'user_provided', 'status': 'not_independently_verified', 'checked_at': '2026-01-01'}
        apps = [{'output_dir': str(self.folder), 'contact_verifications': {'recruiter': contact}, 'touch1_draft_id': 'draft1'},
                {'company': 'Example', 'role': 'PM', 'output_dir': '/different/packet', 'contact_verifications': {'recruiter': {'email': 'unrelated@example.org'}}}]
        (self.root / 'applications.json').write_text(json.dumps(apps))
        snapshot = {'recipient': contact['email'], 'subject': 'Following up', 'body': 'Original draft copy', 'attachment_path': str(self.pdf), 'attachment_sha256': self.data['artifact_sha256']}
        (self.root / '.draft_registry.json').write_text(json.dumps({'one': {'state': 'created', 'draft': {'id': 'draft1'}, 'review_snapshot': snapshot}}))
        detail = self.store.detail(self.id)
        self.assertEqual(len(detail['context']['contacts']), 1)
        self.assertEqual(detail['context']['messages'][0]['body'], 'Original draft copy')
        with patch('Resume.render_pdf.save_resume_artifacts', side_effect=self.mock_render):
            result = self.store.save(self.id, self.payload())
        self.assertEqual(result['context']['messages'][0]['attachment_path'], str(self.pdf))
        self.assertEqual(len(result['context']['contacts']), 1)

    def test_bad_history_is_reported_without_hiding_resume(self):
        (self.root / 'applications.json').write_text('{')
        detail = self.store.detail(self.id)
        self.assertTrue(detail['editable'])
        self.assertTrue(detail['context']['errors'])

    @unittest.skipUnless(os.environ.get('COPILOT_HTTP_TESTS') == '1', 'Loopback integration test: run with COPILOT_HTTP_TESTS=1')
    def test_local_server_requires_session_and_rejects_cross_origin_writes(self):
        import http.client
        import json
        import re
        import threading
        from review_app import make_server
        server = make_server(self.store, port=0)
        from unittest.mock import patch
        with patch('extension_api.ExtensionAPI') as initialize, self.assertRaises(OSError):
            make_server(self.store, port=server.server_port)
        initialize.assert_not_called()
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        thread.start()
        def stop():
            server.shutdown()
            server.server_close()
            thread.join()
        self.addCleanup(stop)
        conn = http.client.HTTPConnection('127.0.0.1', server.server_port)
        self.addCleanup(conn.close)
        conn.request('GET', '/api/packets')
        response = conn.getresponse()
        self.assertEqual(response.status, 403)
        response.read()
        conn.request('GET', '/')
        response = conn.getresponse()
        cookie = response.getheader('Set-Cookie').split(';')[0]
        token = re.search(r'name="review-token" content="([^"]+)"', response.read().decode())[1]
        headers = {'Cookie': cookie, 'Content-Type': 'application/json', 'X-Review-Token': token}
        conn.request('GET', '/api/packets', headers=headers)
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.read())[0]['id'], self.id)
        for extra in ({'Origin': 'https://evil.example'}, {'Host': 'evil.example'}, {'X-Review-Token': 'wrong'}):
            conn.request('POST', f'/api/packets/{self.id}/save', json.dumps(self.payload()), dict(headers, **extra))
            response = conn.getresponse()
            self.assertEqual(response.status, 403)
            response.read()
        conn.request('GET', f'/api/packets/{self.id}/pdf', headers=headers)
        response = conn.getresponse()
        self.assertEqual(response.getheader('Content-Type'), 'application/pdf')
        self.assertEqual(response.read(), b'original pdf fixture')
        # Setup is visible, but only the local session can install the connector.
        conn.request('GET', '/setup')
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        self.assertIn('Enable Chrome connection', response.read().decode())
        with patch('native_bridge.install', return_value={'enabled': True}) as install:
            for extra in ({'Origin':'https://evil.test'}, {'X-Review-Token':'wrong'}):
                conn.request('POST', '/api/setup/install', '{}', dict(headers, **extra))
                response = conn.getresponse()
                self.assertEqual(response.status, 403)
                response.read()
            install.assert_not_called()
            conn.request('POST', '/api/setup/install', '{}', headers)
            response = conn.getresponse()
            self.assertEqual(response.status, 200)
            self.assertTrue(json.loads(response.read())['enabled'])
            install.assert_called_once_with(self.root.resolve())
        # Pairing is only initiated by the authenticated local review screen.
        conn.request('POST', '/api/extension/pair-code', json.dumps({'extension_id': 'a' * 32}), headers)
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        code = json.loads(response.read())['code']
        origin = 'chrome-extension://' + 'a' * 32
        ext_headers = {'Origin': origin, 'Content-Type': 'application/json'}
        conn.request('POST', '/extension/v1/pair', json.dumps({'code': code}), ext_headers)
        response = conn.getresponse()
        self.assertEqual(response.getheader('Access-Control-Allow-Origin'), origin)
        auth = json.loads(response.read())['token']
        ext_headers['Authorization'] = 'Bearer ' + auth
        conn.request('GET', '/extension/v1/packets', headers=ext_headers)
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.read())[0]['id'], self.id)
        conn.request('GET', '/extension/v1/packets', headers={'X-Extension-Id': 'a' * 32, 'Authorization': 'Bearer ' + auth})
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        response.read()
        conn.request('GET', '/extension/v1/packets', headers=dict(ext_headers, Origin='https://evil.test', **{'X-Extension-Id': 'a' * 32}))
        response = conn.getresponse()
        self.assertEqual(response.status, 403)
        self.assertIsNone(response.getheader('Access-Control-Allow-Origin'))
        response.read()
        conn.request('POST', '/api/extension/revoke', '{}', headers)
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        response.read()
        conn.request('GET', '/extension/v1/packets', headers=ext_headers)
        response = conn.getresponse()
        self.assertEqual(response.status, 403)
        response.read()

    def test_review_cli_does_not_invoke_gmail(self):
        import copilot
        from unittest.mock import patch
        with patch('sys.argv', ['copilot.py', '--review', '--review-port', '8777']), patch('review_app.serve') as serve, patch('copilot.verify_gmail_access') as gmail, patch('copilot.process_due_touch2_nudges') as nudge:
            copilot.main()
        serve.assert_called_once_with(8777)
        gmail.assert_not_called()
        nudge.assert_not_called()



class TestExtensionBridge(unittest.TestCase):
    setUp = TestLocalReview.setUp

    @unittest.skipUnless(os.environ.get('COPILOT_BROWSER_TESTS') == '1',
                         'Set COPILOT_BROWSER_TESTS=1 for isolated Chrome regressions')
    def test_live_structure_scanner_regressions(self):
        # Includes outside dropdown labels, anonymous validation helpers,
        # stable education identity, transient described placeholders, unchanged
        # real-instruction guards, flag-backed country retention, and zero submissions.
        import subprocess
        result = subprocess.run(
            [sys.executable, str(Path(__file__).parent / 'scripts/test_extension_browser.py')],
            cwd=Path(__file__).parent, capture_output=True, text=True, timeout=150)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Browser integration tests passed', result.stdout)

    def bridge(self, **kwargs):
        from extension_api import ExtensionAPI
        previous = getattr(self, '_test_bridge', None)
        if previous:
            previous.state.close()
        bridge = ExtensionAPI(self.store, **kwargs)
        self._test_bridge = bridge
        self.addCleanup(bridge.state.close)
        return bridge

    def test_cross_company_history_relationships_and_exact_answers(self):
        import json
        from pathlib import Path
        from application_profile import resolve_question, validate_profile
        app = {'automation': {'relationships_no': True, 'exhaustive_employment': True}}
        profile = {'experiences': [{'company': 'Omitted Employer', 'role': 'Intern'}, {'company': 'Alpha Beta Company', 'role': 'Analyst', 'aliases': ['ABC Corp']}]}
        for company in ('Robinhood', 'Unrelated Inc', 'Another LLC'):
            for question in ('Have you worked for us?', 'Have you ever worked with our company?', 'Have you previously been employed here?', 'Have you worked here before?'):
                self.assertEqual(resolve_question(question, company, app, profile)['value'], 'No', question)
            for question in ('Do you have any relationships at our company?', 'Are you related to anyone who works here?', 'Do you know anyone at our company?'):
                self.assertEqual(resolve_question(question, company, app, profile)['value'], 'No', question)
        self.assertEqual(resolve_question('Do you have any relationship with a current employee?', 'Omitted Employer', app, profile)['value'], 'No')
        self.assertEqual(resolve_question('Have you worked for us?', 'Omitted Employer', app, profile)['value'], 'Yes')
        self.assertNotIn('value', resolve_question('Have you worked for us as a full-time employee?', 'Omitted Employer', app, profile))
        self.assertEqual(resolve_question('Have you worked with ABC Corp?', 'Other', app, profile)['value'], 'Yes')
        self.assertNotIn('value', resolve_question('Have you worked for us?', 'Alpha', app, profile))
        self.assertNotIn('value', resolve_question('Have you worked for us?', '', app, profile))
        self.assertNotIn('value', resolve_question('Have you worked for us or our subsidiaries?', 'Other', app, profile))
        self.assertNotIn('value', resolve_question('Do you have relationships or investments here?', 'Other', app, profile))
        self.assertIsNone(resolve_question('Do you have an employee referral code?', 'Other', app, profile))
        for missing in (None, {}, {'experiences': []}, {'experiences': [{}]}):
            self.assertNotIn('value', resolve_question('Have you worked for us?', 'Other', app, missing))
        self.assertNotIn('value', resolve_question('Have you worked for us?', 'Other', {}, profile))
        questions = json.loads((Path(__file__).parent / 'extension/tests/robinhood-questions.json').read_text())
        app['company_answers'] = [{'company': 'Robinhood', 'question': questions[k], 'answer': 'No'} for k in ('conflicts', 'government')]
        for key in ('conflicts', 'government'):
            self.assertEqual(resolve_question(questions[key], 'Robinhood', app, profile)['value'], 'No')
            self.assertNotIn('value', resolve_question(questions[key], 'Other', app, profile) or {})
            self.assertNotIn('value', resolve_question(questions[key] + ' Also certify accuracy.', 'Robinhood', app, profile) or {})
        self.assertEqual(resolve_question(questions['history'], 'Robinhood', app, profile)['value'], 'No')
        app['disclosures'] = {'lgbtq': 'No'}
        self.assertEqual(validate_profile(app), app)
        with self.assertRaises(ValueError):
            validate_profile({'automation': {'relationships_no': 'yes'}})

    def test_never_employed_alternative_requires_full_history(self):
        from application_profile import resolve_question
        app = {'automation': {'exhaustive_employment': True}}
        question = 'Have you ever worked for Robinhood as an employee, intern or contractor?'
        other = {'experiences': [{'company': 'Other', 'role': 'Intern'}]}
        answer = resolve_question(question, 'Robinhood', app, other)
        self.assertEqual(answer['alternatives'], ['I have never worked at Robinhood'])
        former = {'experiences': [{'company': 'Robinhood', 'role': 'Intern', 'date_range': '2020 – 2021'}]}
        self.assertEqual(resolve_question(question, 'Robinhood', app, former)['value'], 'Yes')
        current = resolve_question('Do you currently work at Robinhood?', 'Robinhood', app, former)
        self.assertEqual(current['value'], 'No')
        self.assertNotIn('alternatives', current)
        self.assertNotIn('alternatives', resolve_question(question, 'Robinhood', {}, other))
        self.assertNotIn('alternatives', resolve_question(question, 'Robinhood', app, None))
        app['company_answers'] = [{'company': 'Robinhood', 'question': question, 'answer': 'No'}]
        self.assertEqual(resolve_question(question, 'Robinhood', app, former)['value'], 'Yes')
        for label, answer in [('Gender', 'Cisgender man'), ('Ethnicity', 'East Asian')]:
            app['company_answers'] = [{'company': 'Robinhood', 'question': label, 'answer': answer}]
            self.assertEqual(resolve_question(label, 'Robinhood', app, other)['value'], answer)
            self.assertIsNone(resolve_question(label, 'Other', app, other))
            self.assertIsNone(resolve_question(label + ' identity', 'Robinhood', app, other))

    def test_history_endpoint_uses_master_and_preserves_preferences(self):
        import json
        bridge = self.bridge()
        app = {'automation': {'relationships_no': True, 'exhaustive_employment': True}, 'disclosures': {'lgbtq': 'No'}}
        bridge.preferences({'application_profile': app})
        profile_path = self.store.root / 'Resume/master_profile.json'
        profile = json.loads(profile_path.read_text())
        profile['experiences'].append({'company': 'Omitted Employer', 'role': 'Intern'})
        profile_path.write_text(json.dumps(profile))
        payload = {'url': 'https://jobs.lever.co/omitted/123', 'company': 'Omitted Employer', 'fields': [{'id': 'q', 'label': 'Have you worked for us?'}]}
        self.assertEqual(bridge.resolve_fields(payload)['q']['value'], 'Yes')
        self.assertNotIn('value', bridge.resolve_fields({**payload, 'company': ''})['q'])
        self.assertNotIn('experiences', json.dumps(bridge.resolve_fields(payload)))
        profile_path.unlink()
        self.assertIn('unavailable', bridge.resolve_fields(payload)['q']['reason'])
        self.assertEqual(bridge.preferences({'facts': {}, 'questions': []})['application_profile'], app)

    def test_preparation_facts_are_scoped_and_missing_is_not_no(self):
        from application_knowledge import fact_catalog, resolve_fact, field_context
        prefs = {'facts': {'city': 'Example City'}, 'application_profile': {
            'disclosures': {'gender_identity': 'Cisgender man', 'ethnicity': 'East Asian',
                            'military_history': 'I have never served in the military'}}}
        catalog = fact_catalog({}, prefs)
        self.assertEqual(resolve_fact('current_city', catalog)['value'], 'Example City')
        self.assertNotIn('value', resolve_fact('summer_location', catalog))
        self.assertNotIn('value', resolve_fact('relocation', catalog))
        self.assertEqual(resolve_fact('gender_identity', catalog)['value'], 'Cisgender man')
        a = field_context({'id': 'a', 'label': 'Location', 'helper': 'Current city'})
        b = field_context({'id': 'a', 'label': 'Location', 'helper': 'Summer residence'})
        self.assertNotEqual(a, b)

    def test_preparation_conflicts_remain_unresolved_across_all_applicable_scopes(self):
        from itertools import permutations
        from application_knowledge import fact_catalog, validate_knowledge
        url = 'https://job-boards.greenhouse.io/example/jobs/1'
        records = [dict(key='current_city', answer=answer, scope=scope,
                        question='Current city', company='Example', posting=url,
                        confirmed_at='2026-01-01') for scope, answer in
                   [('global', 'Alpha'), ('company', 'Beta'), ('posting', 'Alpha')]]
        validate_knowledge(records)
        for ordered in permutations(records):
            for facts in ({}, {'city': 'Alpha'}):
                with self.subTest(scopes=[r['scope'] for r in ordered], facts=facts):
                    catalog = fact_catalog({}, {'facts': facts, 'knowledge': list(ordered)}, 'Example', url)
                    self.assertNotIn('value', catalog['current_city'])
                    self.assertIn('conflict', catalog['current_city']['reason'])
        catalog = fact_catalog({}, {'knowledge': records}, 'Other', url + '2')
        self.assertEqual(catalog['current_city']['value'], 'Alpha')
        agreeing = [{**r, 'answer': 'Alpha'} for r in records]
        self.assertEqual(fact_catalog({}, {'knowledge': agreeing}, 'Example', url)['current_city']['value'], 'Alpha')
        expired = [{**r, 'valid_until': '2000-01-01'} if r['scope'] == 'company' else r for r in records]
        self.assertEqual(fact_catalog({}, {'knowledge': expired}, 'Example', url)['current_city']['value'], 'Alpha')

    def test_preparation_interpretation_cannot_publish_answers_or_sensitive_inferences(self):
        from application_knowledge import interpreted_resolution, fact_catalog
        catalog = fact_catalog({}, {'facts': {'city': 'Example City'}})
        field = {'id': 'a', 'label': 'Where do you currently live?', 'type': 'text'}
        self.assertEqual(interpreted_resolution(field, {'kind': 'fact', 'fact_key': 'current_city'}, catalog)['value'], 'Example City')
        for label in ('Where will you live this summer?', 'Are you willing to relocate?',
                      'What is your gender identity?', 'Have you worked at our subsidiary?',
                      'I certify that this information is accurate'):
            result = interpreted_resolution({**field, 'label': label}, {'kind': 'fact', 'fact_key': 'current_city'}, catalog)
            self.assertNotIn('value', result, label)
        self.assertNotIn('value', interpreted_resolution(field, {'kind': 'fact', 'value': 'Invented'}, catalog))

    def test_preparation_intrinsic_qualifiers_and_family_name_are_not_relationships(self):
        from application_knowledge import interpreted_resolution, fact_catalog
        catalog = fact_catalog({}, {'facts': {'last_name': 'Example', 'city': 'Example City'}})
        self.assertEqual(interpreted_resolution({'label': 'What is your family name?', 'type': 'text'},
                         {'kind': 'fact', 'fact_key': 'last_name', 'qualifiers': []}, catalog)['value'], 'Example')
        self.assertEqual(interpreted_resolution({'label': 'Where do you currently live?', 'type': 'text'},
                         {'kind': 'fact', 'fact_key': 'current_city', 'qualifiers': ['current']}, catalog)['value'], 'Example City')
        self.assertNotIn('value', interpreted_resolution({'label': 'Where do you currently live?', 'type': 'text'},
                         {'kind': 'fact', 'fact_key': 'current_city', 'qualifiers': ['during internship']}, catalog))

    def test_preparation_interpretation_cache_uses_full_context_and_rejects_stale_publication(self):
        bridge = self.bridge(generate=lambda prompt: {'fields': [{'id': 'q', 'kind': 'fact', 'fact_key': 'current_city', 'qualifiers': []}]})
        bridge.preferences({'facts': {'city': 'Example City'}})
        payload = {'url': 'https://job-boards.greenhouse.io/example/jobs/1', 'company': 'Example',
                   'fields': [{'id': 'q', 'label': 'Where do you currently live?', 'type': 'text'}]}
        bridge.interpret_fields(payload, lambda callback: callback())
        self.assertEqual(bridge.resolve_fields(payload)['q']['value'], 'Example City')
        changed = {**payload, 'fields': [{**payload['fields'][0], 'helper': 'Summer location'}]}
        self.assertNotIn('q', bridge.resolve_fields(changed))
        def changed_preferences(callback):
            bridge.preferences({'facts': {'city': 'Changed City'}})
            return callback()
        with self.assertRaisesRegex(ValueError, 'changed during interpretation'):
            bridge.interpret_fields(payload, changed_preferences)
        self.assertNotIn('q', bridge.resolve_fields(payload))

    def test_preparation_context_cache_expires_on_source_or_question_change(self):
        from application_knowledge import context_digest
        payload = {'url': 'https://job-boards.greenhouse.io/example/jobs/1', 'company': 'Example'}
        field = {'label': 'City', 'type': 'text', 'helper': 'Current city'}
        original = context_digest(payload, field, {'facts': {'city': 'A'}}, {})
        self.assertNotEqual(original, context_digest(payload, {**field, 'helper': 'Summer city'}, {'facts': {'city': 'A'}}, {}))
        self.assertNotEqual(original, context_digest(payload, field, {'facts': {'city': 'B'}}, {}))
        self.assertNotEqual(original, context_digest({**payload, 'company': 'Other'}, field, {'facts': {'city': 'A'}}, {}))

    def test_preparation_preferences_backup_and_metadata_survive_old_clients(self):
        import json
        bridge = self.bridge()
        bridge.preferences({'facts': {'city': 'Example City'}, 'knowledge': [
            {'key': 'current_city', 'answer': 'Example City', 'scope': 'global',
             'question': 'Where do you currently live?', 'confirmed_at': '2026-10-05'}]})
        bridge.preferences({'facts': {'city': 'Example City'}, 'questions': []})
        self.assertEqual(bridge.preferences()['knowledge'][0]['scope'], 'global')
        self.assertTrue(bridge.answers.with_suffix('.json.bak').exists())
        self.assertEqual(json.loads(bridge.answers.read_text())['version'], 3)

    def test_preparation_disclosure_facets_do_not_replace_broad_categories(self):
        from application_profile import validate_profile
        value = {'disclosures': {'gender': 'Male', 'gender_identity': 'Cisgender man',
                                 'race': 'Asian', 'ethnicity': 'East Asian',
                                 'military_history': 'I have never served in the military'}}
        self.assertEqual(validate_profile(value), value)

    def test_company_multiselect_preferences_keep_choice_boundaries(self):
        from application_profile import resolve_question
        bridge = self.bridge()
        app = {'company_answers': [{'company': 'Example', 'question': 'Choose locations',
                                   'answer': ['Washington, DC', 'New York, NY']}]}
        bridge.preferences({'application_profile': app})
        stored = bridge.preferences()['application_profile']
        self.assertEqual(stored['company_answers'], app['company_answers'])
        self.assertEqual(resolve_question('Choose locations', 'Example', stored, {})['value'],
                         ['Washington, DC', 'New York, NY'])

    def test_preparation_written_evidence_includes_omitted_experience_and_checks_revision(self):
        import json
        from unittest.mock import patch
        prompts = []
        def generate(prompt):
            prompts.append(prompt)
            return {'answer': 'At Omitted Co, I built SQL reports.', 'citations': ['profile-experience:1:0']}
        bridge = self.bridge(generate=generate)
        packet = bridge.packet(self.id)
        path = self.store.root / 'Resume/master_profile.json'
        profile = json.loads(path.read_text())
        profile['experiences'].append({'company': 'Omitted Co', 'role': 'Intern', 'bullets': [{'text': 'Built SQL reports.'}]})
        path.write_text(json.dumps(profile))
        payload = {**self.answer_payload(), 'evidence_scope': 'profile', 'word_limit': 20}
        with patch.object(bridge, 'packet', return_value=packet):
            answer = bridge.answer(payload)
            self.assertIn('Omitted Co', prompts[0])
            self.assertNotIn(profile['personal_info'].get('email', 'NOT_AN_EMAIL'), prompts[0])
            self.assertEqual(bridge.answer({**payload, **answer}, validate_only=True)['answer'], answer['answer'])
            with self.assertRaisesRegex(ValueError, 'word limit'):
                bridge.answer({**payload, **answer, 'word_limit': 2}, validate_only=True)
            profile['experiences'][1]['bullets'][0]['text'] = 'Different verified fact.'
            path.write_text(json.dumps(profile))
            with self.assertRaisesRegex(ValueError, 'evidence changed'):
                bridge.answer({**payload, **answer}, validate_only=True)

    def test_preparation_missing_written_facts_are_explicit(self):
        bridge = self.bridge(generate=lambda prompt: {'needs_input': 'Your professional license and relevant experience.'})
        with self.assertRaisesRegex(ValueError, 'Your input is needed'):
            bridge.answer(self.answer_payload())

    def test_metric_unit_frequency_and_scale_substitutions(self):
        from Resume.evidence import metric_errors
        source = 'Saved 50 hours per week.'
        for claim in ('Saved 50 days per week.', 'Saved 50 widgets weekly.', 'Saved 50 hours daily.', 'Saved 50 hours.', 'Saved 50 million hours weekly.'):
            self.assertTrue(metric_errors(claim, source, 'test'), claim)
        self.assertFalse(metric_errors('Saved 50 hours weekly.', source, 'test'))

    def test_answer_metrics_stay_with_named_employer(self):
        from unittest.mock import patch
        bridge = self.bridge()
        packet = bridge.packet(self.id)
        packet['experiences'].append({'company': 'Other', 'role': 'Analyst', 'bullets': ['Saved 10 hours weekly.']})
        payload = dict(self.answer_payload(), answer='At Other, I saved 50 hours weekly.', citations=['experience:0:0', 'experience:1:0'])
        with patch.object(bridge, 'packet', return_value=packet), self.assertRaisesRegex(ValueError, 'Employer-specific'):
            bridge.answer(payload, validate_only=True)

    def test_shared_written_question_fixtures(self):
        import json
        from extension_api import WRITTEN
        fixtures = json.loads((ROOT_DIR / 'extension/tests/question-fixtures.json').read_text())
        for fixture in fixtures:
            self.assertEqual(bool(WRITTEN.search(fixture['question'])), fixture['written'])

    def test_resume_job_publishes_only_complete_reviewable_packet(self):
        import shutil
        from unittest.mock import patch
        bridge = self.bridge()
        def pipeline(description, profile_path, output_base_dir, *, target_company, target_role, preserve_source_bullets):
            self.assertEqual((target_company, target_role), ('Example', 'PM'))
            self.assertTrue(preserve_source_bullets)
            destination = Path(output_base_dir) / 'Generated'
            shutil.copytree(self.folder, destination)
            for name in ('resume.md', 'resume.html', 'tailoring_report.md'):
                (destination / name).write_text('fixture artifact')
            return {'output_dir': str(destination)}
        payload = {'kind': 'resume', 'input': {'url': 'https://jobs.lever.co/example/123', 'company': 'Example', 'role': 'PM', 'description': 'Build automation.'}}
        with patch('generate_resume.run_pipeline', side_effect=pipeline):
            result = bridge.operation(payload, lambda callback: callback())
        self.assertTrue(result['review_required'])
        self.assertTrue(self.store.detail(result['packet_id'])['editable'])
        count = len(self.store.list_packets())
        with patch('generate_resume.run_pipeline', side_effect=pipeline), self.assertRaisesRegex(ValueError, 'cancelled'):
            bridge.operation(payload, lambda callback: (_ for _ in ()).throw(ValueError('cancelled')))
        self.assertEqual(len(self.store.list_packets()), count)
        self.assertFalse(list(self.store.output.glob('.applypilot-*')))
        mismatched = {**payload, 'input': {**payload['input'], 'company': 'Different'}}
        def wrong_identity(description, profile_path, output_base_dir, **kwargs):
            destination = Path(output_base_dir) / 'Wrong'
            shutil.copytree(self.folder, destination)
            for name in ('resume.md', 'resume.html', 'tailoring_report.md'):
                (destination / name).write_text('fixture artifact')
            return {'output_dir': str(destination)}
        with patch('generate_resume.run_pipeline', side_effect=wrong_identity), self.assertRaisesRegex(ValueError, 'differs'):
            bridge.operation(mismatched, lambda callback: callback())
        self.assertEqual(len(self.store.list_packets()), count)

    def test_global_essays_blocked_and_legacy_preserved(self):
        import json
        bridge = self.bridge()
        question = 'What interests you about this position?'
        record = {'facts': {}, 'questions': [{'question': question, 'answer': 'An old company essay'}]}
        with self.assertRaises(ValueError):
            bridge.preferences(record)
        bridge.answers.write_text(json.dumps(record))
        self.assertTrue(bridge.preferences()['questions'][0]['blocked'])
        self.assertEqual(json.loads(bridge.answers.read_text()), record)

    def test_session_expiry_clear_and_packet_eligibility(self):
        now = [1000]
        bridge = self.bridge(clock=lambda: now[0])
        state = bridge.state
        state.session({'action': 'save', 'key': 'lever:example:123', 'value': {'answer': 'unfinished'}})
        self.assertEqual(state.session({'key': 'lever:example:123'})['answer'], 'unfinished')
        now[0] += 31 * 86400
        self.assertEqual(state.session({'key': 'lever:example:123'}), {})
        self.assertTrue(bridge.dispatch('GET', '/packets', {})[0]['eligible'])
        self.assertEqual(bridge.dispatch('GET', '/health', {})['api_version'], 1)
        state.session({'action': 'clear-all', 'key': 'all'})
        self.assertTrue(self.pdf.exists())

    def test_question_subject_and_enrollment_need_explicit_answers(self):
        from application_knowledge import interpreted_resolution, validate_knowledge, context_digest, subject_reason
        self.assertIsNone(subject_reason({'label': 'Why this role? Please reference one part of the role description.'}))
        bridge = self.bridge()
        base = {'id': 'q', 'label': 'Email', 'type': 'text', 'subject': 'third_party', 'section': 'References', 'contextVersion': 2}
        payload = {'url': 'https://job-boards.greenhouse.io/example/jobs/123', 'company': 'Example', 'fields': [base]}
        self.assertNotIn('value', bridge.resolve_fields(payload)['q'])
        bridge.preferences({'facts': {}, 'questions': [], 'application_profile': {'automation': {'relationships_no': True}}})
        scoped = dict(base, label='Do you have any relationships at our company?', subject='applicant', section='Applicant information')
        self.assertEqual(bridge.resolve_fields(dict(payload, fields=[scoped]))['q']['value'], 'No')
        catalog = {'school': {'value': 'Example University'}}
        for label in ('Which university are you currently attending?', 'Are you currently enrolled?', 'What degree are you currently pursuing?', 'Current school'):
            answer = interpreted_resolution({'label': label, 'type': 'text'}, {'kind': 'fact', 'fact_key': 'school', 'qualifiers': []}, catalog)
            self.assertNotIn('value', answer)
        with self.assertRaisesRegex(ValueError, 'enrollment'):
            validate_knowledge([{'key': 'school', 'answer': 'Example', 'scope': 'global', 'question': 'Current school', 'confirmed_at': '2026-10-06'}])
        self.assertNotEqual(context_digest(payload, base, {}, {}), context_digest(payload, dict(base, section='Emergency contact'), {}, {}))
        with self.assertRaisesRegex(ValueError, 'Update'):
            bridge.dispatch('POST', '/resolve-fields', payload)

    def test_worker_process_crash_recovery_requires_ownership(self):
        import subprocess, json, time
        script = "from pathlib import Path; from extension_state import ExtensionState; import sys,time; state=ExtensionState(Path(sys.argv[1])); state.job({'request_id':'crash-regression'},lambda p,pub: time.sleep(60)); print('ready',flush=True); time.sleep(60)"
        process = subprocess.Popen([sys.executable, '-c', script, str(self.store.root)], stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(), 'ready')
            from extension_state import ExtensionState
            before = (self.store.root / '.applypilot_state.json').read_text()
            with self.assertRaisesRegex(RuntimeError, 'already running'):
                ExtensionState(self.store.root)
            self.assertNotIn('interrupted', (self.store.root / '.applypilot_state.json').read_text())
        finally:
            process.kill()
            process.wait(timeout=5)
            process.stdout.close()
        recovered = ExtensionState(self.store.root)
        self.addCleanup(recovered.close)
        self.assertEqual(recovered.job({'action': 'status', 'request_id': 'crash-regression'}, None)['status'], 'interrupted')

    def test_written_context_change_rejected_even_with_same_question(self):
        bridge = self.bridge(generate=lambda prompt: {'answer': 'Saved 50 hours weekly.', 'citations': ['experience:0:0']})
        payload = dict(self.answer_payload(), field_context={'contextVersion': 2, 'subject': 'applicant', 'section': 'Application', 'label': 'Why this role?'})
        result = bridge.answer(payload)
        self.assertEqual(bridge.answer({**payload, **result}, validate_only=True)['answer'], result['answer'])
        with self.assertRaisesRegex(ValueError, 'context changed'):
            bridge.answer({**payload, **result, 'field_context': {**payload['field_context'], 'section': 'Other section'}}, validate_only=True)

    def test_second_worker_cannot_recover_owned_jobs(self):
        from extension_state import ExtensionState
        import threading
        bridge = self.bridge()
        entered, gate = threading.Event(), threading.Event()
        self.addCleanup(gate.set)
        def operation(payload, publish):
            entered.set()
            gate.wait(5)
            return publish(lambda: 'done')
        job = bridge.state.job({'request_id': 'owner-regression'}, operation)
        self.assertTrue(entered.wait(2))
        before = bridge.state.path.read_bytes()
        with self.assertRaisesRegex(RuntimeError, 'already running'):
            ExtensionState(self.store.root)
        self.assertEqual(before, bridge.state.path.read_bytes())
        gate.set()

    def test_jobs_idempotency_cancel_and_restart(self):
        import json
        import threading
        from extension_state import ExtensionState
        bridge = self.bridge()
        gate, entered = threading.Event(), threading.Event()
        published = []
        def operation(payload, publish):
            entered.set()
            gate.wait(2)
            return publish(lambda: published.append(True))
        payload = {'request_id': 'request-123', 'kind': 'resume', 'input': {}, 'posting_key': 'posting-123'}
        first = bridge.state.job(payload, operation)
        self.assertTrue(entered.wait(2))
        self.assertEqual(bridge.state.job(payload, operation)['id'], first['id'])
        with self.assertRaises(ValueError):
            bridge.state.job(dict(payload, kind='answer'), operation)
        bridge.state.job({'action': 'cancel', 'request_id': payload['request_id']}, operation)
        gate.set()
        bridge.state.pool.shutdown(wait=True)
        self.assertEqual(published, [])
        self.assertEqual(bridge.state.job({'action': 'status', 'id': first['id']}, operation)['status'], 'cancelled')
        data = json.loads(bridge.state.path.read_text())
        data['jobs'][first['id']]['status'] = 'running'
        bridge.state.path.write_text(json.dumps(data))
        bridge.state.close()
        recovered = ExtensionState(self.store.root)
        self.addCleanup(recovered.close)
        self.assertEqual(recovered.job({'action': 'status', 'id': first['id']}, operation)['status'], 'interrupted')
        recovered.session({'action': 'clear', 'key': 'posting-123'})
        with self.assertRaises(ValueError):
            recovered.job({'action': 'status', 'id': first['id']}, operation)

    def test_completed_preparation_survives_restart_without_regeneration(self):
        from extension_state import ExtensionState
        bridge = self.bridge()
        calls = []
        payload = {'request_id': 'ready-resume-123', 'kind': 'resume', 'input': {}, 'posting_key': 'posting-ready'}
        def prepare(payload, publish):
            calls.append(payload['request_id'])
            return publish(lambda: {'packet_id': self.id})
        job = bridge.state.job(payload, prepare)
        bridge.state.pool.shutdown(wait=True)
        bridge.state.session({'action': 'save', 'key': 'posting-ready', 'value': {'job': {'id': job['id'], 'kind': 'resume', 'status': 'complete'}, 'confirmed': False}})
        bridge.state.close()
        recovered = ExtensionState(self.store.root)
        self.addCleanup(recovered.close)
        saved = recovered.session({'key': 'posting-ready'})
        self.assertFalse(saved['confirmed'])
        ready = recovered.job({'action': 'status', 'id': saved['job']['id']}, prepare)
        self.assertEqual(ready['status'], 'complete')
        self.assertEqual(ready['result']['packet_id'], self.id)
        self.assertEqual(recovered.job(payload, prepare)['id'], job['id'])
        self.assertEqual(calls, ['ready-resume-123'])
        self.assertTrue(self.pdf.exists())

    def test_pairing_origin_expiry_single_use_and_revocation(self):
        bridge = self.bridge(clock=lambda: 100)
        origin = 'chrome-extension://' + 'a' * 32
        code = bridge.create_code('a' * 32)['code']
        with self.assertRaises(PermissionError):
            bridge.pair('chrome-extension://' + 'b' * 32, code)
        token = bridge.pair(origin, code)['token']
        self.assertTrue(bridge.authorized(origin, 'Bearer ' + token))
        self.assertTrue(self.bridge().authorized(origin, 'Bearer ' + token))
        self.assertFalse(bridge.authorized('https://evil.test', 'Bearer ' + token))
        self.assertFalse(bridge.authorized(origin, 'Bearer wrong'))
        with self.assertRaises(PermissionError):
            bridge.pair(origin, code)
        self.assertNotIn(token, bridge.access.read_text())
        bridge.revoke()
        self.assertFalse(bridge.authorized(origin, 'Bearer ' + token))
        code = bridge.create_code('a' * 32)['code']
        bridge.clock = lambda: 500
        with self.assertRaises(PermissionError):
            bridge.pair(origin, code)

    def test_packet_export_checks_revision_and_pdf(self):
        import base64
        bridge = self.bridge()
        result = bridge.packet(self.id, include_pdf=True)
        self.assertEqual(base64.b64decode(result['pdf_base64']), self.pdf.read_bytes())
        self.assertNotIn('pdf_base64', bridge.packet(self.id))
        with self.assertRaisesRegex(ValueError, 'changed'):
            bridge.packet(self.id, revision='old')
        self.pdf.write_bytes(b'changed file')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            bridge.packet(self.id)

    def test_preferences_are_explicit_and_attestations_rejected(self):
        bridge = self.bridge()
        record = {'facts': {'first_name': 'Daniel'}, 'questions': [{'question': 'Do you require sponsorship in the US?', 'answer': 'Yes'}]}
        saved = bridge.preferences(record)
        self.assertEqual(saved['facts'], record['facts'])
        self.assertEqual(saved['questions'][0]['answer'], 'Yes')
        self.assertEqual(bridge.preferences(), saved)
        self.assertEqual(saved['version'], 3)
        for question in ('I certify that this is correct', 'I consent', 'Social security number'):
            with self.assertRaises(ValueError):
                bridge.preferences({'questions': [{'question': question, 'answer': 'Yes'}]})
        for question in ('Gender?', 'Disability status', 'Veteran status'):
            value = bridge.preferences({'questions': [{'question': question, 'answer': 'Decline to answer'}]})
            self.assertTrue(value['questions'][0]['confirmed'])
        with self.assertRaises(ValueError):
            bridge.preferences({'facts': {'salary': '100000'}})
        with self.assertRaises(ValueError):
            bridge.preferences({'questions': [{'question': 'Start date?', 'answer': 'May'}, {'question': 'Start date', 'answer': 'June'}]})

    def test_application_profile_round_trip_migration_and_validation(self):
        import json
        from copy import deepcopy
        bridge = self.bridge()
        fixture = json.loads((ROOT_DIR / 'extension/tests/application-profile.json').read_text())
        saved = bridge.preferences(fixture)
        self.assertEqual(saved['application_profile'], fixture['application_profile'])
        self.assertEqual(bridge.preferences()['application_profile'], fixture['application_profile'])
        # Old clients saving ordinary answers must not erase the expanded profile.
        self.assertEqual(bridge.preferences({'facts': {}, 'questions': []})['application_profile'], fixture['application_profile'])
        for kind, key, value in [('work','authorized','yes'), ('work','country','Canada'), ('disclosures','inferred_race','Asian')]:
            data = deepcopy(fixture)
            data['application_profile'][kind][key] = value
            with self.assertRaises(ValueError):
                bridge.preferences(data)
        for start in ('2024', '2024-13', '2024-08-01', '2030-01'):
            data = deepcopy(fixture)
            data['application_profile']['education'][0]['start'] = start
            with self.assertRaises(ValueError):
                bridge.preferences(data)
        bridge.answers.write_text(json.dumps({'facts': {}, 'questions': [{'question':'Gender','answer':'legacy'}]}))
        self.assertTrue(bridge.preferences()['questions'][0]['blocked'])
        bridge.preferences({'facts': {}, 'questions': []})
        self.assertEqual(json.loads(bridge.answers.read_text())['archived_questions'][0]['answer'], 'legacy')

    def test_diagnostics_are_private_bounded_and_survive_reopening(self):
        import json
        import time
        bridge = self.bridge()
        key = 'lever:jobs.lever.co:example:123'
        entry = {'label':'School','name':'school','type':'combobox','section':'education:0',
                 'status':'failed','code':'option_missing','source':'explicit'}
        bridge.dispatch('POST','/diagnostics',{'posting_key':key,'action':'record','results':[entry]})
        history = self.bridge().dispatch('POST','/diagnostics',{'posting_key':key})
        self.assertEqual(history[0]['code'], 'option_missing')
        self.assertEqual(self.bridge().diagnostics({'posting_key':'other'}), [])
        for forbidden in ('value','answer','message','html','url','options'):
            with self.assertRaises(ValueError):
                bridge.diagnostics({'posting_key':key,'action':'record','results':[dict(entry,**{forbidden:'PRIVATE ANSWER'})]})
        path = self.store.root / '.applypilot_diagnostics.json'
        self.assertNotIn('PRIVATE ANSWER', path.read_text())
        expired = dict(history[0], time=time.time()-31*86400)
        path.write_text(json.dumps([expired]+history))
        self.assertEqual(len(bridge.diagnostics({'posting_key':key})), 1)
        bridge.diagnostics({'posting_key':key,'action':'record','results':[dict(entry,status='filled',code='retained')]})
        self.assertEqual(len(json.loads(path.read_text())), 2)

    def test_diagnostic_attempt_metadata_and_backward_compatible_progress(self):
        bridge = self.bridge()
        key = 'greenhouse:job-boards.greenhouse.io:example:123'
        legacy = {'packet_id': 'old', 'rows': {'school': {'selected': False, 'value': 'saved'}}}
        bridge.state.session({'action': 'save', 'key': key, 'value': legacy})
        self.assertEqual(bridge.state.session({'key': key})['rows'], legacy['rows'])
        modern = dict(legacy, selection_version=2, selections={'school': False, 'degree': None})
        bridge.state.session({'action': 'save', 'key': key, 'value': modern})
        self.assertEqual(bridge.state.session({'key': key})['selections'], modern['selections'])
        base = {'label': 'School', 'name': 'school', 'type': 'combobox', 'section': 'education:0',
                'status': 'failed', 'code': 'list_missing', 'attempt_id': 'test-attempt-1',
                'extension_version': '0.6.0', 'stage': 'final', 'occurrence': 1}
        for code, status in [('list_missing', 'failed'), ('option_ambiguous', 'failed'),
                             ('option_timeout', 'failed'), ('control_replaced', 'failed'),
                             ('excluded', 'excluded'), ('unanswered', 'unanswered'),
                             ('invalidated', 'invalidated')]:
            bridge.diagnostics({'posting_key': key, 'action': 'record',
                                'results': [dict(base, code=code, status=status)]})
        records = self.bridge().diagnostics({'posting_key': key})
        self.assertEqual(len(records), 7)
        self.assertTrue(all(r['occurrence'] == 1 for r in records))
        self.assertTrue(all(r['attempt_id'] == 'test-attempt-1' for r in records))
        for occurrence in (True, -1, 301, 'private answer'):
            with self.assertRaises(ValueError):
                bridge.diagnostics({'posting_key': key, 'action': 'record',
                                    'results': [dict(base, occurrence=occurrence)]})
        for metadata in ('stage', 'extension_version', 'attempt_id'):
            with self.assertRaises(ValueError):
                bridge.diagnostics({'posting_key': key, 'action': 'record',
                                    'results': [dict(base, **{metadata: 'private answer !'})]})

    def test_ai_does_not_infer_disclosures_or_school_dates(self):
        bridge = self.bridge(generate=lambda _: self.fail('Personal facts must never reach AI'))
        for question in ('What is your race?', 'What gender do you identify as?', 'Describe your disability',
                         'Veteran status', 'What is your graduation date?', 'What degree are you pursuing?'):
            with self.subTest(question=question), self.assertRaises(ValueError):
                bridge.answer(dict(self.answer_payload(), question=question))

    def test_control_diagnostics_preserve_legacy_and_reject_private_metadata(self):
        bridge = self.bridge()
        key = 'greenhouse:job-boards.greenhouse.io:example:control-regressions'
        base = {'label': 'School', 'name': 'school', 'type': 'combobox',
                'section': 'education:0', 'status': 'failed', 'code': 'list_missing'}
        bridge.diagnostics({'posting_key': key, 'action': 'record', 'results': [base]})
        for family, stage, code, status in (
                ('custom_select', 'opening', 'list_missing', 'failed'),
                ('custom_select', 'option_loading', 'option_timeout', 'failed'),
                ('phone', 'retention', 'rejected', 'failed'),
                ('upload', 'upload_acknowledgement', 'upload_error', 'failed'),
                ('native', 'final', 'explicit_detail_needed', 'unanswered'),
                ('native', 'final', 'not_applicable', 'not applicable')):
            bridge.diagnostics({'posting_key': key, 'action': 'record', 'results': [
                dict(base, control_family=family, stage=stage, code=code, status=status)]})
        stored = self.bridge().diagnostics({'posting_key': key})
        self.assertEqual(len(stored), 7)
        self.assertNotIn('control_family', stored[0])
        self.assertEqual(stored[-1]['status'], 'not applicable')
        for metadata in ('control_family', 'stage', 'answer', 'html', 'token'):
            with self.subTest(metadata=metadata), self.assertRaises(ValueError):
                bridge.diagnostics({'posting_key': key, 'action': 'record',
                                    'results': [dict(base, **{metadata: 'PRIVATE'})]})
        self.assertEqual(len(self.bridge().diagnostics({'posting_key': key})), 7)

    def answer_payload(self):
        return {'packet_id': self.id, 'revision': self.store.revision(self.path), 'url': 'https://jobs.lever.co/example/123/apply',
                'question': 'Describe your relevant experience', 'description': 'Build automation for business operations.', 'limit': 500}

    def test_generated_answers_are_cited_and_only_selected_evidence_is_sent(self):
        prompts = []
        def generate(prompt):
            prompts.append(prompt)
            return {'answer': 'I saved 50 hours weekly with Python automation.', 'citations': ['experience:0:0']}
        result = self.bridge(generate=generate).answer(self.answer_payload())
        self.assertEqual(result['citations'], ['experience:0:0'])
        self.assertIn('Acme', result['evidence']['experience:0:0'])
        self.assertNotIn('personal_info', prompts[0])
        self.assertIn('untrusted data', prompts[0])
        self.assertIn('Listed coursework does not establish completion', prompts[0])
        self.assertIn('An expected graduation date does not establish an awarded degree', prompts[0])

    def test_ai_errors_missing_evidence_and_unsupported_metrics_are_blocked(self):
        for response in ({'answer': 'I saved 50 hours daily.', 'citations': ['experience:0:0']},
                         {'answer': 'I saved 50 hours weekly.', 'citations': ['invented']},
                         {'answer': 'x' * 501, 'citations': ['experience:0:0']}):
            with self.assertRaises(ValueError):
                self.bridge(generate=lambda prompt: response).answer(self.answer_payload())
        def failing(prompt):
            raise RuntimeError('AI unavailable')
        with self.assertRaisesRegex(RuntimeError, 'unavailable'):
            self.bridge(generate=failing).answer(self.answer_payload())

    def test_edited_answer_revalidation_and_personal_questions(self):
        bridge = self.bridge(generate=lambda _: self.fail('Should not call AI'))
        payload = dict(self.answer_payload(), answer='Saved 50 hours weekly.', citations=['experience:0:0'])
        self.assertEqual(bridge.answer(payload, validate_only=True)['answer'], payload['answer'])
        with self.assertRaises(ValueError):
            bridge.answer(dict(payload, answer='Saved 500 hours weekly.'), validate_only=True)
        for question in ('Will you require sponsorship?', 'What is your salary expectation?', 'Do you consent?'):
            with self.assertRaises(ValueError):
                bridge.answer(dict(payload, question=question))

    def test_automatic_fill_validation_rechecks_evidence_and_revision_without_generation(self):
        bridge = self.bridge(generate=lambda _: self.fail('Validation must not generate another answer'))
        payload = dict(self.answer_payload(), answer='Saved 50 hours weekly.', citations=['experience:0:0'])
        payload['field_context'] = {'contextVersion': 2, 'subject': 'applicant', 'section': '', 'label': payload['question']}
        import hashlib, json
        from application_knowledge import field_context
        payload['answer_context'] = hashlib.sha256(json.dumps([field_context(payload['field_context']), payload['url'], payload['question'], payload['revision'], 'packet'], sort_keys=True).encode()).hexdigest()
        for _ in range(2):  # restored drafts go through the same fresh validation endpoint
            self.assertEqual(bridge.dispatch('POST', '/validate-answer', dict(payload, context_version=2))['answer'], payload['answer'])
        for overrides in ({'answer': 'Saved 500 hours weekly.'}, {'revision': 'stale'},
                          {'citations': ['invented']}, {'question': 'Do you consent?'}):
            with self.assertRaises(ValueError):
                bridge.dispatch('POST', '/validate-answer', dict(payload, context_version=2, **overrides))

    def test_only_hosted_postings_and_no_arbitrary_endpoints(self):
        from extension_api import posting_url
        for url in ('http://jobs.lever.co/test', 'https://jobs.lever.co.evil.test/a', 'file:///etc/passwd'):
            with self.assertRaises(ValueError):
                posting_url(url)
        with self.assertRaises(ValueError):
            self.bridge().dispatch('POST', '/send', {})

if __name__ == "__main__":
    unittest.main()

class TestNativeConnection(unittest.TestCase):
    def setUp(self):
        import tempfile
        import shutil
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / 'extension').mkdir()
        shutil.copy(Path(__file__).parent / 'extension/manifest.json', self.root / 'extension/manifest.json')
        for name in ('scripts/native_host.sh', 'Emails/.python/python/bin/python3'):
            file = self.root / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text('fixture')
        self.registration = self.root / 'Chrome/NativeMessagingHosts/com.applypilot.companion.json'

    def test_install_connection_revoke_and_repair_preserve_history(self):
        import native_bridge as native
        import json
        from extension_api import ExtensionAPI
        from review_app import ReviewStore
        (self.root / 'applications.json').write_text('[{"company":"Existing"}]')
        result = native.install(self.root, self.registration)
        self.assertTrue(result['enabled'])
        self.assertRegex(result['extension_id'], '^[a-p]{32}$')
        manifest = json.loads(self.registration.read_text())
        self.assertEqual(manifest['allowed_origins'], ['chrome-extension://' + result['extension_id'] + '/'])
        self.assertEqual((self.root / '.extension_access.json').stat().st_mode & 0o777, 0o600)
        bridge = ExtensionAPI(ReviewStore(self.root))
        self.addCleanup(bridge.state.close)
        origin = manifest['allowed_origins'][0]
        handshake = native.connect({'action': 'connect', 'version': 1}, origin, self.root, lambda _: 'http://127.0.0.1:8765')
        self.assertTrue(bridge.authorized(origin.rstrip('/'), 'Bearer ' + handshake['token']))
        self.assertTrue(native.status(self.root, self.registration)['last_connected'])
        bridge.revoke()
        with self.assertRaisesRegex(PermissionError, 'disabled'):
            native.connect({'action': 'connect', 'version': 1}, origin, self.root, lambda _: self.fail('Revoked grant started server'))
        self.assertFalse(native.status(self.root, self.registration)['enabled'])
        native.install(self.root, self.registration)
        self.assertFalse(bridge.authorized(origin.rstrip('/'), 'Bearer ' + handshake['token']))
        self.assertEqual(json.loads((self.root / 'applications.json').read_text()), [{'company': 'Existing'}])

    def test_protocol_restricts_origin_payload_size_and_command(self):
        import io
        import json
        import struct
        import native_bridge as native
        native.install(self.root, self.registration)
        origin = 'chrome-extension://' + native.extension_id(self.root) + '/'
        for payload, caller in [({'action': 'connect', 'version': 1}, 'chrome-extension://' + 'a'*32 + '/'), ({'action': 'run', 'command': 'anything'}, origin)]:
            body = json.dumps(payload).encode()
            sink = io.BytesIO()
            native.main(self.root, lambda _: self.fail('Rejected input started server'), caller, io.BytesIO(struct.pack('=I', len(body)) + body), sink)
            value = sink.getvalue()
            self.assertEqual(struct.unpack('=I', value[:4])[0], len(value[4:]))
            self.assertIn('error', json.loads(value[4:]))
        for body in [struct.pack('=I', 99999), struct.pack('=I', 5)+b'{}', b'']:
            sink = io.BytesIO()
            native.main(self.root, None, origin, io.BytesIO(body), sink)
            self.assertIn('error', json.loads(sink.getvalue()[4:]))

    def test_startup_revocation_race_does_not_issue_token(self):
        import native_bridge as native
        from Emails.reliability_store import atomic_write
        native.install(self.root, self.registration)
        def start(_):
            atomic_write(self.root / '.extension_access.json', '{}')
            return 'http://127.0.0.1:8765'
        with self.assertRaises(PermissionError):
            native.connect({'action':'connect','version':1}, 'chrome-extension://' + native.extension_id(self.root) + '/', self.root, start)

    def test_relocation_is_visible_and_repair_updates_path(self):
        import native_bridge as native
        import json
        native.install(self.root, self.registration)
        data = json.loads(self.registration.read_text())
        data['path'] = '/old/location/scripts/native_host.sh'
        self.registration.write_text(json.dumps(data))
        self.assertTrue(native.status(self.root, self.registration)['relocated'])
        self.assertFalse(native.status(self.root, self.registration)['enabled'])
        self.assertTrue(native.install(self.root, self.registration)['enabled'])

    def test_launcher_detects_wrong_server_and_starts_only_on_demand(self):
        from unittest.mock import patch, MagicMock
        from scripts import launch_applypilot as launcher
        import io
        import json
        with patch.object(launcher.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps({'product':'ApplyPilot','api_version':1,'instance':'wrong','native_version':1}).encode())):
            with self.assertRaisesRegex(RuntimeError, 'older review server'):
                launcher.health(self.root)
        with patch.object(launcher, 'health', side_effect=[False, True]), patch.object(launcher.subprocess, 'Popen') as process, patch.object(launcher.time, 'sleep'), patch.object(launcher.webbrowser, 'open') as browser:
            self.assertEqual(launcher.ensure_service(self.root), launcher.URL)
            process.assert_called_once()
            self.assertTrue(process.call_args.kwargs['start_new_session'])
            browser.assert_not_called()
        with patch.object(launcher, 'health', return_value=True), patch.object(launcher.subprocess, 'Popen') as process:
            launcher.ensure_service(self.root)
            process.assert_not_called()

    def test_missing_runtime_and_startup_errors_are_actionable(self):
        import native_bridge as native
        from unittest.mock import Mock
        python = self.root / 'Emails/.python/python/bin/python3'
        python.unlink()
        with self.assertRaisesRegex(RuntimeError, 'bundled Python is missing'):
            native.install(self.root, self.registration)
        self.assertFalse(self.registration.exists())
        python.write_text('fixture')
        native.install(self.root, self.registration)
        with self.assertRaisesRegex(RuntimeError, 'port occupied'):
            native.connect({'action':'connect','version':1}, 'chrome-extension://' + native.extension_id(self.root) + '/', self.root, Mock(side_effect=RuntimeError('port occupied')))
        self.assertIsNone(native.status(self.root, self.registration)['last_connected'])

    def test_launcher_opens_visible_setup_and_reports_browser_failure(self):
        from unittest.mock import patch
        from scripts import launch_applypilot as launcher
        with patch.object(launcher, 'ensure_service'), patch.object(launcher.webbrowser, 'open', return_value=True) as browser:
            launcher.main()
            browser.assert_called_once_with(launcher.URL + '/setup')
        with patch.object(launcher, 'ensure_service'), patch.object(launcher.webbrowser, 'open', return_value=False):
            with self.assertRaisesRegex(RuntimeError, '/setup'):
                launcher.main()


class TestLiveGreenhouseRegressions(unittest.TestCase):
    def test_content_and_manifest_versions_agree(self):
        import json
        import re
        manifest = json.loads((ROOT_DIR / 'extension/manifest.json').read_text())
        content = (ROOT_DIR / 'extension/content.js').read_text()
        version = re.search(r"const version='([^']+)'", content)
        self.assertIsNotNone(version)
        self.assertEqual(version.group(1), manifest['version'],
                         'Mismatched versions prevent all loaded-extension scans')

    def test_live_school_search_typography_and_linkedin_mapping_boundaries(self):
        import shutil
        import subprocess
        runtime = shutil.which('node')
        if not runtime:
            candidate = Path('/Applications/Visual Studio Code.app/Contents/MacOS/Code')
            if candidate.exists():
                runtime = str(candidate)
        if not runtime:
            self.skipTest('JavaScript runtime unavailable; run live-regressions.test.cjs separately')
        result = subprocess.run([runtime, str(ROOT_DIR / 'extension/tests/live-regressions.test.cjs')],
                                env={**os.environ, 'ELECTRON_RUN_AS_NODE': '1'}, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
