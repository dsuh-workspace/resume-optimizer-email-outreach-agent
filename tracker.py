#!/usr/bin/env python3
"""
Master Job Application Tracker & Dashboard Generator
Author: Daniel Suh & Antigravity

Maintains:
  - applications.json: Structured programmatic ledger of all job applications.
  - APPLICATIONS.md: Beautiful human-readable GitHub-style dashboard for inspection and tracking.
"""

import os
import json
import datetime
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional

ROOT_DIR = Path(__file__).resolve().parent
APPLICATIONS_JSON_FILE = ROOT_DIR / "applications.json"
APPLICATIONS_MD_FILE = ROOT_DIR / "APPLICATIONS.md"

def load_applications() -> List[Dict[str, Any]]:
    """Loads all application records from applications.json."""
    if not APPLICATIONS_JSON_FILE.exists():
        return []
    try:
        with open(APPLICATIONS_JSON_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Warning loading applications.json: {e}")
        return []

def save_applications(applications: List[Dict[str, Any]]) -> None:
    """Saves application records to applications.json and regenerates APPLICATIONS.md."""
    with open(APPLICATIONS_JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(applications, f, indent=2)
    
    # Regenerate Markdown dashboard
    md_content = render_dashboard_markdown(applications)
    APPLICATIONS_MD_FILE.write_text(md_content, encoding="utf-8")
    print(f"📊 Updated Master Dashboard: {APPLICATIONS_MD_FILE}")

def record_application(app_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Appends or updates an application entry in the master ledger.
    """
    applications = load_applications()
    
    company = app_data.get("company", "Unknown")
    role = app_data.get("role", "Unknown")
    now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    date_str = datetime.date.today().strftime("%Y-%m-%d")

    entry = {
        "id": f"app_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{company.lower()}",
        "company": company,
        "role": role,
        "date_created": date_str,
        "last_updated": now_iso,
        "stage": app_data.get("stage", "Draft Staged"),
        "ats_score": app_data.get("ats_score", 0),
        "score_breakdown": app_data.get("score_breakdown", {}),
        "pdf_path": str(app_data.get("pdf_path", "")),
        "output_dir": str(app_data.get("output_dir", "")),
        "hiring_manager_name": app_data.get("hiring_manager_name", ""),
        "hiring_manager_email": app_data.get("hiring_manager_email", ""),
        "recruiter_name": app_data.get("recruiter_name", ""),
        "recruiter_email": app_data.get("recruiter_email", ""),
        "touch1_subject": app_data.get("touch1_subject", ""),
        "touch1_staged": app_data.get("touch1_staged", False),
        "touch1_draft_id": app_data.get("touch1_draft_id", ""),
        "touch1_thread_id": app_data.get("touch1_thread_id", ""),
        "touch1_scheduled_send": app_data.get("touch1_scheduled_send", ""),
        "touch2_due_date": str(app_data.get("touch2_due_date", "")),
        "touch2_send_time": app_data.get("touch2_send_time", "09:03 AM"),
        "touch2_status": app_data.get("touch2_status", "Scheduled"),
        "touch2_subject": app_data.get("touch2_subject", ""),
        "touch2_body": app_data.get("touch2_body", ""),
        "touch2_path": str(app_data.get("touch2_path", "")),
        "notes": app_data.get("notes", "")
    }

    # Prepend new application to the top
    applications.insert(0, entry)
    save_applications(applications)
    return entry

def update_application_stage(company_query: str, new_stage: str, role_query: str = "") -> bool:
    """
    Updates the pipeline stage for an application matching company_query (and optional role_query).
    """
    applications = load_applications()
    updated = False
    clean_cq = company_query.strip().lower()
    clean_rq = role_query.strip().lower()

    for app in applications:
        comp_match = clean_cq in app.get("company", "").lower()
        role_match = (clean_rq in app.get("role", "").lower()) if clean_rq else True
        
        if comp_match and role_match:
            old_stage = app.get("stage", "Unknown")
            app["stage"] = new_stage
            app["last_updated"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            updated = True
            print(f"✅ Updated {app.get('company')} — {app.get('role')} stage from '{old_stage}' to: '{new_stage}'")
            break

    if updated:
        save_applications(applications)
    else:
        target_desc = f"{company_query} (Role: {role_query})" if role_query else company_query
        print(f"❌ Application matching '{target_desc}' not found in tracker.")
    return updated

def process_due_touch2_nudges(auto_send: bool = True) -> List[Dict[str, Any]]:
    """
    Scans all applications, checks if 3 business days have passed (today >= touch2_due_date).
    If due:
      1. Inspects Gmail thread for replies.
      2. If reply detected -> marks 'Replied / Terminated' (does not send).
      3. If no reply -> automatically sends Touch 2 quick bump in the same thread.
      4. Updates applications.json & APPLICATIONS.md.
    """
    applications = load_applications()
    processed = []
    today = datetime.date.today()
    today_str = today.strftime("%Y-%m-%d")

    for app in applications:
        status = app.get("touch2_status", "Scheduled")
        due_str = app.get("touch2_due_date", "")
        if not due_str or status in ["Sent", "Replied", "Dismissed", "Sequence Terminated"]:
            continue

        try:
            due_date = datetime.datetime.strptime(due_str, "%Y-%m-%d").date()
        except ValueError:
            continue

        # Check if due: today > due_date, OR (today == due_date and current time >= target time)
        is_due = False
        now_dt = datetime.datetime.now()
        if today > due_date:
            is_due = True
        elif today == due_date:
            target_time_str = app.get("touch2_send_time", "09:03 AM")
            try:
                target_t = datetime.datetime.strptime(target_time_str, "%I:%M %p").time()
            except ValueError:
                target_t = datetime.time(9, 3)
            
            if now_dt.time() >= target_t:
                is_due = True
            else:
                print(f"⏳ Follow-up for {app.get('company')} is due today, but waiting until {target_time_str} (Current time: {now_dt.strftime('%I:%M %p')})")

        if is_due:
            company = app.get("company", "Company")
            role = app.get("role", "Role")
            hm_name = app.get("hiring_manager_name") or "Hiring Manager"
            hm_email = app.get("hiring_manager_email") or ""
            thread_id = app.get("touch1_thread_id") or ""

            print(f"\n⏱️ Checking Due Follow-Up: {company} ({role}) — Scheduled for {due_date} around 9:03 AM")

            # 1. Check for replies first (Kill Switch)
            reply_status = {'has_reply': False}
            if thread_id:
                try:
                    from gmail_draft import check_thread_for_replies
                    reply_status = check_thread_for_replies(thread_id, hm_email)
                except Exception as e:
                    print(f"⚠️ Reply check warning: {e}")

            if reply_status.get("has_reply"):
                app["touch2_status"] = "Replied (Sequence Cancelled)"
                app["stage"] = "Replied / In Conversation"
                app["last_updated"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"🛑 SEQUENCE TERMINATED: {hm_name} at {company} replied! Skipping Touch 2.")
                processed.append({"company": company, "action": "terminated_reply", "app": app})
            elif auto_send and hm_email:
                # 2. Retrieve Touch 2 copy
                t2_subj = app.get("touch2_subject", f"Following up: {role} — Daniel Suh")
                t2_body = app.get("touch2_body")
                if not t2_body and app.get("touch2_path"):
                    try:
                        p = Path(app.get("touch2_path"))
                        if p.exists():
                            raw = p.read_text(encoding="utf-8")
                            code_match = re.search(r'```text\s*(.*?)\s*```', raw, re.DOTALL)
                            if code_match:
                                t2_body = code_match.group(1).strip()
                    except Exception:
                        pass

                if not t2_body:
                    try:
                        from agent import generate_touch2_nudge
                        _, t2_body = generate_touch2_nudge(hm_name, role)
                    except Exception:
                        t2_body = f"Hi {hm_name.split()[0]},\n\nFollowing up in case my note below got buried, totally understand things get busy. Would still love the chance to connect if timing works on your end!\n\nThanks for your time,\nDaniel Suh\nlinkedin.com/in/daniel-suh-994411297 | 661-476-8194"

                # 3. Automatically send via Gmail with thread chaining and RFC 2822 In-Reply-To header
                first_msg_id = reply_status.get("first_message_id")
                print(f"📤 Automatically sending Touch 2 nudge to {hm_name} ({hm_email}) [Target: 9:03 AM]...")
                sent_msg = None
                try:
                    from gmail_draft import send_gmail_message
                    sent_msg = send_gmail_message(
                        to_email=hm_email,
                        subject=t2_subj,
                        body_text=t2_body,
                        thread_id=thread_id or None,
                        in_reply_to=first_msg_id or None
                    )
                except Exception as e:
                    print(f"⚠️ Direct send error: {e}")

                if sent_msg:
                    app["touch2_status"] = "Sent"
                    app["stage"] = "Touch 2 Sent"
                    app["touch2_sent_date"] = f"{today_str} 09:03 AM"
                    app["last_updated"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    print(f"🚀 SUCCESS: Automatically sent Touch 2 nudge to {company} at 9:03 AM!")
                    processed.append({"company": company, "action": "sent_nudge", "app": app})
                else:
                    print(f"⚠️ Could not send automated Touch 2 to {company}.")

    if processed:
        save_applications(applications)
    return processed

def render_dashboard_markdown(applications: List[Dict[str, Any]]) -> str:
    """Renders the master human-readable Markdown dashboard."""
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p")
    total_apps = len(applications)
    
    avg_ats = 0
    scores = [a.get("ats_score", 0) for a in applications if isinstance(a.get("ats_score"), (int, float))]
    if scores:
        avg_ats = round(sum(scores) / len(scores), 1)

    staged_count = sum(1 for a in applications if a.get("stage") == "Draft Staged")
    interviewing_count = sum(1 for a in applications if a.get("stage") == "Interviewing")
    offer_count = sum(1 for a in applications if a.get("stage") == "Offer")

    lines = []
    lines.append("# 📊 Master Job Application Ledger & Pipeline Dashboard\n")
    lines.append(f"> **Last Updated:** `{now_str}`  \n> **Total Applications Tracked:** `{total_apps}`  \n")
    lines.append("---\n")

    lines.append("## 📈 Pipeline Overview\n")
    lines.append("| Total Applications | Avg ATS Match Score | Staged Drafts | Active Interviews | Offers |")
    lines.append("| :---: | :---: | :---: | :---: | :---: |")
    lines.append(f"| **{total_apps}** | **{avg_ats}/100** | **{staged_count}** | **{interviewing_count}** | **{offer_count}** |\n")
    lines.append("---\n")

    lines.append("## 📋 Active Applications Table\n")
    if not applications:
        lines.append("*No applications recorded yet. Run `copilot.py` to create your first application packet.*\n")
    else:
        lines.append("| # | Company | Role | ATS Match | Touch 1 Status | Touch 2 Due | Hiring Manager (P1) | Recruiter (P2) | Stage | Artifacts |")
        lines.append("| :-: | :--- | :--- | :-: | :-: | :-: | :--- | :--- | :-: | :-: |")
        for idx, app in enumerate(applications, 1):
            comp = app.get("company", "N/A")
            role = app.get("role", "N/A")
            score = f"`{app.get('ats_score', 'N/A')}/100`"
            t1_status = "✅ Staged" if app.get("touch1_staged") else "📝 Draft"
            t2_time = app.get("touch2_send_time", "09:03 AM")
            t2_due = f"`{app.get('touch2_due_date', 'N/A')} @ {t2_time}`"
            hm_disp = app.get("hiring_manager_name") or app.get("hiring_manager_email") or "Team Lead"
            rec_disp = app.get("recruiter_name") or app.get("recruiter_email") or "Recruiting Team"
            stage = f"**{app.get('stage', 'Draft Staged')}**"
            
            pdf_link = f"[PDF]({app.get('pdf_path')})" if app.get("pdf_path") else "PDF"
            out_link = f"[Folder]({app.get('output_dir')})" if app.get("output_dir") else "Folder"
            artifacts = f"{pdf_link} • {out_link}"

            lines.append(f"| {idx} | **{comp}** | {role} | {score} | {t1_status} | {t2_due} | {hm_disp} | {rec_disp} | {stage} | {artifacts} |")
        lines.append("\n---\n")

        lines.append("## 🏢 Detailed Application Cards\n")
        for idx, app in enumerate(applications, 1):
            comp = app.get("company", "N/A")
            role = app.get("role", "N/A")
            date_c = app.get("date_created", "N/A")
            score = app.get("ats_score", "N/A")
            hm_name = app.get("hiring_manager_name", "Team Lead")
            hm_email = app.get("hiring_manager_email", "N/A")
            recip_name = app.get("recruiter_name", "Recruiting Team")
            recip_email = app.get("recruiter_email", "N/A")
            t1_subj = app.get("touch1_subject", "N/A")
            t1_sched = app.get("touch1_scheduled_send", "Next business day @ 9:00 AM")
            t2_due = app.get("touch2_due_date", "N/A")
            t2_time = app.get("touch2_send_time", "09:03 AM")
            stage = app.get("stage", "Draft Staged")
            pdf_p = app.get("pdf_path", "")
            out_p = app.get("output_dir", "")
            t2_p = app.get("touch2_path", "")
            notes = app.get("notes", "")

            lines.append(f"### {idx}. {comp} — {role}")
            lines.append(f"- **📅 Created:** `{date_c}` | **Status / Stage:** `{stage}`")
            lines.append(f"- **🎯 ATS Match Score:** `{score}/100`")
            lines.append(f"- **⭐ Hiring Manager (Priority 1):** {hm_name} (`{hm_email}`)")
            lines.append(f"- **📋 Recruiter (Priority 2):** {recip_name} (`{recip_email}`)")
            lines.append(f"- **📌 Touch 1 Scheduled Send:** `{t1_sched}` (Subject: `{t1_subj}`)")
            lines.append(f"- **⏱️ Touch 2 Follow-Up Send:** `{t2_due} at {t2_time}` (2 business days after Touch 1)")
            if notes:
                lines.append(f"- **💡 Key Metric Highlighted:** *{notes}*")
            lines.append("- **📁 Quick Links:**")
            if pdf_p:
                lines.append(f"  - 📄 [Tailored PDF Resume]({pdf_p})")
            if out_p:
                lines.append(f"  - 📊 [ATS Tailoring Report & Artifacts Folder]({out_p})")
            if t2_p:
                lines.append(f"  - ⏱️ [Touch 2 Nudge Draft File]({t2_p})")
            lines.append("")

    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description="Master Application Tracker CLI.")
    parser.add_argument("--list", action="store_true", help="Display all tracked applications in terminal")
    parser.add_argument("--update", nargs=2, metavar=("COMPANY", "STAGE"), help="Update application stage (e.g. --update Stripe Interviewing)")
    parser.add_argument("--refresh", action="store_true", help="Re-render APPLICATIONS.md from applications.json")

    args = parser.parse_args()

    if args.update:
        company_q, new_st = args.update
        update_application_stage(company_q, new_st)
        return

    if args.refresh:
        apps = load_applications()
        save_applications(apps)
        return

    # Default: list applications
    apps = load_applications()
    print("\n" + "=" * 65)
    print(f"📊 MASTER APPLICATION TRACKER ({len(apps)} Applications)")
    print("=" * 65)
    if not apps:
        print("No applications recorded yet.")
    for idx, app in enumerate(apps, 1):
        print(f"{idx}. {app.get('company')} — {app.get('role')} | ATS: {app.get('ats_score')}/100 | Stage: {app.get('stage')} | Touch 2: {app.get('touch2_due_date')}")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    main()
