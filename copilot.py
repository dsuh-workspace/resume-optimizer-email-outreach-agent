#!/usr/bin/env python3
"""
Master Job Search Co-Pilot (Supervisor Orchestrator)
Author: Daniel Suh & Antigravity

A hierarchical multi-agent supervisor that orchestrates:
  1. Resume Specialist Agent (Tailoring, Google X-Y-Z formula, ATS math, 1-page PDF render)
  2. Outreach & Email Specialist Agent (Hunter.io, voice matching, Gmail draft staging with PDF)
  3. Continuous Unit Test Runner (Validating 100% test coverage)
"""

import os
import re
import sys
import json
import argparse
import asyncio
import unittest
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, List

# Root setup and path injection for specialist subagents
ROOT_DIR = Path(__file__).resolve().parent
RESUME_DIR = ROOT_DIR / "Resume"
EMAILS_DIR = ROOT_DIR / "Emails"

if str(RESUME_DIR) not in sys.path:
    sys.path.insert(0, str(RESUME_DIR))
if str(EMAILS_DIR) not in sys.path:
    sys.path.insert(0, str(EMAILS_DIR))

try:
    from reliability_store import application_operation_key
    from evidence import evidence_markdown, validate_outreach_evidence
    from tailor import tailor_resume, generate_report_markdown, get_genai_client, calculate_deterministic_ats_score
    from render_pdf import save_resume_artifacts, clean_file_name
    from agent import (
        generate_email_draft_async,
        find_email_via_hunter,
        search_company_contacts_via_hunter,
        get_company_domain,
        calculate_business_days_ahead,
        calculate_touch_schedule
    )
    from contact_finder import (
        discover_ranked_contacts,
        generate_xray_search_links,
        verify_or_synthesize_email,
        prompt_hunter_failsafe_loop,
        extract_name_from_input
    )
    from contact_auditor import (
        run_seniority_sanity_audit,
        render_sanity_report_cli,
        detect_seniority_tier
    )
    from gmail_draft import create_gmail_draft, create_scheduled_send, check_thread_for_replies, verify_gmail_access
    from resume_finder import find_tailored_resume, load_verified_packet
    from email_validator import (
        is_valid_email,
        validate_email,
        sanitize_and_validate_email,
        contact_verification,
        verify_email_with_hunter
    )
    from tracker import (
        record_application,
        find_application,
        update_application_stage,
        load_applications,
        process_due_touch2_nudges,
        APPLICATIONS_MD_FILE
    )
    from notifier import (
        notify_pipeline_completion,
        send_system_notification,
        play_alert_sound,
        open_in_file_manager,
        get_latest_output_packet
    )
except ImportError as e:
    print(f"⚠️ Warning during subagent module import: {e}")

def render_review_packet(company, role, pdf_path, report, verifications, messages):
    lines = [f'# Application review: {role} at {company}', '',
             f'Resume attachment: [{Path(pdf_path).name}]({pdf_path})', '',
             f"Job-description match estimate: {report.get('ats_match_score', 'N/A')}/100. This is an internal estimate, not an employer score.", '',
             evidence_markdown(report.get('evidence_review', {})), '', '## Contact verification', '']
    for kind, record in verifications.items():
        lines.append(f"- {kind}: {record['email']} — {record['source']}; {record['status']}; score {record.get('score')}; checked {record['checked_at']}")
    lines.extend(['', '## Outreach drafts', '', 'Review and send in Gmail. Follow-up timing begins only after a confirmed send.', ''])
    for recipient, subject, body in messages:
        if recipient and body:
            lines.extend([f'### To: {recipient}', '', f'Subject: {subject}', '', body, ''])
    return '\n'.join(lines)


def render_draft_receipts(snapshots):
    lines = ['\n## Gmail draft creation snapshots', '',
             'These are the contents originally staged for each draft ID. Repeated runs reuse that draft; later manual edits in Gmail are not reflected here.', '']
    for item in snapshots:
        lines.extend([f"### {item['recipient']}", '', f"Subject: {item['subject']}", '',
                      f"Attachment: {item.get('attachment_path') or 'none'}", '', item['body'], ''])
    return '\n'.join(lines)


