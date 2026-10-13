# ApplyPilot

Chrome autofill using your tailored resume. Open a job application, click ApplyPilot, and choose **Autofill this page**. Clear answers fill without review prompts; you submit the application yourself.

## Version 0.9.2 reliability candidate

School search uses full-name punctuation variants as well as saved aliases, and
waits for delayed results instead of treating a previous empty menu as final.
The 0.9.1 IEX trial completed 22/23 eligible fields; 0.9.2 addresses its remaining
school-search failure. Fresh supervised acceptance is still pending.

Section and subject context now travels with every scanned question, saved answer,
interpretation and fill check. Reference and emergency-contact sections remain
manual, as do ambiguous repeated identity fields. Current enrollment needs an
explicit answer to the exact question; a school, expected degree or date range
cannot establish it. Existing values, exclusions and optional essays are preserved.

Packet eligibility, autofill and written-answer evidence use one validated snapshot.
Stored identity or education that would need normalization is rejected with a
regeneration explanation. Original and legacy packets stay available for viewing.
Resume publication uses private staging and unique directories; failed or cancelled
preparation cannot expose an incomplete packet. Only one preparation worker can
own a project, including when companions use different ports.

This candidate uses preparation/field-context contract 2. Older clients must update.
Saved progress is retained, but answers from older context identities are not
silently reused. Rescan, revalidate, or redraft where requested.

1. Preserve unsaved page entries and any attachment you need to restore.
2. Stop the idle companion and reopen ApplyPilot (or reconnect through Chrome).
3. Reload ApplyPilot at `chrome://extensions`; confirm version 0.9.2.
4. Refresh the application tab after recovery is ready, then reopen the panel.

The six-form, three-pass supervised live gate must pass before release. Local tests
alone do not establish live acceptance. See `GREENHOUSE_RELIABILITY_REPORT.txt` in
the project root for the gate status and deferred audit findings.

## Version 0.8.2 preparation candidate

React Select's transient described placeholder is excluded from question helper
text. Removing “Select...” during search or selection no longer invalidates the
field, blocks its education group, or duplicates its result as a newly revealed
question. Real helper instructions still participate in stale-context checks.
Synthetic regressions reproduce the observed IEX structure and alias search;
the supervised live campaign remains incomplete until fresh trials pass.

On hosted Greenhouse pages, **Prepare application** selects a matching validated
resume or prepares one, fills supported blank fields, interprets unfamiliar
ordinary questions, and drafts required writing from the full verified profile.
It rescans up to five times, checks retained values after five seconds, and leaves
the form unsubmitted. Existing values and individual exclusions are preserved.
Optional essays stay blank. Unknown commitments, new agreements, unsupported
controls and unavailable choices remain visible for your input.

Resume preparation passes the reviewed company and role through to tailoring and
rendering as explicit metadata. Job-description analysis may extract requirements,
but cannot shorten the employer name or rename the role. The publication check
still rejects any packet whose company or role differs from the selected posting.
Automatically generated resumes copy achievement bullets directly from the
verified profile, keeping their source references and experience order. Skills
and coursework are still selected for the role. The report identifies this mode;
generated experience prose and notes about discarded rewrites are not used.
Resume evidence checks also reject known tool and financial-domain claims when
the cited bullet text or tags do not support them. Global skills and unrelated
projects cannot establish tool usage for an achievement. This targeted check
does not prove that arbitrary paraphrases preserve meaning; original sources
remain available for review.

Model interpretation selects confirmed evidence; it cannot create personal facts.
Saved facts include provenance and reuse scope. Exact company answers keep their
scope; source conflicts block reuse. Version 3 preferences preserve older client
fields and save a prior-version backup. Interpretation caches expire after 30 days
and are invalidated by question, source, employer or resolver changes.

This candidate requires companion restart, extension reload and application
refresh after recovery is saved. Its ten-application live acceptance campaign is
not complete until the private trial report records three fresh passes per form.
Synthetic tests and model evaluations do not substitute for those live trials.

## One-time setup on this Mac

1. Double-click **ApplyPilot.app**. A visible setup guide opens in your browser.
2. Click **Enable Chrome connection**. This installs the small native connector for your macOS user. It runs on demand; no login task is installed.
3. Open `chrome://extensions`, turn on **Developer mode**, click **Load unpacked**, and choose this project's `extension` folder. The setup guide has a **Copy folder path** button.
4. Pin ApplyPilot from Chrome's Extensions menu. Open a hosted Greenhouse or Lever application and click its icon.

