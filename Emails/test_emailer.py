import os
import unittest
import json
import tempfile
import csv
import sys
from unittest.mock import patch, MagicMock
from pathlib import Path
from email.message import EmailMessage

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from resume_finder import clean_token, find_tailored_resume
from agent import get_company_domain, update_contact_status, get_pending_contacts, calculate_business_days_ahead, calculate_touch_schedule, BASE_DIR
import datetime

class TestEmailerSuite(unittest.TestCase):

    def setUp(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent if Path(__file__).parent.name in ('Emails', 'Resume') else Path(__file__).parent))
        from testing_support import isolate
        isolate(self)


    def test_contact_updates_preserve_headers_backup_and_reject_ambiguity(self):
        import agent
        path = agent.BASE_DIR / 'contacts.csv'
        original = 'First Name,Last Name,Company,Status,Email,Resume Path,Notes\nAlex,Smith,Example,Pending,,,keep\nAlex,Smith,Example,Pending,,,also keep\n'
        path.write_text(original)
        self.assertIn('ERROR', update_contact_status('Alex', 'Smith', 'Example', 'Ready'))
        self.assertEqual(path.read_text(), original)
        original = original.replace('Alex,Smith,Example,Pending,,,also keep', 'Other,Person,Other,Pending,,,also keep')
        path.write_text(original)
        self.assertIn('SUCCESS', update_contact_status('Alex', 'Smith', 'Example', 'Ready'))
        self.assertEqual(path.with_suffix('.csv.bak').read_text(), original)
        self.assertIn('also keep', path.read_text())
        self.assertIn('Notes', path.read_text())

    def test_contact_atomic_failure_and_concurrent_updates(self):
        import agent, reliability_store
        from concurrent.futures import ThreadPoolExecutor
        path = agent.BASE_DIR / 'contacts.csv'
        original = 'First Name,Last Name,Company,Status\nOne,A,Example,Pending\nTwo,B,Example,Pending\n'
        path.write_text(original)
        write = reliability_store.atomic_write
        def interrupted(destination, content):
            if destination == path:
                raise OSError('interrupted')
            write(destination, content)
        with patch('reliability_store.atomic_write', side_effect=interrupted):
            self.assertIn('ERROR', update_contact_status('One', 'A', 'Example', 'Ready'))
        self.assertEqual(path.read_text(), original)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(update_contact_status, first, last, 'Example', 'Ready') for first, last in [('One', 'A'), ('Two', 'B')]]
            self.assertTrue(all('SUCCESS' in future.result() for future in futures))
        self.assertEqual(path.read_text().count('Ready'), 2)
        for broken in ('First Name,First Name,Company,Status\nOne,A,Example,Pending\n', 'First Name,Last Name,Company,Status\nOne,A,Example\n'):
            path.write_text(broken)
            self.assertIn('ERROR', update_contact_status('One', 'A', 'Example', 'Ready'))
            self.assertEqual(path.read_text(), broken)

    def test_clean_token(self):
        """Tests that string cleaning strips non-alphanumeric characters properly."""
        self.assertEqual(clean_token("IBM, Inc."), "ibminc")
        self.assertEqual(clean_token("Stripe - APM"), "stripeapm")
        self.assertEqual(clean_token("Goldman Sachs"), "goldmansachs")

    def test_resume_finder_tailored_match(self):
        """Tests that find_tailored_resume locates existing company output folders."""
        ibm_resume = find_tailored_resume("IBM", "Brand Sales Specialist")
        self.assertIsNotNone(ibm_resume)
        self.assertTrue(os.path.exists(ibm_resume))
        self.assertTrue(ibm_resume.endswith(".pdf"))
        self.assertIn("IBM", ibm_resume)

    def test_resume_finder_fallback(self):
        """Tests that find_tailored_resume falls back to base resume when no company folder exists."""
        fallback_resume = find_tailored_resume("NonExistentCompanyXYZ", "Engineer")
        self.assertIsNotNone(fallback_resume)
        self.assertTrue(os.path.exists(fallback_resume))
        self.assertTrue(fallback_resume.endswith(".pdf"))
        self.assertTrue("Daniel_Suh_Resume.pdf" in fallback_resume or "DanielSuh_Resume.pdf" in fallback_resume)

    def test_get_company_domain_passthrough(self):
        """Tests that direct domain inputs pass through cleanly."""
        self.assertEqual(get_company_domain("google.com"), "google.com")
        self.assertEqual(get_company_domain("stripe.com"), "stripe.com")
        self.assertEqual(get_company_domain("ibm.com"), "ibm.com")

    def test_contacts_csv_operations(self):
        """Tests reading and updating contacts.csv safely."""
        contacts_json = get_pending_contacts()
        contacts = json.loads(contacts_json)
        self.assertIsInstance(contacts, list)

        # Update contact status test
        res = update_contact_status("TestFirst", "TestLast", "TestCorp", "Pending", "test@testcorp.com", "/path/to/test.pdf")
        self.assertIn("Contact not found", res)

    def test_subject_line_standard_option2(self):
        """Verifies that the standard subject line conforms to Option 2: Following up: [Role] — Daniel Suh."""
        role = "Brand Sales Specialist Co-Op"
        expected_prefix = f"Following up: {role} — Daniel Suh"
        self.assertTrue(expected_prefix.startswith("Following up:"))
        self.assertTrue(expected_prefix.endswith("Daniel Suh"))
        self.assertIn("—", expected_prefix)

    def test_email_attachment_mime_structure(self):
        """Verifies that EmailMessage correctly formats attachments without corruption."""
        msg = EmailMessage()
        msg.set_content("Test body text.")
        msg['Subject'] = "Following up: APM — Daniel Suh"
        msg['To'] = "recruiter@example.com"

        dummy_pdf_content = b"%PDF-1.4 dummy content"
        msg.add_attachment(dummy_pdf_content, maintype="application", subtype="pdf", filename="Daniel_Suh_Resume.pdf")

        # Verify message parts
        payload = msg.get_payload()
        self.assertEqual(len(payload), 2)
        self.assertEqual(payload[0].get_content_type(), "text/plain")
        self.assertEqual(payload[1].get_content_type(), "application/pdf")
        self.assertEqual(payload[1].get_filename(), "Daniel_Suh_Resume.pdf")

    def test_calculate_business_days_ahead(self):
        """Verifies that calculate_business_days_ahead accurately skips Saturdays and Sundays."""
        # Friday -> should land on Tuesday (+2 business days: Mon, Tue)
        friday = datetime.date(2026, 8, 28)
        due_tuesday = calculate_business_days_ahead(friday, days=2)
        self.assertEqual(due_tuesday, datetime.date(2026, 9, 1))
        self.assertEqual(due_tuesday.weekday(), 1) # Tuesday

        # Wednesday -> should land on Friday (+2 business days: Thu, Fri)
        wednesday = datetime.date(2026, 9, 2)
        due_friday = calculate_business_days_ahead(wednesday, days=2)
        self.assertEqual(due_friday, datetime.date(2026, 9, 4))
        self.assertEqual(due_friday.weekday(), 4) # Friday

    def test_calculate_touch_schedule_full_matrix(self):
        """
        Verifies the full schedule matrix:
          - Touch 1: Next business day at 9:00 AM (Monday if created Friday/weekend).
          - Touch 2: 2 business days after Touch 1 send at 9:03 AM.
        """
        # Friday creation (2026-08-28) -> Touch 1 Monday 2026-08-31 9:03 AM -> Touch 2 Wednesday 2026-09-02 9:06 AM
        fri_sched = calculate_touch_schedule(datetime.date(2026, 8, 28))
        self.assertEqual(fri_sched["touch1_date"], datetime.date(2026, 8, 31))
        self.assertEqual(fri_sched["touch1_scheduled_send"], "2026-08-31 09:03 AM")
        self.assertEqual(fri_sched["touch2_date"], datetime.date(2026, 9, 2))
        self.assertEqual(fri_sched["touch2_send_time"], "09:06 AM")
        self.assertIn("9:06 AM", fri_sched["touch2_formatted"])

        # Saturday creation (2026-08-29) -> Touch 1 Monday 2026-08-31 9:03 AM -> Touch 2 Wednesday 2026-09-02 9:06 AM
        sat_sched = calculate_touch_schedule(datetime.date(2026, 8, 29))
        self.assertEqual(sat_sched["touch1_date"], datetime.date(2026, 8, 31))
        self.assertEqual(sat_sched["touch2_date"], datetime.date(2026, 9, 2))

        # Sunday creation (2026-08-30) -> Touch 1 Monday 2026-08-31 9:03 AM -> Touch 2 Wednesday 2026-09-02 9:06 AM
        sun_sched = calculate_touch_schedule(datetime.date(2026, 8, 30))
        self.assertEqual(sun_sched["touch1_date"], datetime.date(2026, 8, 31))
        self.assertEqual(sun_sched["touch2_date"], datetime.date(2026, 9, 2))

        # Thursday creation (2026-08-27) -> Touch 1 Friday 2026-08-28 9:03 AM -> Touch 2 Tuesday 2026-09-01 9:06 AM
        thu_sched = calculate_touch_schedule(datetime.date(2026, 8, 27))
        self.assertEqual(thu_sched["touch1_date"], datetime.date(2026, 8, 28))
        self.assertEqual(thu_sched["touch2_date"], datetime.date(2026, 9, 1))

        # Wednesday creation (2026-08-26) -> Touch 1 Thursday 2026-08-27 9:00 AM -> Touch 2 Monday 2026-08-31 9:03 AM
        wed_sched = calculate_touch_schedule(datetime.date(2026, 8, 26))
        self.assertEqual(wed_sched["touch1_date"], datetime.date(2026, 8, 27))
        self.assertEqual(wed_sched["touch2_date"], datetime.date(2026, 8, 31))

        # Monday creation (2026-08-24) -> Touch 1 Tuesday 2026-08-25 9:00 AM -> Touch 2 Thursday 2026-08-27 9:03 AM
        mon_sched = calculate_touch_schedule(datetime.date(2026, 8, 24))
        self.assertEqual(mon_sched["touch1_date"], datetime.date(2026, 8, 25))
        self.assertEqual(mon_sched["touch2_date"], datetime.date(2026, 8, 27))

    def test_quick_bump_skill_exists(self):
        """Verifies that the Quick Bump Follow-up skill file is present and valid markdown."""
        skill_file = BASE_DIR / "skills" / "Quick Bump Follow-up" / "SKILL.md"
        self.assertTrue(skill_file.exists())
        content = skill_file.read_text(encoding="utf-8")
        self.assertIn("Quick Bump Follow-up", content)
        self.assertIn("note below got buried", content.lower())
        self.assertIn("totally understand things get busy", content.lower())

    def test_thread_headers_and_reply_termination_logic(self):
        """Verifies In-Reply-To and References header chaining on threaded follow-up drafts."""
        msg = EmailMessage()
        msg['To'] = "recruiter@stripe.com"
        msg['Subject'] = "Re: Following up: APM — Daniel Suh"
        msg['In-Reply-To'] = "<original_msg_123@mail.gmail.com>"
        msg['References'] = "<original_msg_123@mail.gmail.com>"
        msg.set_content("Following up in case my note below got buried...")

        self.assertEqual(msg['In-Reply-To'], "<original_msg_123@mail.gmail.com>")
        self.assertEqual(msg['References'], "<original_msg_123@mail.gmail.com>")

    def test_generate_touch2_nudge_exact_copy(self):
        """Verifies that generate_touch2_nudge generates 100% deterministic copy with zero variance."""
        from agent import generate_touch2_nudge
        subj, body = generate_touch2_nudge("Sarah Jenkins", "Brand Sales Specialist")
        self.assertEqual(subj, "Following up: Brand Sales Specialist — Daniel Suh")
        self.assertIn("Hi Sarah,", body)
        self.assertIn("Following up in case my note below got buried, totally understand things get busy. Would still love the chance to connect if timing works on your end!", body)
        self.assertIn("Daniel Suh", body)
        self.assertIn("linkedin.com/in/daniel-suh-994411297", body)

    def test_search_company_contacts_fallback(self):
        """Verifies search_company_contacts_via_hunter returns valid dictionary structure."""
        from agent import search_company_contacts_via_hunter
        contacts = search_company_contacts_via_hunter("Stripe", "Associate Product Manager")
        self.assertIn("hiring_manager", contacts)
        self.assertIn("recruiter", contacts)

    def test_verify_gmail_access_active(self):
        """Verifies verify_gmail_access returns valid dictionary with authenticated status."""
        from gmail_draft import verify_gmail_access
        service = MagicMock()
        service.users().getProfile().execute.return_value = {'emailAddress': 'test@berkeley.edu'}
        with patch('gmail_draft.get_gmail_service', return_value=service):
            health = verify_gmail_access()
        self.assertIsInstance(health, dict)
        self.assertIn("authenticated", health)
        self.assertIn("email_address", health)
        self.assertTrue(health["authenticated"], f"Gmail authentication failed: {health.get('error')}")
        self.assertIn("@", health["email_address"])

    def test_contact_auditor_seniority_detection(self):
        """Verifies detect_seniority_tier categorizes role titles and JD keywords accurately."""
        from contact_auditor import detect_seniority_tier
        self.assertEqual(detect_seniority_tier("Summer Analyst 2027 – Veritas"), "INTERNSHIP")
        self.assertEqual(detect_seniority_tier("Brand Sales Specialist Co-Op"), "INTERNSHIP")
        self.assertEqual(detect_seniority_tier("New Grad Associate Product Manager"), "NEW_GRAD")
        self.assertEqual(detect_seniority_tier("VP of Engineering"), "EXECUTIVE")
        self.assertEqual(detect_seniority_tier("Senior Consultant"), "MID_LEVEL")

    def test_contact_auditor_partner_flagged_for_internship(self):
        """Verifies that Partners/Global Heads are flagged as TOO_SENIOR_REJECT for internships."""
        from contact_auditor import audit_candidate_seniority
        partner_candidate = {
            "name": "Alex Morgan",
            "position": "Partner & Global Head of Veritas",
            "department": "Executive",
            "relevance_score": 80
        }
        audited = audit_candidate_seniority(partner_candidate, "INTERNSHIP", "Oliver Wyman")
        self.assertEqual(audited["sanity_rating"], "TOO_SENIOR_REJECT")
        self.assertIn("🔴", audited["sanity_badge"])
        self.assertTrue(audited["adjusted_score"] < 80)

    def test_contact_auditor_campus_recruiter_elevated_for_internship(self):
        """Verifies that Campus/University Recruiters are rated OPTIMAL_GATEKEEPER for internships."""
        from contact_auditor import audit_candidate_seniority
        rec_candidate = {
            "name": "Emily Rodriguez",
            "position": "Senior Campus Recruiter, Early Careers",
            "department": "Human Resources",
            "relevance_score": 75
        }
        audited = audit_candidate_seniority(rec_candidate, "INTERNSHIP", "Oliver Wyman")
        self.assertEqual(audited["sanity_rating"], "OPTIMAL_GATEKEEPER")
        self.assertIn("🟢", audited["sanity_badge"])
        self.assertTrue(audited["adjusted_score"] > 75)

    def test_contact_auditor_full_audit_workflow(self):
        """Verifies run_seniority_sanity_audit correctly picks Campus Recruiter as P1 over Partner."""
        from contact_auditor import run_seniority_sanity_audit
        pool = {
            "hiring_managers": [
                {"name": "Alex Morgan", "position": "Partner & Global Head", "relevance_score": 85, "email": "alex@ow.com"},
                {"name": "David Lee", "position": "Engagement Manager", "relevance_score": 70, "email": "david@ow.com"}
            ],
            "recruiters": [
                {"name": "Emily Rodriguez", "position": "Senior Campus Recruiter", "relevance_score": 75, "email": "emily@ow.com"}
            ]
        }
        result = run_seniority_sanity_audit(pool, "Summer Analyst 2027", "Oliver Wyman")
        self.assertEqual(result["seniority_tier"], "INTERNSHIP")
        self.assertEqual(result["recommended_p1"]["name"], "Emily Rodriguez") # Campus Recruiter
        self.assertEqual(result["recommended_p2"]["name"], "David Lee") # Engagement Manager Peer

    def test_detect_seniority_tier_precedence(self):
        """Verifies that explicit senior titles are not misclassified as internships even if JD mentions interns."""
        from contact_auditor import detect_seniority_tier
        jd_with_intern_mentions = "We expect you to mentor and guide software engineering interns during the summer."
        self.assertEqual(detect_seniority_tier("Senior Software Engineer", jd_with_intern_mentions), "MID_LEVEL")
        self.assertEqual(detect_seniority_tier("Director of Product", jd_with_intern_mentions), "EXECUTIVE")

    def test_detect_seniority_tier_implicit_internship(self):
        """Verifies that neutral titles with enrolled student keywords in JD body are correctly classified."""
        from contact_auditor import detect_seniority_tier
        jd_body = "Part of IBM Sales Internship Program. Actively enrolled undergraduate student."
        self.assertEqual(detect_seniority_tier("Brand Sales Specialist", jd_body), "INTERNSHIP")

    def test_contact_auditor_empty_pool_safe(self):
        """Verifies run_seniority_sanity_audit handles empty pools without runtime errors."""
        from contact_auditor import run_seniority_sanity_audit
        result = run_seniority_sanity_audit({"hiring_managers": [], "recruiters": []}, "Summer Analyst", "TestCo")
        self.assertIsNone(result["recommended_p1"])
        self.assertIsNone(result["recommended_p2"])
        self.assertEqual(result["total_evaluated"], 0)

    def test_contact_auditor_experienced_role_filtering(self):
        """Verifies that for experienced roles, direct managers are P1 and campus recruiters are penalized."""
        from contact_auditor import run_seniority_sanity_audit
        pool = {
            "hiring_managers": [
                {"name": "Marcus Vance", "position": "Engineering Manager - Platform", "relevance_score": 75, "email": "marcus@stripe.com"}
            ],
            "recruiters": [
                {"name": "Lisa Ray", "position": "Campus Recruiter", "relevance_score": 80, "email": "lisa@stripe.com"}
            ]
        }
        result = run_seniority_sanity_audit(pool, "Senior Software Engineer", "Stripe")
        self.assertEqual(result["seniority_tier"], "MID_LEVEL")
        self.assertEqual(result["recommended_p1"]["name"], "Marcus Vance")
        self.assertEqual(result["audited_recruiters"][0]["sanity_rating"], "WRONG_PIPELINE_REJECT")

    def test_email_validator_rfc_syntax_valid(self):
        """Verifies that valid RFC 5322 emails are recognized as valid."""
        from email_validator import is_valid_email, validate_email
        valid_samples = [
            "john.doe@company.com",
            "sarah+recruiting@stripe.com",
            "alex@sub.domain.org",
            "first-last@company.tech",
            "user_name@service.io",
            "recruiting@ibm.com"
        ]
        for email in valid_samples:
            self.assertTrue(is_valid_email(email), f"Expected valid: {email}")
            is_valid, msg = validate_email(email)
            self.assertTrue(is_valid)

    def test_email_validator_rfc_syntax_invalid(self):
        """Verifies that malformed email addresses fail RFC 5322 syntax validation."""
        from email_validator import is_valid_email, validate_email
        invalid_samples = [
            "",
            "   ",
            "not-an-email",
            "@missinglocal.com",
            "missingdomain@",
            "user@@domain.com",
            "user@domain..com",
            "user..name@domain.com",
            ".leadingdot@domain.com",
            "trailingdot.@domain.com",
            "user@domain",  # Missing TLD
            "user@domain.c",  # TLD too short (<2 chars)
            "user name@domain.com",  # Space in local part
            "user@dom ain.com",  # Space in domain
            "user@-domain.com",  # Hyphen at start of label
            "user@domain-.com",  # Hyphen at end of label
            "a" * 65 + "@domain.com",  # Local part exceeds 64 chars
        ]
        for email in invalid_samples:
            self.assertFalse(is_valid_email(email), f"Expected invalid: {email}")
            is_valid, reason = validate_email(email)
            self.assertFalse(is_valid)
            self.assertTrue(len(reason) > 0)

    def test_email_validator_placeholder_detection(self):
        """Verifies that dummy, disposable, and placeholder emails are detected and rejected."""
        from email_validator import validate_email, is_placeholder_or_dummy_email
        dummy_samples = [
            "user@example.com",
            "test@test.com",
            "recruiter@fake.com",
            "user@localhost",
            "candidate@mailinator.com",
            "placeholder@stripe.com",
            "your-email@stripe.com",
            "yourname@stripe.com",
            "null@stripe.com"
        ]
        for email in dummy_samples:
            is_dummy, reason = is_placeholder_or_dummy_email(email)
            self.assertTrue(is_dummy, f"Expected dummy: {email}")
            is_valid, _ = validate_email(email, allow_placeholders=False)
            self.assertFalse(is_valid, f"Expected rejected placeholder: {email}")

        # Company.com generic fallback check
        is_dummy_company, _ = is_placeholder_or_dummy_email("recruiting@company.com", target_company="Stripe")
        self.assertTrue(is_dummy_company)

    @patch("email_validator.requests.get")
    def test_email_validator_hunter_verifier_mock(self, mock_get):
        """Verifies that Hunter.io verifier deliverability responses are accurately evaluated."""
        from email_validator import verify_email_with_hunter, validate_email

        # Case 1: Deliverable / Valid response
        mock_resp_valid = MagicMock()
        mock_resp_valid.status_code = 200
        mock_resp_valid.json.return_value = {
            "data": {
                "status": "valid",
                "result": "deliverable",
                "score": 95,
                "email": "sarah@stripe.com"
            }
        }
        mock_get.return_value = mock_resp_valid

        res = verify_email_with_hunter("sarah@stripe.com", api_key="test_key_123")
        self.assertTrue(res["checked"])
        self.assertTrue(res["is_valid"])
        self.assertEqual(res["score"], 95)

        is_val, _ = validate_email("sarah@stripe.com", hunter_api_key="test_key_123")
        self.assertTrue(is_val)

        # Case 2: Undeliverable / Invalid response
        mock_resp_invalid = MagicMock()
        mock_resp_invalid.status_code = 200
        mock_resp_invalid.json.return_value = {
            "data": {
                "status": "invalid",
                "result": "undeliverable",
                "score": 0,
                "email": "bounced@stripe.com"
            }
        }
        mock_get.return_value = mock_resp_invalid

        res_inv = verify_email_with_hunter("bounced@stripe.com", api_key="test_key_123")
        self.assertTrue(res_inv["checked"])
        self.assertFalse(res_inv["is_valid"])

        is_val, reason = validate_email("bounced@stripe.com", hunter_api_key="test_key_123")
        self.assertFalse(is_val)
        self.assertIn("Hunter.io Deliverability Check Failed", reason)

    @patch("agent.requests.get")
    def test_hunter_email_finder_validity_filter(self, mock_get):
        """Verifies find_email_via_hunter filters out emails flagged invalid by Hunter."""
        from agent import find_email_via_hunter

        # Case 1: Hunter returns status invalid in verification object
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {
                "email": "invalid_user@stripe.com",
                "score": 20,
                "verification": {"status": "invalid"}
            }
        }
        mock_get.return_value = mock_resp

        with patch("agent.HUNTER_API_KEY", "valid_key"):
            email, score = find_email_via_hunter("Bad", "User", "Stripe")
            self.assertIsNone(email)
            self.assertIsNone(score)

    def test_save_gmail_draft_rejects_invalid_email(self):
        """Verifies save_gmail_draft halts execution immediately if recipient email is invalid."""
        from agent import save_gmail_draft
        res = save_gmail_draft(
            to_email="invalid-recipient",
            subject="Test Subject",
            body_text="Test Body"
        )
        self.assertIn("ERROR: Invalid recipient email 'invalid-recipient'", res)

    def test_verify_or_synthesize_email_guarantees_validity(self):
        """Verifies verify_or_synthesize_email always outputs an email with valid RFC 5322 syntax."""
        from contact_finder import verify_or_synthesize_email
        from email_validator import is_valid_email

        with patch('agent.find_email_via_hunter', return_value=(None, None)):
            email, score = verify_or_synthesize_email('John', 'Doe', 'Stripe')
        self.assertEqual((email, score), ('', 0))
        with patch('agent.find_email_via_hunter', return_value=('john.doe@stripe.com', 90)):
            email, score = verify_or_synthesize_email('John', 'Doe', 'Stripe')
        self.assertEqual((email, score), ('john.doe@stripe.com', 90))

    def test_stage1_three_attempts_and_failure_report(self):
        """Verifies discover_ranked_contacts runs at least 3 separate attempts and formats failure report."""
        from contact_finder import discover_ranked_contacts, format_stage1_failure_report

        res = discover_ranked_contacts("Stripe", "Associate Product Manager")
        self.assertIn("stage1_attempts", res)
        self.assertGreaterEqual(len(res["stage1_attempts"]), 3)
        attempts = res["stage1_attempts"]
        self.assertEqual(attempts[0]["attempt"], 1)
        self.assertEqual(attempts[1]["attempt"], 2)
        self.assertEqual(attempts[2]["attempt"], 3)

        # Test report generator
        mock_attempts = [
            {"attempt": 1, "strategy": "Hunter.io Live Domain Directory Search", "status": "FAILED", "reason": "No matching contacts found"},
            {"attempt": 2, "strategy": "AI Leadership Resolution + Hunter Email Finder", "status": "FAILED", "reason": "Hunter returned no verified mailboxes"},
            {"attempt": 3, "strategy": "Corporate Pattern Synthesis & Deliverability Verification", "status": "FAILED", "reason": "DNS host resolution failed"}
        ]
        report = format_stage1_failure_report(mock_attempts, "NonExistentCorp", "Product Manager")
        self.assertIn("STAGE 1 AUTOMATIC DISCOVERY FAILURE REPORT", report)
        self.assertIn("Attempt 1", report)
        self.assertIn("Attempt 2", report)
        self.assertIn("Attempt 3", report)
        self.assertIn("STAGE 2", report)

    def test_build_email_message_html_and_clean_attachment(self):
        """Verifies build_email_message formats multipart/alternative HTML and clean attachment naming."""
        from gmail_draft import build_email_message
        import tempfile

        with tempfile.NamedTemporaryFile(suffix="Daniel_Suh_Resume_Stripe_2026.pdf", delete=False) as tf:
            tf.write(b"%PDF-1.4 test")
            temp_pdf = tf.name

        try:
            body = "Hi Sarah,\n\nI applied for the role. See my profile: linkedin.com/in/daniel-suh-994411297\n\nThanks,\nDaniel"
            msg = build_email_message(
                to_email="sarah@stripe.com",
                subject="Following up: APM — Daniel Suh",
                body_text=body,
                attachment_path=temp_pdf
            )

            # Assert headers
            self.assertEqual(msg["To"], "sarah@stripe.com")
            self.assertEqual(msg["Subject"], "Following up: APM — Daniel Suh")

            # Check multipart structure
            payload = msg.get_payload()
            self.assertGreaterEqual(len(payload), 2)

            # Text / HTML alternative part
            alt_part = payload[0]
            self.assertEqual(alt_part.get_content_type(), "multipart/alternative")
            subparts = alt_part.get_payload()
            self.assertEqual(subparts[0].get_content_type(), "text/plain")
            self.assertEqual(subparts[1].get_content_type(), "text/html")

            # HTML must contain clickable link
            html_content = subparts[1].get_content()
            self.assertIn('<a href="https://linkedin.com/in/daniel-suh-994411297"', html_content)

            # Attachment must have clean display filename
            att_part = payload[1]
            self.assertEqual(att_part.get_content_type(), "application/pdf")
            self.assertEqual(att_part.get_filename(), "Daniel_Suh_Resume.pdf")
        finally:
            if os.path.exists(temp_pdf):
                os.unlink(temp_pdf)

    def test_hunter_quota_depletion_handling(self):
        """Verifies that HTTP 402 and 429 from Hunter.io are cleanly captured and reported."""
        from unittest.mock import patch, MagicMock
        from contact_finder import discover_ranked_contacts

        mock_resp = MagicMock()
        mock_resp.status_code = 402
        mock_resp.text = "Monthly quota reached"

        with patch("requests.get", return_value=mock_resp), \
             patch("contact_finder.HUNTER_API_KEY", "valid_key"):
            res = discover_ranked_contacts("Stripe", "APM")
            attempts = res["stage1_attempts"]
            self.assertEqual(attempts[0]["status"], "FAILED")
            self.assertIn("monthly credit quota exhausted", attempts[0]["reason"])

    def test_touch2_draft_only_safety_mode(self):
        """Verifies process_due_touch2_nudges defaults to draft staging and never calls send_gmail_message when auto_send=False."""
        import tracker
        from unittest.mock import patch

        test_app = {
            "id": "draft-safety",
            "touch1_thread_id": "thread-123",
            "company": "DraftSafetyTestCo",
            "role": "Product Lead",
            "stage": "Draft Staged",
            "hiring_manager_name": "Taylor Swift",
            "hiring_manager_email": "taylor@draftsafety.com",
            "touch2_due_date": "2020-01-01",  # Due in past
            "touch2_status": "Scheduled",
            "touch2_subject": "Following up: Product Lead — Daniel Suh",
            "touch2_body": "Hi Taylor, following up in case my note got buried."
        }
        with patch("gmail_draft.send_gmail_message") as mock_send, \
             patch("gmail_draft.create_gmail_draft", return_value={"id": "mock_draft_123"}) as mock_draft, \
             patch("gmail_draft.check_thread_for_replies", return_value={"has_reply": False, "touch1_sent": True, "sent_at": "2020-01-01T17:00:00+00:00", "first_message_id": "<sent>"}), \
             patch("tracker.load_applications", return_value=[test_app]), \
             patch("tracker._save_applications_unlocked"):

            # Run with auto_send=False (the safe default)
            processed = tracker.process_due_touch2_nudges(auto_send=False, stage_draft=True)

            # send_gmail_message MUST NOT have been called
            mock_send.assert_not_called()
            # create_gmail_draft MUST have been called to stage draft safely
            mock_draft.assert_called_once()
            self.assertEqual(len(processed), 1)
            self.assertEqual(processed[0]["action"], "draft_staged")

    def test_stage2_skip_ends_workflow_without_stage3_alias(self):
        """Verifies that skipping Stage 2 returns None and does NOT route to generic aliases (#3)."""
        from contact_finder import prompt_hunter_failsafe_loop

        for skip_cmd in ["skip", "stop", "exit", "quit", "cancel"]:
            name, email, pos = prompt_hunter_failsafe_loop(
                "Stripe",
                "Product Manager",
                "Hiring Manager",
                input_func=lambda _: skip_cmd
            )
            self.assertIsNone(name, f"Expected None name on '{skip_cmd}'")
            self.assertIsNone(email, f"Expected None email on '{skip_cmd}' (Stage 3 alias must NOT be used)")
            self.assertIsNone(pos, f"Expected None pos on '{skip_cmd}'")


