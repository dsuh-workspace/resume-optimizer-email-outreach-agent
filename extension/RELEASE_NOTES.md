# ApplyPilot 0.9.2 candidate — 2026-10-07

The supervised 0.9.1 IEX trial completed 22 of 23 eligible fields (95.7%).
LinkedIn, required writing and conditional race worked; school remained blank.

- Search school catalogs with full-name comma and spaced-dash variants, preserving
  all institution and campus words. Matching still rejects other campuses and
  duplicate equivalent choices; searches never reduce to a campus fragment.
- Allow delayed school search results to replace a previous empty or unrelated
  result within the existing four-second search window.
- Add an asynchronous catalog reproduction and a manifest/content version check.

Reload ApplyPilot and refresh the application page after preserving unsaved work.
Fresh 0.9.2 live acceptance is still required; this candidate is not released.

---

# ApplyPilot 0.9.1 candidate — 2026-10-07

First supervised IEX trial exposed three gaps; this candidate remains unreleased.

- School catalogs may use a comma or spaced dash before a campus. Match those
  separators while preserving every word, rejecting duplicate choices and other campuses.
- Recognize the explicit LinkedIn profile URL label and its direct-link instruction.
- Continue independent facts and required writing after unavailable choices or upload
  failures. Attempt failed fields once per Prepare click and retain the failure summary.
  Changed application context still stops preparation for a fresh review.

Local regressions must pass and live trials restart on this candidate. The initial
IEX trial is a failed acceptance trial, not one of the required 18 passing trials.

---

# ApplyPilot 0.9.0 candidate — 2026-10-06

Reliability candidate; not released until supervised acceptance passes.

- Literal notification arguments and environment data; locked, backed-up atomic
  contact updates; unique staged publication for every resume generation path.
- One snapshot for saved-packet validation/export/evidence; persisted factual
  changes fail closed. C, C++ and C# retain distinct evidence identities.
- Applicant/third-party/uncertain subjects and enclosing sections survive scans,
  interpretation, answer identity, caching and final field checks.
- Current enrollment requires an explicit exact-question answer. Saved schools,
  expected degrees and education dates do not authorize that answer.
- One lifetime worker owner per project; recovery only after acquiring ownership.
- Preparation and field-context version 2. Existing progress is preserved and old
  answer contexts require a fresh scan and revalidation/redrafting.

Recovery-aware reload instructions are in README.md. No application submission,
Gmail sending, tracker update, background login task or automatic release is added.

---

# ApplyPilot 0.7.3 — 2026-10-05

Verify Greenhouse's compressed country display using the explicit US flag plus
+1, both immediately after selection and during the final retained-value check.
Do not infer United States from the shared dial code alone. Regression coverage
includes Canadian/missing flags, subsequent flag changes, and the real loaded
extension against a synthetic compressed-country control.

# ApplyPilot 0.7.2 — 2026-10-05

Fix anonymous Greenhouse required-input helpers whose question labels live outside
`select-shell`. Recognize the single owning combobox without requiring the helper
to repeat its label; preserve separately labelled inputs and ambiguous wrappers.
This prevents phantom questions and split education groups. Synthetic tests cover
the observed outside-label structure, helper removal, retained graduation values,
and actual panel/worker fills. Test expectations read the manifest version.

Preserve entered answers and a recoverable attachment before refreshing the live
page. Reloading the extension alone cannot replace already injected page code.

# ApplyPilot 0.7.1 — 2026-10-05

Repairs the six remaining answer/menu cases with local synthetic regression
coverage. Supported answers commit and remain selected; narrower personal facts
require an explicit company-and-question answer through the existing panel.

- Disability No no longer claims no past disability or a participation preference.
- Male does not imply cisgender; Asian does not imply East Asian. General military
  service, veteran status, and protected-veteran status remain distinct.
- Python supplies optional employment alternatives only from the authorized full
  history check. Former employment cannot become never employed.
- Native and custom degree menus share qualification ranking and duplicate checks.
  Completed-qualification fields require an explicitly completed qualification.
