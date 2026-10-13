# Multi-Agent System Manifest & Architecture

This repository is Daniel Suh's job application preparation and recruiter outreach co-pilot. `copilot.py` coordinates specialized Python modules. The current operating policy is **Gmail drafts only**: Daniel reviews and sends messages himself.

## Agent responsibilities

### Master Supervisor — `copilot.py`

- Coordinate Resume Specialist → contact audit → Outreach & Email Specialist.
- Keep resume achievements, outreach claims, attachments, and application records consistent.
- Create a review packet with source evidence, verification provenance, email copy, and original Gmail draft creation snapshots.
- Run regression suites before creating drafts in the full pipeline; fail if checks fail.
- Read-only commands must not process pending follow-ups.

### Resume Specialist — `Resume/`

- Use `master_profile.json` as the verified source of career facts. Never silently load the template when the profile is missing.
- Tailor the four selected experiences, normally Autopilot Local, Asian American Christian Fellowship, Aroma Vault, and ClayThis. Keep existing experience-selection and consulting-bullet rules in `tailor.py`.
- Require source references for each rewritten bullet and evidence for listed skills. Preserve the original source text in reports. Block unsupported numbers/units, wrong experience references, roles/dates, and unsupported qualifications before rendering.
- Preserve EDUCATION → EXPERIENCE → SKILLS, the `phone | email | linkedin | github` header, and Times New Roman/serif styling. Require exactly one page after layout adjustments.
- Check bottom whitespace as well as page count. Use bounded font and spacing adjustments to balance the page; do not add content just to fill space. Honor the renderer's layout-review failure and visually inspect the final PDF before delivery.
- Save PDF, Markdown, HTML, JSON, and the tailoring report. Include a PDF checksum so attachment verification detects changed files.
- After creating and verifying a resume for Daniel, open its output folder in macOS Finder with the final PDF selected (`open -R <final_pdf_path>`). This is a standing user preference; use the exact newly generated artifact path.
- Call the weighted 45% technical / 30% business / 25% keywords result a **job-description match estimate**. Do not present it as an employer ATS score or hiring probability.
- Automated checks do not prove every paraphrase's meaning. Keep originals and rewrites visible for human review.

### Contact and Seniority Specialists — `Emails/`

- Find role-appropriate hiring managers and recruiters, with seniority calibration for internships and early-career roles.
- Treat discovery results as candidates until mailbox verification succeeds.
- Require an explicit Hunter `valid`/`deliverable` result and score >= 50 before using discovered mailboxes. Direct user entries are allowed but labeled user-provided, never independently verified.
- Never synthesize mailbox addresses or manufacture confidence scores. Syntax and DNS checks do not establish mailbox deliverability.
- Record verification source, score/status, and date. Pause when verification is unavailable.

### Outreach & Email Specialist — `Emails/`

- Read `email-agent-context.md` and `memory.md` for voice and preferences.
- Create post-application follow-ups only, with the validated PDF for the exact company/role. Do not silently substitute a base resume or omit a required attachment.
- Keep outreach numeric achievements grounded in the attached resume. Use subject `Following up: [Role Title] — Daniel Suh`.
- Create Gmail drafts; never send automatically. The legacy `create_scheduled_send` wrapper also only creates a draft. `--send-due` and the direct-send helper are disabled.
- Repeated operations reuse draft IDs. An uncertain API response leaves a pending registry entry and blocks duplicate creation until reconciled.
- Start follow-up timing only from an actual Gmail `SENT` message timestamp. Prepare Touch 2 two business days later at 9:06 AM America/Los_Angeles. Skip weekends; holiday calendars are out of scope.
- Check exact reply sender addresses. Additional outgoing messages or drafts are not incoming replies. Gmail inspection errors pause processing. Each recipient has a separate sequence.

### Tracker and Notifications — `tracker.py`, `notifier.py`

- Preserve application history and unrelated work. Use locks, atomic writes, and a prior-version backup. Corrupt history is a hard error, not an empty tracker.
- Reuse applications by normalized company, role, and attempt label. A separate attempt requires explicit `--new-attempt LABEL`.
- Treat legacy “Scheduled” records as unconfirmed until inspected in Gmail.
- Keep dashboard states accurate: created draft, confirmed sent, awaiting follow-up, replied, or paused.
- Desktop/audio notifications report actual outcomes, without implying automatic sending.

### Local Review Screen — `review_app.py`, `review_ui/`

- Show saved PDFs, source evidence, contact verification records, and original draft snapshots together. Do not claim snapshots reflect later Gmail edits.
- Manual bullet edits must pass the existing evidence and one-page PDF checks. Publish complete new packet versions atomically; preserve originals, master profile, tracker state, and existing Gmail attachments.
- Reject stale source packets and unsupported metrics. Keep legacy packets without evidence/checksums view-only. Label the match estimate as not recalculated after manual editing.
- Serve on loopback only. Keep packet paths constrained to local output, escape displayed content, and require session/CSRF checks. Resume review does not require Gmail authentication or make external API calls.