class TestGmailReliability(unittest.TestCase):
    def setUp(self):
        from testing_support import isolate
        isolate(self)

    def service(self, messages=None):
        service = MagicMock()
        service.users().getProfile().execute.return_value = {'emailAddress': 'daniel@berkeley.edu'}
        service.users().drafts().create().execute.return_value = {'id': 'draft', 'message': {'threadId': 'thread'}}
        service.users().threads().get().execute.return_value = {'messages': messages or []}
        return service

    def test_repeated_draft_operation_creates_once(self):
        from gmail_draft import create_gmail_draft
        service = self.service()
        with patch('gmail_draft.get_gmail_service', return_value=service):
            first = create_gmail_draft('alex@acme.org', 'Subject', 'First wording', idempotency_key='operation')
            second = create_gmail_draft('alex@acme.org', 'Subject', 'Changed wording', idempotency_key='operation')
        self.assertEqual(first['id'], second['id'])
        self.assertTrue(second['reused'])
        self.assertEqual(service.users().drafts().create().execute.call_count, 1)

    def test_stable_correlation_survives_changed_gmail_resource_id(self):
        from gmail_draft import create_gmail_draft
        import base64
        from email import message_from_bytes
        service = self.service()
        with patch('gmail_draft.get_gmail_service', return_value=service):
            draft = create_gmail_draft('alex@acme.org', 'Subject', 'Body', idempotency_key='correlated')
        request = service.users().drafts().create.call_args.kwargs['body']
        mime = message_from_bytes(base64.urlsafe_b64decode(request['message']['raw']))
        self.assertEqual(mime['Message-ID'], draft['rfc_message_id'])
        self.assertEqual(mime['X-ApplyPilot-Operation'].strip(), draft['operation_id'])
        sent = self.message(['SENT'], 'daniel@berkeley.edu')
        sent['id'] = 'new-sent-id'
        sent['payload']['headers'].append({'name': 'X-ApplyPilot-Operation', 'value': draft['operation_id']})
        self.assertEqual(self.inspect([sent])['sent_messages'][0]['operation_id'], draft['operation_id'])

    def test_uncertain_draft_response_blocks_retry(self):
        from gmail_draft import create_gmail_draft
        service = self.service()
        service.users().drafts().create().execute.side_effect = TimeoutError('response lost')
        with patch('gmail_draft.get_gmail_service', return_value=service):
            with self.assertRaises(TimeoutError):
                create_gmail_draft('alex@acme.org', 'Subject', 'Body', idempotency_key='operation')
            with self.assertRaisesRegex(RuntimeError, 'uncertain'):
                create_gmail_draft('alex@acme.org', 'Subject', 'Body', idempotency_key='operation')
        self.assertEqual(service.users().drafts().create().execute.call_count, 1)

    def test_compatibility_schedule_only_creates_draft(self):
        from gmail_draft import create_scheduled_send, send_gmail_message
        service = self.service()
        with patch('gmail_draft.get_gmail_service', return_value=service):
            result = create_scheduled_send('alex@acme.org', 'Subject', 'Body', datetime.datetime.now())
            with self.assertRaisesRegex(RuntimeError, 'Draft-only'):
                send_gmail_message('alex@acme.org', 'Subject', 'Body')
        self.assertEqual(result['threadId'], 'thread')
        service.users().messages().send.assert_not_called()

    def message(self, labels, sender, date='1578078000000'):
        return {'labelIds': labels, 'internalDate': date, 'payload': {'headers': [{'name': 'From', 'value': sender}, {'name': 'To', 'value': 'alex@acme.org'}, {'name': 'Message-ID', 'value': '<sent>'}]}}

    def inspect(self, messages):
        from gmail_draft import check_thread_for_replies
        with patch('gmail_draft.get_gmail_service', return_value=self.service(messages)):
            return check_thread_for_replies('thread', 'alex@acme.org')

    def test_drafts_and_multiple_outgoing_are_not_replies(self):
        self.assertFalse(self.inspect([self.message(['DRAFT'], 'daniel@berkeley.edu')])['touch1_sent'])
        result = self.inspect([self.message(['SENT'], 'daniel@berkeley.edu'), self.message(['DRAFT'], 'daniel@berkeley.edu'), self.message(['SENT'], 'daniel@berkeley.edu')])
        self.assertTrue(result['touch1_sent'])
        self.assertFalse(result['has_reply'])
        self.assertIsNotNone(result['sent_at'])

    def test_exact_recipient_reply_detection(self):
        sent = self.message(['SENT'], 'daniel@berkeley.edu')
        self.assertTrue(self.inspect([sent, self.message(['INBOX'], 'Alex <alex@acme.org>')])['has_reply'])
        self.assertFalse(self.inspect([sent, self.message(['INBOX'], 'alex@acme.org.attacker.net')])['has_reply'])

    def test_gmail_errors_never_imply_sent(self):
        from gmail_draft import check_thread_for_replies
        result = check_thread_for_replies('thread', 'alex@acme.org')
        self.assertFalse(result['touch1_sent'])
        self.assertIsNotNone(result['error'])

    def test_unknown_or_risky_mailbox_cannot_pass(self):
        from email_validator import contact_verification
        for record in [{'checked': False, 'is_valid': True, 'score': 90}, {'checked': True, 'is_valid': False, 'score': 90}, {'checked': True, 'is_valid': True, 'score': 49}]:
            with patch('email_validator.verify_email_with_hunter', return_value=record), self.assertRaises(ValueError):
                contact_verification('alex@acme.org')

    def test_direct_email_has_explicit_provenance(self):
        from email_validator import contact_verification
        with patch('email_validator.verify_email_with_hunter') as verify:
            record = contact_verification('Alex@acme.org', user_provided=True)
        self.assertEqual(record['source'], 'user-provided')
        self.assertEqual(record['email'], 'alex@acme.org')
        self.assertIn('checked_at', record)
        verify.assert_not_called()

    def test_no_gmail_send_call_in_production_sources(self):
        import ast
        for path in (BASE_DIR.parent / 'copilot.py', BASE_DIR.parent / 'tracker.py', BASE_DIR / 'gmail_draft.py', BASE_DIR / 'agent.py'):
            tree = ast.parse(path.read_text())
            calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'send']
            self.assertEqual(calls, [], str(path))


