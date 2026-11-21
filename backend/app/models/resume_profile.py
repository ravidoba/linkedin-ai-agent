from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class ResumeProfile(Base):
    """
    Structured facts read once from a resume (and editable by the user), used for
    job matching and screening answers instead of re-reading the full resume.

    skills    : [{"name": "Java", "years": 5.0}]  (years is null when unknown)
    education : [{"degree": "Bachelor of Engineering", "level": "bachelor", "field": "Computer"}]
                level: "phd" | "master" | "bachelor" | "diploma" | "other"
    """

    __tablename__ = "resume_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resume_id: Mapped[int] = mapped_column(
        ForeignKey("resumes.id", ondelete="CASCADE"), unique=True, index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    skills: Mapped[list] = mapped_column(JSON, default=list)
    total_experience_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    education: Mapped[list] = mapped_column(JSON, default=list)
    current_role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    edited_by_user: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