- Already-open menus stay open during inspection. Loaded options precede bounded
  searches. Only an associated menu and a committed selection establish success.
- Search cleanup preserves concurrent user edits. School precedes dependent fields;
  helper removal is harmless, while reordered or ambiguous entries remain stale.
- The worker rechecks current preferences and Python resolutions after restart.
  Existing answers and deliberate opt-outs survive retries.

Verification is recorded in `tests/coverage_report.txt`. No live application was
filled or submitted for testing. Fixtures reproduce the menu labels and behavior
in the task; they do not certify every current option on Robinhood's live site.

Restart the companion, reload version 0.7.1 at `chrome://extensions`, preserve
unsaved entries and refresh application tabs before reopening ApplyPilot. Old
injected code is rejected. No preference migration is needed.

---

# ApplyPilot 0.7.0 — 2026-10-05

Repairs the mechanisms behind the saved Robinhood failures: 15 missing dropdown
menus, a phone formatting rejection, and a replaced resume-upload input. Read-only
live inspection confirmed the existing upload receipt and reformatted phone value.
No live application was filled, uploaded, or submitted during this work.

## Changes

- Expected mouse events open React-style dropdowns. Menus must be associated through
  ARIA relationships or the field container; an unrelated global menu is never used.
  Exact compatible options, bounded loading waits, control identity checks, and
  final retained-value verification remain mandatory.
- Greenhouse select-shell/file-upload containers and US phone-country labels are
  supported. Country fills precede phone fills. Formatting may change, digits may
  not; country-code normalization requires an explicit saved country.
- Upload verification follows the visible filename receipt even if the input is
  removed. Error and busy indicators take precedence, with portal-specific Lever
  indicators. Missing acknowledgement remains “needs review”.
- Panel choice loading supports optional search, exact one-time answers, and
  explicitly saved company answers. Existing proposals can be overridden from
  the same actual options. No option is selected while loading choices.
- Conditional explanations with a proven immediately preceding No answer are
  marked not applicable and rechecked before filling. Other conditions stay manual.
- Lever sibling question labels are recognized independently of radio option labels.
  Its token-based location widget is explicitly manual pending a dedicated adapter.
- Diagnostic metadata includes a bounded control family and failure stage. Legacy
  records remain readable. Stale injected script versions produce a refresh message.

## Verification and limits

See `tests/coverage_report.txt` for final checks and source URLs. Automated checks
use synthetic identities and intercepted/local forms, including 57-field modern
portal fixtures. Live inspection provides structure, not proof of a submitted or
employer-saved application. Unsupported widgets, missing facts, ambiguous options,
manual attestations, history-row creation, Next and Submit remain user actions.

## Upgrade

Restart the companion, reload ApplyPilot 0.7.0 at `chrome://extensions`, and refresh
application tabs after preserving unsaved entries. Existing preferences, resumes,
saved progress, authentication, and application history remain in place. No schema
migration is required for existing diagnostics or progress.

---

# ApplyPilot 0.6.0 — 2026-10-05

This local release repairs saved field selection, school searches, recovery after
portal changes, and the accuracy of autofill results. Live Robinhood and Lever
confirmation by Daniel is still required before the overall task is complete.

## Behavior

- Selection metadata version 2 stores deliberate choices separately from automatic
  eligibility, successful fills, failures, and deferred conditional fields.
  Legacy unchecked records become eligible again when empty and answerable;
  populated controls and saved written answers are preserved. Future opt-outs
  survive rescanning and reopening. An old unchecked record cannot reliably
  distinguish a deliberate exclusion from an earlier failure, so legacy opt-outs
  may need to be reapplied once.
- School searches try only the institution and its approved aliases, with bounded
  waits and one exact compatible result. Temporary search text is not treated as
  a committed school. Failure removes only unchanged ApplyPilot search text;
  concurrent edits remain intact. Uncertain school/employer identity blocks
  dependent fields, while safe recovery allows independent degree/date fields.
- Controls replaced by the portal are rebound only when uniquely identifiable.
  A final retention check catches values cleared or rejected by later fills.
  Submit, reset and navigation buttons cannot masquerade as dropdowns.