**Upgrading:** this release uses a stable extension ID. If your old installation has a different ID from the setup guide, remove that old extension and load this folder again. Server-side resumes, preferences and 30-day progress are preserved. Written answers are revalidated automatically before filling. For version **0.7.3**, restart the local companion if it is already running, click **Reload** on the extension card, and refresh the application tab before reopening ApplyPilot.

The normal flow no longer requires opening the app, a Terminal command, or copying pairing codes. Chrome asks the native connector to start the local companion and connect automatically.

## Version 0.7.3 update

Greenhouse phone country selections may display only a flag and +1. Retention now
recognizes the explicit US flag together with that code; +1 alone or a Canadian
flag cannot establish United States. This also detects a later country change.

## Version 0.7.2 update

Greenhouse dropdowns with labels outside their select container no longer expose
anonymous validation inputs as extra questions. Education fields stay in one
entry, including when the portal removes those helper inputs after selection.
Separately labelled controls and ambiguous containers remain distinct.

The injected code version changes, so preserve unsaved entries and establish how
to restore the existing attachment before refreshing an application. Restart the
companion and reload the extension, then refresh only when recovery is ready.

## Version 0.7.1 update

Disability “No” covers present-tense choices only. Gender, ethnicity, and military
menus that require more detail ask for your explicit choice. Use **Load page
choices**, select an answer, then **Save this answer** to reuse it only for that
company and exact question. Existing page selections are not silently saved.

Employment alternatives come from the authorized full master-profile check;
“not currently employed” never becomes “never worked there”. Degree choices prefer
the saved qualification, approved equivalents, then the generic degree level.
Expected degrees cannot fill completed-qualification questions.

Open menus are inspected before search. School fills precede dependent fields;
helper inputs do not create extra education entries. Reordered entries, changed
schools, ambiguous replacements and concurrent edits stop the affected field.
Failures distinguish explicit detail needed, unavailable choices, changed pages,
and selections that were not retained. Preferences need no migration.

1. Restart the local companion if it is running.
2. Reload ApplyPilot at `chrome://extensions`.
3. Preserve unsaved entries, refresh the application tab, then reopen ApplyPilot.

## Version 0.7.0 update

Restart the local companion to load the diagnostic format, then reload ApplyPilot
at `chrome://extensions`. Preserve unsaved application entries before refreshing
the application tab. Reopen ApplyPilot and select the prepared resume. An old
injected script now gives a refresh instruction instead of silently remaining active.

This release opens React-style dropdowns with their expected mouse events, supports
Greenhouse's observed `select-shell` and `file-upload` containers, and waits for
associated menus and committed selections. Country choices include the explicit
US phone label “United States +1”. Phone punctuation changes are accepted only
when the digits match; country-code equivalence additionally needs a saved country.
Uploads are checked against a visible filename receipt and upload error/busy state,
including when the portal removes the original file input.

**Load page choices** opens a dropdown without choosing an answer. Enter an optional
search, load the real choices, then choose **Use once** or **Save this answer**.
Dropdowns with an existing proposal expose this under **Choose a different answer**.
Temporary search text is restored without replacing concurrent user edits. Your
answer fills on the next Autofill click and is checked against the current options.

An immediately associated “If Yes” explanation is not applicable only when its
parent has a committed No answer. Other ambiguous conditions remain unresolved.
Lever location widgets with a separate location token require choosing a suggestion
on the page; plain typed text is not reported as a completed place selection.

## Selection and recovery

Old progress could store every row as unchecked after a failure. The one-time
migration now selects eligible empty fields again while preserving saved answers
and existing page values. From this version onward, deliberate opt-outs are stored
separately and survive rescans and restarts. A failed fill never becomes an opt-out.

School dropdowns search only the saved institution and approved aliases, require
one exact compatible option, and remove only ApplyPilot's temporary search text on
failure. Independent degree/date fields can continue after a safely recovered
school search. Retention is checked again after the complete attempt. Current
preferences, full-profile question resolutions, company context and consent are
rechecked before filling. Newly revealed fields are rescanned and remain unselected,
including after reopening, until you select them.

