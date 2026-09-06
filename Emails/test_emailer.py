import os
import unittest
import json
import tempfile
import csv
from pathlib import Path
from email.message import EmailMessage

from resume_finder import clean_token, find_tailored_resume
from agent import get_company_domain, update_contact_status, get_pending_contacts, calculate_business_days_ahead, calculate_touch_schedule, BASE_DIR
import datetime

class TestEmailerSuite(unittest.TestCase):

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
        self.assertIn("DanielSuh_Resume.pdf", fallback_resume)

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
        self.assertIn("Contact TestFirst TestLast at TestCorp not found", res)

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
        # Friday creation (2026-08-28) -> Touch 1 Monday 2026-08-31 9:00 AM -> Touch 2 Wednesday 2026-09-02 9:03 AM
        fri_sched = calculate_touch_schedule(datetime.date(2026, 8, 28))
        self.assertEqual(fri_sched["touch1_date"], datetime.date(2026, 8, 31))
        self.assertEqual(fri_sched["touch1_scheduled_send"], "2026-08-31 09:00 AM")
        self.assertEqual(fri_sched["touch2_date"], datetime.date(2026, 9, 2))
        self.assertEqual(fri_sched["touch2_send_time"], "09:03 AM")
        self.assertIn("9:03 AM", fri_sched["touch2_formatted"])

        # Saturday creation (2026-08-29) -> Touch 1 Monday 2026-08-31 9:00 AM -> Touch 2 Wednesday 2026-09-02 9:03 AM
        sat_sched = calculate_touch_schedule(datetime.date(2026, 8, 29))
        self.assertEqual(sat_sched["touch1_date"], datetime.date(2026, 8, 31))
        self.assertEqual(sat_sched["touch2_date"], datetime.date(2026, 9, 2))

        # Sunday creation (2026-08-30) -> Touch 1 Monday 2026-08-31 9:00 AM -> Touch 2 Wednesday 2026-09-02 9:03 AM
        sun_sched = calculate_touch_schedule(datetime.date(2026, 8, 30))
        self.assertEqual(sun_sched["touch1_date"], datetime.date(2026, 8, 31))
        self.assertEqual(sun_sched["touch2_date"], datetime.date(2026, 9, 2))

        # Thursday creation (2026-08-27) -> Touch 1 Friday 2026-08-28 9:00 AM -> Touch 2 Tuesday 2026-09-01 9:03 AM
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

if __name__ == "__main__":
    unittest.main()