class TestAdditionalEmailReliability(unittest.TestCase):
    setUp = TestGmailReliability.setUp
    service = TestGmailReliability.service
    message = TestGmailReliability.message

    def test_missing_attachment_fails_before_gmail(self):
        from gmail_draft import create_gmail_draft
        with patch('gmail_draft.get_gmail_service') as service, self.assertRaises(FileNotFoundError):
            create_gmail_draft('alex@acme.org', 'Subject', 'Body', attachment_path='/missing/resume.pdf')
        service.assert_not_called()

    def test_old_thread_messages_do_not_start_new_attempt(self):
        from gmail_draft import check_thread_for_replies
        service = self.service([self.message(['SENT'], 'daniel@berkeley.edu')])
        with patch('gmail_draft.get_gmail_service', return_value=service):
            result = check_thread_for_replies('thread', 'alex@acme.org', not_before='2026-01-01T00:00:00+00:00')
        self.assertFalse(result['touch1_sent'])

    def test_sent_to_other_recipient_is_not_confirmation(self):
        from gmail_draft import check_thread_for_replies
        service = self.service([self.message(['SENT'], 'daniel@berkeley.edu')])
        with patch('gmail_draft.get_gmail_service', return_value=service):
            result = check_thread_for_replies('thread', 'someoneelse@acme.org')
        self.assertFalse(result['touch1_sent'])

    def test_draft_reuse_reports_original_body(self):
        from gmail_draft import create_gmail_draft
        with patch('gmail_draft.get_gmail_service', return_value=self.service()):
            create_gmail_draft('alex@acme.org', 'Subject', 'Original', idempotency_key='same')
            result = create_gmail_draft('alex@acme.org', 'Subject', 'New text', idempotency_key='same')
        self.assertEqual(result['review_snapshot']['body'], 'Original')
        self.assertIn('created_at', result['review_snapshot'])

    def test_direct_entry_provenance_is_not_assigned_to_hunter_lookup(self):
        from contact_finder import prompt_hunter_failsafe_loop
        direct = set()
        entries = iter(['alex@acme.org', 'Recruiter'])
        result = prompt_hunter_failsafe_loop('Acme', 'PM', input_func=lambda _: next(entries), user_provided_emails=direct)
        self.assertEqual(direct, {'alex@acme.org'})
        direct.clear()
        entries = iter(['Alex Smith', 'Recruiter'])
        with patch('agent.find_email_via_hunter', return_value=('alex@acme.org', 90)):
            prompt_hunter_failsafe_loop('Acme', 'PM', input_func=lambda _: next(entries), user_provided_emails=direct)
        self.assertEqual(direct, set())


