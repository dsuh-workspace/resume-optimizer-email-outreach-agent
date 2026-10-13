# Resume and Recruiter Outreach Co-Pilot

This Python project prepares Daniel Suh's job application materials: a tailored one-page resume, an evidence review, personalized Gmail drafts, and a local application tracker. It does not submit job-portal applications or send emails. Daniel reviews and sends messages in Gmail.

## Where to find things

Open **[Workspace](Workspace/)** for everyday use. Its shortcuts open ApplyPilot, generated resume packets, job descriptions, the application tracker, and extension setup instructions. They point to the original files, so there are no extra copies to keep in sync. Keep this folder inside the project so its relative shortcuts continue to work.

- **[job_descriptions](job_descriptions/)** — saved job descriptions grouped into company folders. Original filenames are preserved. For example, use `--file job_descriptions/IBM/current_ibm_jd.txt` for that saved posting. The runnable sample stays at `Resume/sample_jd.txt`.
- **[Resume/output](Resume/output/)** — generated application packets, with their existing folder names and paths preserved.
- **[Resume](Resume/)** — resume code, verified profile, templates, reference PDFs, and the automatic job-description cache. Reference PDFs stay in place because saved application history and attachment lookup use those paths.
- **[backups/application_history](backups/application_history/)** — historical dated tracker backups. Live history remains in root `applications.json`; automatic current-version backups retain their normal location.
- **[extension](extension/)** — the actual folder to select in Chrome's **Load unpacked** dialog.

The macOS launcher, Python entry points, credentials, and live application state keep their existing locations. The private `backups/folder_organization_2026-10-05.json` manifest records every moved file's original path, new path, and checksum for recovery. Nothing was deleted or deduplicated during organization.

## Workflow

1. Supply a job description through `copilot.py` or the standalone resume generator.
2. Gemini selects and rewrites achievements from `Resume/master_profile.json`. Every rewritten bullet references its source bullets. Checks reject unsupported metrics, wrong employers/roles/dates, unsupported listed skills, and missing evidence.
3. Chrome renders a one-page PDF. The output includes HTML, Markdown, structured JSON, and a tailoring report showing originals beside rewrites. A PDF checksum ties outreach attachments to the validated packet.
4. Contact discovery identifies possible recruiters and hiring managers. Before drafting, discovered mailboxes require an explicit Hunter result of `valid`/`deliverable` with a score of at least 50. A directly entered address is marked **user-provided**, not independently verified. Guessed address patterns and DNS checks never qualify as mailbox proof.
5. The review packet shows the attachment, claim evidence, contact verification source/date, and outreach copy. Gmail drafts are created for review. Repeated operations reuse their original draft IDs; draft creation snapshots identify the contents originally staged.
6. An explicit follow-up check reads Gmail. Only an actual `SENT` message starts the clock. A second draft becomes due two business days later at 9:06 AM Pacific. A reply cancels that contact's sequence; inspection errors pause it. Hiring-manager and recruiter sequences are tracked separately.

The **job-description match estimate** uses 45% technical skills, 30% business skills, and 25% keyword coverage. It is an internal keyword estimate, not an employer's ATS score or a hiring probability. Automated evidence checks do not prove that every paraphrase preserves meaning; review the originals and rewrites.

## Project layout

| Component | Purpose |
| --- | --- |
| `Workspace/` | Shortcuts for daily use |
| `job_descriptions/<Company>/` | Saved job descriptions organized by company |
| `backups/application_history/` | Historical dated tracker backups |
| `copilot.py` | Main terminal workflow and application review packet |
| `review_app.py`, `review_ui/` | Local review screen, bullet editing, and PDF regeneration |
| `extension/`, `extension_api.py`, `extension_state.py` | ApplyPilot Chrome autofill, local progress, and background drafting/generation |
| `ApplyPilot.app`, `scripts/launch_applypilot.py` | On-demand macOS companion launcher |
| `Resume/tailor.py`, `Resume/evidence.py` | Tailoring, source references, factual checks, match report |
| `Resume/render_pdf.py`, `Resume/generate_resume.py` | PDF rendering and resume-only generation |
| `Emails/contact_finder.py`, `contact_auditor.py`, `email_validator.py` | Contact discovery, role suitability, mailbox verification |
| `Emails/gmail_draft.py` | Draft creation, duplicate prevention, sent/reply inspection |
| `tracker.py` | Locked application updates and Markdown dashboard |
| `scripts/daily_nudge.py` | Optional weekday background draft checks |
| `notifier.py` | Desktop/audio completion notifications |

