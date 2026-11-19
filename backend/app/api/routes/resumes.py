
from io import BytesIO

from docx import Document
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.database import get_db
from app.models.resume import Resume
from app.models.user import User
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
    await db.commit()
    await db.refresh(resume)

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
        .order_by(Resume.created_at.desc(), Resume.id.desc())
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
