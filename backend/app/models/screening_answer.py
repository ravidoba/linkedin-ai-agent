
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class ScreeningAnswer(Base):
    """
    Persists user-confirmed answers to LinkedIn screening questions so
    they can be reused across future applications.

    question_text : the exact question label shown in the form
    answer_text   : the user-confirmed answer
    input_type    : "text", "select", "radio", "checkbox" — informs
                    how the answer should be applied to the form control
    provenance    : "user" (confirmed by user) or "resume" (derived from
                    resume text without user confirmation — lower trust)
    """

    __tablename__ = "screening_answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    question_text: Mapped[str] = mapped_column(Text, unique=True, index=True)
    answer_text: Mapped[str] = mapped_column(Text)
    input_type: Mapped[str] = mapped_column(String(50), default="text")
    provenance: Mapped[str] = mapped_column(String(50), default="user")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
