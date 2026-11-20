# LinkedIn AI Agent — Remaining Coding Tasks

> Scope: Extend the EXISTING `linkedin-ai-agent` codebase. Do not rebuild completed features.
> Kiro: implement ONE task explicitly requested by the user, then STOP. Code only; no tests, debugging, browser/server execution, linting, terminal commands, or unrelated refactoring.
> Target: approximately 5–10 minutes per task; split a task if its actual scope is larger.
> All paths below are relative to the project root. Locate and reuse existing functions before editing. Do not invent selectors, APIs, or resume facts.

## User workflow (one run)
1. Use an existing authorized LinkedIn browser session and the uploaded resume.
2. Search remote jobs, posted in the last 24 hours, with Easy Apply.
3. Inspect jobs **one at a time on page 1**. Calculate resume/job match; threshold is **75%**.
4. If below threshold, dismiss using the UI's available X control (when supported), then continue. Skip already-applied or duplicate jobs.
5. For the first qualifying job, open Easy Apply, fill only verified information, and answer questions from resume or saved confirmed answers.
6. If an answer is unknown, pause and ask the user. Save their confirmed Q&A for later reuse.
7. Require explicit user approval before final submission; submit at most **one** application per run, save status, and stop. If no qualifying job on page 1, stop without submitting.
8. Do not bypass CAPTCHA, rate limits, platform restrictions, or approval requirements.

## Tasks

- [ ] **01 — Fix job-card detection**
  - Primary file: `backend/app/agents/browser_agent.py`.
  - Reuse the existing extraction method; detect all currently rendered result cards rather than just the selected detail panel.
  - Use stable, verified DOM attributes and preserve existing output shape; deduplicate by job ID.
  - No scrolling, pagination, filters, or application actions.
  - Done when code can return a collection of distinct result cards without including the detail panel.

- [ ] **02 — Search jobs by keywords**
  - Primary file: `backend/app/agents/browser_agent.py`.
  - Extend existing search/navigation logic to accept job keywords derived from the user's stated preferences or resume.
  - Preserve the logged-in persistent browser profile and existing search behavior.
  - Do not add filters or scan jobs in this task.

- [ ] **03 — Apply last-24-hours filter**
  - Primary file: `backend/app/agents/browser_agent.py`.
  - Add a small reusable step to apply LinkedIn's available date-posted filter for the past 24 hours.
  - Detect absent/changed UI controls and return a clear error; do not silently assume success.
  - Do not implement other filters.

- [ ] **04 — Apply Easy Apply and Remote filters**
  - Primary file: `backend/app/agents/browser_agent.py`.
  - Extend the existing filter flow to select Easy Apply and Remote using supported UI controls.
  - Verify filter state from the page when possible; fail clearly if controls are unavailable.
  - Do not scan or apply to jobs.

- [ ] **05 — Iterate first-page jobs one at a time**
  - Primary file: `backend/app/agents/browser_agent.py`.
  - Reuse the existing card collection; select one job at a time in page 1 order.
  - Skip duplicates/already-applied entries; do not navigate to page 2.
  - Preserve a stable job ID/URL for each candidate.

- [ ] **06 — Read selected job details**
  - Primary file: `backend/app/agents/browser_agent.py`.
  - Extract title, company, location, job ID/URL, full description, and available Easy Apply indicator.
  - Keep existing return schema where possible; report missing fields without fabricated values.
  - Do not implement scoring or submission.

- [ ] **07 — Calculate match score**
  - Reuse the EXISTING resume parsing and AI/job matching service (inspect its actual file before editing).
  - Add only the minimal integration needed to score a selected job against the uploaded resume.
  - Return score (0–100) and a short reason using the existing matching format.
  - Do not create a second matching algorithm or change the scoring threshold globally.

- [ ] **08 — Skip or dismiss jobs below 75%**
  - Primary file: `backend/app/agents/browser_agent.py`; reuse the existing orchestration if present.
  - For each scored job: if score <75%, use the available X/dismiss action when supported, otherwise mark skipped and continue.
  - Skip duplicates and already-applied jobs. Stop scanning at the first score >=75%.
  - Stay on page 1; never dismiss a qualifying job automatically.

- [ ] **09 — Open Easy Apply for first qualifying job**
  - Primary file: `backend/app/agents/browser_agent.py`.
  - Open the Easy Apply dialog for the first qualifying, not-yet-applied job.
  - Handle missing/unavailable Easy Apply by recording a skip reason and continuing within page 1.
  - Do not fill, submit, or bypass any platform restriction.

- [ ] **10 — Fill verified application details**
  - Reuse the existing resume/profile services and browser form helpers.
  - Fill only supported contact, resume, experience, and other fields with verified values.
  - Leave unknown or conflicting values unanswered for user confirmation.
  - Do not guess personal data or submit the form.

- [ ] **11 — Screening questions and reusable Q&A**
  - Reuse existing database models/services if present; add minimal persistence only if needed.
  - Answer from resume and previously user-confirmed answers; keep question text, answer, and provenance.
  - When unknown, pause and expose the question to the user; save only the answer they confirm.
  - Never automatically choose positive answers without evidence; no submission.

- [ ] **12 — User-approved submit, save status, stop**
  - Reuse existing application status persistence and orchestration where available.
  - Require an explicit per-application approval before the final submit action.
  - Submit no more than one application per run; record applied/skipped/failed status and job ID to prevent duplicates.
  - Stop after success, user denial, or reaching the end of page 1; handle recoverable failures without duplicate submissions.

## Task execution rule
When the user says **"Implement task NN"**, implement **only that numbered task**. Inspect only directly relevant files, make minimal code changes, and respond with exact changed paths, a brief summary, and blockers (max 80 words). Do not mark a checkbox complete until the user confirms the task is finished. No tests or debugging by Kiro.

## Out of scope for this first version
- Multi-page scanning, bulk applications, unattended scheduling, anti-bot evasion, new frameworks, broad architecture rewrites, or extra dashboards.
