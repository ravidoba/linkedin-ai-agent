"""
Easy Apply workflow route.

POST /apply/run      — start or resume the workflow
POST /apply/answers  — submit user-confirmed screening answers
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.services.apply_workflow import run_apply_workflow

router = APIRouter(prefix="/apply", tags=["Apply"])


class ConfirmedAnswer(BaseModel):
    question: str
    answer: str
    input_type: str = "text"


class RunWorkflowRequest(BaseModel):
    keywords: str = "Java Backend Developer"
    applicant_data: dict = {}
    confirmed_answers: list[ConfirmedAnswer] = []
    user_approved: bool = False
    resume_path: str = ""


@router.post("/run")
async def run_workflow(
    body: RunWorkflowRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Run (or resume) the single-application Easy Apply workflow.

    Call with user_approved=False first to review the form state.
    Call again with user_approved=True to submit after reviewing.
    Supply confirmed_answers to resolve pending screening questions.
    """
    result = await run_apply_workflow(
        db=db,
        user=current_user,
        keywords=body.keywords,
        applicant_data=body.applicant_data,
        confirmed_answers=[a.model_dump() for a in body.confirmed_answers],
        user_approved=body.user_approved,
        resume_path=body.resume_path,
    )
    return result
