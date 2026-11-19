from app.core.dependencies import get_current_user
from app.models.user import User
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.job import Job
from app.schemas.job import JobCreate, JobResponse

router = APIRouter(
    prefix="/jobs",
    tags=["Jobs"],
    dependencies=[Depends(get_current_user)],
)


@router.post("/", response_model=JobResponse, status_code=201)
async def create_job(
    data: JobCreate,
    db: AsyncSession = Depends(get_db),
):
    existing = await db.scalar(
        select(Job).where(Job.linkedin_job_id == data.linkedin_job_id)
    )

    if existing:
        raise HTTPException(status_code=409, detail="Job already exists")

    job = Job(**data.model_dump())
    db.add(job)
    await db.commit()
    await db.refresh(job)

    return job


@router.get("/", response_model=list[JobResponse])
async def list_jobs(db: AsyncSession = Depends(get_db)):
    result = await db.scalars(
        select(Job).order_by(Job.created_at.desc(), Job.id.desc())
    )
    return result.all()


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
):
    job = await db.get(Job, job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return job
