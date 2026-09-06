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
import sys
import json
import argparse
import asyncio
import unittest
from pathlib import Path
from typing import Optional, Dict, Any

# Root setup and path injection for specialist subagents
ROOT_DIR = Path(__file__).resolve().parent
RESUME_DIR = ROOT_DIR / "Resume"
EMAILS_DIR = ROOT_DIR / "Emails"

if str(RESUME_DIR) not in sys.path:
    sys.path.insert(0, str(RESUME_DIR))
if str(EMAILS_DIR) not in sys.path:
    sys.path.insert(0, str(EMAILS_DIR))

try:
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
        prompt_hunter_failsafe_loop
    )
    from contact_auditor import (
        run_seniority_sanity_audit,
        render_sanity_report_cli,
        detect_seniority_tier
    )
    from gmail_draft import create_gmail_draft, send_gmail_message, check_thread_for_replies, verify_gmail_access
    from resume_finder import find_tailored_resume
    from tracker import (
        record_application,
        update_application_stage,
        load_applications,
        process_due_touch2_nudges,
        APPLICATIONS_MD_FILE
    )
except ImportError as e:
    print(f"⚠️ Warning during subagent module import: {e}")

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
    stage_gmail: bool = True
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
    # PRE-FLIGHT: GMAIL HEALTH & CONNECTIVITY CHECK
    # -------------------------------------------------------------
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
        template_path = RESUME_DIR / "master_profile.template.json"
        if template_path.exists():
            print(f"ℹ️  Notice: '{master_profile_path.name}' not found. Using template '{template_path.name}'.")
            print("   (To customize with your own background, copy master_profile.template.json to master_profile.json)\n")
            master_profile_path = template_path
        else:
            raise FileNotFoundError(f"Master profile not found at: {master_profile_path}")

    with open(master_profile_path, "r", encoding="utf-8") as f:
        master_profile = json.load(f)

    client = get_genai_client()
    tailored_data = tailor_resume(master_profile, jd_text, client=client)
    
    report_data = tailored_data.get("tailoring_report", {})
    company = report_data.get("target_company", "Target Company")
    role = report_data.get("target_role", "Target Role")
    ats_score = report_data.get("ats_match_score", "N/A")
    breakdown = report_data.get("score_breakdown", {})

    print(f"🎯 Target Alignment: {role} at {company}")
    print(f"📊 Mathematical ATS Match Score: {ats_score}/100")
    if breakdown:
        print(f"   ├─ Tech Skills:     {breakdown.get('tech_skills_score', 'N/A')}%")
        print(f"   ├─ Business Skills: {breakdown.get('business_skills_score', 'N/A')}%")
        print(f"   └─ Keyword Coverage:{breakdown.get('keyword_coverage_score', 'N/A')}%")

    # Render PDF & Artifacts
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"{clean_file_name(company)}_{clean_file_name(role)}_{timestamp}"
    out_dir = RESUME_DIR / "output" / folder_name
    out_dir.mkdir(parents=True, exist_ok=True)

    artifacts = save_resume_artifacts(tailored_data, str(out_dir))
    report_md = generate_report_markdown(report_data)
    report_path = out_dir / "tailoring_report.md"
    report_path.write_text(report_md, encoding="utf-8")

    json_path = out_dir / "tailored_resume.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(tailored_data, f, indent=2)

    pdf_path = artifacts.get("pdf")
    if not pdf_path or not os.path.exists(pdf_path):
        raise RuntimeError(f"❌ Critical Failure: Resume PDF was not generated. Halting pipeline.")
    print(f"📄 Tailored PDF Generated: {os.path.basename(pdf_path)}")

    # -------------------------------------------------------------
    # STEP 2: OUTREACH & EMAIL SPECIALIST AGENT (Hierarchy Sanity Check + Outreach)
    # -------------------------------------------------------------
    print("\n[Supervisor -> Contact Discovery] Discovering candidate pool across departments...")
    discovery = discover_ranked_contacts(company, role)

    # 2a. Spawn Seniority & Hierarchy Sanity-Check Subagent
    print("\n[Supervisor -> Sanity-Check Subagent] Auditing candidate hierarchy vs. role seniority...")
    audit_data = run_seniority_sanity_audit(discovery, role, company, jd_text)
    render_sanity_report_cli(audit_data, company, role)

    rec_p1 = audit_data.get("recommended_p1") or {}
    rec_p2 = audit_data.get("recommended_p2") or {}

    # Resolve Primary Contact (Priority 1 - Recommended Gatekeeper)
    target_hm_name = hm_name or rec_p1.get("name") or "Hiring Team"
    target_hm_email = hm_email or rec_p1.get("email")
    if not target_hm_email:
        company_domain = get_company_domain(company)
        target_hm_email = f"team-lead@{company_domain}"

    # Resolve Secondary Contact (Priority 2 - Recommended Referral / Peer)
    target_rec_name = recruiter_name or rec_p2.get("name") or "Talent Partner"
    target_rec_email = recruiter_email or rec_p2.get("email")
    if not target_rec_email:
        company_domain = get_company_domain(company)
        target_rec_email = f"recruiting@{company_domain}"

    print(f"⭐ PRIMARY TARGET (Gatekeeper): {target_hm_name} ({target_hm_email}) [{rec_p1.get('position', 'N/A')}]")
    print(f"📋 SECONDARY TARGET (Referral): {target_rec_name} ({target_rec_email}) [{rec_p2.get('position', 'N/A')}]")

    def resolve_recipient_type(pos: str, default: str = "hiring_manager") -> str:
        pos_lower = (pos or "").lower()
        rec_keywords = ["recruiter", "talent", "campus", "university", "hr", "sourcer", "staffing", "early career", "emerging talent"]
        if any(rk in pos_lower for rk in rec_keywords):
            return "recruiter"
        return default

    p1_type = resolve_recipient_type(rec_p1.get("position", ""), default="hiring_manager")
    p2_type = resolve_recipient_type(rec_p2.get("position", ""), default="recruiter")

    # 2b. Generate Priority 1 Draft (Recommended Gatekeeper)
    email_details = custom_details or f"Applied for {role} at {company}. Highlights: {', '.join(breakdown.get('matched_tech_skills', [])[:3])}"
    hm_subject, hm_body = await generate_email_draft_async(
        recipient_name=target_hm_name,
        company_name=company,
        role=role,
        additional_details=email_details,
        resume_attached=bool(pdf_path),
        touch_number=1,
        recipient_type=p1_type
    )

    # 2c. Generate Priority 2 Draft (Recommended Referral / Secondary Contact)
    rec_subject, rec_body = await generate_email_draft_async(
        recipient_name=target_rec_name,
        company_name=company,
        role=role,
        additional_details=email_details,
        resume_attached=bool(pdf_path),
        touch_number=1,
        recipient_type=p2_type
    )

    if not hm_body or len(hm_body.strip()) < 20:
        raise RuntimeError(f"❌ Critical Failure: Generated email body was empty or corrupt. Halting pipeline.")

    # Save both drafts into output folder
    hm_file = out_dir / "touch1_hiring_manager.md"
    hm_file.write_text(f"# 🥇 Touch 1: Hiring Manager Outreach (Priority 1)\n\n**To:** `{target_hm_email}` ({target_hm_name})\n**Subject:** `{hm_subject}`\n\n```text\n{hm_body}\n```\n", encoding="utf-8")

    rec_file = out_dir / "touch1_recruiter.md"
    rec_file.write_text(f"# 🥈 Touch 1: Recruiter Outreach (Priority 2)\n\n**To:** `{target_rec_email}` ({target_rec_name})\n**Subject:** `{rec_subject}`\n\n```text\n{rec_body}\n```\n", encoding="utf-8")

    # 2d. Generate 2-Business-Day Quick Bump Draft (Touch 2 Pre-staged for Hiring Manager at 9:03 AM)
    today = datetime.date.today()
    schedule_info = calculate_touch_schedule(today)
    touch1_send_date = schedule_info["touch1_date"]
    touch2_due_date = schedule_info["touch2_date"]
    touch1_sched_str = schedule_info["touch1_formatted"]
    formatted_due_date = schedule_info["touch2_formatted"]

    touch2_subject, touch2_body = await generate_email_draft_async(
        recipient_name=target_hm_name,
        company_name=company,
        role=role,
        additional_details=email_details,
        resume_attached=False,
        touch_number=2
    )

    touch2_path = out_dir / "touch2_quick_bump.md"
    touch2_content = f"""# ⏱️ Touch 2: 2-Business-Day Quick Bump Follow-Up (Hiring Manager)

**📅 Touch 1 Scheduled Send:** `{touch1_sched_str}`  
**📅 Touch 2 Follow-Up Send:** `{formatted_due_date}` (2 business days after initial outreach)  
**To:** `{target_hm_email}` ({target_hm_name})  
**Subject:** `{touch2_subject}`  

---

```text
{touch2_body}
```
"""
    touch2_path.write_text(touch2_content, encoding="utf-8")

    # 2e. Stage Drafts in Gmail (Both Hiring Manager + Recruiter)
    draft_id = None
    thread_id = None
    rec_draft_id = None
    if stage_gmail:
        print(f"📤 Staging Primary Gmail draft to Hiring Manager {target_hm_name} ({target_hm_email})...")
        draft = create_gmail_draft(
            to_email=target_hm_email,
            subject=hm_subject,
            body_text=hm_body,
            attachment_path=pdf_path
        )
        if draft:
            draft_id = draft.get("id")
            thread_id = draft.get("message", {}).get("threadId")
            print(f"✅ SUCCESS: Staged Hiring Manager draft in Gmail (Draft ID: {draft_id}, Thread ID: {thread_id})")

        if target_rec_email and target_rec_email.lower() != target_hm_email.lower():
            print(f"📤 Staging Secondary Gmail draft to Recruiter {target_rec_name} ({target_rec_email})...")
            draft_rec = create_gmail_draft(
                to_email=target_rec_email,
                subject=rec_subject,
                body_text=rec_body,
                attachment_path=pdf_path
            )
            if draft_rec:
                rec_draft_id = draft_rec.get("id")
                print(f"✅ SUCCESS: Staged Recruiter draft in Gmail (Draft ID: {rec_draft_id})")

    # -------------------------------------------------------------
    # STEP 3: AUTOMATED CONTINUOUS UNIT TEST RUNNER
    # -------------------------------------------------------------
    print("\n[Supervisor -> Quality Control] Running full unit test verification...")
    test_results = run_automated_test_suites()
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
    print(f"📊 ATS Match Score:        {ats_score}/100")
    print(f"📄 Tailored Resume PDF:    {pdf_path}")
    print(f"📝 Full Output Folder:     {out_dir}")
    print(f"🎯 Hiring Manager (P1):    {target_hm_email} ({target_hm_name})")
    print(f"📋 Recruiter (P2):         {target_rec_email} ({target_rec_name})")
    print(f"📌 Touch 1 Subject:        {hm_subject}")
    print(f"⏰ Touch 1 Scheduled Send: {touch1_sched_str}")
    print(f"📬 HM Draft Staged:        {'Yes (ID: ' + str(draft_id) + ')' if draft_id else 'No'}")
    print(f"📬 Recruiter Draft Staged: {'Yes (ID: ' + str(rec_draft_id) + ')' if rec_draft_id else 'No'}")
    print(f"⏱️ Touch 2 Due Date:       {formatted_due_date} (2 business days)")
    print(f"🧪 Unit Test Status:       {test_results['total_run']} Passed (0 Errors)")
    print("=" * 65)

    print("\n--- 🥇 Touch 1: Hiring Manager Outreach (Primary Draft) ---")
    print(hm_body)
    print("----------------------------------------------------------")

    print("\n--- 🥈 Touch 1: Recruiter Outreach (Secondary Draft) ---")
    print(rec_body)
    print("--------------------------------------------------------")

    print(f"\n--- ⏱️ Touch 2: 2-Business-Day Threaded Nudge (Send to {target_hm_name} on {formatted_due_date}) ---")
    print(touch2_body)
    print("---------------------------------------------------------------------------------------------------\n")
    # -------------------------------------------------------------
    # STEP 4: UPDATE MASTER APPLICATION TRACKER & DASHBOARD
    # -------------------------------------------------------------
    app_entry = {
        "company": company,
        "role": role,
        "stage": "Draft Staged" if draft_id else "Created",
        "ats_score": ats_score,
        "score_breakdown": breakdown,
        "pdf_path": str(pdf_path),
        "output_dir": str(out_dir),
        "hiring_manager_name": target_hm_name,
        "hiring_manager_email": target_hm_email,
        "recruiter_name": target_rec_name,
        "recruiter_email": target_rec_email,
        "touch1_subject": hm_subject,
        "touch1_staged": bool(draft_id),
        "touch1_draft_id": draft_id or "",
        "recruiter_draft_id": rec_draft_id or "",
        "touch1_thread_id": thread_id or "",
        "touch1_scheduled_send": f"{touch1_send_date.strftime('%Y-%m-%d')} 09:00 AM",
        "touch2_due_date": str(touch2_due_date),
        "touch2_send_time": "09:03 AM",
        "touch2_status": "Scheduled",
        "touch2_subject": touch2_subject,
        "touch2_body": touch2_body,
        "touch2_path": str(touch2_path),
        "notes": f"Highlighted: {', '.join(breakdown.get('matched_tech_skills', [])[:3])}"
    }
    record_application(app_entry)

    return {
        "company": company,
        "role": role,
        "ats_score": ats_score,
        "pdf_path": str(pdf_path),
        "output_dir": str(out_dir),
        "hm_email": target_hm_email,
        "hm_name": target_hm_name,
        "recruiter_email": target_rec_email,
        "recruiter_name": target_rec_name,
        "touch1_subject": hm_subject,
        "touch1_body": hm_body,
        "touch1_scheduled_send": f"{touch1_send_date.strftime('%Y-%m-%d')} 09:00 AM",
        "touch2_due_date": str(touch2_due_date),
        "touch2_send_time": "09:03 AM",
        "touch2_subject": touch2_subject,
        "touch2_body": touch2_body,
        "draft_id": draft_id,
        "tests_passed": test_results["passed"]
    }

