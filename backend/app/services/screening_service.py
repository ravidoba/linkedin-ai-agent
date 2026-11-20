"""
Screening-question persistence service.

Keeps database access separate from browser interaction,
following the pattern used by the existing services.
"""

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.screening_answer import ScreeningAnswer


async def get_saved_answer(
    db: AsyncSession,
    question_text: str,
) -> ScreeningAnswer | None:
    """Return the saved answer for question_text, or None if not found."""
    return await db.scalar(
        select(ScreeningAnswer).where(
            ScreeningAnswer.question_text == question_text
        )
    )


async def save_answer(
    db: AsyncSession,
    question_text: str,
    answer_text: str,
    input_type: str = "text",
    provenance: str = "user",
) -> ScreeningAnswer:
    """
    Upsert a confirmed answer for question_text.
    Updates answer, input_type, and provenance if the row already exists.
    Only 'user'-confirmed answers should overwrite 'resume'-derived ones.
    """
    existing = await get_saved_answer(db, question_text)
    if existing:
        existing.answer_text = answer_text
        existing.input_type = input_type
        existing.provenance = provenance
        await db.commit()
        await db.refresh(existing)
        return existing

    record = ScreeningAnswer(
        question_text=question_text,
        answer_text=answer_text,
        input_type=input_type,
        provenance=provenance,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


# ---------------------------------------------------------------------------
# User-scoped screening answers
#
# screening_answers has no user_id column (and no schema change is allowed here), so
# the owner is encoded in the unique question_text key: "screen:<user_id>:<question>".
# The prefix keeps answers private per user and apart from "contact:" values.
# ---------------------------------------------------------------------------

_OPTION_TYPES = ("select", "radio", "checkbox")
_BOOL_WORDS = {"yes", "y", "true", "checked", "no", "n", "false", "unchecked"}


def normalize_question(text: str) -> str:
    """Lower-case, collapse whitespace, drop trailing punctuation / required markers."""
    t = re.sub(r"\s+", " ", text or "").strip().lower()
    return re.sub(r"[\s*?:.!]+$", "", t)


def _screening_key(user_id: int, question_text: str) -> str:
    return f"screen:{user_id}:{normalize_question(question_text)}"


def _compatible(row: ScreeningAnswer, input_type: str | None, options: list[str] | None) -> bool:
    """True when the saved answer can be applied to the current control."""
    answer = (row.answer_text or "").strip()
    if not answer:
        return False
    if input_type in _OPTION_TYPES:
        # Imported lazily: browser_agent already imports this module lazily.
        from app.agents.browser_agent import _resolve_option

        if _resolve_option(answer, options or []) is not None:
            return True
        # A single checkbox (Yes/No) also accepts true/false style answers.
        return input_type == "checkbox" and answer.lower() in _BOOL_WORDS
    # Text-like control: an answer chosen from fixed options is not free text.
    return row.input_type not in _OPTION_TYPES


async def get_screening_answer(
    db: AsyncSession,
    user_id: int | None,
    question_text: str,
    input_type: str | None = None,
    options: list[str] | None = None,
) -> ScreeningAnswer | None:
    """
    Saved answer of THIS user for the same question (normalised exact match only),
    or None when absent, when no user is given, or when the saved answer does not fit
    the current control type/options (the question then stays unanswered).
    """
    if user_id is None or not normalize_question(question_text):
        return None
    row = await get_saved_answer(db, _screening_key(user_id, question_text))
    if row is None or not _compatible(row, input_type, options):
        return None
    return row


async def save_screening_answer(
    db: AsyncSession,
    user_id: int,
    question_text: str,
    answer_text: str,
    input_type: str = "text",
    provenance: str = "user",
) -> ScreeningAnswer:
    """Upsert a user-confirmed answer under this user's key."""
    return await save_answer(
        db,
        question_text=_screening_key(user_id, question_text),
        answer_text=answer_text,
        input_type=input_type,
        provenance=provenance,
    )


async def list_saved_answers(
    db: AsyncSession,
) -> list[ScreeningAnswer]:
    """Return all saved screening answers ordered by question text."""
    result = await db.scalars(
        select(ScreeningAnswer).order_by(ScreeningAnswer.question_text)
    )
    return list(result.all())