Every discovered field receives an outcome, including preserved, deliberately
excluded, unanswered, manual, failed and invalidated fields. Reports include an
attempt ID, extension version and stage without answer values. See
[release notes](RELEASE_NOTES.md) for verification and rollback details.

## Apply to a job

1. **Your resume:** a selected resume for this exact posting is restored after validation. Otherwise choose **Prepare my resume**, or **Change** to select a saved resume. Use **Edit** to check the detected job details; enter the company if the page does not provide it.
2. Choose a saved resume or prepare one. It is ready immediately; **Preview** and **Compare with source evidence** are optional. Older packets without evidence/checksums stay in **Manage resumes** and cannot be used for autofill.
3. Click **Autofill this page** to fill the selected routine details. Existing page values are preserved unless you explicitly select replacement under **Your details**.
4. For written questions without a recorded answer, request **Draft answer** or **Draft unanswered questions**. Click Autofill to insert them; evidence is checked automatically, including after edits or restoration. A failed check leaves that answer unresolved while clear fields still fill.
5. Review any reported failures and **Needs your input** items. Download the PDF from **Change** or the preview if manual upload is needed. Complete unresolved questions, navigate, and submit yourself.

**Undo last fills** restores supported fields only when they still contain ApplyPilot's value. Remove files and restore custom dropdowns or checkbox groups manually. Employment entries match known company/role. A single saved school can populate an empty education section; ambiguous school entries require explicit mapping. ApplyPilot does not add rows or click Next.

## Saved details and progress

The gear button opens **Settings**. Save names, address components, US work authorization, separate current/future sponsorship answers, school/degree/major/month-year dates, and optional disclosures. These application details are separate from the master resume. Saved disclosure choices are selected automatically for Autofill. Unknown or incompatible options stay unresolved. School aliases and common question variants are supported; other countries and ambiguous wording require an explicit answer.

Settings also provides explicit cross-company relationship answers, exhaustive master-profile employment checks, LGBTQ+ identification, and separate recruitment/demographic data consent switches. These switches default off. Authorized personal-relationship questions use the saved No answer; questions about working for or with a company always check the full master profile in Python. Absence means No only after a successful exhaustive-list check. Missing profiles, ambiguous employer identities, qualified employment types without evidence, and combined questions stay unresolved. Exact company answers appear separately in Settings and never transfer to another employer or changed wording.

Only recognized, standalone recruitment-data or demographic-data processing consent can be checked automatically. Wording and authorization are rechecked at fill time, checked boxes are preserved, and retained state is verified. Accuracy certifications, signatures, background checks, marketing, mixed agreements, and submission remain manual. Date fields use their school or employer section; unclassified dates are not guessed. Multiple elements of a dropdown appear once, while separate experience dates retain their identities.

Use **Answer missing questions** to choose from the actual page options. **Use once** keeps the answer in the current panel session; **Save this answer** reuses the exact wording for the same company and checks compatibility with the current options. **Draft unanswered questions** handles text inputs and textareas, with automatic evidence checks before filling. Personal eligibility and disclosure facts are never inferred by AI.

**Recent fill results** persists for 30 days, including after reopening the panel. **Retry failed fields** rescans and selects only failed empty fields; click Autofill to retry. Existing values are preserved unless explicitly selected for replacement. **Copy diagnostic report** exports field metadata and outcome codes, without answer values, full HTML, resume contents, or URL query parameters.

Unfinished work, selected resumes, and pending jobs stay locally for **30 days**. Written answers restore for fresh automatic validation. Changed questions, pages, resume versions, or answer text are checked again before filling. **Continue preparation** resumes the same pending job after a connection failure without another AI request. Completed validated resumes are selected directly when their preparation finishes or is resumed. Edited job details also survive reopening. **Cancel preparation** prevents publication; **Dismiss preparation** clears a completed job from the panel while keeping any generated PDF in Change. A job interrupted by a backend restart reports an error and needs a new request. Cancellation cannot undo an AI request already running.

Settings also has progress deletion controls. These preserve PDFs and application history.

## Connection repair

Open **ApplyPilot.app** and click **Enable Chrome connection** (or **Repair Chrome connection**). Do this after moving the project or disabling access, then reload the extension. Keep the app beside the project files. **Launch ApplyPilot.command** opens the same setup guide and displays startup errors in Terminal.

The companion uses `http://127.0.0.1:8765`. A different project or an old server on that port is rejected. Stop the old server and reopen ApplyPilot. Startup diagnostics are in `.applypilot.log`.