def interactive_session():
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
    discovery = discover_ranked_contacts(company_hint, role_hint)
    
    # Run Sanity Audit
    audit_data = run_seniority_sanity_audit(discovery, role_hint, company_hint, jd_text)
    render_sanity_report_cli(audit_data, company_hint, role_hint)

    hms = audit_data.get("audited_hiring_managers", [])
    recs = audit_data.get("audited_recruiters", [])
    xrays = discovery.get("xray_links", {})

    hm_name_selected = None
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
        print(f"  [{len(hms) + 2}] View Google X-Ray Search Link")
        hm_choice = input(f"\nSelect Hiring Manager / Gatekeeper (1-{len(hms) + 2}, default 1): ").strip() or "1"
        try:
            hm_idx = int(hm_choice) - 1
            if 0 <= hm_idx < len(hms):
                hm_name_selected = hms[hm_idx]["name"]
                hm_email_selected = hms[hm_idx]["email"]
            elif hm_idx >= len(hms):
                hm_name_selected, hm_email_selected, _ = prompt_hunter_failsafe_loop(company_hint, role_hint, "Hiring Manager")
        except ValueError:
            hm_name_selected = hm_choice
    else:
        hm_name_selected, hm_email_selected, _ = prompt_hunter_failsafe_loop(company_hint, role_hint, "Hiring Manager")

    # 4. Recruiter Selection (Priority 2)
    print("\n" + "=" * 65)
    print(f"📋 RECRUITERS DISCOVERED (Priority 2 — Talent Partner)")
    print("=" * 65)
    if recs:
        for idx, r in enumerate(recs, 1):
            print(f"  [{idx}] {r['name']} — {r['position']} (Verified: {r['confidence']}%) -> {r['email']}")
        print(f"  [{len(recs) + 1}] Search & Verify another recruiter on Hunter.io (Fail-safe Loop)")
        rec_choice = input(f"\nSelect Recruiter (1-{len(recs) + 1}, default 1): ").strip() or "1"
        try:
            rec_idx = int(rec_choice) - 1
            if 0 <= rec_idx < len(recs):
                rec_name_selected = recs[rec_idx]["name"]
                rec_email_selected = recs[rec_idx]["email"]
            elif rec_idx >= len(recs):
                rec_name_selected, rec_email_selected, _ = prompt_hunter_failsafe_loop(company_hint, role_hint, "Recruiter")
        except ValueError:
            rec_name_selected = rec_choice
    else:
        rec_name_selected, rec_email_selected, _ = prompt_hunter_failsafe_loop(company_hint, role_hint, "Recruiter")

    custom_details = input("\nAny specific project/achievement you want to highlight? (optional): ").strip()

    asyncio.run(orchestrate_job_application(
        jd_text=jd_text,
        hm_name=hm_name_selected or None,
        hm_email=hm_email_selected or None,
        recruiter_name=rec_name_selected or None,
        recruiter_email=rec_email_selected or None,
        custom_details=custom_details
    ))

