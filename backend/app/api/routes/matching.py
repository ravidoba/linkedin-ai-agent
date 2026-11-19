
import httpx

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.models.resume import Resume
from app.models.job import Job
from app.services.job_matching_service import calculate_job_match
from app.services.ai_matching_service import calculate_ai_job_match


router = APIRouter(prefix="/matching", tags=["Job Matching"])


async def get_resume_and_job(
    resume_id: int,
    job_id: int,
    db: AsyncSession,
    current_user: User,
):
    resume = await db.scalar(
        select(Resume).where(
            Resume.id == resume_id,
            Resume.user_id == current_user.id,
        )
    )

    if resume is None:
        raise HTTPException(
            status_code=404,
            detail="Resume not found",
        )

    job = await db.scalar(
        select(Job).where(Job.id == job_id)
    )

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    return resume, job


@router.post("/resume/{resume_id}/job/{job_id}")
async def match_resume_to_job(
    resume_id: int,
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume, job = await get_resume_and_job(
        resume_id, job_id, db, current_user
    )

    result = calculate_job_match(
        resume_text=resume.content or "",
        job_description=job.description or "",
    )

    # Do not save uncertain scores as genuine matches.
    if not result["needs_review"]:
        job.match_score = result["match_score"]
        await db.commit()

    return {
        "resume_id": resume.id,
        "job_id": job.id,
        "method": "keyword",
        **result,
    }


@router.post("/ai/resume/{resume_id}/job/{job_id}")
async def ai_match_resume_to_job(
    resume_id: int,
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume, job = await get_resume_and_job(
        resume_id, job_id, db, current_user
    )

    try:
        result = await calculate_ai_job_match(
            resume_text=resume.content or "",
            job_description=job.description or "",
        )
    except (httpx.HTTPError, TimeoutError):
        raise HTTPException(
            status_code=503,
            detail="Local AI service is unavailable",
        )

    return {
        "resume_id": resume.id,
        "job_id": job.id,
        "method": "ai",
        "eligible": (
            result["match_score"] >= 75
            and not result["needs_review"]
        ),
        **result,
    }
