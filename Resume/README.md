# Evidence-backed Resume Generator

Generate a tailored one-page resume from a job description and `master_profile.json`. Gemini may rewrite wording, but every bullet must reference source bullets from the same experience. Numbers, units, roles, dates, listed skills, coursework, and honors are checked before rendering. Identity and degree display come from the verified profile.

## Usage

Saved company postings are organized under [`../job_descriptions/`](../job_descriptions/). Pass the selected file's new path to `--jd` (or `copilot.py --file`). `sample_jd.txt` stays here for the example below. Existing PDFs, generated packets, the verified profile, and `jd_cache/` keep their original paths.

From the repository root:

```bash
Emails/.python/python/bin/python3 Resume/generate_resume.py --jd Resume/sample_jd.txt --output-dir Resume/output
```

`--jd` accepts a file or inline text. Running without it opens interactive mode. `--profile` selects a verified profile file; missing files fail instead of loading sample data. Use Python 3.10+, the repository dependencies, Google Chrome/Chromium, and `GEMINI_API_KEY`.

## Outputs

Each run creates a timestamped company/role folder containing:

- `Daniel_Suh_Resume_<Company>.pdf`: one-page PDF with selectable text.
- `resume.html` and `resume.md`: formatted and plain-text versions.
- `tailored_resume.json`: resume data, parallel `bullet_source_refs` arrays, `evidence_version`, PDF checksum, and validation report.
- `tailoring_report.md`: match breakdown, original and rewritten bullets, skill sources, and interview suggestions.

The full co-pilot adds `review_packet.md` and outreach copy. Email attachment lookup requires the exact company and role and a PDF matching the stored checksum.

## Evidence contract

Source IDs use `<experience-id>:bullet:<zero-based-index>`. They are resolved against the profile used for the run; reports retain original source text. A rewritten bullet may cite multiple source bullets from the same employer. Unsupported metrics or missing references raise errors. Known skill aliases are narrow; partial word overlap is insufficient evidence. Contact, education, and employment details cannot be invented.

The report's **job-description match estimate** is an internal 45/30/25 weighted keyword calculation, not an employer ATS result. Automated checks cannot establish complete semantic equivalence; review each rewrite against its original. Adding a new verified capability belongs in the master profile, not in a validation bypass.

The renderer preserves EDUCATION → EXPERIENCE → SKILLS, the contact header, and serif styling. It checks both page count and bottom whitespace. After fitting to one page, it gradually increases bullet font size and spacing when excess room remains, aiming for at most 60 points (about 0.83 inches) below the text. Growth is capped at 10.8-point bullet text. It retains the last one-page layout if further growth overflows, and rejects layouts with more than 72 points (one inch) of bottom whitespace for manual review. Blank or unmeasurable PDFs also fail. Final spacing measurements are saved in `layout_settings`; no achievements are added or rewritten to fill space. Visual PDF review is still required.

## Testing

Run `Emails/.python/python/bin/python3 copilot.py --test-only` from the repository root. Tests use temporary files and mocked services. Existing output packets remain untouched.