def run_automated_test_suites() -> Dict[str, Any]:
    """Runs all unit test suites across Emails and Resume repositories."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Discover and add test suites with explicit top_level_dir
    emails_tests = loader.discover(start_dir=str(EMAILS_DIR), pattern="test_*.py", top_level_dir=str(EMAILS_DIR))
    resume_tests = loader.discover(start_dir=str(RESUME_DIR), pattern="test_*.py", top_level_dir=str(RESUME_DIR))
    root_tests = loader.loadTestsFromName("test_copilot")

    suite.addTests(emails_tests)
    suite.addTests(resume_tests)
    suite.addTests(root_tests)

    runner = unittest.TextTestRunner(verbosity=0)
    result = runner.run(suite)

    return {
        "total_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "passed": result.wasSuccessful()
    }

async def orchestrate_job_application(
    jd_text: str,
    hm_name: Optional[str] = None,
    hm_email: Optional[str] = None,
    recruiter_name: Optional[str] = None,
    recruiter_email: Optional[str] = None,
    custom_details: str = "",
    stage_gmail: bool = True,
    run_tests: bool = True,
    selected_experience_ids: Optional[List[str]] = None,
    notify: bool = True,
    open_folder: bool = False,
    output_base_dir: Optional[Path] = None,
    precomputed_discovery: Optional[Dict[str, Any]] = None,  # Avoid duplicate API calls
    attempt: str = "",
    user_provided_emails: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Main supervisor orchestration workflow:
      1. Dispatches Resume Specialist -> Tailored PDF, ATS score, Strategic Brief.
      2. Dispatches Email Specialist -> Resolves Hiring Manager (Priority 1) & Recruiter (Priority 2), creates tailored drafts for both.
      3. Executes Unit Test Runner -> Quality guarantee.
      4. Updates Master Ledger Dashboard (APPLICATIONS.md).
    """
    print("\n" + "=" * 65)
    print("👑 MASTER JOB SEARCH CO-PILOT: Starting Application Pipeline")
    print("=" * 65)

    # -------------------------------------------------------------
    # PRE-FLIGHT: CONTACT EMAIL VALIDATION & GMAIL HEALTH
    # -------------------------------------------------------------
    if hm_email:
        clean_hm, hm_err = sanitize_and_validate_email(hm_email)
        if not clean_hm:
            raise ValueError(f"❌ Critical Failure: Primary Contact email '{hm_email}' is invalid: {hm_err}. Halting pipeline per Fail-Fast policy.")
        hm_email = clean_hm

    if recruiter_email:
        clean_rec, rec_err = sanitize_and_validate_email(recruiter_email)
        if not clean_rec:
            raise ValueError(f"❌ Critical Failure: Secondary Contact email '{recruiter_email}' is invalid: {rec_err}. Halting pipeline per Fail-Fast policy.")
        recruiter_email = clean_rec

    gmail_health = verify_gmail_access()
    if gmail_health.get("authenticated"):
        print(f"📬 Gmail Access Verified: Connected as {gmail_health.get('email_address')}")
    else:
        print(f"⚠️ Gmail Access Warning: {gmail_health.get('error')}")
        if stage_gmail:
            raise RuntimeError(f"Gmail Access Error: {gmail_health.get('error')}")

    # -------------------------------------------------------------
    # STEP 1: RESUME SPECIALIST AGENT
    # -------------------------------------------------------------
    print("\n[Supervisor -> Resume Specialist] Analyzing JD and tailoring experiences...")
    master_profile_path = RESUME_DIR / "master_profile.json"
    if not master_profile_path.exists():
        raise FileNotFoundError(f"Verified master profile missing: {master_profile_path}")

    with open(master_profile_path, "r", encoding="utf-8") as f:
        master_profile = json.load(f)

    client = get_genai_client()
    tailored_data = tailor_resume(
        master_profile, jd_text, client=client, selected_experience_ids=selected_experience_ids
    )

    report_data = tailored_data.get("tailoring_report", {})
    company = report_data.get("target_company", "Target Company")
    role = report_data.get("target_role", "Target Role")
    ats_score = report_data.get("ats_match_score", "N/A")
    breakdown = report_data.get("score_breakdown", {})

    print(f"🎯 Target Alignment: {role} at {company}")
    print(f"📊 Job-description Match Estimate: {ats_score}/100")
    if breakdown:
        print(f"   ├─ Tech Skills:     {breakdown.get('tech_skills_score', 'N/A')}%")
        print(f"   ├─ Business Skills: {breakdown.get('business_skills_score', 'N/A')}%")
        print(f"   └─ Keyword Coverage:{breakdown.get('keyword_coverage_score', 'N/A')}%")

    # Stable identity prevents duplicate draft creation after AI rewrites change.
    operation_key = application_operation_key(company, role, attempt)
    find_application(company, role, attempt)  # Validate history before creating any drafts.

    # Render PDF & Artifacts
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"{clean_file_name(company)}_{clean_file_name(role)}_{timestamp}"
    base_out = Path(output_base_dir) if output_base_dir else (RESUME_DIR / "output")
    from Resume.publication import staged_packet, publish_packet
    with staged_packet(base_out, folder_name) as (stage, out_dir):
        artifacts = save_resume_artifacts(tailored_data, str(stage))
        tailored_data['artifact_sha256'] = hashlib.sha256(Path(artifacts['pdf']).read_bytes()).hexdigest()
        report_md = generate_report_markdown(report_data)
        (stage / 'tailoring_report.md').write_text(report_md, encoding='utf-8')
        (stage / 'tailored_resume.json').write_text(json.dumps(tailored_data, indent=2), encoding='utf-8')
        publish_packet(stage, out_dir)
        artifacts = {key: str(out_dir / Path(value).name) if key in ('pdf', 'md', 'html') else value for key, value in artifacts.items()}
    report_path = out_dir / 'tailoring_report.md'
    json_path = out_dir / 'tailored_resume.json'

    pdf_path = artifacts.get("pdf")
    if not pdf_path or not os.path.exists(pdf_path):
        raise RuntimeError(f"❌ Critical Failure: Resume PDF was not generated. Halting pipeline.")
    print(f"📄 Tailored PDF Generated: {os.path.basename(pdf_path)}")

    # -------------------------------------------------------------
    # STEP 2: OUTREACH & EMAIL SPECIALIST AGENT (Hierarchy Sanity Check + Outreach)
    # -------------------------------------------------------------
    print("\n[Supervisor -> Contact Discovery] Discovering candidate pool across departments...")
    # Priority 5 fix: reuse precomputed discovery from interactive_session to avoid double API call
    discovery = precomputed_discovery if precomputed_discovery is not None else discover_ranked_contacts(company, role, jd_text=jd_text)

    # 2a. Spawn Seniority & Hierarchy Sanity-Check Subagent
    print("\n[Supervisor -> Sanity-Check Subagent] Auditing candidate hierarchy vs. role seniority...")
    audit_data = run_seniority_sanity_audit(discovery, role, company, jd_text)
    render_sanity_report_cli(audit_data, company, role)

    rec_p1 = audit_data.get("recommended_p1") or {}
    rec_p2 = audit_data.get("recommended_p2") or {}

    has_hm_specified = bool(hm_name or hm_email)
    has_rec_specified = bool(recruiter_name or recruiter_email)

    if not has_hm_specified and not has_rec_specified:
        # Full auto-discovery mode: populate both from sanity audit
        target_hm_name = rec_p1.get("name")
        target_hm_email = rec_p1.get("email")
        target_rec_name = rec_p2.get("name")
        target_rec_email = rec_p2.get("email")
    else:
        # Targeted outreach: only target contacts that were explicitly provided
        target_hm_name = hm_name
        target_hm_email = hm_email
        target_rec_name = recruiter_name
        target_rec_email = recruiter_email

        # If a name was specified without an email, search in discovery or hunter
        if target_hm_name and not target_hm_email:
            # Fix: discovery dict uses "hiring_managers"/"recruiters", not "candidates"
            all_discovered = discovery.get("hiring_managers", []) + discovery.get("recruiters", [])
            for c in all_discovered:
                if target_hm_name.lower() in c.get("name", "").lower() and c.get("email"):
                    target_hm_email = c["email"]
                    break
            if not target_hm_email and rec_p1.get("name", "").lower() == target_hm_name.lower():
                target_hm_email = rec_p1.get("email")
            if not target_hm_email:
                first, last = extract_name_from_input(target_hm_name)
                target_hm_email, _ = find_email_via_hunter(first, last, company)

        if target_rec_name and not target_rec_email:
            all_discovered = discovery.get("hiring_managers", []) + discovery.get("recruiters", [])
            for c in all_discovered:
                if target_rec_name.lower() in c.get("name", "").lower() and c.get("email"):
                    target_rec_email = c["email"]
                    break
            if not target_rec_email and rec_p2.get("name", "").lower() == target_rec_name.lower():
                target_rec_email = rec_p2.get("email")
            if not target_rec_email:
                first, last = extract_name_from_input(target_rec_name)
                target_rec_email, _ = find_email_via_hunter(first, last, company)

    # Must have at least one verified contact to proceed with automated drafting
    if not target_hm_email and not target_rec_email:
        if discovery.get("stage1_failed") and discovery.get("failure_report"):
            print(discovery["failure_report"])

        # Display targeted X-Ray links so user can find the contact on LinkedIn
        xrays = discovery.get("xray_links") or generate_xray_search_links(company, role, jd_context=discovery.get("jd_context"))
        print("\n" + "=" * 65)
        print("🔗 DIRECT LINKEDIN X-RAY SEARCH LINKS (Anti-Bounce Protocol)")
        print("=" * 65)
        print(f"⭐ Hiring Manager X-Ray:\n   {xrays.get('hiring_manager_xray')}\n")
        print(f"📋 Campus / Early Talent Recruiter X-Ray:\n   {xrays.get('recruiter_xray')}\n")
        print(f"📡 'I\'m hiring' Beacon Posts:\n   {xrays.get('hiring_beacon_posts')}\n")
        print("=" * 65)

        # Record application with "Needs Contact" stage so resume & packet are preserved in tracker
        app_entry = {
            "company": company,
            "role": role,
            "stage": "Needs Contact",
            "attempt": attempt,
            "ats_score": ats_score,
            "score_breakdown": breakdown,
            "pdf_path": str(pdf_path),
            "output_dir": str(out_dir),
            "hiring_manager_name": "",
            "hiring_manager_email": "",
            "recruiter_name": "",
            "recruiter_email": "",
            "touch1_subject": "",
            "touch1_staged": False,
            "notes": f"Highlighted: {', '.join(breakdown.get('matched_tech_skills', [])[:3])}"
        }
        record_application(app_entry)

        if notify:
            send_system_notification(
                title=f"📄 Resume Tailored ({ats_score}/100) — Needs Contact",
                message=f"{company}: {role}. Find contact on LinkedIn & run --outreach",
                subtitle=company
            )
        if open_folder:
            open_in_file_manager(pdf_path)

        print(f"\n✅ Tailored Resume PDF created: {pdf_path}")
        print(f"📊 Job-description Match Estimate: {ats_score}/100")
        print(f"💡 NEXT STEP: Click the X-Ray link above to find the hiring manager on LinkedIn, then run:")
        print(f"   Emails/.python/python/bin/python3 copilot.py --outreach \"<Name or LinkedIn URL>\"\n")
        return {
            "company": company,
            "role": role,
            "ats_score": ats_score,
            "pdf_path": str(pdf_path),
            "output_dir": str(out_dir),
            "stage": "Needs Contact"
        }

    direct_emails = {e.lower() for e in (user_provided_emails if user_provided_emails is not None else [e for e in (hm_email, recruiter_email) if e])}
    verifications = {}
    if target_hm_email:
        verifications['hiring_manager'] = contact_verification(target_hm_email, user_provided=target_hm_email.lower() in direct_emails, target_company=company)
    if target_rec_email:
        verifications['recruiter'] = contact_verification(target_rec_email, user_provided=target_rec_email.lower() in direct_emails, target_company=company)

    # Enforce strict Fail-Fast Email Validation on whichever contacts are provided
    if target_hm_email:
        clean_hm_email, hm_val_err = sanitize_and_validate_email(target_hm_email, target_company=company)
        if not clean_hm_email:
            raise ValueError(f"❌ Critical Failure: Primary Contact email '{target_hm_email}' is invalid: {hm_val_err}. Halting pipeline per Fail-Fast policy.")
        target_hm_email = clean_hm_email
        print(f"⭐ PRIMARY TARGET (Gatekeeper): {target_hm_name} ({target_hm_email}) [{rec_p1.get('position', 'N/A')}]")

    if target_rec_email:
        clean_rec_email, rec_val_err = sanitize_and_validate_email(target_rec_email, target_company=company)
        if not clean_rec_email:
            raise ValueError(f"❌ Critical Failure: Secondary Contact email '{target_rec_email}' is invalid: {rec_val_err}. Halting pipeline per Fail-Fast policy.")
        target_rec_email = clean_rec_email
        print(f"📋 SECONDARY TARGET (Referral): {target_rec_name} ({target_rec_email}) [{rec_p2.get('position', 'N/A')}]")

    def resolve_recipient_type(pos: str, default: str = "hiring_manager") -> str:
        pos_lower = (pos or "").lower()
        rec_keywords = ["recruiter", "talent", "campus", "university", "hr", "sourcer", "staffing", "early career", "emerging talent"]
        if any(rk in pos_lower for rk in rec_keywords):
            return "recruiter"
        return default

    p1_type = resolve_recipient_type(rec_p1.get("position", ""), default="hiring_manager")
    p2_type = resolve_recipient_type(rec_p2.get("position", ""), default="recruiter")

    email_details = custom_details or f"Applied for {role} at {company}. Highlights: {', '.join(breakdown.get('matched_tech_skills', [])[:3])}"

    email_details += "\nUse only these attached resume achievements for factual claims: " + json.dumps(tailored_data.get('experiences', []))

    # 2b. Generate Priority 1 Draft (if Primary Contact established)
    hm_subject = None
    hm_body = None
    if target_hm_email:
        hm_subject, hm_body = await generate_email_draft_async(
            recipient_name=target_hm_name,
            company_name=company,
            role=role,
            additional_details=email_details,
            resume_attached=bool(pdf_path),
            touch_number=1,
            recipient_type=p1_type
        )
        if not hm_body or len(hm_body.strip()) < 20:
            raise RuntimeError(f"❌ Critical Failure: Generated email body was empty or corrupt. Halting pipeline.")
        validate_outreach_evidence(hm_body, tailored_data, role)
        hm_file = out_dir / "touch1_hiring_manager.md"
        hm_file.write_text(f"# 🥇 Touch 1: Hiring Manager Outreach (Priority 1)\n\n**To:** `{target_hm_email}` ({target_hm_name})\n**Subject:** `{hm_subject}`\n\n```text\n{hm_body}\n```\n", encoding="utf-8")

    # 2c. Generate Priority 2 Draft (if Secondary Contact established)
    rec_subject = None
    rec_body = None
    if target_rec_email and (not target_hm_email or target_rec_email.lower() != target_hm_email.lower()):
        rec_subject, rec_body = await generate_email_draft_async(
            recipient_name=target_rec_name,
            company_name=company,
            role=role,
            additional_details=email_details,
            resume_attached=bool(pdf_path),
            touch_number=1,
            recipient_type=p2_type
        )
        if not rec_body or len(rec_body.strip()) < 20:
            raise RuntimeError(f"❌ Critical Failure: Generated email body was empty or corrupt. Halting pipeline.")
        validate_outreach_evidence(rec_body, tailored_data, role)
        rec_file = out_dir / "touch1_recruiter.md"
        rec_file.write_text(f"# 🥈 Touch 1: Recruiter Outreach (Priority 2)\n\n**To:** `{target_rec_email}` ({target_rec_name})\n**Subject:** `{rec_subject}`\n\n```text\n{rec_body}\n```\n", encoding="utf-8")

    # 2d. Generate 2-Business-Day Quick Bump Draft (Touch 2)
    today = datetime.date.today()
    schedule_info = calculate_touch_schedule(today)
    touch1_send_date = schedule_info["touch1_date"]
    touch2_due_date = schedule_info["touch2_date"]
    touch1_sched_str = schedule_info["touch1_formatted"]
    formatted_due_date = schedule_info["touch2_formatted"]

    primary_target_name = target_hm_name or target_rec_name
    primary_target_email = target_hm_email or target_rec_email

    touch2_subject, touch2_body = await generate_email_draft_async(
        recipient_name=primary_target_name,
        company_name=company,
        role=role,
        additional_details=email_details,
        resume_attached=False,
        touch_number=2
    )

    touch2_path = out_dir / "touch2_quick_bump.md"
    touch2_content = f"""# ⏱️ Touch 2: 2-Business-Day Quick Bump Follow-Up

**📅 Touch 1 Suggested Review Time:** `{touch1_sched_str}`
**📅 Touch 2:** Awaiting confirmed first send; review draft two business days afterward
**To:** `{primary_target_email}` ({primary_target_name})
**Subject:** `{touch2_subject}`

---

```text
{touch2_body}
```
"""
    touch2_path.write_text(touch2_content, encoding="utf-8")

    review_path = out_dir / 'review_packet.md'
    review_path.write_text(render_review_packet(company, role, pdf_path, report_data, verifications,
        [(target_hm_email, hm_subject, hm_body), (target_rec_email, rec_subject, rec_body)]), encoding='utf-8')
    print(f"Review packet: {review_path}")

    if run_tests:
        preflight_tests = run_automated_test_suites()
        if not preflight_tests['passed']:
            raise RuntimeError('Unit tests failed; Gmail draft creation was blocked.')

    # 2e. Create drafts in Gmail (Primary and/or Secondary)
    draft_id = None
    thread_id = None
    rec_draft_id = None
    result = result_rec = None
    if stage_gmail:
        # Suggested review time only; the compatibility function creates a draft
        import datetime as _dt
        touch1_send_dt = _dt.datetime.combine(
            touch1_send_date,
            _dt.time(9, 3, 0)
        ).astimezone()  # local timezone-aware

        if target_hm_email and hm_subject and hm_body:
            print(f"Creating Gmail draft for {target_hm_name} ({target_hm_email}); send manually in Gmail")
            result = create_scheduled_send(
                to_email=target_hm_email,
                subject=hm_subject,
                body_text=hm_body,
                send_at_datetime=touch1_send_dt,
                attachment_path=pdf_path,
                idempotency_key=f"{operation_key}:touch1:{target_hm_email.lower()}"
            )
            if result:
                draft_id = result.get("id")
                thread_id = result.get("threadId")
                print(f"✅ SUCCESS: Touch 1 draft available in Gmail (Draft ID: {draft_id}, Thread ID: {thread_id})")

        if target_rec_email and rec_subject and rec_body:
            print(f"Creating Gmail draft for {target_rec_name} ({target_rec_email}); send manually in Gmail")
            result_rec = create_scheduled_send(
                to_email=target_rec_email,
                subject=rec_subject,
                body_text=rec_body,
                send_at_datetime=touch1_send_dt,
                attachment_path=pdf_path,
                idempotency_key=f"{operation_key}:touch1:{target_rec_email.lower()}"
            )
            if result_rec:
                rec_draft_id = result_rec.get("id")
                if not thread_id:
                    thread_id = result_rec.get("threadId")
                print(f"✅ SUCCESS: Touch 1 draft available in Gmail for Recruiter (Draft ID: {rec_draft_id})")


    snapshots = [r['review_snapshot'] for r in (result, result_rec) if r and r.get('review_snapshot')]
    if snapshots:
        with review_path.open('a', encoding='utf-8') as review_file:
            review_file.write(render_draft_receipts(snapshots))

    # -------------------------------------------------------------
    # STEP 3: AUTOMATED CONTINUOUS UNIT TEST RUNNER
    # -------------------------------------------------------------
    test_results = {"total_run": 0, "passed": True}
    if run_tests:
        print("\n[Supervisor -> Quality Control] Running full unit test verification...")
        test_results = preflight_tests
        test_status = "100% Passing" if test_results["passed"] else "FAILURES DETECTED"
        print(f"🧪 Unit Tests: {test_results['total_run']}/{test_results['total_run']} passed ({test_status})")

    # -------------------------------------------------------------
    # SUMMARY DASHBOARD
    # -------------------------------------------------------------
    print("\n" + "=" * 65)
    print("🎉 APPLICATION & MULTI-TOUCH PACKET COMPLETE")
    print("=" * 65)
    print(f"🏢 Company:                {company}")
    print(f"💼 Role:                   {role}")
    print(f"📊 Job-description Match Estimate:        {ats_score}/100")
    print(f"📄 Tailored Resume PDF:    file://{pdf_path}")
    print(f"📝 Full Output Folder:     file://{out_dir}")
    print(f"🎯 Hiring Manager (P1):    {target_hm_email or 'None'} ({target_hm_name or 'N/A'})")
    print(f"📋 Recruiter (P2):         {target_rec_email or 'None'} ({target_rec_name or 'N/A'})")
    print(f"📌 Touch 1 Subject:        {hm_subject or rec_subject}")
    print(f"⏰ Touch 1 Suggested Review Time: {touch1_sched_str}")
    print(f"📬 HM Draft Staged:        {'Yes (ID: ' + str(draft_id) + ')' if draft_id else 'No'}")
    print(f"📬 Recruiter Draft Staged: {'Yes (ID: ' + str(rec_draft_id) + ')' if rec_draft_id else 'No'}")
    print("⏱️ Touch 2: Awaiting confirmed first send; due two business days afterward")
    print(f"🧪 Unit Test Status:       {test_results['total_run']} Passed (0 Errors)")
    print("=" * 65)

    if hm_body:
        print("\n--- 🥇 Touch 1: Hiring Manager Outreach (Primary Draft) ---")
        print(hm_body)
        print("----------------------------------------------------------")

    if rec_body:
        print("\n--- 🥈 Touch 1: Recruiter Outreach (Secondary Draft) ---")
        print(rec_body)
        print("--------------------------------------------------------")

    print(f"\n--- Touch 2: Follow-up draft for {primary_target_name}, after confirmed first send ---")
    print(touch2_body)
    print("---------------------------------------------------------------------------------------------------\n")
    # -------------------------------------------------------------
    # STEP 4: UPDATE MASTER APPLICATION TRACKER & DASHBOARD
    # -------------------------------------------------------------
    app_entry = {
        "company": company,
        "role": role,
        "stage": "Draft Staged" if (draft_id or rec_draft_id) else "Created",
        "ats_score": ats_score,
        "score_breakdown": breakdown,
        "pdf_path": str(pdf_path),
        "output_dir": str(out_dir),
        "hiring_manager_name": target_hm_name or "",
        "hiring_manager_email": target_hm_email or "",
        "recruiter_name": target_rec_name or "",
        "recruiter_email": target_rec_email or "",
        "touch1_subject": hm_subject or rec_subject or "",
        "touch1_staged": bool(draft_id or rec_draft_id),
        "touch1_draft_id": draft_id or "",
        "recruiter_draft_id": rec_draft_id or "",
        "touch1_thread_id": thread_id or "",
        "touch1_suggested_review_at": f"{touch1_send_date.strftime('%Y-%m-%d')} 09:03 AM",
        "touch2_due_date": "",
        "touch2_send_time": "09:06 AM",
        "touch2_status": "Awaiting Send Confirmation",
        "contact_verifications": verifications,
        "review_packet_path": str(review_path),
        "attempt": attempt,
        "touch2_subject": touch2_subject,
        "touch2_body": touch2_body,
        "touch2_path": str(touch2_path),
        "notes": f"Highlighted: {', '.join(breakdown.get('matched_tech_skills', [])[:3])}"
    }
    app_entry['outreach_sequences'] = []
    for recipient, name, draft, thread, subject in [
        (target_hm_email, target_hm_name, draft_id, thread_id, hm_subject),
        (target_rec_email, target_rec_name, rec_draft_id, result_rec.get('threadId') if rec_draft_id else None, rec_subject)]:
        if recipient and draft:
            app_entry['outreach_sequences'].append({'id': operation_key + ':' + recipient.lower(),
                'company': company, 'role': role, 'hiring_manager_email': recipient, 'hiring_manager_name': name,
                'touch1_draft_id': draft, 'touch1_thread_id': thread, 'touch1_subject': subject,
                'touch1_created_at': next((snap.get('created_at') for snap in snapshots if snap['recipient'].lower() == recipient.lower()), None),
                'touch2_status': 'Awaiting Send Confirmation'})
    record_application(app_entry)

    # -------------------------------------------------------------
    # STEP 5: SEND DESKTOP NOTIFICATION & AUDIBLE ALERT
    # -------------------------------------------------------------
    if notify:
        primary_contact_disp = target_hm_name or target_rec_name
        notify_pipeline_completion(
            company=company,
            role=role,
            ats_score=ats_score,
            contact_name=primary_contact_disp,
            draft_staged=bool(draft_id or rec_draft_id)
        )

    # -------------------------------------------------------------
    # STEP 6: REVEAL IN NATIVE FILE MANAGER (IF REQUESTED)
    # -------------------------------------------------------------
    if open_folder and pdf_path:
        print(f"📂 Revealing generated resume in macOS Finder: {pdf_path}")
        open_in_file_manager(pdf_path, reveal=True)

    return {
        "company": company,
        "role": role,
        "ats_score": ats_score,
        "pdf_path": str(pdf_path),
        "output_dir": str(out_dir),
        "hm_email": target_hm_email,
        "hm_name": target_hm_name,
        "hiring_manager_email": target_hm_email,
        "hiring_manager_name": target_hm_name,
        "recruiter_email": target_rec_email,
        "recruiter_name": target_rec_name,
        "touch1_subject": hm_subject,
        "touch1_body": hm_body,
        "touch1_suggested_review_at": f"{touch1_send_date.strftime('%Y-%m-%d')} 09:03 AM",
        "touch2_due_date": "",
        "touch2_send_time": "09:06 AM",
        "touch2_subject": touch2_subject,
        "touch2_body": touch2_body,
        "draft_id": draft_id,
        "tests_passed": test_results["passed"]
    }