### ApplyPilot Chrome Application Autofill — `extension/`, `extension_api.py`, `extension_state.py`

- Fill only user-selected fields on hosted Greenhouse and Lever pages from a validated, explicitly selected packet. Preserve populated values unless replacement is explicitly selected.
- The user-invoked **Prepare application** flow on hosted Greenhouse authorizes eligible blank fields, matching validated resume selection/generation, and required written answers from the full verified profile. Preserve opt-outs; batch genuinely missing facts for user input. Model interpretation may select evidence, never authorize unknown facts. Keep optional essays untouched and leave final review/submission to Daniel.
- Use the explicitly installed Chrome native connector for on-demand startup and authenticated connection; retain short-lived code pairing as an advanced fallback. Only the stable extension origin may invoke the narrow handshake. Revocation must disable the native grant too; never silently reauthorize it. Keep API keys and source data in Python. Use a separate authenticated extension API without weakening existing review-session checks.
- Fill optional disclosures only from explicit user-provided application preferences, selected automatically when the user clicks Autofill. Never infer sensitive facts. With explicit saved authorization, fill clear recruitment-data and demographic-data processing consent only; revalidate wording and retained checked state. Keep mixed agreements, attestations, background-check/marketing permissions, credentials, unknown answers, and ambiguous controls manual. Never click Next or Submit or invoke submission APIs.
- Use explicit cross-company personal-relationship answers. Route work-for/work-with questions to Python against the full master profile, including experiences omitted from a tailored resume. Only an explicit exhaustive-list preference authorizes answering No for absent employers; missing profiles and ambiguous entities remain unresolved. Company-specific compound answers require matching company and exact wording.
- Draft written answers only on request using the configured Gemini service. Show evidence without an approval step; revalidate written answers at fill time, including restored or edited answers. Reject stale question, packet, page, or answer context. Validate metric frequency including daily/weekly/monthly/annual aliases and missing qualifiers.
- Validate portal acknowledgement and retained field values. Report failed fills and provide manual upload fallback. No automatic tracker/Gmail/profile updates.
- Keep unfinished posting-specific work locally for 30 days; restore written answers for automatic revalidation at fill time. Background jobs use idempotent requests, bounded concurrency, cancellation before publication, and restart diagnostics. Resume generation is resume-only and publishes complete validated packets; select validated prepared resumes directly and offer optional PDF/evidence preview.
- Keep the macOS companion on-demand. Do not install a login task.
- Test adapters against synthetic local forms. Run mapping and worker tests plus browser integration tests; do not fill live applications merely to test code. Report sandbox-blocked or skipped integration checks explicitly.
- For the explicitly authorized Greenhouse generalization campaign, supervised live preparation is permitted on suitable applications after local regression checks. Keep private recovery/evidence, use normal panel controls, and never click Next or Submit. Require three fresh passes per acceptance form; this authorization does not enable unattended live testing.

## Mandatory operating policies

1. **Fail-Fast and no fabricated facts:** Missing critical data, verification, source evidence, or valid artifacts must stop the affected operation with a specific diagnostic. Do not substitute guesses.
2. **Regression tests:** Code changes require corresponding tests in `Emails/test_emailer.py`, `Resume/test_resume.py`, or `test_copilot.py`. Execute the full suite. Tests must isolate application history, contact files, draft state, and external APIs.
3. **Draft-only control:** No message-send API calls in supported application workflows. Daniel sends in Gmail. Installing the optional background job is a separate user-invoked action.
4. **Signature:**

   ```text
   Thanks for your time,
   Daniel Suh
   linkedin.com/in/daniel-suh-994411297 | 661-476-8194
   ```

5. **Gmail health:** Verify access before Gmail-dependent work. Resume-only generation remains available separately. Background tasks must not launch an interactive authorization flow.
6. **Privacy:** Keep profiles, applications, credentials, token files, contact lists, local draft registries, and generated packets out of version control.

## Common commands

Run from this repository's actual location; do not hardcode old project paths.

```bash
Emails/.python/python/bin/python3 copilot.py
Emails/.python/python/bin/python3 copilot.py --file Resume/sample_jd.txt
Emails/.python/python/bin/python3 copilot.py --outreach "Alex Smith" --company "Company" --role "Role"
Emails/.python/python/bin/python3 copilot.py --auto-nudge
Emails/.python/python/bin/python3 copilot.py --tracker
Emails/.python/python/bin/python3 copilot.py --review
Emails/.python/python/bin/python3 copilot.py --check-thread "THREAD_ID" --email "person@company.org"
Emails/.python/python/bin/python3 copilot.py --test-only
bash scripts/setup_daily_nudge_daemon.sh --dry-run
```

The optional background checker runs once successfully per weekday from 9:10 AM Pacific, using a five-minute retry/catch-up interval. Configuration paths are derived from the project location. Never install it merely to inspect or test the configuration.
