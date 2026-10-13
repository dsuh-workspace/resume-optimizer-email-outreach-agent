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
import uuid
from zoneinfo import ZoneInfo
from Emails.reliability_store import read_json, atomic_write, store_lock
from pathlib import Path
from typing import List, Dict, Any, Optional

ROOT_DIR = Path(__file__).resolve().parent
APPLICATIONS_JSON_FILE = ROOT_DIR / "applications.json"
APPLICATIONS_MD_FILE = ROOT_DIR / "APPLICATIONS.md"

def load_applications() -> List[Dict[str, Any]]:
    applications = read_json(APPLICATIONS_JSON_FILE, [])
    if not isinstance(applications, list) or any(not isinstance(a, dict) for a in applications):
        raise RuntimeError("Application history must be a list of records; refusing to overwrite it.")
    return applications


def _save_applications_unlocked(applications):
    # Validate old data before replacing it, including when invoked through --refresh.
    load_applications()
    markdown = render_dashboard_markdown(applications)
    if APPLICATIONS_JSON_FILE.exists():
        atomic_write(APPLICATIONS_JSON_FILE.with_suffix('.json.bak'), APPLICATIONS_JSON_FILE.read_text())
    atomic_write(APPLICATIONS_JSON_FILE, json.dumps(applications, indent=2))
    atomic_write(APPLICATIONS_MD_FILE, markdown)


def save_applications(applications: List[Dict[str, Any]]) -> None:
    with store_lock(APPLICATIONS_JSON_FILE):
        _save_applications_unlocked(applications)


def application_key(app):
    return tuple(str(app.get(k, '')).strip().casefold() for k in ('company', 'role', 'attempt'))


def find_application(company, role, attempt=''):
    key = application_key({'company': company, 'role': role, 'attempt': attempt})
    return next((a for a in load_applications() if application_key(a) == key), None)


def legacy_sequences(app):
    """Preserve a pre-sequence contact before adding another recipient."""
    if app.get('outreach_sequences'):
        return app['outreach_sequences']
    if not app.get('touch1_thread_id'):
        return []
    recipient = app.get('hiring_manager_email') or app.get('recruiter_email')
    if not recipient:
        return []
    sequence = {k: v for k, v in app.items() if k.startswith(('touch1_', 'touch2_')) or k in ('company', 'role', 'stage', 'attempt', 'followup_error')}
    sequence.update(id=app['id'], hiring_manager_email=recipient,
                    hiring_manager_name=app.get('hiring_manager_name') or app.get('recruiter_name', ''))
    return [sequence]


def aggregate_outreach(parent, sequences):
    states = {seq.get('touch2_status', 'Awaiting Send Confirmation') for seq in sequences}
    parent['touch2_status'] = next(iter(states)) if len(states) == 1 else 'Multiple contacts: see sequences'
    if any('Replied' in str(state) for state in states):
        stage = 'Replied / In Conversation'
    elif any(str(state).startswith('Paused') for state in states):
        stage = 'Outreach Paused'
    elif 'Draft Staged' in states:
        stage = 'Touch 2 Draft Staged'
    elif 'Sent' in states:
        stage = 'Touch 2 Sent'
    elif 'Awaiting Follow-Up' in states:
        stage = 'Awaiting Follow-Up'
    else:
        stage = 'Draft Staged'
    parent['outreach_stage'] = stage
    automated = {'Created', 'Draft Staged', 'Touch 2 Draft Staged', 'Touch 2 Sent', 'Awaiting Follow-Up', 'Outreach Paused', 'Replied / In Conversation', 'Scheduled'}
    if parent.get('stage') in automated or not parent.get('stage'):
        parent['stage'] = stage
    due_dates = [seq['touch2_due_date'] for seq in sequences if seq.get('touch2_due_date') and seq.get('touch2_status') == 'Awaiting Follow-Up']
    parent['touch2_due_date'] = min(due_dates) if due_dates else ''