**Disable all extension access** in setup revokes browser tokens and the native grant. Automatic reconnect cannot undo revocation. **Disconnect this browser** in Settings removes its credential and pauses automatic connection until you click **Connect automatically**. The advanced code-pairing option remains available for a manually started companion on another port; it is not needed for normal setup.

The connector registration lives at `~/Library/Application Support/Google/Chrome/NativeMessagingHosts/com.applypilot.companion.json`. It contains a fixed executable path and permits only this extension's stable ID. Moving the project requires repair. Installation is per macOS user, so the same extension in another Chrome profile for that user can also connect. This release targets macOS Google Chrome.

## Privacy and boundaries

Only HTTPS hosted Greenhouse and Lever pages are supported. Custom sites, embedded frames, unusual widgets, complete-history questions, legal attestations, credentials, mixed or unrecognized consent wording, incompatible disclosure options, and unknown facts may require manual completion. There is no CAPTCHA handling or application submission. Retained-value checks cannot guarantee a later employer-server save.

Permissions: `activeTab`, `scripting`, `storage`, `sidePanel`, `nativeMessaging`, and loopback access. Clicking the icon grants temporary access to the page. Filling shares selected information with that website. Gemini receives selected evidence and posting details only when you explicitly request drafting or resume preparation. API keys remain in Python.

The native process accepts only a versioned connection handshake from Chrome's exact allowed extension origin. It returns a credential through Chrome's native pipe, never a page URL. Credentials use trusted Chrome storage and a private local access file. The local grant stores the token to support reconnection; API authentication compares its hash. Review cookie/CSRF checks remain separate. Revocation is checked again after startup.

Private files are ignored by Git: `.extension_access.json`, `.application_answers.json`, `.applypilot_state.json`, `.applypilot_diagnostics.json`. No Chrome Sync is used. The extension does not update Gmail, the tracker, the master profile, or existing packets.

## Verification

```bash
Emails/.python/python/bin/python3 copilot.py --test-only
COPILOT_HTTP_TESTS=1 Emails/.python/python/bin/python3 -m unittest test_copilot.TestLocalReview.test_local_server_requires_session_and_rejects_cross_origin_writes
node extension/tests/core.test.cjs
node extension/tests/worker.test.cjs
node extension/tests/profile.test.cjs
Emails/.python/python/bin/python3 scripts/test_autofill_matrix.py
Emails/.python/python/bin/python3 scripts/test_extension_browser.py
node scripts/test_extension_loaded.cjs --skip-assets  # preserve production icons
node scripts/test_autofill_loaded.cjs greenhouse immediate
node scripts/test_autofill_loaded.cjs greenhouse delayed
node scripts/test_autofill_loaded.cjs greenhouse rerender
node scripts/test_autofill_loaded.cjs lever immediate
node scripts/test_autofill_loaded.cjs lever delayed
node scripts/test_autofill_loaded.cjs lever rerender
node scripts/test_autofill_loaded.cjs greenhouse challenge
```

Without Node on PATH, use `ELECTRON_RUN_AS_NODE=1 '/Applications/Visual Studio Code.app/Contents/MacOS/Code'` in place of `node`.

The loaded-extension test uses an isolated Chrome profile and temporary native registration. It verifies cold backend startup, automatic connection, actual toolbar permissions, panel messaging, selected resume review, uploads, partial rejection, a 32-second background job, panel/browser restarts, and revocation. Hosted URLs are intercepted before network access. Fixture AI never spends credits or submits applications. Browser/HTTP tests need permission to launch Chrome and bind loopback in a sandbox.

The expanded test uses a fixed 40-field acceptance matrix, independently checks actual form values, forces two failures, reopens the panel, then verifies selective recovery and privacy. See `tests/coverage_report.txt` for results and limits. The optional `scripts/smoke_application_answers.py` uses the configured Gemini service on three synthetic questions; it is intentionally excluded from offline regression runs.

## Brand assets

`icons/logo.svg` contains the document-and-forward-arrow mark; monochrome, wordmark, and PNG variants accompany it. The macOS launcher uses the same identity.

Chrome references: [native messaging](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging), [end-to-end extension testing](https://developer.chrome.com/docs/extensions/how-to/test/end-to-end-testing), [activeTab](https://developer.chrome.com/docs/extensions/develop/concepts/activeTab).