## Setup

Use Python 3.10+ on macOS or Linux, Google Chrome/Chromium, and the dependencies in `Emails/requirements.txt`. The existing local interpreter is `Emails/.python/python/bin/python3`.

1. Install dependencies: `python3 -m pip install -r Emails/requirements.txt`.
2. Configure `GEMINI_API_KEY` and `HUNTER_API_KEY` in `Emails/.env`.
3. Supply Gmail OAuth client credentials in `Emails/client_secret.json`, then run `copilot.py --reauth-gmail` with the configured Python interpreter. The current implementation uses `gmail.modify` for drafting and thread inspection; application code disables sending.
4. Populate `Resume/master_profile.json` with verified facts. A missing profile is an error; the template is never silently substituted.

## Commands

Run from the project folder with the configured interpreter:

```bash
# Guided preparation
Emails/.python/python/bin/python3 copilot.py

# Prepare a packet and draft to a directly supplied contact
Emails/.python/python/bin/python3 copilot.py --file Resume/sample_jd.txt --hm "Alex Smith" --hm-email "alex@company.org"

# Resume only, without Gmail
Emails/.python/python/bin/python3 Resume/generate_resume.py --jd Resume/sample_jd.txt --output-dir Resume/output

# Outreach using an existing, evidence-backed company/role packet
Emails/.python/python/bin/python3 copilot.py --outreach "Alex Smith" --company "Company" --role "Product Manager"

# Explicit draft-only follow-up processing
Emails/.python/python/bin/python3 copilot.py --auto-nudge

# Read-only inspection
Emails/.python/python/bin/python3 copilot.py --tracker
Emails/.python/python/bin/python3 copilot.py --check-thread "GMAIL_THREAD_ID" --email "alex@company.org"

# Local browser review and bullet editing (no Gmail access needed)
Emails/.python/python/bin/python3 copilot.py --review

# Offline regression suites
Emails/.python/python/bin/python3 copilot.py --test-only
```

`--new-attempt LABEL` explicitly creates a separate attempt for the same company and role. Reuse the same label to resume that attempt. The default attempt updates the existing application. `--send-due` is rejected; sending is performed manually in Gmail.

## Review and edit a saved resume

1. Run `Emails/.python/python/bin/python3 copilot.py --review` from this folder. Leave the terminal running, then open **http://127.0.0.1:8765**. Use `--review-port 8777` if that port is already occupied. The standalone `review_app.py` command also works.
2. Select a packet in the sidebar. The saved PDF appears alongside each tailored bullet and its verified original. Open **Contacts & email** to inspect verification source/date and saved email copy. Gmail snapshots show the contents at draft creation, not later edits in Gmail.
3. Edit the bullet text, then click **Save & regenerate PDF**. Evidence and metric checks run again, followed by the one-page layout check. A successful save creates a complete new version in `Resume/output/`; the original packet remains intact. Failed saves preserve your on-screen edits and the original files.
4. Review the new PDF. If you already have a Gmail draft, review its claims and replace its attachment manually before sending. The review screen does not change Gmail drafts, application history, or the master profile. New outreach can discover the newly saved resume, but duplicate protection still reuses existing draft IDs.
5. Press **Ctrl+C** in the terminal to stop the server.