- Each fill rechecks the validated packet, current preferences, Python resolutions
  against the full master profile, and company context. Company-specific answers
  still require exact wording. Consent still requires explicit authorization and
  recognized, unchanged wording. Conditional “If Yes” text is not drafted blindly.
- Newly revealed controls are counted, rescanned, and left unselected until chosen,
  including after reopening. Duplicate unnamed controls are counted separately.
- Diagnostics account for filled/retained, preserved, excluded, unanswered,
  manual-only, failed and invalidated fields. They record an attempt ID, extension
  version, stage and duplicate occurrence, without answer values or page HTML.
  Dropdown diagnostics distinguish list discovery, missing options, ambiguity,
  timeout, replacement and context change. Older diagnostics remain readable.

Berkeley's existing saved graduation date is May 2028. This release does not
change Daniel's preferences, master profile, application history, Gmail, or PDFs.
The old local session contained 24 unchecked legacy records; migration occurs
when that application is next opened in the updated extension.

## Verification

The repeatable acceptance matrix is independent of mapping eligibility. Assertions
read retained DOM values directly and check zero Next and Submit actions.

- Full Python suite: 186 tests, zero failures/errors, one opt-in HTTP skip.
  That loopback HTTP security test passed separately.
- Core mapping, application-profile policy, and worker tests passed, including
  changed preferences, company changes, missing profiles, employer ambiguity,
  consent boundaries and contextual date mapping.
- Greenhouse/Lever synthetic DOM and real panel tests passed, including alias-only
  searches, ambiguous results, user edits, safe school-search recovery, late
  clearing, separate experience dates, duplicate discovery and action controls.
- All 12 final real-extension scenarios passed. Fixed 40-field scenarios cover approved-alias search,
  missing-school recovery, durable legacy progress, classic native selects,
  button dropdowns, replaced controls, conditional fields, late clearing, and
  distinct Lever markup with delayed/replaced results.
- The expanded Lever workflow checks 57 fields, including contact information,
  recorded address, PDF upload, and two independently identified employment
  entries with different dates.
- Cold native startup, 32-second job recovery after panel reload, PDF attachment
  acknowledgement, full browser restart, extension reload, and revocation checks passed.

These tests use isolated Chrome profiles, intercepted synthetic portal pages and
synthetic applicant data. No live application was filled and no model or Gmail
operation was performed. Chrome startup required execution outside the sandbox.
The Computer Use client mismatch prevented read-only live inspection; fixing it
is deferred at Daniel's request.

## Install and verify locally

1. Preserve any unsaved manual entries on the application before refreshing it.
2. Open `chrome://extensions`, find ApplyPilot and click **Reload**. Verify version
   **0.6.0**. The existing extension ID and native connection remain the same.
3. Refresh the application tab, reopen ApplyPilot, select the matching resume and
   click **Autofill this page**. Preview remains optional.
4. Review retained values and **Recent fill results**. If anything fails, use
   **Copy diagnostic report** and share the report for that attempt.
5. Confirm the result on Robinhood and at least one Lever application. Daniel
   controls navigation and submission.

The local companion was restarted after confirming no queued/running jobs, and
its local health check passed. No login task was installed.

## Rollback and remaining limits

A source rollback copy is under
`backups/applypilot-0.5.0-before-reliability/`; the versioned local release archive
is `backups/ApplyPilot-0.6.0-local.zip`. Both exclude private applicant data.
For rollback, restore the extension and Python files from that copy, restart an
idle companion, reload the extension and refresh application tabs. Do not restore
or delete private progress/preferences to roll back code.

Missing facts, ambiguous entities/options, mixed agreements, accuracy
certifications, background checks, marketing, signatures, missing calendar days,
adding repeat entries and navigating/submitting remain manual. Scope is hosted
Greenhouse and Lever, not other portals or unsupported embedded applications.
Retained browser values do not prove that an employer server saved the application.
Exact live school-widget behavior remains subject to Daniel's real-use check.