def record_application(app_data: Dict[str, Any]) -> Dict[str, Any]:
    """Upsert one application while preserving existing history and confirmed states."""
    with store_lock(APPLICATIONS_JSON_FILE):
        applications = load_applications()

        company = app_data.get("company", "Unknown")
        role = app_data.get("role", "Unknown")
        now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        date_str = datetime.date.today().strftime("%Y-%m-%d")

        entry = {
            "id": app_data.get("id") or f"app_{uuid.uuid4().hex}",
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
            "touch2_send_time": app_data.get("touch2_send_time", "09:06 AM"),
            "touch2_status": app_data.get("touch2_status", "Awaiting Send Confirmation"),
            "touch2_subject": app_data.get("touch2_subject", ""),
            "touch2_body": app_data.get("touch2_body", ""),
            "touch2_path": str(app_data.get("touch2_path", "")),
            "notes": app_data.get("notes", "")
        }

        entry.update({k: v for k, v in app_data.items() if k not in entry})
        existing = next((a for a in applications if application_key(a) == application_key(app_data)), None)
        if existing:
            # Keep history, IDs, and confirmed sends when updating a preparation packet.
            protected = {k: v for k, v in existing.items() if k in ('id', 'date_created', 'touch1_sent_at', 'touch1_draft_id', 'touch1_thread_id', 'recruiter_draft_id', 'touch2_draft_id', 'touch2_status', 'stage', 'touch1_staged') and v}
            previous_sequences = {seq['id']: seq for seq in legacy_sequences(existing)}
            for seq in entry.get('outreach_sequences', []):
                same = next((old for old in previous_sequences.values() if seq.get('touch1_thread_id') and old.get('touch1_thread_id') == seq.get('touch1_thread_id')
                             and old.get('hiring_manager_email', '').casefold() == seq.get('hiring_manager_email', '').casefold()), None)
                if same:
                    for key, value in seq.items():
                        if key != 'id' and not same.get(key):
                            same[key] = value
                else:
                    previous_sequences.setdefault(seq['id'], seq)
            if previous_sequences:
                entry['outreach_sequences'] = list(previous_sequences.values())
            if not existing.get('touch1_staged'):
                protected.pop('stage', None)
            updates = {k: v for k, v in entry.items() if k in app_data or k in ('last_updated', 'outreach_sequences')}
            if 'contact_verifications' in updates:
                updates['contact_verifications'] = {**existing.get('contact_verifications', {}), **updates['contact_verifications']}
            existing.update(updates)
            existing.update(protected)
            if existing.get('outreach_sequences'):
                aggregate_outreach(existing, existing['outreach_sequences'])
            entry = existing
        else:
            entry['touch2_status'] = 'Awaiting Send Confirmation'
            entry['touch2_due_date'] = ''
            applications.insert(0, entry)
        _save_applications_unlocked(applications)
        return entry

def update_application_stage(company_query: str, new_stage: str, role_query: str = "") -> bool:
    """Update one unambiguous application; require an exact role when needed."""
    with store_lock(APPLICATIONS_JSON_FILE):
        applications = load_applications()
        updated = False
        clean_cq = company_query.strip().lower()
        clean_rq = role_query.strip().lower()

        candidates = [a for a in applications if clean_cq in a.get('company', '').lower()
                      and (not clean_rq or clean_rq in a.get('role', '').lower())]
        if len(candidates) > 1:
            raise ValueError('Multiple applications match; use an exact company and role, or update by application ID.')
        for app in candidates:
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
            _save_applications_unlocked(applications)
        else:
            target_desc = f"{company_query} (Role: {role_query})" if role_query else company_query
            print(f"❌ Application matching '{target_desc}' not found in tracker.")
        return updated

