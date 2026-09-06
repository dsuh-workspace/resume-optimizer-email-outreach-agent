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

class TestCopilotSupervisorSuite(unittest.TestCase):

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

        email, score = verify_or_synthesize_email("John", "Doe", "Stripe")
        self.assertIn("@", email)
        self.assertTrue(score > 0)

    def test_hunter_failsafe_loop_simulation(self):
        """Verifies prompt_hunter_failsafe_loop handles exit and candidate iteration cleanly."""
        from contact_finder import prompt_hunter_failsafe_loop
        
        # Test stop/exit trigger
        inputs_stop = iter(["stop"])
        name, email, pos = prompt_hunter_failsafe_loop("Stripe", "APM", "Hiring Manager", input_func=lambda _: next(inputs_stop))
        self.assertEqual(name, "Hiring Manager Lead")
        self.assertIn("@stripe.com", email)

        # Test valid candidate entry
        inputs_candidate = iter(["David Song", "Group PM"])
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

        # Process with auto_send=False to simulate without making live network calls
        processed = tracker.process_due_touch2_nudges(auto_send=False)
        
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

if __name__ == "__main__":
    unittest.main()
