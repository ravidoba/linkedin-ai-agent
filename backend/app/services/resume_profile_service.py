"""
Resume profile: read the resume ONCE with the AI model into structured facts
(skills with years, total experience, education, current role), saved in
resume_profiles. Matching and screening answers use the profile, not the full
resume text. A profile edited by the user is never overwritten automatically.
"""
import asyncio
import json
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import AsyncSessionLocal
from app.models.resume import Resume
from app.models.resume_profile import ResumeProfile
from app.services.ollama_service import ask_ollama

EDUCATION_LEVELS = ("phd", "master", "bachelor", "diploma", "other")


class _Skill(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    years: float | None = Field(default=None, ge=0, le=60)


class _Education(BaseModel):
    degree: str = Field(default="", max_length=200)
    level: str = "other"
    field: str = Field(default="", max_length=200)


class _Profile(BaseModel):
    skills: list[_Skill] = []
    total_experience_years: float | None = Field(default=None, ge=0, le=60)
    education: list[_Education] = []
    current_role: str | None = Field(default=None, max_length=255)


# The model only lists facts; numbers (total years) are computed in code, because
# language models are unreliable at date arithmetic.
_PROMPT = """
Read the resume and return ONLY a JSON object, no markdown, with this shape:
{
  "skills": ["Java", "Spring Boot", "PostgreSQL"],
  "jobs": [{"title": "Software Engineer", "company": "Acme", "start": "2021-05", "end": "2023-10"}],
  "education": [{"degree": "Bachelor of Engineering", "level": "bachelor", "field": "Computer Engineering"}],
  "current_role": "Senior Software Engineer"
}
Rules:
1. Use only facts written in the resume. Never invent skills, jobs, dates or degrees.
2. skills: technical skills, tools, languages, frameworks, databases and cloud services listed.
   Use the common short name ("Spring Boot", "PostgreSQL", "AWS").
3. jobs: every paid job with its dates as "YYYY-MM"; use "present" for a current job.
   If one employer has several date ranges, add one entry per range.
   Do NOT include studies, education, career breaks or gaps.
4. education level is one of: phd, master, bachelor, diploma, other.
5. current_role: the most recent job title, or null.

RESUME:
<resume>
%s
</resume>
"""


def _month_index(value: str, today: tuple[int, int]) -> int | None:
    """'2021-05' -> months since year 0; 'present' -> today; else None."""
    value = (value or "").strip().lower()
    if value in ("present", "current", "now", "till date", "today"):
        return today[0] * 12 + today[1] - 1
    m = re.match(r"^(\d{4})-(\d{1,2})$", value)
    if not m or not 1 <= int(m.group(2)) <= 12:
        return None
    return int(m.group(1)) * 12 + int(m.group(2)) - 1


def total_years_from_jobs(jobs: list[dict], today: tuple[int, int] | None = None) -> float | None:
    """Total professional years from job date ranges, merging overlaps; None if no dates."""
    from datetime import date

    if today is None:
        d = date.today()
        today = (d.year, d.month)
    ranges = []
    for job in jobs or []:
        start = _month_index(str(job.get("start", "")), today)
        end = _month_index(str(job.get("end", "")), today)
        if start is None or end is None or end < start:
            continue
        ranges.append((start, end + 1))  # end month counts as worked
    if not ranges:
        return None
    ranges.sort()
    months, cur_start, cur_end = 0, *ranges[0]
    for s, e in ranges[1:]:
        if s <= cur_end:
            cur_end = max(cur_end, e)
        else:
            months += cur_end - cur_start
            cur_start, cur_end = s, e
    months += cur_end - cur_start
    return round(months / 12, 1)


def normalize_profile(data: dict[str, Any]) -> dict[str, Any]:
    """Validate and clean a profile dict (from the model or from the user's edit)."""
    profile = _Profile.model_validate(data)
    skills: dict[str, dict] = {}
    for s in profile.skills:
        name = re.sub(r"\s+", " ", s.name).strip()
        key = name.casefold()
        if not name or key in skills:
            continue
        skills[key] = {"name": name, "years": round(s.years, 1) if s.years is not None else None}
    education = []
    for e in profile.education:
        level = (e.level or "other").strip().lower()
        education.append({
            "degree": e.degree.strip(),
            "level": level if level in EDUCATION_LEVELS else "other",
            "field": e.field.strip(),
        })
    return {
        "skills": list(skills.values()),
        "total_experience_years": (
            round(profile.total_experience_years, 1)
            if profile.total_experience_years is not None else None
        ),
        "education": education,
        "current_role": (profile.current_role or "").strip() or None,
    }


_MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
_MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
_RANGE_RE = re.compile(
    rf"\b{_MON}\s+((?:19|20)\d\d)\s*(?:[–—-]|to)\s*(?:{_MON}\s+((?:19|20)\d\d)|(present|current|now|till date))",
    re.I,
)
# Lines that describe studies or breaks, not paid work.
_NOT_WORK_RE = re.compile(
    r"stud(y|ies)|career break|sabbatical|education|universit|college|school|degree|\bgap\b", re.I)


def job_ranges_from_text(resume_text: str) -> list[dict]:
    """Work date ranges ("Sep 2018 – Jul 2019", "May 2025 – Present") read straight from the text."""
    jobs = []
    for line in (resume_text or "").splitlines():
        if _NOT_WORK_RE.search(line):
            continue
        for m in _RANGE_RE.finditer(line):
            start = f"{m.group(2)}-{_MONTHS[m.group(1)[:3].lower()]:02d}"
            end = "present" if m.group(5) else f"{m.group(4)}-{_MONTHS[m.group(3)[:3].lower()]:02d}"
            jobs.append({"start": start, "end": end})
    return jobs


async def extract_profile(resume_text: str) -> dict[str, Any] | None:
    """Ask the AI model once for the resume's facts; None when the reply is unusable."""
    if not (resume_text or "").strip():
        return None
    raw = await ask_ollama(_PROMPT % resume_text[:12000])
    try:
        start, end = raw.index("{"), raw.rindex("}") + 1
        data = json.loads(raw[start:end])
        skills = data.get("skills") or []
        return normalize_profile({
            # Years per skill are not reliably in a resume: left empty for the user to fill.
            "skills": [{"name": n.strip(), "years": None}
                       for n in (s if isinstance(s, str) else (s or {}).get("name", "") for s in skills)
                       if isinstance(n, str) and 0 < len(n.strip()) <= 100],
            # Dates read by code from the text win; the model's job list is a fallback.
            "total_experience_years": total_years_from_jobs(
                job_ranges_from_text(resume_text) or data.get("jobs") or []
            ),
            "education": data.get("education") or [],
            "current_role": data.get("current_role"),
        })
    except (ValueError, ValidationError, TypeError, AttributeError) as exc:
        print(f"[profile] AI reply could not be used: {exc}", flush=True)
        return None


def profile_to_dict(row: ResumeProfile) -> dict[str, Any]:
    return {
        "resume_id": row.resume_id,
        "skills": row.skills or [],
        "total_experience_years": row.total_experience_years,
        "education": row.education or [],
        "current_role": row.current_role,
        "edited_by_user": row.edited_by_user,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


async def get_profile(db: AsyncSession, resume_id: int) -> ResumeProfile | None:
    return await db.scalar(select(ResumeProfile).where(ResumeProfile.resume_id == resume_id))


async def build_profile(
    db: AsyncSession, resume: Resume, *, force: bool = False, overwrite_edits: bool = False,
) -> ResumeProfile | None:
    """
    Read the resume once and save its profile. An existing profile is kept unless
    force=True; a profile edited by the user is replaced only with overwrite_edits=True
    (the user confirmed it).
    """
    existing = await get_profile(db, resume.id)
    if existing is not None and (not force or (existing.edited_by_user and not overwrite_edits)):
        return existing
    data = await extract_profile(resume.content)
    if data is None:
        return existing
    if existing is None:
        existing = ResumeProfile(resume_id=resume.id, user_id=resume.user_id)
        db.add(existing)
    existing.skills = data["skills"]
    existing.total_experience_years = data["total_experience_years"]
    existing.education = data["education"]
    existing.current_role = data["current_role"]
    existing.edited_by_user = False
    await db.commit()
    await db.refresh(existing)
    return existing


async def get_or_build_profile(db: AsyncSession, resume: Resume) -> dict[str, Any] | None:
    """Profile dict for matching; built on first use for resumes uploaded earlier."""
    row = await build_profile(db, resume)
    return profile_to_dict(row) if row is not None else None


# Strong references so background builds are not garbage-collected mid-flight.
_build_tasks: set[asyncio.Task] = set()


def build_profile_in_background(resume_id: int) -> None:
    """Start reading a just-uploaded resume without delaying the upload response."""

    async def _run() -> None:
        try:
            async with AsyncSessionLocal() as db:
                resume = await db.get(Resume, resume_id)
                if resume is not None:
                    await build_profile(db, resume)
        except Exception as exc:
            print(f"[profile] building the profile of resume {resume_id} failed: {exc}", flush=True)

    task = asyncio.get_running_loop().create_task(_run())
    _build_tasks.add(task)
    task.add_done_callback(_build_tasks.discard)
