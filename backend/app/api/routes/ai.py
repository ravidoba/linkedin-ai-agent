
import json
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import get_current_user
from app.db.database import get_db
from app.models.agent_run import AgentRun
from app.models.agent_run_log import AgentRunLog
from app.models.resume import Resume
from app.models.user import User
from app.services import apply_workflow
from app.services.apply_workflow import run_apply_workflow
from app.services.ollama_service import ask_ollama

router = APIRouter(
    prefix="/ai",
    tags=["AI"],
    dependencies=[Depends(get_current_user)],
)


class AIRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=10000)


class AIResponse(BaseModel):
    response: str


class AgentResponse(BaseModel):
    response: str
    status: str = "chat"
    conversation_id: str | None = None
    results: list[dict] = []
    errors: list[str] = []
    pending_questions: list[dict] = []
    missing_fields: list[str] = []
    # Status "error" only: auth_expired | access_restricted | navigation_timeout | search_failed
    error_type: str | None = None
    run_id: int | None = None


class AgentAnswer(BaseModel):
    question: str
    answer: str
    input_type: str = "text"


class AgentRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10000)
    resume_id: int | None = None
    conversation_id: str | None = Field(default=None, max_length=100)
    # Supplying answers/applicant_data resumes the paused application.
    answers: list[AgentAnswer] = []
    applicant_data: dict = {}
    approve: bool = False
    # Set by the UI Start button: number of job postings to process in this run.
    job_count: int | None = Field(default=None, ge=1)


_INTENT_PROMPT = (
    "Classify the user message. Reply with ONLY a JSON object with keys: "
    '"action" ("search" to only find/list jobs, "match" to find jobs and score them against the resume, '
    '"apply" only if the user explicitly asks to apply/submit, "chat" for anything else), '
    '"keywords" (string job title/skills or null), "remote_only" (bool or null), '
    '"date_posted" ("24h", "week", "month", "any" or null), '
    '"threshold" (integer 0-100 minimum resume match or null), '
    '"limit" (integer maximum number of job postings to scan, e.g. "25 jobs" means 25, or null), '
    '"auto_submit" (true if the user explicitly asks to apply/submit, else false).\n'
    "User message: "
)
_DATE_MAP = {"24h": "r86400", "week": "r604800", "month": "r2592000", "any": ""}
MAX_APPLICATIONS = 10
# Search criteria of the manual apply flow in README.md, used for Start-button runs.
_START_RUN_INTENT: dict = {
    "action": "apply",
    "keywords": "Java",
    "remote_only": True,
    "date_posted": "24h",
    "auto_submit": False,
}


def _parse_intent(raw: str) -> dict | None:
    try:
        start, end = raw.index("{"), raw.rindex("}") + 1
        data = json.loads(raw[start:end])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