Older packets without source evidence or a matching PDF checksum can be inspected but cannot be edited here. Regenerate those through the resume pipeline first. Manually edited versions do not retain a supposedly current match score; it is marked as not recalculated. Contact records are historical verification results, not a live mailbox check. Missing structured outreach data is shown explicitly, with saved Markdown review notes available as a fallback.

The server listens only on `127.0.0.1`, uses no external assets, and protects local review requests with a browser session and mutation token. Reviewing and editing resumes requires no AI call. The extension's explicit **Draft answer** action uses the configured Gemini service. Bullet source references, experience selection, and resume geometry remain governed by the existing pipeline.

## ApplyPilot Chrome application autofill

Open **ApplyPilot.app** once, click **Enable Chrome connection**, and load the extension using the setup guide. After setup, just click ApplyPilot on a job posting: Chrome starts the companion automatically. Choose the matching resume, then click **Autofill this page**; preview is optional. Unfinished work is saved locally for 30 days. The panel can generate a new tailored resume from a reviewed posting, draft answers as background jobs, and restore progress after Chrome restarts. Requested written answers are checked automatically when filling, including after restoration or editing.

The personal extension fills hosted Greenhouse and Lever applications from your selected evidence-backed resume. It previews field values, preserves existing answers by default, uses explicitly saved preferences, and automatically validates requested written answers before inserting them. Unknown or ambiguous answers are listed with reasons; a rejected written answer does not block clear factual fields. You navigate and submit yourself.

See [extension installation and usage](extension/README.md) for Chrome's **Load unpacked** setup, automatic connection and repair, preferences, supported controls, and tests. It does not send email, submit applications, or mark them submitted in the tracker. Legacy packets must be regenerated before autofill.

The default Python suite skips the loopback integration test in restricted environments. Run that check explicitly with `COPILOT_HTTP_TESTS=1` as documented in the extension README; a skipped check is not a verified integration.

## Optional background checks

Preview the configuration without installing it:

```bash
bash scripts/setup_daily_nudge_daemon.sh --dry-run
```

To install it yourself, run the same command without `--dry-run`. Installation is separate from normal pipeline execution. The job performs one successful weekday check from **9:10 AM America/Los_Angeles**, with a five-minute polling interval for catch-up/retries. It handles daylight saving time and a changed macOS time zone. A sleeping computer checks after waking. Weekends are skipped; public holidays are not modeled. The background process never opens an OAuth browser; authorization failures require an interactive `--reauth-gmail` run.

## Local state and recovery

- `applications.json` is the authoritative history. Updates are locked and atomic; `applications.json.bak` retains the prior valid version. Invalid history stops writes. `APPLICATIONS.md` is derived and can be regenerated with `tracker.py --refresh`.
- `.draft_registry.json` records operations before contacting Gmail. If a response is lost, the pending operation blocks a second creation. Inspect Gmail and reconcile that operation before retrying; do not delete the registry to bypass duplicate protection.
- Legacy records labeled “Scheduled” remain unconfirmed until Gmail proves a send. Existing application files and old resume packets are preserved. Old packets without evidence/checksums must be regenerated before new outreach.
- A retry may reuse an older draft while generating updated local copy. The review packet includes the original creation snapshot and attachment path for each reused draft. Always review the current message in Gmail before sending.
- Tests use temporary history/contact stores and mocked external services. Passing tests do not establish that live Gmail credentials, Hunter credits, or Gemini access are currently healthy.

## License

MIT. See `LICENSE`.

Follow-up monitoring continues after Touch 2 is staged. Exact SENT correlation headers can confirm a send even when Gmail replaces its resource ID; missing correlation remains unconfirmed, and replies are still checked. This follows [Gmail’s draft lifecycle](https://developers.google.com/workspace/gmail/api/guides/drafts). Legacy contact state is retained when adding sequences, and inspection failures appear as paused diagnostics.

ApplyPilot 0.5.0 adds explicitly authorized cross-company relationship answers, full-master-profile employment checks, structural date recognition, and narrow application-data consent. See [extension setup and reload instructions](extension/README.md) and [verification details](extension/tests/coverage_report.txt).
