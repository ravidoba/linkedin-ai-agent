
import re


SKILLS = {
    "java": ["java"],
    "spring boot": ["spring boot", "springboot"],
    "python": ["python"],
    "postgresql": ["postgresql", "postgres"],
    "mysql": ["mysql"],
    "docker": ["docker"],
    "kubernetes": ["kubernetes", "k8s"],
    "aws": ["aws", "amazon web services"],
    "azure": ["azure"],
    "gcp": ["gcp", "google cloud"],
    "microservices": ["microservices", "microservice"],
    "rest api": ["rest api", "restful api", "rest apis"],
    "kafka": ["kafka"],
    "redis": ["redis"],
    "mongodb": ["mongodb", "mongo db"],
    "react": ["react", "reactjs", "react.js"],
    "typescript": ["typescript"],
    "javascript": ["javascript"],
    "git": ["git"],
    "jenkins": ["jenkins"],
    "terraform": ["terraform"],
    "hibernate": ["hibernate"],
    "jpa": ["jpa"],
    "sql": ["sql"],
}


def extract_skills(text: str) -> set[str]:
    text = text.lower()
    found = set()

    for skill, aliases in SKILLS.items():
        for alias in aliases:
            pattern = rf"(?<!\w){re.escape(alias)}(?!\w)"
            if re.search(pattern, text):
                found.add(skill)
                break

    return found


def calculate_job_match(
    resume_text: str,
    job_description: str,
) -> dict:
    resume_skills = extract_skills(resume_text)
    job_skills = extract_skills(job_description)

    if not job_skills:
        return {
            "match_score": 0,
            "matched_skills": [],
            "missing_skills": [],
            "eligible": False,
            "needs_review": True,
        }

    matched = resume_skills & job_skills
    missing = job_skills - resume_skills

    score = round(len(matched) / len(job_skills) * 100, 2)

    return {
        "match_score": score,
        "matched_skills": sorted(matched),
        "missing_skills": sorted(missing),
        "eligible": score >= 75,
        "needs_review": False,
    }