def interactive_session(attempt=""):
    """Interactive conversational session with the Master Co-Pilot."""
    print("\n" + "=" * 65)
    print("👋 Welcome to the Master Job Search Co-Pilot")
    print("=" * 65)
    print("I'll coordinate your Resume Specialist and Outreach Specialist to:")
    print("  1. Tailor your resume & maximize your ATS match score.")
    print("  2. Render a validated 1-page PDF.")
    print("  3. Find the Hiring Manager (Priority 1) & Recruiter (Priority 2).")
    print("  4. Stage a personalized Gmail draft to the Hiring Manager.")
    print("  5. Verify the entire system with automated unit tests.")
    print("  6. Update your Master Ledger (APPLICATIONS.md).")
    print("-" * 65)

    # Pre-flight Gmail Check
    gmail_health = verify_gmail_access()
    if gmail_health.get("authenticated"):
        print(f"📬 Gmail Access: ✅ Active ({gmail_health.get('email_address')})")
    else:
        print(f"📬 Gmail Access: ⚠️ {gmail_health.get('error')}")

    # 1. Job Description
    print("\n📋 How would you like to provide the Job Description?")
    print("  [1] Paste text directly")
    print("  [2] Provide a file path (e.g. sample_jd.txt)")
    choice = input("Select (1 or 2, default 1): ").strip() or "1"

    jd_text = ""
    if choice == "2":
        fpath = input("Enter path to JD file: ").strip()
        p = Path(fpath).expanduser().resolve()
        if not p.exists():
            print(f"❌ File '{fpath}' not found.")
            sys.exit(1)
        jd_text = p.read_text(encoding="utf-8")
    else:
        print("\nPaste the Job Description below. When finished, press Ctrl+D (Mac/Linux) or Ctrl+Z (Windows) on a new line:")
        lines = []
        try:
            while True:
                line = input()
                lines.append(line)
        except EOFError:
            jd_text = "\n".join(lines).strip()

    if not jd_text or len(jd_text) < 30:
        print("❌ Error: Job Description was empty or too short.")
        sys.exit(1)

    # 2. Quick company / role discovery
    first_lines = jd_text[:400]
    comp_match = re.search(r'(?:Company|Organization):\s*([^\n,]+)', first_lines, re.I)
    role_match = re.search(r'(?:Role|Position|Title):\s*([^\n,]+)', first_lines, re.I)

    company_hint = comp_match.group(1).strip() if comp_match else ""
    role_hint = role_match.group(1).strip() if role_match else ""

    if not company_hint:
        company_hint = input("\nTarget Company Name (e.g. 'Stripe'): ").strip()
    if not role_hint:
        role_hint = input("Target Role Title (e.g. 'Associate Product Manager'): ").strip()

    print(f"\n🔍 Searching Hunter.io & LinkedIn Directory for {role_hint} at {company_hint}...")
    discovery = discover_ranked_contacts(company_hint, role_hint, jd_text=jd_text)

    # Priority 7: Surface X-Ray links BEFORE the contact list so you can cross-reference manually
    xrays = discovery.get("xray_links", {})
    if xrays:
        print("\n" + "─" * 65)
        print("🔗 GOOGLE X-RAY SEARCH LINKS (cross-reference with auto-discovered contacts below)")
        print("─" * 65)
        print(f"  🎯 Hiring Manager X-Ray:  {xrays.get('hiring_manager_xray', '')}")
        print(f"  🏫 Campus Recruiter X-Ray: {xrays.get('recruiter_xray', '')}")
        print(f"  📢 'I'm Hiring' Beacon:   {xrays.get('hiring_beacon_posts', '')}")
        print("─" * 65)

    # Run Sanity Audit
    audit_data = run_seniority_sanity_audit(discovery, role_hint, company_hint, jd_text)
    render_sanity_report_cli(audit_data, company_hint, role_hint)

    hms = audit_data.get("audited_hiring_managers", [])
    recs = audit_data.get("audited_recruiters", [])

    hm_name_selected = None
    direct_emails = set()
    hm_email_selected = None
    rec_name_selected = None
    rec_email_selected = None

    # 3. Hiring Manager Selection (Priority 1)
    print("\n" + "=" * 65)
    print(f"🎯 HIRING MANAGERS / GATEKEEPERS (Priority 1)")
    print("=" * 65)
    if hms:
        for idx, h in enumerate(hms, 1):
            badge = h.get("sanity_badge", "🟡")
            print(f"  [{idx}] {h['name']} — {h['position']} | {badge} -> {h['email']}")
        print(f"  [{len(hms) + 1}] Search & Verify another candidate on Hunter.io (Fail-safe Loop)")
        hm_choice = input(f"\nSelect Hiring Manager / Gatekeeper (1-{len(hms) + 1}, default 1): ").strip() or "1"
        try:
            hm_idx = int(hm_choice) - 1
            if 0 <= hm_idx < len(hms):
                hm_name_selected = hms[hm_idx]["name"]
                hm_email_selected = hms[hm_idx]["email"]
            elif hm_idx >= len(hms):
                hm_name_selected, hm_email_selected, _ = prompt_hunter_failsafe_loop(company_hint, role_hint, "Hiring Manager", user_provided_emails=direct_emails)
        except ValueError:
            if "@" in hm_choice:
                clean_e, err_e = sanitize_and_validate_email(hm_choice, target_company=company_hint)
                if clean_e:
                    hm_email_selected = clean_e
                    direct_emails.add(clean_e.lower())
                    hm_name_selected = clean_e.split("@")[0].replace(".", " ").title()
                else:
                    print(f"⚠️ Warning: '{hm_choice}' failed email validation: {err_e}")
                    hm_name_selected = hm_choice
            else:
                hm_name_selected = hm_choice
    else:
        hm_name_selected, hm_email_selected, _ = prompt_hunter_failsafe_loop(company_hint, role_hint, "Hiring Manager", user_provided_emails=direct_emails)

    if not hm_email_selected:
        print("ℹ️ Hiring Manager was not selected or skipped.")

    # 4. Recruiter Selection (Priority 2)
    print("\n" + "=" * 65)
    print(f"📋 RECRUITERS DISCOVERED (Priority 2 — Talent Partner)")
    print("=" * 65)
    if recs:
        for idx, r in enumerate(recs, 1):
            print(f"  [{idx}] {r['name']} — {r['position']} (Verified: {r['confidence']}%) -> {r['email']}")
        print(f"  [{len(recs) + 1}] Search & Verify another recruiter on Hunter.io (Fail-safe Loop)")
        rec_choice = input(f"\nSelect Recruiter (1-{len(recs) + 1}, default 1, or 'skip'): ").strip() or "1"
        if rec_choice.lower() in ["skip", "none", "no", "exit", "stop", "cancel"]:
            print("ℹ️ Recruiter selection skipped.")
        else:
            try:
                rec_idx = int(rec_choice) - 1
                if 0 <= rec_idx < len(recs):
                    rec_name_selected = recs[rec_idx]["name"]
                    rec_email_selected = recs[rec_idx]["email"]
                elif rec_idx >= len(recs):
                    rec_name_selected, rec_email_selected, _ = prompt_hunter_failsafe_loop(company_hint, role_hint, "Recruiter", user_provided_emails=direct_emails)
            except ValueError:
                if "@" in rec_choice:
                    clean_e, err_e = sanitize_and_validate_email(rec_choice, target_company=company_hint)
                    if clean_e:
                        rec_email_selected = clean_e
                        direct_emails.add(clean_e.lower())
                        rec_name_selected = clean_e.split("@")[0].replace(".", " ").title()
                    else:
                        print(f"⚠️ Warning: '{rec_choice}' failed email validation: {err_e}")
                        rec_name_selected = rec_choice
                else:
                    rec_name_selected = rec_choice
    else:
        rec_name_selected, rec_email_selected, _ = prompt_hunter_failsafe_loop(company_hint, role_hint, "Recruiter", user_provided_emails=direct_emails)

    if not hm_email_selected and not rec_email_selected:
        print("\n🛑 Pipeline Terminated: No valid contact email established for either Hiring Manager or Recruiter.")
        print("Generic fallback aliases (Stage 3) are disabled per user instructions. Exiting workflow.")
        return

    if hm_email_selected and not rec_email_selected:
        print(f"\nℹ️ Proceeding with single-contact outreach to Hiring Manager: {hm_name_selected} ({hm_email_selected})")
    elif rec_email_selected and not hm_email_selected:
        print(f"\nℹ️ Proceeding with single-contact outreach to Recruiter: {rec_name_selected} ({rec_email_selected})")
    else:
        print(f"\nℹ️ Proceeding with dual-target outreach to Hiring Manager and Recruiter.")

    custom_details = input("\nAny specific project/achievement you want to highlight? (optional): ").strip()

    # Priority 5: pass precomputed discovery to avoid running discover_ranked_contacts a second time
    result = asyncio.run(orchestrate_job_application(
        jd_text=jd_text,
        hm_name=hm_name_selected or None,
        hm_email=hm_email_selected or None,
        recruiter_name=rec_name_selected or None,
        recruiter_email=rec_email_selected or None,
        custom_details=custom_details,
        precomputed_discovery=discovery,
        user_provided_emails=list(direct_emails),
        attempt=attempt
    ))

    if result and result.get("pdf_path"):
        try:
            open_nav = input("\n📂 Open tailored resume in macOS Finder? (Y/n, default Y): ").strip().lower()
            if open_nav not in ["n", "no"]:
                open_in_file_manager(result["pdf_path"], reveal=True)
        except (EOFError, KeyboardInterrupt):
            pass

