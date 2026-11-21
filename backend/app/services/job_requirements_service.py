"""
Job requirements: read once per LinkedIn job ID from the job description with a
short AI prompt (the resume is not sent), cached in jobs.requirements.
"""
import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from app.services.ollama_service import ask_ollama

_LEVELS = ("phd", "master", "bachelor", "diploma")


class _Requirements(BaseModel):
    required_skills: list[str] = Field(default_factory=list)
    min_years: float | None = Field(default=None, ge=0, le=40)
    education_level: str | None = None


_PROMPT = """
Read the job description and return ONLY a JSON object, no markdown:
{"required_skills": ["Java", "Spring Boot"], "min_years": 3, "education_level": "bachelor"}
Rules:
1. required_skills: only technical skills, tools, languages, frameworks, databases or cloud
   services the job states as required or mandatory. Ignore "preferred", "nice to have",
   "plus", "bonus" and soft skills. Use the common short name ("PostgreSQL", "AWS").
2. min_years: the MINIMUM years of experience required ("3-5 years" -> 3, "5+ years" -> 5),
   or null when the job does not state it.
3. education_level: the minimum degree required, one of phd, master, bachelor, diploma,
   or null when not stated.
4. Use only what the description says. Never invent requirements.

JOB DESCRIPTION:
<job_description>
%s
</job_description>
"""


def _normalize(data: dict[str, Any]) -> dict[str, Any]:
    req = _Requirements.model_validate(data)
    skills, seen = [], set()
    for s in req.required_skills:
        name = " ".join(str(s).split())
        if name and len(name) <= 100 and name.casefold() not in seen:
            seen.add(name.casefold())
            skills.append(name)
    level = (req.education_level or "").strip().lower() or None
    return {
        "required_skills": skills,
        "min_years": req.min_years,
        "education_level": level if level in _LEVELS else None,
    }


async def extract_requirements(description: str) -> dict[str, Any] | None:
    """Ask the AI model for the job's requirements; None when the reply is unusable."""
    if not (description or "").strip():
        return None
    raw = await ask_ollama(_PROMPT % description[:8000])
    try:
        start, end = raw.index("{"), raw.rindex("}") + 1
        return _normalize(json.loads(raw[start:end]))
    except (ValueError, ValidationError, TypeError) as exc:
        print(f"[requirements] AI reply could not be used: {exc}", flush=True)
        return None


async def get_job_requirements(db: AsyncSession, job_row: Job, description: str) -> dict[str, Any] | None:
    """Cached requirements for this LinkedIn job ID; read from the description only once."""
    if job_row.requirements is not None:
        return job_row.requirements
    requirements = await extract_requirements(description or job_row.description or "")
    if requirements is not None:
        job_row.requirements = requirements
        await db.commit()
    return requirements
