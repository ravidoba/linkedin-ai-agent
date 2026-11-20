
import json

from pydantic import BaseModel, Field, ValidationError

from app.services.ollama_service import ask_ollama


class AIMatchResult(BaseModel):
    match_score: int = Field(ge=0, le=100)
    matched_skills: list[str]
    missing_skills: list[str]
    experience_match: bool | None = None
    years_of_experience: float | None = None
    required_experience_years: float | None = None
    explanation: str
    needs_review: bool = False


def review_result(message: str) -> dict:
    return {
        "match_score": 0,
        "matched_skills": [],
        "missing_skills": [],
        "experience_match": None,
        "years_of_experience": None,
        "required_experience_years": None,
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
3. Evaluate required technical skills and experience separately.
4. List ONLY technical skills the job description states as required/mandatory.
   Ignore preferred, optional, "nice to have" or "plus" skills.
   Put each required skill in matched_skills if the resume supports it, otherwise in missing_skills.
5. match_score is the percentage (0-100) of required skills that are matched.
6. required_experience_years is the MINIMUM years of experience the job requires
   (for "3-5 years" use 3, for "5+ years" use 5), or null if the job does not state it.
7. years_of_experience is the candidate's total professional experience in years,
   calculated only from the resume's dates, or null if it cannot be determined.
8. experience_match must be true, false, or null.
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
    "required_experience_years": null,
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

        data = result.model_dump()

        # Skills: percentage of required skills supported by the resume.
        matched = {s.strip().lower() for s in data["matched_skills"] if s.strip()}
        missing = {s.strip().lower() for s in data["missing_skills"] if s.strip()} - matched
        if not matched and not missing:
            return review_result("No required skills could be determined from the job description.")
        data["match_score"] = round(len(matched) / (len(matched) + len(missing)) * 100)

        # Experience: candidate years must meet the job's minimum; unknown stays uncertain.
        have = data["years_of_experience"]
        need = data["required_experience_years"]
        if have is not None and need is not None:
            data["experience_match"] = have >= need
        else:
            data["experience_match"] = None
            data["needs_review"] = True
            data["explanation"] = (
                data["explanation"] + " Experience requirement could not be confirmed."
            ).strip()

        return data

    except (json.JSONDecodeError, ValidationError):
        return review_result(
            "AI returned an invalid response."
        )