async def outreach_from_linkedin_contact(
    contact_input: str,
    company: Optional[str] = None,
    role: Optional[str] = None,
    is_recruiter: bool = False,
    attempt: str = "",
    custom_details: str = ""
) -> None:
    """
    Lightweight outreach-only pipeline.
    You found the hiring manager on LinkedIn — pass in their name or profile URL
    and this resolves their email, generates the draft, and stages it in Gmail.
    No resume re-tailoring or broad contact discovery; Hunter lookup credits may be used.

    Usage:
      --outreach "Sarah Chen"
      --outreach "https://linkedin.com/in/sarah-chen-abc123"
      --outreach "Sarah Chen" --company Robinhood --role "Special Projects Intern"
    """
    print("\n" + "=" * 65)
    print("✉️  OUTREACH-ONLY MODE — Skipping Resume & Discovery Pipelines")
    print("=" * 65)
    # Fail before discovery, generation, or any external draft mutation.
    load_applications()

    # --- Step 1: Resolve name from input (full name or LinkedIn URL) ---
    fname, lname = extract_name_from_input(contact_input)
    if not fname:
        print(f"❌ Could not parse a name from: '{contact_input}'")
        print("   Try: --outreach \"Sarah Chen\" OR --outreach \"https://linkedin.com/in/sarah-chen\"")
        return
    full_name = f"{fname} {lname}".strip()
    print(f"👤 Contact parsed: {full_name}")

    # --- Step 2: Infer company + role from tracker if not provided ---
    if not company or not role:
        apps = load_applications()
        if apps:
            latest = apps[0]  # Most recently recorded application is at index 0
            company = company or latest.get("company", "")
            role = role or latest.get("role", "")
            if company and role:
                print(f"📋 Inferred from latest application: {role} at {company}")
    if not company:
        company = input("Company name: ").strip()
    if not role:
        role = input("Role title: ").strip()
    if not company or not role:
        print("❌ Company and role are required.")
        return

    # --- Step 3: Find resume PDF from latest output packet ---
    resume_path, resume_data = load_verified_packet(company, role)
    print(f"Resume attachment: {Path(resume_path).name}")
    operation_key = application_operation_key(company, role, attempt)

    # --- Step 4: Hunter verification or explicitly supplied email ---
    print(f"\n🔍 Resolving email for {full_name} at {company} via Hunter.io...")
    found_email = None
    conf = 0
    try:
        found_email, conf = find_email_via_hunter(fname, lname, company)
    except Exception as e:
        print(f"  ⚠️ Hunter lookup exception: {e}")

    user_provided = False
    if found_email:
        clean_email, err = sanitize_and_validate_email(found_email, target_company=company)
        if clean_email:
            print(f"  ✅ Hunter.io found: {clean_email} (confidence: {conf}%)")
            found_email = clean_email
        else:
            print(f"  ⚠️ Hunter returned '{found_email}' but it failed validation: {err}")
            found_email = None

    if not found_email:
        print(f"  ⚠️ Hunter.io could not find a verified email for {full_name} at {company}.")
        print("     Per Zero-Hallucination & Anti-Bounce policy, unverified pattern guessing is disabled.")
        manual = input("  Paste their verified email directly from LinkedIn/company directory (or Enter to abort): ").strip()
        if manual:
            clean_email, err = sanitize_and_validate_email(manual, target_company=company)
            if clean_email:
                found_email = clean_email
                user_provided = True
                print(f"  ✅ Using manually provided email: {found_email}")
            else:
                print(f"  ❌ '{manual}' is invalid: {err}")
                return
        else:
            print("❌ Aborted — no verified email provided. Draft staging cancelled to protect sender reputation.")
            return

    verification = contact_verification(found_email, user_provided=user_provided, target_company=company)

    # --- Step 5: Pre-flight Gmail health check ---
    if not verify_gmail_access().get("authenticated"):
        print("❌ Gmail access verification failed. Run --reauth-gmail and retry.")
        return

    # --- Step 6: Calculate send schedule ---
    schedule = calculate_touch_schedule()
    touch1_sched_str = schedule["touch1_formatted"]
    touch2_due_date = schedule["touch2_due_date"]
    touch2_sched_str = schedule["touch2_formatted"]

    # --- Step 7: Generate email copy ---
    print(f"\n✍️  Generating personalised email draft for {full_name}...")
    contact_role = "Recruiter" if is_recruiter else "Hiring Manager"
    recipient_type = "recruiter" if is_recruiter else "hiring_manager"
    try:
        subject, email_body = await generate_email_draft_async(
            recipient_name=full_name,
            company_name=company,
            role=role,
            additional_details=(custom_details or f"Applied for {role} at {company}.") + "\nUse only these attached resume achievements: " + json.dumps(resume_data.get("experiences", [])),
            resume_attached=bool(resume_path),
            touch_number=1,
            recipient_type=recipient_type
        )
    except Exception as e:
        print(f"❌ Email generation failed: {e}")
        return

    validate_outreach_evidence(email_body, resume_data, role)
    review_path = Path(resume_path).parent / 'outreach_review_packet.md'
    review_path.write_text(render_review_packet(company, role, resume_path, resume_data['tailoring_report'],
        {recipient_type: verification}, [(found_email, subject, email_body)]), encoding='utf-8')
    print(f"Review packet: {review_path}")

    # --- Step 8: Create Touch 1 draft ---
    print(f"Creating Gmail draft for {found_email}; send manually in Gmail")
    draft_id = None
    thread_id = None
    try:
        import datetime as _dt
        touch1_send_dt = _dt.datetime.combine(
            schedule["touch1_date"],
            _dt.time(9, 3, 0)
        ).astimezone()  # local timezone-aware
        result = create_scheduled_send(
            to_email=found_email,
            subject=subject,
            body_text=email_body,
            send_at_datetime=touch1_send_dt,
            attachment_path=resume_path,
            idempotency_key=f"{operation_key}:touch1:{found_email.lower()}"
        )
        if result:
            draft_id = result.get("id")
            thread_id = result.get("threadId")
            print(f"  ✅ Touch 1 draft created in Gmail (Message ID: {draft_id}, Thread ID: {thread_id})")
        else:
            print("  ⚠️ Draft creation failed — inspect Gmail drafts before retrying.")
    except Exception as e:
        print(f"  ❌ Gmail draft creation error: {e}")
        return

    if result and result.get('review_snapshot'):
        with review_path.open('a', encoding='utf-8') as review_file:
            review_file.write(render_draft_receipts([result['review_snapshot']]))

    # --- Step 9: Update tracker ---
    hm_name_key = "hiring_manager_name" if not is_recruiter else "recruiter_name"
    hm_email_key = "hiring_manager_email" if not is_recruiter else "recruiter_email"
    existing = find_application(company, role, attempt) or {}
    app = dict(existing)
    app.update(company=company, role=role, attempt=attempt, stage='Draft Staged',
        touch1_subject=subject, touch1_staged=True, touch1_draft_id=draft_id,
        touch1_thread_id=thread_id, touch2_status='Awaiting Send Confirmation',
        touch2_due_date='', pdf_path=resume_path, output_dir=str(Path(resume_path).parent),
        review_packet_path=str(review_path))
    app[hm_name_key] = full_name
    app[hm_email_key] = found_email
    app.setdefault('contact_verifications', {})[recipient_type] = verification
    sequence = {'id': operation_key + ':' + found_email.lower(), 'company': company, 'role': role,
        'hiring_manager_email': found_email, 'hiring_manager_name': full_name,
        'touch1_thread_id': thread_id, 'touch1_draft_id': draft_id,
        'touch1_created_at': (result.get('review_snapshot') or {}).get('created_at'),
        'touch2_status': 'Awaiting Send Confirmation'}
    app['outreach_sequences'] = [sequence]
    record_application(app)

    # --- Step 10: Notify ---
    send_system_notification(
        title="✉️ Outreach Draft Staged",
        message=f"{full_name} ({found_email})",
        subtitle=f"{role} at {company}"
    )

    print("\n" + "=" * 65)
    print("🎉 OUTREACH COMPLETE")
    print("=" * 65)
    print(f"👤 Contact:      {full_name} ({contact_role})")
    print(f"📧 Email:        {found_email}")
    print(f"🏢 Company:      {company} — {role}")
    print(f"Touch 1 suggested review time: {touch1_sched_str}; send manually in Gmail")
    print("Touch 2: Awaiting confirmed send; follow-up draft due two business days afterward")
    print(f"📬 Draft ID:     {draft_id or 'Check Gmail drafts'}")
    print("=" * 65 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Master Job Search Co-Pilot Orchestrator.")
    parser.add_argument("--jd", help="Inline Job Description text")
    parser.add_argument("--file", help="Path to Job Description text file")
    parser.add_argument("--hm", help="Hiring Manager full name (Priority 1, e.g. 'David Song')")
    parser.add_argument("--hm-email", help="Hiring Manager direct email address")
    parser.add_argument("--recruiter", help="Recruiter / Talent Partner full name (Priority 2, e.g. 'Sarah Jenkins')")
    parser.add_argument("--email", help="Recruiter direct email address")
    parser.add_argument("--details", default="", help="Custom details or points to emphasize")
    parser.add_argument("--use-bwb", action="store_true", help="Swap Blue Water Battery Logistics in place of AACF")
    parser.add_argument("--interactive", action="store_true", help="Launch guided interactive session")
    parser.add_argument("--auto-nudge", action="store_true", help="Process and stage due 2-business-day Touch 2 follow-ups")
    parser.add_argument("--send-due", action="store_true", help="Disabled legacy option; all outreach is draft-only")
    parser.add_argument("--test-only", action="store_true", help="Run full automated unit test suites only")
    parser.add_argument("--check-thread", help="Inspect a Gmail thread ID to check if recipient replied and terminate sequence")
    parser.add_argument("--tracker", action="store_true", help="Display Master Application Tracker dashboard")
    parser.add_argument("--stage", nargs="+", metavar="ARGS", help="Update application stage (e.g. --stage Stripe Interviewing OR --stage Stripe APM Interviewing)")
    parser.add_argument("--reauth-gmail", action="store_true", help="Re-authenticate Gmail OAuth with full thread/reply inspection permissions")
    parser.add_argument("--no-notify", action="store_true", help="Disable desktop notification and audio chime upon completion")
    parser.add_argument("--open", "--reveal", dest="open_folder", action="store_true", help="Automatically reveal the generated PDF in macOS Finder upon completion")
    parser.add_argument("--open-latest", "--latest", dest="open_latest", action="store_true", help="Immediately reveal the most recent application packet in macOS Finder and exit")
    # Outreach-only mode: you found the contact on LinkedIn, skip the automated discovery pipeline
    parser.add_argument("--outreach", metavar="NAME_OR_URL",
                        help="Hiring manager name or LinkedIn URL. Resolves email via Hunter and stages draft — "
                             "no re-tailoring, no discovery waterfall. "
                             "e.g. --outreach \"Sarah Chen\"  OR  --outreach \"https://linkedin.com/in/sarah-chen\"")
    parser.add_argument("--recruiter-outreach", metavar="NAME_OR_URL",
                        help="Same as --outreach but marks the contact as a Recruiter (P2) instead of Hiring Manager (P1).")
    parser.add_argument("--company", help="Company name (used with --outreach to override tracker inference)")
    parser.add_argument("--role", help="Role title (used with --outreach to override tracker inference)")

    parser.add_argument('--new-attempt', metavar='LABEL', default='', help='Explicit unique label for a separate application attempt')
    parser.add_argument('--review', action='store_true', help='Open a local review server for saved resumes, evidence, and outreach snapshots')
    parser.add_argument('--review-port', type=int, default=8765, help='Local review server port (default: 8765)')
    args = parser.parse_args()
    if args.send_due:
        parser.error('--send-due is disabled: draft-only policy. Review and send in Gmail.')

    if args.review:
        from review_app import serve
        serve(args.review_port)
        return

    # --outreach / --recruiter-outreach: lightweight email-only pipeline
    if args.outreach or args.recruiter_outreach:
        contact_input = args.outreach or args.recruiter_outreach
        is_recruiter = bool(args.recruiter_outreach)
        asyncio.run(outreach_from_linkedin_contact(
            contact_input=contact_input,
            company=getattr(args, "company", None),
            role=getattr(args, "role", None),
            is_recruiter=is_recruiter,
            custom_details=args.details,
            attempt=args.new_attempt
        ))
        return


    if args.open_latest:
        latest = get_latest_output_packet()
        if not latest:
            print("⚠️ No output packets found in Resume/output/")
            return
        target = latest.get("pdf") or latest.get("dir")
        print(f"📂 Revealing latest application packet in macOS Finder: {target}")
        open_in_file_manager(target, reveal=True)
        return

    if args.reauth_gmail:
        from gmail_draft import reauthorize_gmail
        reauthorize_gmail()
        return


    if args.auto_nudge:
        print("\n" + "=" * 65)
        print("⏱️ MASTER CO-PILOT: Checking Due Touch 2 Follow-Ups")
        print("=" * 65)
        results = process_due_touch2_nudges(auto_send=bool(args.send_due), stage_draft=True)
        if not results:
            print("🟢 All follow-up sequences are up-to-date. No Touch 2 emails due today.")
        else:
            for result in results:
                if result['action'] == 'paused':
                    print(f"⚠️ {result.get('company')}: paused — {result.get('error')}")
                else:
                    print(f"{result.get('company')}: {result['action'].replace('_', ' ')}")
        return

    if args.tracker:
        apps = load_applications()
        print("\n" + "=" * 65)
        print(f"📊 MASTER APPLICATION TRACKER ({len(apps)} Applications)")
        print(f"Dashboard File: {APPLICATIONS_MD_FILE}")
        print("=" * 65)
        if not apps:
            print("No applications recorded yet.")
        for idx, app in enumerate(apps, 1):
            hm_disp = app.get('hiring_manager_name') or app.get('recruiter_name') or 'N/A'
            print(f"{idx}. {app.get('company')} — {app.get('role')} | ATS: {app.get('ats_score')}/100 | Contact: {hm_disp} | Stage: {app.get('stage')} | Touch 2: {app.get('touch2_due_date')} ({app.get('touch2_status', 'Scheduled')})")
            for sequence in app.get('outreach_sequences') or [app]:
                diagnostic = sequence.get('followup_error') or sequence.get('followup_note')
                if diagnostic:
                    print(f'   Follow-up: {diagnostic}')
        print("=" * 65 + "\n")
        return

    if args.stage:
        if len(args.stage) == 2:
            company_q, new_st = args.stage
            update_application_stage(company_q, new_st)
        elif len(args.stage) >= 3:
            company_q = args.stage[0]
            role_q = " ".join(args.stage[1:-1])
            new_st = args.stage[-1]
            update_application_stage(company_q, new_st, role_query=role_q)
        else:
            print("⚠️ Usage: --stage <COMPANY> <STAGE> OR --stage <COMPANY> <ROLE> <STAGE>")
        return

    if args.test_only:
        print("🧪 Running Master Co-Pilot Automated Unit Tests...")
        results = run_automated_test_suites()
        print(f"Results: {results['total_run']} run, {results['failures']} failures, {results['errors']} errors. Passed: {results['passed']}")
        sys.exit(0 if results["passed"] else 1)

    if args.check_thread:
        print(f"🔍 Inspecting Gmail thread '{args.check_thread}' for replies...")
        status = check_thread_for_replies(args.check_thread, args.email or "")
        if status.get("has_reply"):
            print(f"🛑 SEQUENCE TERMINATED: Recruiter replied! (Message count: {status.get('message_count')})")
            print(f"💬 Snippet: {status.get('snippet')}")
        else:
            print(f"Thread status: {status.get('status')}; confirmed sent: {status.get('touch1_sent')}; follow-ups require a confirmed send and successful inspection.")
        return

    if args.interactive or (not args.jd and not args.file):
        interactive_session(attempt=args.new_attempt)
        return

    jd_text = args.jd
    if args.file:
        fpath = Path(args.file).expanduser().resolve()
        if not fpath.exists():
            print(f"❌ File '{args.file}' not found.")
            sys.exit(1)
        jd_text = fpath.read_text(encoding="utf-8")

    if args.hm_email:
        clean_hm_e, hm_e_err = sanitize_and_validate_email(args.hm_email)
        if not clean_hm_e:
            print(f"❌ Error: CLI argument --hm-email '{args.hm_email}' is invalid: {hm_e_err}")
            sys.exit(1)
        args.hm_email = clean_hm_e

    if args.email:
        clean_rec_e, rec_e_err = sanitize_and_validate_email(args.email)
        if not clean_rec_e:
            print(f"❌ Error: CLI argument --email '{args.email}' is invalid: {rec_e_err}")
            sys.exit(1)
        args.email = clean_rec_e

    selected_exp = ["exp_autopilot_local", "exp_blue_water_battery", "exp_aroma_vault", "exp_claythis"] if args.use_bwb else None

    asyncio.run(orchestrate_job_application(
        jd_text=jd_text,
        hm_name=args.hm,
        hm_email=args.hm_email,
        recruiter_name=args.recruiter,
        recruiter_email=args.email,
        custom_details=args.details,
        selected_experience_ids=selected_exp,
        notify=not args.no_notify,
        open_folder=args.open_folder,
        attempt=args.new_attempt
    ))

if __name__ == "__main__":
    main()
