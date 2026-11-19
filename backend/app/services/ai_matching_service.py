
import json

from pydantic import BaseModel, Field, ValidationError

from app.services.ollama_service import ask_ollama


class AIMatchResult(BaseModel):
    match_score: int = Field(ge=0, le=100)
    matched_skills: list[str]
    missing_skills: list[str]
    experience_match: bool | None = None
    years_of_experience: float | None = None
    explanation: str
    needs_review: bool = False


def review_result(message: str) -> dict:
    return {
        "match_score": 0,
        "matched_skills": [],
        "missing_skills": [],
        "experience_match": None,
        "years_of_experience": None,
        "explanation": message,
        "needs_review": True,
    }


async def calculate_ai_job_match(
    resume_text: str,
    job_description: str,
) -> dict:

    if not resume_text.strip():
        return review_result("Resume is empty.")

    if not job_description.strip():
        return review_result("Job description is empty.")

    prompt = f"""
You are an accurate AI resume-to-job matching assistant.

Compare the candidate's resume against the job description.

IMPORTANT RULES:
1. Use only qualifications supported by the resume.
2. Never invent skills, experience, or certifications.
3. Evaluate technical skills, experience, and mandatory requirements.
4. Calculate a match score between 0 and 100.
5. Missing mandatory requirements must reduce the score.
6. If experience is unknown, use null.
7. experience_match must be true, false, or null.
8. years_of_experience must be a number or null.
9. If information is insufficient, set needs_review to true.
10. Return ONLY valid JSON.
11. Do not include markdown, comments, or text outside JSON.

REQUIRED JSON FORMAT:
{{
    "match_score": 0,
    "matched_skills": [],
    "missing_skills": [],
    "experience_match": null,
    "years_of_experience": null,
    "explanation": "",
    "needs_review": false
}}

RESUME:
<resume>
{resume_text[:12000]}
</resume>

JOB DESCRIPTION:
<job_description>
{job_description[:10000]}
</job_description>
"""

    raw_response = await ask_ollama(prompt)
    print("RAW AI RESPONSE:", repr(raw_response))
    try:
        parsed_response = json.loads(raw_response)

        result = AIMatchResult.model_validate(
            parsed_response
        )

        return result.model_dump()

    except (json.JSONDecodeError, ValidationError):
        return review_result(
            "AI returned an invalid response."
        )