class TestPacketSelection(unittest.TestCase):
    def test_attachment_checksum_and_evidence_are_required(self):
        import tempfile
        import hashlib
        from resume_finder import load_verified_packet
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / 'Resume' / 'output' / 'Acme_PM'
            output.mkdir(parents=True)
            (root / 'Resume' / 'master_profile.json').write_text('{}')
            pdf = output / 'resume.pdf'
            pdf.write_bytes(b'validated artifact')
            data = {'evidence_version': 1, 'target_company': 'Acme', 'target_role': 'PM', 'artifact_sha256': hashlib.sha256(pdf.read_bytes()).hexdigest()}
            (output / 'tailored_resume.json').write_text(json.dumps(data))
            with patch('resume_finder.BASE_DIR', root / 'Emails'), patch('evidence.validate_resume_evidence'):
                selected, _ = load_verified_packet('Acme', 'PM')
                self.assertEqual(selected, str(pdf))
                with self.assertRaises(FileNotFoundError):
                    load_verified_packet('Acme', 'Different Role')
                pdf.write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError, 'does not match'):
                    load_verified_packet('Acme', 'PM')
                data.pop('evidence_version')
                (output / 'tailored_resume.json').write_text(json.dumps(data))
                with self.assertRaisesRegex(ValueError, 'no source evidence'):
                    load_verified_packet('Acme', 'PM')

    def test_operation_identity_is_shared_and_normalized(self):
        from reliability_store import application_operation_key
        self.assertEqual(application_operation_key(' Acme ', ' PM ', 'Renewal'), application_operation_key('acme', 'pm', 'renewal'))
        self.assertNotEqual(application_operation_key('Acme', 'PM'), application_operation_key('Acme', 'PM', 'new'))

if __name__ == "__main__":
    unittest.main()
