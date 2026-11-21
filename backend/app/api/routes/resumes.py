
from io import BytesIO
import os
from uuid import uuid4

from docx import Document
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from pypdf import PdfReader
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.browser_agent import resume_file_path
from app.core.dependencies import get_current_user
from app.db.database import get_db
from app.models.application import Application
from app.models.resume import Resume
from app.models.user import User
from app.models.resume_profile import ResumeProfile
from app.services.resume_profile_service import (
    build_profile,
    build_profile_in_background,
    get_profile,
    normalize_profile,
    profile_to_dict,
)
from app.schemas.resume import (
    ResumeDetailResponse,
    ResumeResponse,
)

router = APIRouter(
    prefix="/resumes",
    tags=["Resumes"],
)

MAX_FILE_SIZE = 5 * 1024 * 1024


def extract_text(filename: str, data: bytes) -> str:
    try:
        if filename.lower().endswith(".pdf"):
            reader = PdfReader(BytesIO(data))
            return "\n".join(
                page.extract_text() or ""
                for page in reader.pages
            )

        if filename.lower().endswith(".docx"):
            document = Document(BytesIO(data))
            return "\n".join(
                paragraph.text
                for paragraph in document.paragraphs
            )

    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail="Unable to read resume file",
        ) from exc

    raise HTTPException(
        status_code=415,
        detail="Only PDF and DOCX files are supported",
    )


@router.post(
    "/",
    response_model=ResumeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_resume(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    filename = file.filename or ""

    if not filename.lower().endswith((".pdf", ".docx")):
        raise HTTPException(
            status_code=415,
            detail="Only PDF and DOCX files are supported",
        )

    data = await file.read(MAX_FILE_SIZE + 1)

    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="Maximum file size is 5 MB",
        )

    if not data:
        raise HTTPException(
            status_code=422,
            detail="Uploaded file is empty",
        )

    content = extract_text(filename, data).strip()

    if not content:
        raise HTTPException(
            status_code=422,
            detail="No readable text found in resume",
        )

    resume = Resume(
        user_id=current_user.id,
        filename=filename,
        content=content,
    )

    db.add(resume)
    await db.flush()

    try:
        stored = resume_file_path(
            current_user.id,
            resume.id,
            filename,
        )
        stored.parent.mkdir(parents=True, exist_ok=True)
        stored.write_bytes(data)

    except OSError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to store the resume file",
        ) from exc

    await db.commit()
    await db.refresh(resume)

    # Read the resume once into its profile (skills, experience, education).
    build_profile_in_background(resume.id)

    return resume


@router.get(
    "/",
    response_model=list[ResumeResponse],
)
async def list_my_resumes(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.scalars(
        select(Resume)
        .where(Resume.user_id == current_user.id)
        .order_by(
            Resume.created_at.desc(),
            Resume.id.desc(),
        )
    )

    return result.all()


@router.get(
    "/{resume_id}",
    response_model=ResumeDetailResponse,
)
async def get_my_resume(
    resume_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
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

    return resume


async def _own_resume(db: AsyncSession, user: User, resume_id: int) -> Resume:
    resume = await db.scalar(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == user.id)
    )
    if resume is None:
        raise HTTPException(status_code=404, detail="Resume not found")
    return resume


class ProfileSkill(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    years: float | None = Field(default=None, ge=0, le=60)


class ProfileEducation(BaseModel):
    degree: str = Field(default="", max_length=200)
    level: str = "other"
    field: str = Field(default="", max_length=200)


class ProfileUpdate(BaseModel):
    skills: list[ProfileSkill] = Field(default_factory=list, max_length=300)
    total_experience_years: float | None = Field(default=None, ge=0, le=60)
    education: list[ProfileEducation] = Field(default_factory=list, max_length=20)
    current_role: str | None = Field(default=None, max_length=255)


@router.get("/{resume_id}/profile")
async def get_resume_profile(
    resume_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The resume's profile; read from the resume first if it does not exist yet."""
    resume = await _own_resume(db, current_user, resume_id)
    row = await build_profile(db, resume)
    if row is None:
        raise HTTPException(status_code=503, detail="The resume could not be read into a profile. Try again.")
    return profile_to_dict(row)


@router.put("/{resume_id}/profile")
async def update_resume_profile(
    resume_id: int,
    update: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save the user's edits; edited profiles are never overwritten automatically."""
    resume = await _own_resume(db, current_user, resume_id)
    data = normalize_profile(update.model_dump())
    row = await get_profile(db, resume.id)
    if row is None:
        row = ResumeProfile(resume_id=resume.id, user_id=current_user.id)
        db.add(row)
    row.skills = data["skills"]
    row.total_experience_years = data["total_experience_years"]
    row.education = data["education"]
    row.current_role = data["current_role"]
    row.edited_by_user = True
    await db.commit()
    await db.refresh(row)
    return profile_to_dict(row)


@router.post("/{resume_id}/profile/rebuild")
async def rebuild_resume_profile(
    resume_id: int,
    overwrite_edits: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Read the resume again. The user's edits are replaced only with overwrite_edits=true."""
    resume = await _own_resume(db, current_user, resume_id)
    existing = await get_profile(db, resume.id)
    if existing is not None and existing.edited_by_user and not overwrite_edits:
        raise HTTPException(status_code=409, detail="The profile has your edits. Confirm to replace them.")
    row = await build_profile(db, resume, force=True, overwrite_edits=overwrite_edits)
    if row is None:
        raise HTTPException(status_code=503, detail="The resume could not be read into a profile. Try again.")
    return profile_to_dict(row)


@router.delete("/{resume_id}")
async def delete_my_resume(
    resume_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Check workflow activity before removing a resume.
    # This guard assumes the workflow uses the same in-process lock.
    from app.services.apply_workflow import _lock, _paused

    if _lock.locked() or current_user.id in _paused:
        raise HTTPException(
            status_code=409,
            detail=(
                "An application is running or paused. "
                "Finish it before removing the resume."
            ),
        )

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

    stored = resume_file_path(
        current_user.id,
        resume.id,
        resume.filename,
    )

    staged = stored.with_name(
        f".{stored.name}.{uuid4().hex}.deleting"
    )

    moved = False

    try:
        # Temporarily rename the file so it can be restored
        # if the database transaction fails.
        if stored.exists():
            os.replace(stored, staged)
            moved = True

        # Keep application history but remove its resume reference.
        await db.execute(
            update(Application)
            .where(Application.resume_id == resume.id)
            .values(resume_id=None)
        )

        await db.delete(resume)
        await db.commit()

    except Exception as exc:
        await db.rollback()

        if moved:
            try:
                os.replace(staged, stored)
            except OSError:
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "Resume deletion failed and file restoration "
                        "requires attention."
                    ),
                ) from exc

        raise HTTPException(
            status_code=500,
            detail="Unable to delete resume.",
        ) from exc

    if moved:
        try:
            staged.unlink()
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Resume record deleted, but stored file "
                    "cleanup failed."
                ),
            ) from exc

    return {
        "deleted": True,
        "resume_id": resume_id,
    }
