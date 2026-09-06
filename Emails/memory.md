# Memory

## Voice
- Write like a real person, not corporate boilerplate. Warm, friendly, direct, concise (under 130 words).
- Use natural contractions (I'm, we've, don't).
- Always use Daniel Suh's signature:
  Thanks for your time,
  Daniel Suh
  linkedin.com/in/daniel-suh-994411297 | 661-476-8194

## Process
- Post-job-application outreach only. No cold coffee chat templates.
- Always create drafts in Gmail — never send automatically.
- Automatically find and attach the tailored resume PDF from `Resume/output/` matching the target company.
- **Mandatory Unit Testing & Coverage**: Whenever any changes or new features are added to the codebase, always create corresponding unit test cases in `test_emailer.py` / `test_resume.py` and execute the test suite to verify a 100% test pass rate before completion.
- **Fail-Fast & Zero Hallucination Mandate**: If any critical information is missing, ambiguous, or fails validation (e.g. missing profile metric, failed 1-page PDF layout, missing API key), never guess or invent data. Immediately halt execution and alert Daniel with the exact issue.

## People
- Target recipients: Hiring Managers, Technical Recruiters, Team Leads.

## Projects
- Automated Job Application Follow-up Agent integrated with Hunter.io, Gemini AI, and Gmail API.
- AI Resume Generator & ATS Optimizer located in `../Resume`.

## Output
- **Subject Standard**: `Following up: [Role Title] — Daniel Suh` (or `Following up: [Role Title] at [Company] — Daniel Suh`).
- **Touch 1 (Day 1 Outreach)**: 3 short paragraphs referencing application, exact quantifiable metric from profile matching JD, tailored PDF resume attachment, and low-friction invitation to connect.
- **Touch 2 (3-Business-Day Threaded Nudge)**: Ultra-concise threaded reply: "Following up in case my note below got buried, totally understand things get busy. Would still love the chance to connect if timing works on your end!"

## Tools
- Hunter.io API for contact email discovery.
- Google Gemini for domain resolution and personalized copy generation.
- Gmail API (`gmail.compose`) for draft creation with PDF resume attachments.