def process_due_touch2_nudges(auto_send: bool = False, stage_draft: bool = True) -> List[Dict[str, Any]]:
    """Confirm Gmail sends/replies, then stage due follow-up drafts. Never sends."""
    if auto_send:
        raise ValueError("Draft-only policy: send messages yourself in Gmail.")
    if not stage_draft:
        return []
    from gmail_draft import check_thread_for_replies, create_gmail_draft
    from agent import calculate_business_days_ahead, generate_touch2_nudge
    processed = []
    now = datetime.datetime.now(ZoneInfo('America/Los_Angeles'))
    with store_lock(APPLICATIONS_JSON_FILE):
        applications = load_applications()
        for parent in applications:
            sequences = parent.get('outreach_sequences') or [parent]
            for app in sequences:
                if app.get('touch2_status') in ('Dismissed', 'Replied', 'Sequence Terminated', 'Replied (Sequence Cancelled)'):
                    continue
                thread_id = app.get('touch1_thread_id')
                recipient = app.get('hiring_manager_email') or app.get('recruiter_email')
                if not thread_id or not recipient:
                    app['touch2_status'] = 'Awaiting Send Confirmation'
                    app['touch2_due_date'] = ''
                    continue
                status = check_thread_for_replies(thread_id, recipient, not_before=app.get("touch1_created_at"))
                if status.get('error') or str(status.get('status', '')).startswith('ERROR'):
                    app['touch2_status'] = 'Paused: Gmail Inspection Failed'
                    app['followup_error'] = status.get('error') or status.get('status')
                    processed.append({'company': parent.get('company'), 'action': 'paused', 'error': app['followup_error'], 'app': app})
                    continue
                if not status.get('touch1_sent') or not status.get('sent_at'):
                    app['touch2_status'] = 'Awaiting Send Confirmation'
                    app['touch2_due_date'] = ''
                    continue
                try:
                    sent = datetime.datetime.fromisoformat(status['sent_at']).astimezone(ZoneInfo('America/Los_Angeles'))
                except (ValueError, TypeError):
                    app['touch2_status'] = 'Paused: Invalid Send Timestamp'
                    processed.append({'company': parent.get('company'), 'action': 'paused', 'error': 'Invalid confirmed send timestamp', 'app': app})
                    continue
                app['touch1_sent_at'] = sent.isoformat()
                due = calculate_business_days_ahead(sent.date(), 2)
                app['touch2_due_date'] = due.isoformat()
                app['touch2_send_time'] = '09:06 AM'
                if status.get('has_reply'):
                    app['touch2_status'] = 'Replied (Sequence Cancelled)'
                    app['stage'] = 'Replied / In Conversation'
                    processed.append({'company': app.get('company'), 'action': 'terminated_reply', 'app': app})
                    continue
                app.pop('followup_error', None)
                if app.get('touch2_draft_id'):
                    # A staged draft is a duplicate-prevention marker, not a reason
                    # to stop monitoring. Require exact SENT correlation evidence.
                    expected_id = app.get('touch2_message_id')
                    confirmed = next((m for m in status.get('sent_messages', []) if
                        (expected_id and m.get('id') == expected_id) or
                        (app.get('touch2_rfc_message_id') and m.get('rfc_message_id') == app['touch2_rfc_message_id']) or
                        (app.get('touch2_operation_id') and m.get('operation_id') == app['touch2_operation_id'])), None)
                    if confirmed:
                        already_confirmed = app.get('touch2_status') == 'Sent'
                        app['touch2_status'] = 'Sent'
                        app['touch2_sent_at'] = confirmed['sent_at']
                        app['touch2_sent_message_id'] = confirmed.get('id')
                        app.pop('followup_note', None)
                        app['stage'] = 'Touch 2 Sent'
                        if not already_confirmed:
                            processed.append({'company': parent.get('company'), 'action': 'confirmed_followup_sent', 'app': app})
                    else:
                        app['touch2_status'] = 'Draft Staged'
                        app['followup_note'] = 'Draft was staged; its send is unconfirmed. Gmail may replace draft IDs or headers. Replies are still monitored.'
                    continue
                if not status.get('first_message_id'):
                    app['touch2_status'] = 'Paused: Missing Message-ID'
                    processed.append({'company': parent.get('company'), 'action': 'paused', 'error': 'Missing original Message-ID', 'app': app})
                    continue
                app['touch2_status'] = 'Awaiting Follow-Up'
                if now < datetime.datetime.combine(due, datetime.time(9, 6), tzinfo=ZoneInfo('America/Los_Angeles')):
                    continue
                subject = status.get('subject') or app.get('touch1_subject') or app.get('touch2_subject') or f"Following up: {app.get('role')} — Daniel Suh"
                body = app.get('touch2_body') or generate_touch2_nudge(app.get('hiring_manager_name') or app.get('recruiter_name') or 'there', app.get('role', ''))[1]
                try:
                    draft = create_gmail_draft(recipient, subject, body, thread_id=thread_id,
                        in_reply_to=status.get('first_message_id'),
                        idempotency_key=f"{app['id']}:touch2:{recipient.lower()}")
                except Exception as exc:
                    app['touch2_status'] = 'Paused: Draft Creation Failed'
                    app['followup_error'] = str(exc)
                    processed.append({'company': parent.get('company'), 'action': 'paused', 'error': str(exc), 'app': app})
                    continue
                if draft:
                    app['touch2_status'] = 'Draft Staged'
                    app['stage'] = 'Touch 2 Draft Staged'
                    app['touch2_draft_id'] = draft['id']
                    app['touch2_message_id'] = (draft.get('message') or {}).get('id')
                    app['touch2_rfc_message_id'] = draft.get('rfc_message_id')
                    app['touch2_operation_id'] = draft.get('operation_id')
                    app['touch2_created_at'] = now.isoformat()
                    processed.append({'company': app.get('company'), 'action': 'draft_staged', 'app': app})
            if parent.get('outreach_sequences'):
                aggregate_outreach(parent, sequences)
        _save_applications_unlocked(applications)
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
    lines.append("| Total Applications | Avg Job-description Match Estimate | Staged Drafts | Active Interviews | Offers |")
    lines.append("| :---: | :---: | :---: | :---: | :---: |")
    lines.append(f"| **{total_apps}** | **{avg_ats}/100** | **{staged_count}** | **{interviewing_count}** | **{offer_count}** |\n")
    lines.append("---\n")

    lines.append("## 📋 Active Applications Table\n")
    if not applications:
        lines.append("*No applications recorded yet. Run `copilot.py` to create your first application packet.*\n")
    else:
        lines.append("| # | Company | Role | Match Estimate | Touch 1 Status | Touch 2 Due | Hiring Manager (P1) | Recruiter (P2) | Stage | Artifacts |")
        lines.append("| :-: | :--- | :--- | :-: | :-: | :-: | :--- | :--- | :-: | :-: |")
        for idx, app in enumerate(applications, 1):
            comp = app.get("company", "N/A")
            role = app.get("role", "N/A")
            score = f"`{app.get('ats_score', 'N/A')}/100`"
            t1_status = "Sent (confirmed)" if app.get("touch1_sent_at") else ("Draft created" if app.get("touch1_staged") else "Unconfirmed")
            t2_time = app.get("touch2_send_time", "09:06 AM")
            t2_due = f"`{app['touch2_due_date']} @ {t2_time}`" if app.get("touch1_sent_at") and app.get("touch2_due_date") else "Awaiting confirmed send"
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
            t1_sched = app.get("touch1_sent_at") or "Unconfirmed; review and send in Gmail"
            t2_due = app.get("touch2_due_date") if app.get("touch1_sent_at") else "Awaiting confirmed send"
            t2_time = app.get("touch2_send_time", "09:06 AM")
            stage = app.get("stage", "Draft Staged")
            pdf_p = app.get("pdf_path", "")
            out_p = app.get("output_dir", "")
            t2_p = app.get("touch2_path", "")
            notes = app.get("notes", "")

            lines.append(f"### {idx}. {comp} — {role}")
            lines.append(f"- **📅 Created:** `{date_c}` | **Status / Stage:** `{stage}`")
            lines.append(f"- **🎯 Job-description Match Estimate:** `{score}/100`")
            lines.append(f"- **⭐ Hiring Manager (Priority 1):** {hm_name} (`{hm_email}`)")
            lines.append(f"- **📋 Recruiter (Priority 2):** {recip_name} (`{recip_email}`)")
            lines.append(f"- **📌 Touch 1 Confirmed Send:** `{t1_sched}` (Subject: `{t1_subj}`)")
            lines.append(f"- **⏱️ Touch 2 Follow-Up Send:** `{t2_due} at {t2_time}` (2 business days after Touch 1)")
            for seq in app.get('outreach_sequences', []):
                lines.append(f"- **Contact sequence:** {seq.get('hiring_manager_email')} — {seq.get('touch2_status', 'Awaiting Send Confirmation')}; confirmed first send: {seq.get('touch1_sent_at') or 'none'}; follow-up due: {seq.get('touch2_due_date') or 'not yet determined'}")
            for sequence in app.get('outreach_sequences') or [app]:
                diagnostic = sequence.get('followup_error') or sequence.get('followup_note')
                if diagnostic:
                    lines.append(f"- **Follow-up inspection:** {diagnostic}")
            if app.get('review_packet_path'):
                lines.append(f"- [Review packet]({app['review_packet_path']})")
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
        with store_lock(APPLICATIONS_JSON_FILE):
            _save_applications_unlocked(load_applications())
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
