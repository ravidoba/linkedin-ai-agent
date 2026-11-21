"""
Single-application workflow orchestrator.

Wires together the existing components:
  - iter_first_page_jobs  Ã¢â‚¬â€ sequential first-page card scan
  - score_job             Ã¢â‚¬â€ resume/job matching
  - should_dismiss        Ã¢â‚¬â€ score-based eligibility decision
  - dismiss_job           Ã¢â‚¬â€ Playwright dismiss control
  - open_easy_apply       Ã¢â‚¬â€ Playwright Easy Apply opener
  - fill_easy_apply_fields Ã¢â‚¬â€ Playwright basic field filler
  - handle_screening_questions Ã¢â‚¬â€ modal Q&A extraction + fill

Database access uses the existing AsyncSession pattern.

The workflow state is returned as a dict so the caller (API route or CLI)
can present pending questions to the user and resume the run.

Browser: one shared persistent Playwright context is reused across runs
(preserving LinkedIn login cookies) and all runs are serialised by a lock so
the profile directory is never opened twice.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
import traceback
from collections import deque
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import AsyncSessionLocal
from app.models.agent_run_log import AgentRunLog
from app.services.job_requirements_service import get_job_requirements
from app.services.profile_matching_service import match_job_to_profile
from app.services.resume_profile_service import get_or_build_profile

from app.agents.browser_agent import (
    MATCH_THRESHOLD,
    PROFILE_DIR,
    DEFAULT_EASY_APPLY,
    DEFAULT_REMOTE_ONLY,
    DATE_POSTED_24H,
    SEARCH_KEYWORDS,
    dismiss_job,
    fill_easy_apply_fields,
    find_unanswered_required,
    handle_screening_questions,
    SearchError,
    iter_search_page_jobs,
    open_easy_apply,
    title_matches_role,
    resume_file_path,
    cursor_click,
    install_cursor,
    _RESUME_MODAL_SEL,
    _resolve_option,
    _YES_VALUES,
    _NO_VALUES,
    score_job,
    should_dismiss,
    _build_browser_search_url,
)
from app.models.application import Application
from app.models.job import Job
from app.models.resume import Resume
from app.models.user import User
from app.services.screening_service import (
    get_saved_answer,
    normalize_question,
    save_answer,
    save_screening_answer,
)


# ---------------------------------------------------------------------------
# Shared browser session
# ---------------------------------------------------------------------------

_pw: Any = None
_context: Any = None
_browser_owner_id: int | None = None
_lock = asyncio.Lock()
# user.id -> state of an application paused for user input / approval.
_paused: dict[int, dict[str, Any]] = {}

# In-memory per-user progress stream. Single backend worker only.
_activity: dict[int, deque[dict[str, Any]]] = {}
_activity_sequence: dict[int, int] = {}
# user.id -> (current job number, total jobs to process) of the running apply scan.
_job_progress: dict[int, tuple[int, int]] = {}
# user.id -> job dict currently being processed, so an unexpected failure can be
# reported as that job's "Failed" result.
_current_job: dict[int, dict[str, Any]] = {}


def _friendly_error(exc: Exception) -> tuple[str, str]:
    """Plain-language message and error_type for an unexpected exception."""
    name, text = type(exc).__name__, str(exc).lower()
    if "closed" in text and ("target" in name.lower() or "browser" in text or "context" in text):
        return "The agent browser was closed, so the run stopped. Nothing more was submitted.", "browser_closed"
    if "timeout" in name.lower() or "timeout" in text:
        return "LinkedIn took too long to respond, so the run stopped. Nothing more was submitted.", "navigation_timeout"
    return (
        f"An unexpected error stopped the run ({name}). Nothing more was submitted. "
        "The server log has the details.",
        "unexpected",
    )
_manual_owner_id: int | None = None


def emit_activity(user_id: int, kind: str, status: str, message: str, job: dict | None = None, score: int | float | None = None, step: str | None = None, result: str | None = None) -> None:
    seq = _activity_sequence.get(user_id, 0) + 1
    _activity_sequence[user_id] = seq
    event: dict[str, Any] = {"id": seq, "type": kind, "status": status, "message": message, "timestamp": int(time.time() * 1000)}
    if user_id in _job_progress:
        current, total = _job_progress[user_id]
        event["progress"] = {"current": current, "total": total}
    if job:
        event["job"] = {"jobId": str(job.get("job_id", "")), "title": job.get("title", ""), "company": job.get("company", ""), "location": job.get("location", ""), "url": job.get("url", "")}
    if isinstance(score, (int, float)):
        event["matchScore"] = score
    if step:
        event["step"] = step
    if result:
        event["result"] = result  # final outcome of this job: Applied | Skipped | Failed
    _activity.setdefault(user_id, deque(maxlen=300)).append(event)
    run_id = active_run_ids.get(user_id)
    if run_id is not None:
        try:
            task = asyncio.get_running_loop().create_task(_save_run_log(run_id, event))
        except RuntimeError:  # no event loop (e.g. CLI use): nothing to persist to
            return
        _log_tasks.add(task)
        task.add_done_callback(_log_tasks.discard)


# user.id -> AgentRun.id of the Start-button run in progress (set by the /ai/agent route).
active_run_ids: dict[int, int] = {}
# Strong references so pending log writes are not garbage-collected mid-flight.
_log_tasks: set[asyncio.Task] = set()
# user.id values whose running scan should stop before its next job (Stop button).
_stop_requested: set[int] = set()


def stop_run(user_id: int) -> str:
    """
    Stop the user's run safely. A paused application is discarded (nothing is
    submitted) and "stopped" is returned; a running scan is asked to stop before
    its next job and "stopping" is returned.
    """
    if _paused.pop(user_id, None) is not None:
        _job_progress.pop(user_id, None)
        emit_activity(user_id, "searching_jobs", "completed", "Stopped by you. The paused application was not submitted.")
        return "stopped"
    _stop_requested.add(user_id)
    emit_activity(user_id, "searching_jobs", "running", "Stopping after the current job...")
    return "stopping"


async def _save_run_log(run_id: int, event: dict[str, Any]) -> None:
    """Persist one activity event of a run; a failed write never stops the workflow."""
    job = event.get("job") or {}
    progress = event.get("progress") or {}
    try:
        async with AsyncSessionLocal() as session:
            session.add(AgentRunLog(
                run_id=run_id,
                seq=event["id"],
                type=event["type"],
                status=event["status"],
                message=event.get("message", ""),
                step=event.get("step"),
                result=event.get("result"),
                job_number=progress.get("current"),
                job_total=progress.get("total"),
                linkedin_job_id=job.get("jobId") or None,
                job_title=job.get("title") or None,
                job_company=job.get("company") or None,
            ))
            await session.commit()
    except Exception as exc:
        print(f"[activity] run {run_id}: could not save log event {event.get('id')}: {exc}", flush=True)



async def close_browser_session() -> None:
    """Close the shared browser context and Playwright driver (idempotent)."""
    global _pw, _context, _browser_owner_id, _manual_owner_id
    context, pw, _context, _pw = _context, _pw, None, None
    _browser_owner_id = None
    _manual_owner_id = None
    _paused.clear()
    if context is not None:
        try:
            await context.close()
        except Exception:
            pass
    if pw is not None:
        try:
            await pw.stop()
        except Exception:
            pass


async def _get_context() -> Any:
    """Return the shared persistent context, launching it only when needed."""
    global _pw, _context
    if _context is not None:
        try:
            await _context.cookies("https://www.linkedin.com")
            return _context
        except Exception:
            await close_browser_session()

    if "DISPLAY" not in os.environ:
        os.environ["DISPLAY"] = ":0"
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    from playwright.async_api import async_playwright

    _pw = await async_playwright().start()
    try:
        _context = await _pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
            ignore_default_args=["--enable-automation"],
        )
    except Exception:
        await close_browser_session()
        raise
    await install_cursor(_context)  # visible cursor overlay on every page and navigation
    return _context


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def _get_latest_resume(db: AsyncSession, user: User) -> Resume | None:
    """Return the most recently uploaded resume for the user."""
    return await db.scalar(
        select(Resume)
        .where(Resume.user_id == user.id)
        .order_by(Resume.created_at.desc(), Resume.id.desc())
        .limit(1)
    )


async def _upsert_job(db: AsyncSession, job: dict) -> Job:
    """Insert or return existing Job row for a scanned job dict."""
    existing = await db.scalar(
        select(Job).where(Job.linkedin_job_id == job["job_id"])
    )
    if existing:
        return existing
    record = Job(
        linkedin_job_id=job["job_id"],
        title=job.get("title", ""),
        company=job.get("company", ""),
        location=job.get("location"),
        description=job.get("description"),
        job_url=job.get("url"),
        status="scanned",
    )
    db.add(record)
    await db.flush()   # assign PK without committing yet
    return record


async def _save_application(
    db: AsyncSession,
    user: User,
    job: Job,
    resume: Resume | None,
    status: str,
) -> Application:
    """
    Persist the outcome of a submission attempt and commit. One row per user and job:
    an existing row is updated, and a confirmed "applied" row is never downgraded.
    Statuses: "applied" (confirmed), "submit_uncertain", "submit_failed".
    """
    app = await db.scalar(
        select(Application)
        .where(Application.user_id == user.id, Application.job_id == job.id)
        .order_by(Application.id)
        .limit(1)
    )
    if app is None:
        app = Application(
            user_id=user.id,
            job_id=job.id,
            resume_id=resume.id if resume else None,
            status=status,
        )
        db.add(app)
    elif app.status != "applied":
        app.status = status
        app.resume_id = resume.id if resume else app.resume_id
    await db.commit()
    return app


# Outcomes that must never be submitted again automatically.
_BLOCKING_STATUSES = ("applied", "submit_uncertain")


async def _already_applied(db: AsyncSession, user: User, job: Job) -> bool:
    """True if this job was applied to, or its submission outcome is uncertain."""
    result = await db.scalar(
        select(Application).where(
            Application.user_id == user.id,
            Application.job_id == job.id,
            Application.status.in_(_BLOCKING_STATUSES),
        ).limit(1)
    )
    return result is not None


# ---------------------------------------------------------------------------
# Workflow result helpers
# ---------------------------------------------------------------------------

def _result(
    status: str,
    *,
    job: dict | None = None,
    pending_questions: list | None = None,
    filled: list | None = None,
    missing: list | None = None,
    skipped_jobs: list | None = None,
    message: str = "",
    application_id: int | None = None,
    jobs: list | None = None,
    error_type: str | None = None,
    summary: dict | None = None,
) -> dict:
    return {
        # Apply scans only: {"scanned", "applied", "skipped", "failed"} counts.
        "summary": summary,
        "status": status,          # "applied" | "needs_input" | "search_results" |
                                   # "no_match" | "awaiting_approval" | "error"
        "message": message,
        # Set only for status "error": auth_expired | access_restricted |
        # navigation_timeout | search_failed
        "error_type": error_type,
        "job": job,
        "jobs": jobs or [],
        "pending_questions": pending_questions or [],
        "filled_fields": filled or [],
        "missing_fields": missing or [],
        "skipped_jobs": skipped_jobs or [],
        "application_id": application_id,
    }


async def _screening_pending(page: Any, screening: dict, fill_result: dict) -> list[dict]:
    """
    Required screening questions that are still unanswered or invalid on this step.

    The page is scanned directly (not only the extracted questions), so a required
    control the extractor missed also blocks progress. Contact controls are excluded
    (handled separately). Extracted entries are preferred when available so the
    question text matches the saved-answer key.
    """
    contact_ids = set(fill_result.get("contact_control_ids", []))
    extracted = {
        q["control_id"]: q
        for q in screening.get("pending_questions", [])
        if q.get("control_id")
    }
    return [
        extracted.get(q["control_id"], q)
        for q in await find_unanswered_required(page)
        if q["control_id"] not in contact_ids
    ]


def _validate_answer(asked: dict, answer: str) -> str | None:
    """
    Check a user's answer against the question that was asked. Returns the value to
    save (the exact option label for option controls) or None when it is not valid.
    """
    options = asked.get("options") or []
    if asked.get("input_type") in ("select", "radio", "checkbox"):
        if not options:
            return None
        resolved = _resolve_option(answer, options)
        if resolved is not None:
            return resolved
        if asked.get("input_type") == "checkbox":  # single Yes/No checkbox
            low = answer.strip().lower()
            if low in _YES_VALUES:
                return "Yes"
            if low in _NO_VALUES:
                return "No"
        return None
    return answer.strip() or None


# A cheap fingerprint of the current Easy Apply step (heading, progress, controls),
# used to confirm that Next/Review really moved to a new step.
_STEP_SIGNATURE_JS = """
() => {
  const modal = document.querySelector('div[data-test-modal]')
    || document.querySelector('dialog[open]')
    || document.querySelector('[role="dialog"][aria-label*="Easy Apply"]')
    || document.querySelector('[role="dialog"]');
  if (!modal) return '';
  const heading = modal.querySelector('h1, h2, h3');
  const bar = modal.querySelector('progress, [role="progressbar"]');
  const controls = Array.from(modal.querySelectorAll('input, select, textarea, fieldset, button'))
    .map(e => e.id || e.getAttribute('aria-label') || (e.textContent || '').trim().slice(0, 30))
    .join('|');
  return [
    heading ? heading.textContent.trim() : '',
    bar ? (bar.getAttribute('value') || bar.getAttribute('aria-valuenow') || '') : '',
    controls,
  ].join('#');
}
"""


# Title of the open Easy Apply step (e.g. "Contact info"). The dialog's own
# title "Apply to <company>" is never used.
_STEP_HEADING_JS = """
() => {
  const text = e => (e.textContent || '').replace(/\\s+/g, ' ').trim();
  const shown = e => e.getClientRects().length > 0
    && !/visually-hidden|sr-only|a11y-text/.test(e.className || '');
  // The Easy Apply dialog is the one titled "Apply to <company>"; other dialogs
  // on the page (e.g. notifications) must not be read.
  const dialogs = Array.from(document.querySelectorAll(
    '[role="dialog"][aria-label*="Easy Apply"], div[data-test-modal], dialog[open], [role="dialog"]'));
  const easy = dialogs.find(d => Array.from(d.querySelectorAll('h1, h2, h3'))
      .some(h => /^apply to\\b/i.test(text(h))))
    || dialogs.find(d => /easy apply/i.test(d.getAttribute('aria-label') || ''));
  if (!easy) return '';
  // 1. A visible element whose text is (or starts with) a known step name,
  //    whatever its tag (LinkedIn does not always use <h3> for the step title).
  const KNOWN = /^(contact info|resume|additional questions|work experience|education|review your application|home address|voluntary self identification|work authorization|screening questions)\\b/i;
  for (const e of easy.querySelectorAll('h1, h2, h3, h4, h5, h6, [role="heading"], span, p, div')) {
    const t = text(e);
    if (e.children.length <= 1 && t.length <= 60 && KNOWN.test(t) && shown(e)) return t;
  }
  // 2. Any other visible heading except the dialog title "Apply to <company>".
  for (const e of easy.querySelectorAll('h3, h4, [role="heading"], h2')) {
    const t = text(e);
    if (t && shown(e) && !/^apply to\\b/i.test(t) && !/notification/i.test(t)) return t;
  }
  return '';
}
"""
_STEP_LABELS = (
    ("contact", "Contact info"),
    ("resume", "Resume"),
    ("work experience", "Work experience"),
    ("education", "Education"),
    ("review", "Review"),
    ("question", "Additional questions"),
    ("additional", "Additional questions"),
)


async def _form_step_label(page: Any) -> str:
    """Readable name of the current Easy Apply step, e.g. "Contact info"."""
    try:
        heading = (await page.evaluate(_STEP_HEADING_JS) or "").strip()
    except Exception:
        heading = ""
    lowered = heading.lower()
    for needle, label in _STEP_LABELS:
        if needle in lowered:
            return label
    return heading[:60] or "Application form"


async def _step_signature(page: Any) -> str:
    try:
        return await page.evaluate(_STEP_SIGNATURE_JS)
    except Exception:
        return ""


async def _wait_step_change(page: Any, before: str) -> bool:
    """Wait (bounded) until the step differs from `before`; False if it never does."""
    for _ in range(8):
        await page.wait_for_timeout(1_000)
        if await _step_signature(page) != before:
            return True
    return False


def _contact_first(required: list[str], other: list[str]) -> list[str]:
    return list(required) + [m for m in other if m not in required]


_SUBMIT_OK_RE = re.compile(r"application (was )?sent|application submitted", re.I)
_SUBMIT_ERROR_RE = re.compile(
    r"something went wrong|(couldn.t|could not|unable to) (submit|send)|"
    r"error submitting|try again later",
    re.I,
)


async def _await_submission(page: Any) -> tuple[str, str]:
    """
    After Submit was clicked, wait (bounded) inside the Easy Apply dialog for LinkedIn's
    success text. Returns ("confirmed", ""), ("error", detail) when the dialog shows an
    error or invalid fields, or ("uncertain", ""). A closed dialog alone is not success.
    """
    dialog = page.locator(_RESUME_MODAL_SEL)
    for _ in range(15):
        try:
            if await dialog.filter(has_text=_SUBMIT_OK_RE).first.is_visible():
                return "confirmed", ""
            if await dialog.filter(has_text=_SUBMIT_ERROR_RE).first.is_visible():
                return "error", "error message shown by LinkedIn"
            if await dialog.locator('[aria-invalid="true"]').count() > 0:
                return "error", "fields are marked invalid"
        except Exception:
            pass
        await page.wait_for_timeout(1_000)
    return "uncertain", ""


async def _dismiss_confirmation(page: Any) -> bool:
    """
    Close LinkedIn's post-submit dialog (Done / Not now / Dismiss) so the next job card
    can be clicked. Buttons are looked up inside the Easy Apply dialog only. Returns
    True when no dialog remains open.
    """
    dialog = page.locator(_RESUME_MODAL_SEL).first
    finish = (
        dialog.get_by_role("button", name="Done", exact=True)
        .or_(dialog.get_by_role("button", name="Not now", exact=True))
    ).first
    dismiss = (
        dialog.get_by_role("button", name="Dismiss", exact=True)
        .or_(dialog.locator('[aria-label="Dismiss"]'))
    ).first
    try:
        for _ in range(3):
            if not await dialog.is_visible():
                return True
            if await finish.is_visible():
                await cursor_click(finish, timeout=3_000)
            elif await dismiss.is_visible():
                await cursor_click(dismiss, timeout=3_000)
                await _confirm_discard(page)  # unfinished form: Save/Discard prompt
            else:
                await page.keyboard.press("Escape")
            await page.wait_for_timeout(1_000)
        return not await dialog.is_visible()
    except Exception:
        return False


async def _confirm_discard(page: Any) -> None:
    """
    After Dismiss on an unfinished application LinkedIn asks Save / Discard. Click
    Discard only (never Save). The prompt is a separate dialog, so every dialog is
    searched; if no prompt appears within a few seconds nothing is clicked.
    """
    discard = page.locator(_RESUME_MODAL_SEL).get_by_role(
        "button", name="Discard", exact=True
    ).first
    try:
        await discard.wait_for(state="visible", timeout=3_000)
    except Exception:
        return
    await cursor_click(discard, timeout=3_000)


_CONTACT_FIELDS = ("first_name", "last_name", "email", "phone", "phone_country", "city")


def _contact_key(user: User, field: str) -> str:
    # Stored in the existing screening_answers table; the prefix keeps it per-user
    # and prevents it from matching any screening question label.
    return f"contact:{user.id}:{field}"


async def _saved_contact(db: AsyncSession, user: User) -> dict:
    """User-confirmed contact values saved by earlier runs."""
    saved: dict = {}
    for field in _CONTACT_FIELDS:
        row = await get_saved_answer(db, _contact_key(user, field))
        if row and row.answer_text:
            saved[field] = row.answer_text
    return saved


async def _save_contact(db: AsyncSession, user: User, data: dict | None) -> None:
    """Persist contact values the user supplied so later applications reuse them."""
    for field in _CONTACT_FIELDS:
        value = str((data or {}).get(field) or "").strip()
        if value:
            await save_answer(
                db, question_text=_contact_key(user, field), answer_text=value,
                input_type="contact", provenance="user",
            )


def _default_applicant_data(
    user: User, overrides: dict | None, saved: dict | None = None
) -> dict:
    """
    Account fields < saved user-confirmed contact values < supplied data.
    "_override_fields" lists the user-verified keys that may replace a wrong
    prefilled value; account-derived values only fill empty controls.
    """
    parts = (user.full_name or "").split()
    data: dict = {"email": user.email}
    if parts:
        data["first_name"] = parts[0]
        if len(parts) > 1:
            data["last_name"] = " ".join(parts[1:])
    verified = {k: v for k, v in (saved or {}).items() if v}
    verified.update({k: v for k, v in (overrides or {}).items() if v})
    data.update(verified)
    data["_override_fields"] = sorted(k for k in verified if k in _CONTACT_FIELDS)
    return data


# ---------------------------------------------------------------------------
# Application form handling (shared by fresh runs and resumed runs)
# ---------------------------------------------------------------------------

async def _run_form(
    db: AsyncSession,
    user: User,
    page: Any,
    job_row: Job,
    scored: dict,
    app_data: dict,
    resume: Resume | None,
    resume_text: str,
    user_approved: bool,
    skipped_jobs: list[str],
    profile: dict | None = None,
) -> dict:
    """Fill the open Easy Apply modal, pause for input/approval, or submit."""

    def _pause(status: str, message: str, qs: list, filled: list, missing: list) -> dict:
        _paused[user.id] = {
            "page": page,
            "job_db_id": job_row.id,
            "scored": scored,
            "app_data": app_data,
            "resume_id": resume.id if resume else None,
            "user_approved": user_approved,
            "resume_ok": resume_ok,  # resume attachment already verified for this application
            "pending": qs,  # questions asked, so the user's answers can be validated
        }
        return _result(
            status,
            job=scored,
            pending_questions=qs,
            filled=filled,
            missing=missing,
            skipped_jobs=skipped_jobs,
            message=message,
        )

    def _fail(message: str, error_type: str | None = None) -> dict:
        _paused.pop(user.id, None)
        return _result(
            "error", job=scored, skipped_jobs=skipped_jobs, message=message,
            error_type=error_type,
        )

    async def _record_unconfirmed(status: str, message: str) -> dict:
        """Store an attempted but unconfirmed submission, then stop the run."""
        job_row.status = status
        try:
            await _save_application(db, user, job_row, resume, status)
        except Exception:
            await db.rollback()
        return _fail(message, error_type=status)

    # A paused state still present here belongs to this same application.
    resume_ok = bool((_paused.get(user.id) or {}).get("resume_ok"))
    wants_resume = bool(app_data.get("resume_path"))
    resume_failed = (
        "The selected resume could not be attached to the application "
        "(not silently replaced). Nothing was submitted."
    )

    step_label = await _form_step_label(page)
    emit_activity(user.id, "filling_fields", "running", f"Step: {step_label}", scored, step=step_label)
    fill_result = await fill_easy_apply_fields(page, app_data)
    if fill_result.get("resume") == "failed":
        return _fail(resume_failed)
    resume_ok = resume_ok or fill_result.get("resume") in ("attached", "kept")
    screening = await handle_screening_questions(page, resume_text, db, user.id, profile)
    pending_qs = await _screening_pending(page, screening, fill_result)
    contact_missing = fill_result.get("required_missing", [])

    # Never guess: unresolved required questions / contact fields go back to the user.
    if pending_qs or contact_missing:
        return _pause(
            "needs_input",
            "Required information is needed before the application can continue "
            "(contact fields are returned in missing_fields). Nothing was submitted.",
            pending_qs,
            fill_result.get("filled", []),
            _contact_first(contact_missing, fill_result.get("missing", [])),
        )

    # --- Walk the form with Next/Review; Submit is clicked only when user_approved.
    # Without approval the run pauses on the page that shows Submit (the Review
    # page), so the user approves the finished application. ---
    # Controls are looked up inside the Easy Apply modal only, so buttons of the page
    # behind it (e.g. result pagination "Next") are never clicked. Next/Review use
    # LinkedIn's aria-labels or the exact button text.
    modal_loc = page.locator(_RESUME_MODAL_SEL).first
    submit_loc = modal_loc.locator(
        '[aria-label="Submit application"],'
        'button:has-text("Submit application")'
    ).first
    # Accessible-role matching (exact name) works when LinkedIn wraps the label in a
    # nested element; the aria-label forms are kept as alternatives.
    next_loc = (
        modal_loc.get_by_role("button", name="Next", exact=True)
        .or_(modal_loc.get_by_role("button", name="Review", exact=True))
        .or_(modal_loc.locator(
            '[aria-label="Continue to next step"], [aria-label="Review your application"]'
        ))
    ).first
    submitted = False
    click_attempted = False
    try:
        for _ in range(10):
            if await submit_loc.is_visible():
                if wants_resume and not resume_ok:
                    return _fail(
                        "The resume could not be verified as attached to the "
                        "application. Nothing was submitted."
                    )
                if not await submit_loc.is_enabled():
                    return _fail(
                        "Submit is disabled: LinkedIn reports the form is incomplete. "
                        "Nothing was submitted."
                    )
                if not user_approved:
                    return _pause(
                        "awaiting_approval",
                        "The application is complete and on the Review page. "
                        "Approve to submit.",
                        [],
                        fill_result.get("filled", []),
                        [],
                    )
                click_attempted = True
                await cursor_click(submit_loc)
                submitted = True  # one click only; confirmation is checked below
                break
            if not await next_loc.is_visible():
                break
            if not await next_loc.is_enabled():
                return _fail(
                    "Next/Review is disabled: LinkedIn reports the step is incomplete. "
                    "Nothing was submitted."
                )
            before = await _step_signature(page)
            await cursor_click(next_loc)
            if not await _wait_step_change(page, before):
                return _fail(
                    "The form did not advance after Next/Review (LinkedIn may be showing "
                    "a validation error). Nothing was submitted."
                )
            step_label = await _form_step_label(page)
            emit_activity(user.id, "filling_fields", "running", f"Step: {step_label}", scored, step=step_label)
            step_fill = await fill_easy_apply_fields(page, app_data)
            if step_fill.get("resume") == "failed":
                return _fail(resume_failed)
            resume_ok = resume_ok or step_fill.get("resume") in ("attached", "kept")
            step_scr = await handle_screening_questions(page, resume_text, db, user.id, profile)
            step_qs = await _screening_pending(page, step_scr, step_fill)
            step_contact = step_fill.get("required_missing", [])
            if step_qs or step_contact:
                return _pause(
                    "needs_input",
                    "Required information is unavailable; user input needed. "
                    "Nothing was submitted.",
                    step_qs,
                    step_fill.get("filled", []),
                    _contact_first(step_contact, step_fill.get("missing", [])),
                )
    except Exception as exc:
        if click_attempted:
            # The click may have gone through: uncertain, never retried.
            return await _record_unconfirmed(
                "submit_uncertain",
                f"Submit step failed after Submit was clicked ({exc}); the application "
                "may or may not have been sent. It will not be retried; check LinkedIn.",
            )
        return _fail(f"Submit step failed: {exc}")

    if not submitted:
        return _fail(
            "The Easy Apply form showed no Next, Review or Submit button, so it could not "
            "continue (LinkedIn may have changed the form). Nothing was submitted."
        )

    # --- Verify LinkedIn's actual submission confirmation (never retried). ---
    outcome, detail = await _await_submission(page)
    if outcome == "error":
        return await _record_unconfirmed(
            "submit_failed",
            f"LinkedIn reported a problem after Submit ({detail}). The application was "
            "not confirmed. Submit will not be retried automatically.",
        )
    if outcome != "confirmed":
        return await _record_unconfirmed(
            "submit_uncertain",
            "Submit was clicked but LinkedIn's confirmation was not seen, so the "
            "application may or may not have been sent. It is recorded as uncertain "
            "and Submit will not be retried; check LinkedIn.",
        )

    # Confirmed by LinkedIn: record it. A database failure must not hide the fact
    # that the application was sent.
    job_row.status = "applied"
    note = ""
    application_id: int | None = None
    try:
        application_id = (await _save_application(db, user, job_row, resume, "applied")).id
    except Exception:
        await db.rollback()
        note = " It could not be saved to the database; do not submit this job again."
    _paused.pop(user.id, None)
    return _result(
        "applied",
        job=scored,
        skipped_jobs=skipped_jobs,
        message="Application submitted successfully." + note,
        application_id=application_id,
    )


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

async def run_apply_workflow(
    db: AsyncSession,
    user: User,
    *,
    keywords: str = SEARCH_KEYWORDS,
    date_posted: str = DATE_POSTED_24H,
    easy_apply: bool = DEFAULT_EASY_APPLY,
    remote_only: bool = DEFAULT_REMOTE_ONLY,
    threshold: int = MATCH_THRESHOLD,
    applicant_data: dict | None = None,
    confirmed_answers: list[dict] | None = None,
    user_approved: bool = False,
    resume_path: str = "",
    resume_id: int | None = None,
    intent: str = "apply",
    max_results: int = 10,
    resume_paused: bool = False,
) -> dict[str, Any]:
    """
    Run the single-application workflow.

    intent        : "search" (list jobs only), "match" (list jobs scoring at or
                    above threshold) or "apply". Only "apply" opens Easy Apply.
    max_results   : cap on jobs returned for "search"/"match".
    resume_paused : continue the application paused for this user (same page
                    and job) instead of starting a new search.

    Status values:
      "search_results"     Ã¢â‚¬â€ search/match intent; jobs returned, nothing opened
      "no_match"           Ã¢â‚¬â€ page 1 exhausted, no qualifying job found
      "needs_input"        Ã¢â‚¬â€ paused; pending_questions/missing_fields returned
      "awaiting_approval"  Ã¢â‚¬â€ form ready; waiting for user_approved=True
      "applied"            Ã¢â‚¬â€ submitted and confirmed by LinkedIn
      "error"              Ã¢â‚¬â€ unrecoverable failure
    """
    if _manual_owner_id == user.id:
        return _result("error", message="Manual browser control is active. Return control to the agent first.")
    if not resume_paused:
        _job_progress.pop(user.id, None)  # a new run starts without job progress
        _current_job.pop(user.id, None)
        _stop_requested.discard(user.id)  # a Stop from an earlier run does not carry over
    emit_activity(user.id, "searching_jobs", "running", f"Starting {intent} workflow: {keywords}")
    async with _lock:
        try:
            result = await _run_locked(
            db, user,
            keywords=keywords, date_posted=date_posted, easy_apply=easy_apply,
            remote_only=remote_only, threshold=threshold,
            applicant_data=applicant_data, confirmed_answers=confirmed_answers,
            user_approved=user_approved, resume_path=resume_path,
            resume_id=resume_id, intent=intent, max_results=max_results,
            resume_paused=resume_paused,
            )
            status = result.get("status", "")
            emit_activity(user.id, "error" if status == "error" else "searching_jobs", "failed" if status == "error" else "completed", str(result.get("message", status))[:500])
            return result
        except Exception as exc:
            # Unexpected failure (browser closed, LinkedIn changed, bug): never leak a
            # raw exception to the user. Full details go to the server log.
            traceback.print_exc()
            message, error_type = _friendly_error(exc)
            try:
                await db.rollback()  # the session may be mid-transaction
            except Exception:
                pass
            if error_type == "browser_closed":
                _paused.pop(user.id, None)
                await close_browser_session()  # the next run opens a fresh browser
            job = _current_job.get(user.id)
            if job is not None:
                emit_activity(user.id, "error", "failed", message, job, result="Failed")
            else:
                emit_activity(user.id, "error", "failed", message)
            return _result("error", message=message, error_type=error_type)


async def _run_locked(
    db: AsyncSession,
    user: User,
    *,
    keywords: str,
    date_posted: str,
    easy_apply: bool,
    remote_only: bool,
    threshold: int,
    applicant_data: dict | None,
    confirmed_answers: list[dict] | None,
    user_approved: bool,
    resume_path: str,
    resume_id: int | None,
    intent: str,
    max_results: int,
    resume_paused: bool,
) -> dict[str, Any]:
    # --- 0. Persist user-confirmed answers from a previous round. When resuming a
    # paused application, only answers to the questions that were actually asked are
    # saved, and only if they fit the control (an option answer must be one of the
    # offered options). Rejected answers are reported, never saved. ---
    answer_issues: list[str] = []
    if confirmed_answers:
        pending_ctx: dict[str, dict] | None = None
        if resume_paused:
            pending_ctx = {
                normalize_question(p.get("question", "")): p
                for p in (_paused.get(user.id) or {}).get("pending", [])
            }
        for entry in confirmed_answers:
            q = (entry.get("question") or "").strip()
            a = (entry.get("answer") or "").strip()
            input_type = entry.get("input_type", "text")
            if not (q and a):
                continue
            if pending_ctx is not None:
                asked = pending_ctx.get(normalize_question(q))
                if asked is None:
                    answer_issues.append(f"Ignored an answer to '{q[:60]}': it is not a pending question.")
                    continue
                valid = _validate_answer(asked, a)
                if valid is None:
                    answer_issues.append(
                        f"The answer to '{q[:60]}' is not valid for this field and was not saved."
                    )
                    continue
                q, a, input_type = asked["question"], valid, asked.get("input_type", input_type)
            await save_screening_answer(
                db, user.id, q, a, input_type=input_type, provenance="user",
            )

    def _note_issues(outcome: dict) -> dict:
        if answer_issues and outcome["status"] == "needs_input":
            outcome["message"] = " ".join(answer_issues) + " " + outcome["message"]
        return outcome

    paused = _paused.get(user.id) if resume_paused else None
    if resume_paused and paused is None:
        return _result("error", message="No paused application to resume.")
    if paused is None:
        _paused.pop(user.id, None)  # a fresh run abandons any stale paused form
    elif resume_id is None:
        resume_id = paused["resume_id"]

    # --- 1. Load resume (not needed for search-only). ---
    resume: Resume | None = None
    resume_text = ""
    profile: dict | None = None
    if intent != "search" or paused is not None:
        if resume_id is not None:
            resume = await db.scalar(
                select(Resume).where(Resume.id == resume_id, Resume.user_id == user.id)
            )
        else:
            resume = await _get_latest_resume(db, user)
        resume_text = resume.content if resume else ""
        if not resume_text:
            return _result("error", message="No uploaded resume found for user.")
        # Resume facts read once (skills, experience, education): used for matching
        # and screening answers instead of re-reading the resume for every job.
        profile = await get_or_build_profile(db, resume)
        if profile is None:
            emit_activity(user.id, "matching_resume", "waiting",
                          "Your resume could not be read into a profile; using the slower AI matching.")

    async def _score(job: dict, job_row: Job | None = None) -> dict:
        """Match a job's cached requirements against the profile (plain code)."""
        if profile is None:
            return await score_job(job, resume_text, threshold=threshold)
        row = job_row or await _upsert_job(db, job)
        requirements = await get_job_requirements(db, row, job.get("description", ""))
        return match_job_to_profile(job, requirements, profile, threshold)

    await _save_contact(db, user, applicant_data)
    app_data = _default_applicant_data(
        user, applicant_data, await _saved_contact(db, user)
    )
    if resume_path:
        app_data.setdefault("resume_path", resume_path)
    if intent == "apply" and resume is not None and not app_data.get("resume_path"):
        # Attach the same stored resume file that is used for matching.
        stored = resume_file_path(user.id, resume.id, resume.filename)
        if not stored.is_file():
            return _result(
                "error",
                message=(
                    f"The file for resume '{resume.filename}' is not stored on the server, "
                    "so it cannot be attached. Re-upload the resume and retry."
                ),
            )
        app_data["resume_path"] = str(stored)

    # --- 2. Shared browser session. ---
    browser = await _get_context()
    global _browser_owner_id
    _browser_owner_id = user.id

    # --- Scan state. While an application is paused it is kept in
    # _paused[user.id]["scan"] so the scan continues after the user responds. ---
    skipped_jobs: list[str] = []
    found: list[dict] = []
    seen_ids: set[str] = set()
    search_errors: list[SearchError] = []
    # Scan limit != application limit: the scan continues after each confirmed
    # submission until max_results postings were inspected.
    scanned = applied = failed = uncertain = 0
    last_applied: dict | None = None
    scan_blocked = False  # set when the post-submit dialog could not be closed
    stopped = False  # set when the user pressed Stop
    progress: dict = {"page": 0}  # current results page, updated by the search generator

    def _summary() -> dict:
        return {
            "scanned": scanned,
            "applied": applied,
            "skipped": len(skipped_jobs),
            "failed": failed,
            "uncertain": uncertain,  # submitted, but LinkedIn's confirmation was not seen
        }

    def _remember_scan(outcome: dict) -> None:
        """Attach scan progress to the paused state created by _run_form."""
        if outcome["status"] in ("needs_input", "awaiting_approval") and user.id in _paused:
            _paused[user.id]["scan"] = {
                "keywords": keywords, "date_posted": date_posted,
                "easy_apply": easy_apply, "remote_only": remote_only,
                "threshold": threshold, "max_results": max_results,
                "user_approved": user_approved,  # authorization of the original run
                "seen_ids": seen_ids, "skipped_jobs": skipped_jobs,
                "scanned": scanned, "applied": applied, "failed": failed,
                "uncertain": uncertain,
                "last_applied": last_applied,
                "progress": progress,
            }

    # --- 2a. Resume the paused application on the same page. ---
    if paused is not None:
        page = paused["page"]
        job_row = await db.get(Job, paused["job_db_id"])
        if page.is_closed() or job_row is None:
            _paused.pop(user.id, None)
            return _result("error", message="The paused application is no longer open.")
        paused["app_data"].update(app_data)
        scan = paused.get("scan")
        form_approved = user_approved or paused["user_approved"]
        if scan:
            # Restore the original search criteria, processed ids and counters.
            keywords, date_posted = scan["keywords"], scan["date_posted"]
            easy_apply, remote_only = scan["easy_apply"], scan["remote_only"]
            threshold, max_results = scan["threshold"], scan["max_results"]
            user_approved = scan["user_approved"]  # a one-time approval does not carry over
            seen_ids, skipped_jobs = scan["seen_ids"], scan["skipped_jobs"]
            scanned, applied, failed = scan["scanned"], scan["applied"], scan["failed"]
            uncertain = scan.get("uncertain", 0)
            last_applied = scan["last_applied"]
            progress = scan["progress"]
            app_data = paused["app_data"]
        outcome = await _run_form(
            db, user, page, job_row, paused["scored"], paused["app_data"],
            resume, resume_text, form_approved, skipped_jobs, profile=profile,
        )
        resumed_job = paused["scored"]
        if outcome["status"] == "applied":
            emit_activity(user.id, "application_submitted", "completed", str(outcome.get("message", ""))[:500], resumed_job, result="Applied")
        elif outcome["status"] == "error":
            emit_activity(user.id, "error", "failed", str(outcome.get("message", ""))[:500], resumed_job, result="Failed")
        if not scan:
            return _note_issues(outcome)
        if outcome["status"] != "applied":
            # Paused again (progress kept) or failed (stop; never retry a submit).
            if outcome["status"] == "error":
                if outcome.get("error_type") == "submit_uncertain":
                    uncertain += 1
                else:
                    failed += 1
                if applied:
                    outcome["message"] = (
                        f"{applied} application(s) were confirmed and recorded before "
                        f"this run stopped. {outcome['message']}"
                    )
            outcome["summary"] = _summary()
            _remember_scan(outcome)
            return _note_issues(outcome)
        applied += 1
        last_applied = outcome
        scan_blocked = not await _dismiss_confirmation(page)
        # Manual flow: remove the applied post from the list with its cross icon
        # (after a short pause so the closing dialog cannot swallow the click).
        if not scan_blocked:
            await page.wait_for_timeout(1_000)
        if not scan_blocked and not await dismiss_job(page, job_row.linkedin_job_id):
            emit_activity(user.id, "dismissing_job", "completed", "Applied; the post could not be removed from the list.", resumed_job)
        # Fall through: continue the remaining scan on the same page.
    else:
        page = browser.pages[0] if browser.pages else await browser.new_page()

    async def _search_jobs():
        # Search through LinkedIn's Jobs UI in the shared page; a failed
        # search is recorded so it is never reported as "0 jobs found".
        # Apply intent: max_results is the scan limit (distinct postings inspected,
        # qualifying or not). seen_ids already de-duplicates job ids. Search/match
        # keep their own limit on returned results.
        if scan_blocked:
            return  # the confirmation dialog could not be closed; do not scan on
        if intent == "apply" and scanned >= max_results:
            return  # limit already reached (e.g. by the resumed application)
        try:
            async for item in iter_search_page_jobs(
                page,
                keywords=keywords,
                date_posted=date_posted,
                easy_apply=easy_apply,
                remote_only=remote_only,
                seen_ids=seen_ids,
                start_page=progress["page"],
                progress=progress,
                on_login_wait=lambda msg: emit_activity(user.id, "searching_jobs", "waiting", msg),
                on_progress=lambda msg: emit_activity(user.id, "searching_jobs", "running", msg),
            ):
                yield item
                # `scanned` is incremented by the consumer before it resumes us.
                if intent == "apply" and scanned >= max_results:
                    return
        except SearchError as exc:
            search_errors.append(exc)

    async for job in _search_jobs():
        # Stop button: checked only between jobs, never in the middle of a form.
        if user.id in _stop_requested:
            stopped = True
            break
        scanned += 1
        if intent == "apply":
            _job_progress[user.id] = (scanned, max_results)
            _current_job[user.id] = job
        job_id = job.get("job_id", "")
        emit_activity(user.id, "reading_job_description", "completed", f"Job {scanned}: inspecting posting", job)

        def _skip_result(reason: str) -> None:
            emit_activity(user.id, "dismissing_job", "completed", f"Job {scanned}: Skipped. {reason}", job, result="Skipped")

        # --- Search / match: never open Easy Apply or submit. ---
        if intent != "apply":
            if intent == "match":
                emit_activity(user.id, "matching_resume", "running", f"Job {scanned}: checking resume match", job)
                scored = await _score(job)
                emit_activity(user.id, "matching_resume", "completed" if scored.get("eligible") else "waiting" if scored.get("needs_review") else "completed", "Eligible" if scored.get("eligible") else str(scored.get("match_reason") or "Not eligible"), job, scored.get("match_score"))
                if not scored.get("eligible"):
                    skipped_jobs.append(job_id)
                    continue
                job = scored
            found.append(job)
            if len(found) >= max_results:
                break
            continue

        # --- Role keyword check on the job title (manual flow, README.md). ---
        role_keyword = title_matches_role(job.get("title", ""))
        emit_activity(
            user.id, "matching_resume", "completed",
            f"Job {scanned}: title matched '{role_keyword}'" if role_keyword
            else f"Job {scanned}: title did not match any role keyword",
            job,
        )

        # --- Persist Job row. ---
        job_row = await _upsert_job(db, job)

        # --- Title does not match any role keyword: dismiss the post, next job. ---
        if not role_keyword:
            job_row.status = "skipped_title"
            if not await dismiss_job(page, job_id):
                job_row.status = "skipped_title_no_dismiss"
            await db.commit()
            _skip_result(
                "Title does not match the role keywords."
                + ("" if job_row.status == "skipped_title" else " The post could not be dismissed.")
            )
            skipped_jobs.append(job_id)
            continue

        # --- Skip already-applied jobs. ---
        if await _already_applied(db, user, job_row) or job.get("linkedin_applied"):
            # Manual flow: an applied post is removed from the list with its cross icon.
            removed = await dismiss_job(page, job_id)
            _skip_result("Already applied." + ("" if removed else " The post could not be removed from the list."))
            skipped_jobs.append(job_id)
            continue

        # --- Score. ---
        emit_activity(user.id, "matching_resume", "running", f"Job {scanned}: checking requirements against your profile", job)
        scored = await _score(job, job_row)
        match_score = scored.get("match_score")
        emit_activity(user.id, "matching_resume", "completed" if scored.get("eligible") else "waiting" if scored.get("needs_review") else "completed", "Eligible" if scored.get("eligible") else str(scored.get("match_reason") or "Not eligible"), job, match_score)

        if match_score is not None:
            job_row.match_score = float(match_score)
            await db.flush()

        # --- Skip unscorable/uncertain jobs (needs_review / None); never dismiss them. ---
        if match_score is None or scored.get("needs_review"):
            job_row.status = "skipped_unscorable"
            _skip_result(str(scored.get("match_reason") or "Resume match could not be scored."))
            skipped_jobs.append(job_id)
            continue

        # --- Dismiss if required-skills match is below threshold. ---
        if should_dismiss(match_score, threshold):
            job_row.status = "dismissed"
            dismissed = await dismiss_job(page, job_id)
            if not dismissed:
                job_row.status = "skipped_no_dismiss"
            _skip_result(str(scored.get("match_reason") or f"Resume match {match_score}% is below {threshold}%."))
            skipped_jobs.append(job_id)
            continue

        # --- Experience requirement not met (skills may be fine): skip, do not apply. ---
        if not scored.get("eligible"):
            job_row.status = "skipped_experience"
            _skip_result(str(scored.get("match_reason") or "Experience requirement not met."))
            skipped_jobs.append(job_id)
            continue

        # --- Qualifying job found (score >= threshold). ---
        job_row.status = "qualifying"
        await db.commit()

        # --- Open Easy Apply. ---
        emit_activity(user.id, "opening_easy_apply", "running", "Opening Easy Apply", job, match_score)
        if not await open_easy_apply(page, job_id):
            job_row.status = "easy_apply_unavailable"
            await db.commit()
            _skip_result("Easy Apply is not available.")
            skipped_jobs.append(job_id)
            continue

        emit_activity(user.id, "filling_fields", "running", "Checking application form", job, match_score)
        outcome = await _run_form(
            db, user, page, job_row, scored, app_data, resume, resume_text,
            user_approved, skipped_jobs, profile=profile,
        )
        emit_activity(user.id, "application_submitted" if outcome["status"] == "applied" else "awaiting_approval" if outcome["status"] == "awaiting_approval" else "pending_questions" if outcome["status"] == "needs_input" else "error", "completed" if outcome["status"] == "applied" else "waiting" if outcome["status"] in ("awaiting_approval", "needs_input") else "failed", str(outcome.get("message", ""))[:500], job, match_score, result="Applied" if outcome["status"] == "applied" else "Failed" if outcome["status"] == "error" else None)
        if outcome["status"] == "applied":
            # Confirmed by LinkedIn and saved; continue with the next posting.
            applied += 1
            last_applied = outcome
            if not await _dismiss_confirmation(page):
                scan_blocked = True  # an open dialog would obstruct the next job
                break
            # Manual flow: remove the applied post from the list with its cross icon
            # (after a short pause so the closing dialog cannot swallow the click).
            await page.wait_for_timeout(1_000)
            if not await dismiss_job(page, job_id):
                emit_activity(user.id, "dismissing_job", "completed", f"Job {scanned}: applied; the post could not be removed from the list.", job)
            continue
        # needs_input / awaiting_approval keep the paused state (set in _run_form)
        # and error stops the run; never move on to another job from here.
        if outcome["status"] == "error":
            if outcome.get("error_type") == "submit_uncertain":
                uncertain += 1
            else:
                failed += 1
            if applied:
                outcome["message"] = (
                    f"{applied} application(s) were confirmed and recorded before "
                    f"this run stopped. {outcome['message']}"
                )
        outcome["summary"] = _summary()
        _remember_scan(outcome)
        return outcome

    if stopped:
        _stop_requested.discard(user.id)
        return _result(
            "stopped",
            skipped_jobs=skipped_jobs,
            message=(
                f"Stopped by you after {scanned} job(s): {applied} applied, "
                f"{len(skipped_jobs)} skipped, {failed} failed."
            ),
            summary=_summary(),
        )

    if search_errors:
        err = search_errors[0]
        return _result(
            "error",
            skipped_jobs=skipped_jobs,
            message=(f"{applied} application(s) submitted before the search stopped. " if applied else "") + str(err),
            error_type=err.kind,
            summary=_summary(),
        )

    if intent != "apply":
        return _result(
            "search_results",
            jobs=found,
            skipped_jobs=skipped_jobs,
            message=f"Found {len(found)} job(s). No applications were opened or submitted.",
        )

    if last_applied is not None:
        last_applied["summary"] = _summary()
        last_applied["message"] = (
            f"Scanned {scanned} job(s); submitted {applied} application(s), "
            f"skipped {len(skipped_jobs)}, failed {failed}."
        ) + (
            " Scanning stopped because the confirmation dialog could not be closed."
            if scan_blocked else ""
        )
        return last_applied

    # Scan finished with no qualifying job.
    return _result(
        "no_match",
        skipped_jobs=skipped_jobs,
        message=f"No qualifying job found after scanning {scanned} job(s).",
        summary=_summary(),
    )