@router.post("/agent", response_model=AgentResponse)
async def run_agent_prompt(
    request: AgentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run LinkedIn search/apply workflows via the existing apply workflow, or answer with Ollama."""
    is_resume = bool(request.answers or request.applicant_data or request.approve)
    if request.job_count is None or is_resume:
        if not is_resume:
            # A new non-Start request: its events do not belong to any run.
            apply_workflow.active_run_ids.pop(current_user.id, None)
        response = await _run_agent(request, current_user, db)
        await _update_run_status(db, current_user.id, response)
        return response

    # A Start-button run: record it before the workflow begins.
    run = AgentRun(user_id=current_user.id, job_count=request.job_count)
    db.add(run)
    await db.commit()
    await db.refresh(run)

    apply_workflow.active_run_ids[current_user.id] = run.id
    try:
        response = await _run_agent(request, current_user, db)
    except Exception:
        apply_workflow.active_run_ids.pop(current_user.id, None)
        await db.rollback()
        run.status = "failed"
        await db.commit()
        raise
    response.run_id = run.id
    await _update_run_status(db, current_user.id, response)
    return response


@router.post("/runs/stop")
async def stop_current_run(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stop button: end the active Start run safely (between jobs, never mid-submit)."""
    run_id = apply_workflow.active_run_ids.get(current_user.id)
    if run_id is None:
        # No live run in memory (e.g. the backend restarted): a run still marked
        # running/paused cannot continue, so close it as stopped.
        stale = await db.scalar(
            select(AgentRun)
            .where(AgentRun.user_id == current_user.id, AgentRun.status.in_(("running", "paused")))
            .order_by(AgentRun.id.desc())
            .limit(1)
        )
        if stale is None:
            return {"status": "idle", "run_id": None}
        stale.status = "stopped"
        await db.commit()
        apply_workflow._paused.pop(current_user.id, None)
        return {"status": "stopped", "run_id": stale.id}
    state = apply_workflow.stop_run(current_user.id)
    if state == "stopped":
        # It was paused waiting for the user: nothing is running, so finish it now.
        apply_workflow.active_run_ids.pop(current_user.id, None)
        run = await db.get(AgentRun, run_id)
        if run is not None:
            run.status = "stopped"
            await db.commit()
    return {"status": state, "run_id": run_id}


@router.get("/runs")
async def list_runs(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The user's Start-button runs, newest first, with per-result job counts."""
    runs = (await db.scalars(
        select(AgentRun)
        .where(AgentRun.user_id == current_user.id)
        .order_by(AgentRun.id.desc())
        .limit(limit)
    )).all()
    counts: dict[int, dict[str, int]] = {}
    if runs:
        rows = await db.execute(
            select(AgentRunLog.run_id, AgentRunLog.result, func.count())
            .where(AgentRunLog.run_id.in_([r.id for r in runs]), AgentRunLog.result.is_not(None))
            .group_by(AgentRunLog.run_id, AgentRunLog.result)
        )
        for run_id, result, n in rows:
            counts.setdefault(run_id, {})[result] = n
    return {
        "runs": [
            {
                "id": r.id,
                "job_count": r.job_count,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "applied": counts.get(r.id, {}).get("Applied", 0),
                "skipped": counts.get(r.id, {}).get("Skipped", 0),
                "failed": counts.get(r.id, {}).get("Failed", 0),
            }
            for r in runs
        ]
    }


@router.get("/runs/logs")
async def get_run_logs(
    run_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Saved log entries of one Start-button run (the latest run when run_id is omitted)."""
    query = select(AgentRun).where(AgentRun.user_id == current_user.id)
    if run_id is not None:
        query = query.where(AgentRun.id == run_id)
    else:
        query = query.order_by(AgentRun.id.desc()).limit(1)
    run = await db.scalar(query)
    if run is None:
        if run_id is not None:
            raise HTTPException(status_code=404, detail="Run not found")
        return {"run": None, "logs": []}
    logs = (await db.scalars(
        select(AgentRunLog).where(AgentRunLog.run_id == run.id).order_by(AgentRunLog.seq, AgentRunLog.id)
    )).all()
    return {
        "run": {
            "id": run.id,
            "job_count": run.job_count,
            "status": run.status,
            "created_at": run.created_at.isoformat() if run.created_at else None,
        },
        "logs": [
            {
                "id": log.id,
                "type": log.type,
                "status": log.status,
                "message": log.message,
                "step": log.step,
                "result": log.result,
                "job_number": log.job_number,
                "job_total": log.job_total,
                "job_title": log.job_title,
                "job_company": log.job_company,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ],
    }


_PAUSED_STATUSES = ("needs_input", "awaiting_approval")


async def _update_run_status(db: AsyncSession, user_id: int, response: AgentResponse) -> None:
    """
    Record the active Start run's state after a request: "paused" while it waits for
    the user, else "completed" / "failed"; a finished run stops collecting events.
    """
    run_id = apply_workflow.active_run_ids.get(user_id)
    if run_id is None:
        return
    paused = response.status in _PAUSED_STATUSES
    if not paused:
        apply_workflow.active_run_ids.pop(user_id, None)
    run = await db.get(AgentRun, run_id)
    if run is None:
        return
    run.status = (
        "paused" if paused
        else "failed" if response.status == "error"
        else "stopped" if response.status == "stopped"
        else "completed"
    )
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise


async def _run_agent(
    request: AgentRequest,
    current_user: User,
    db: AsyncSession,
) -> AgentResponse:
    resume = None
    if request.resume_id is not None:
        resume = await db.scalar(
            select(Resume).where(
                Resume.id == request.resume_id,
                Resume.user_id == current_user.id,
            )
        )
        if resume is None:
            raise HTTPException(status_code=404, detail="Resume not found")
    # Resume a paused application with the user's answers (no new search).
    if request.answers or request.applicant_data or request.approve:
        try:
            result = await run_apply_workflow(
                db=db,
                user=current_user,
                resume_id=request.resume_id,
                confirmed_answers=[a.model_dump() for a in request.answers],
                applicant_data=request.applicant_data,
                user_approved=request.approve,
                resume_paused=True,
            )
        except Exception as exc:
            return AgentResponse(
                response=f"{type(exc).__name__}: {exc}",
                status="error",
                conversation_id=request.conversation_id,
                errors=[f"{type(exc).__name__}: {exc}"],
            )
        return _to_response(result, request.conversation_id, [result])

    try:
        if request.job_count is not None:
            # Start-button run: fixed manual-flow criteria (README.md), no model parsing.
            # APPLY_AUTO_SUBMIT decides whether complete forms are submitted directly.
            intent = {**_START_RUN_INTENT, "auto_submit": get_settings().APPLY_AUTO_SUBMIT}
        else:
            intent = _parse_intent(await ask_ollama(_INTENT_PROMPT + request.message))
        if not intent or intent.get("action") not in ("search", "match", "apply"):
            prompt = request.message
            if resume is not None:
                prompt = f"Resume:\n{resume.content}\n\nUser request:\n{request.message}"
            return AgentResponse(
                response=await ask_ollama(prompt),
                status="chat",
                conversation_id=request.conversation_id,
            )
    except httpx.HTTPError:
        raise HTTPException(
            status_code=503,
            detail="Ollama service is unavailable",
        )

    # Applying needs an explicit apply/submit verb; otherwise stay read-only.
    wants_apply = bool(re.search(r"\b(apply|applying|submit)\b", request.message, re.I)) and not re.search(
        r"\b(don'?t|do not|without|not)\b.*\b(apply|applying|submit)\b", request.message, re.I
    )
    action = intent.get("action")
    if action == "apply" and not wants_apply:
        action = "match"
    # The small model sometimes labels an explicit auto-apply request as "match".
    if action in ("search", "match") and wants_apply and intent.get("auto_submit") is True:
        action = "apply"
    auto = action == "apply" and bool(intent.get("auto_submit"))

    kwargs: dict = {}
    if isinstance(intent.get("keywords"), str) and intent["keywords"].strip():
        kwargs["keywords"] = intent["keywords"].strip()
    if isinstance(intent.get("remote_only"), bool):
        kwargs["remote_only"] = intent["remote_only"]
    if intent.get("date_posted") in _DATE_MAP:
        kwargs["date_posted"] = _DATE_MAP[intent["date_posted"]]
    threshold = intent.get("threshold")
    if isinstance(threshold, int) and not isinstance(threshold, bool) and 0 <= threshold <= 100:
        kwargs["threshold"] = threshold
    # "limit" is the maximum number of job postings to scan, not applications to submit.
    # An explicit job_count (Start button) wins over the model's parsed limit.
    raw_limit = request.job_count or intent.get("limit")
    requested = raw_limit if isinstance(raw_limit, int) and not isinstance(raw_limit, bool) and raw_limit > 0 else MAX_APPLICATIONS
    limit = 1  # applications submitted per request

    # Search/match: read-only listing, never opens Easy Apply.
    if action != "apply":
        try:
            result = await run_apply_workflow(
                db=db,
                user=current_user,
                resume_id=request.resume_id,
                intent=action,
                max_results=min(requested, MAX_APPLICATIONS),
                **kwargs,
            )
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            return AgentResponse(
                response=msg, status="error",
                conversation_id=request.conversation_id, errors=[msg],
            )
        return _to_response(result, request.conversation_id, [result])

    results: list[dict] = []
    errors: list[str] = []
    applied = 0
    for _ in range(limit):
        try:
            result = await run_apply_workflow(
                db=db,
                user=current_user,
                user_approved=auto,
                resume_id=request.resume_id,
                intent="apply",
                max_results=requested,
                **kwargs,
            )
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
            break
        results.append(result)
        if result.get("status") != "applied":
            if result.get("status") == "error":
                errors.append(result.get("message", "Unknown error"))
            break
        applied += 1

    last = results[-1] if results else {"status": "error", "message": "; ".join(errors)}
    response = _to_response(last, request.conversation_id, results)
    if last.get("status") != "error" and not last.get("summary"):
        response.response = f"Applied to {applied} of {limit} requested job(s). {last.get('message', '')}".strip()
    response.errors = errors
    return response


def _to_response(result: dict, conversation_id: str | None, results: list[dict]) -> AgentResponse:
    status = result.get("status", "error")
    return AgentResponse(
        response=result.get("message", ""),
        status=status,
        conversation_id=conversation_id,
        results=results,
        errors=[result.get("message", "Unknown error")] if status == "error" else [],
        pending_questions=result.get("pending_questions", []),
        missing_fields=result.get("missing_fields", []),
        error_type=result.get("error_type") if status == "error" else None,
    )

@router.post("/chat", response_model=AIResponse)
async def chat_with_ai(request: AIRequest):
    try:
        result = await ask_ollama(request.prompt)
        return AIResponse(response=result)
    except httpx.HTTPError:
        raise HTTPException(
            status_code=503,
            detail="Ollama service is unavailable",
        )
