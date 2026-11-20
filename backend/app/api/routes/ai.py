
import json
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.database import get_db
from app.models.resume import Resume
from app.models.user import User
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
    raw_limit = intent.get("limit")
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