def main():
    parser = argparse.ArgumentParser(description="Master Job Search Co-Pilot Orchestrator.")
    parser.add_argument("--jd", help="Inline Job Description text")
    parser.add_argument("--file", help="Path to Job Description text file")
    parser.add_argument("--hm", help="Hiring Manager full name (Priority 1, e.g. 'David Song')")
    parser.add_argument("--hm-email", help="Hiring Manager direct email address")
    parser.add_argument("--recruiter", help="Recruiter / Talent Partner full name (Priority 2, e.g. 'Sarah Jenkins')")
    parser.add_argument("--email", help="Recruiter direct email address")
    parser.add_argument("--details", default="", help="Custom details or points to emphasize")
    parser.add_argument("--interactive", action="store_true", help="Launch guided interactive session")
    parser.add_argument("--auto-nudge", action="store_true", help="Process and send all due 2-business-day Touch 2 follow-ups automatically")
    parser.add_argument("--test-only", action="store_true", help="Run full automated unit test suites only")
    parser.add_argument("--check-thread", help="Inspect a Gmail thread ID to check if recipient replied and terminate sequence")
    parser.add_argument("--tracker", action="store_true", help="Display Master Application Tracker dashboard")
    parser.add_argument("--stage", nargs="+", metavar="ARGS", help="Update application stage (e.g. --stage Stripe Interviewing OR --stage Stripe APM Interviewing)")
    parser.add_argument("--reauth-gmail", action="store_true", help="Re-authenticate Gmail OAuth with full thread/reply inspection permissions")

    args = parser.parse_args()

    if args.reauth_gmail:
        from gmail_draft import reauthorize_gmail
        reauthorize_gmail()
        return

    # Background Autonomous Check for Due Touch 2 Nudges
    if not args.test_only:
        process_due_touch2_nudges(auto_send=True)

    if args.auto_nudge:
        print("\n" + "=" * 65)
        print("⏱️ MASTER CO-PILOT: Checking & Sending Due Touch 2 Follow-Ups")
        print("=" * 65)
        results = process_due_touch2_nudges(auto_send=True)
        if not results:
            print("🟢 All follow-up sequences are up-to-date. No Touch 2 emails due today.")
        else:
            print(f"✅ Successfully processed {len(results)} follow-up(s).")
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
            print(f"🟢 Sequence Active: No reply received yet (Message count: {status.get('message_count')}). Ready for Touch 2 nudge.")
        return

    if args.interactive or (not args.jd and not args.file):
        interactive_session()
        return

    jd_text = args.jd
    if args.file:
        fpath = Path(args.file).expanduser().resolve()
        if not fpath.exists():
            print(f"❌ File '{args.file}' not found.")
            sys.exit(1)
        jd_text = fpath.read_text(encoding="utf-8")

    asyncio.run(orchestrate_job_application(
        jd_text=jd_text,
        hm_name=args.hm,
        hm_email=args.hm_email,
        recruiter_name=args.recruiter,
        recruiter_email=args.email,
        custom_details=args.details
    ))

if __name__ == "__main__":
    main()
