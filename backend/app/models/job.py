
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True
    )

    linkedin_job_id: Mapped[str] = mapped_column(
        String(100), unique=True, index=True
    )

    title: Mapped[str] = mapped_column(String(255))
    company: Mapped[str] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    job_url: Mapped[str | None] = mapped_column(Text)

    match_score: Mapped[float | None] = mapped_column(Float)

    status: Mapped[str] = mapped_column(
        String(50), default="new"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
