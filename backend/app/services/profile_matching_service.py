"""
Plain-code job matching: a job's cached requirements against the resume profile.
Same rules as before (required-skills match >= threshold AND experience met), but
instant, the same result every time, and with a readable reason for every skip.
"""
import re
from typing import Any

from app.services.job_matching_service import SKILLS

# alias -> canonical skill name, e.g. "postgres" -> "postgresql", "k8s" -> "kubernetes"
_ALIASES = {alias: canonical for canonical, aliases in SKILLS.items() for alias in aliases}


def canonical_skill(name: str) -> str:
    """Lower-case, single-spaced, punctuation-light form used to compare skill names."""
    text = re.sub(r"[^a-z0-9+#.\s]", " ", (name or "").lower())
    text = re.sub(r"\.js\b", "", text)          # "react.js" -> "react"
    text = re.sub(r"\s+", " ", text).strip(" .")
    text = re.sub(r"\b(apis)\b", "api", text)   # "rest apis" -> "rest api"
    return _ALIASES.get(text, text)


def _skill_matches(required: str, have: set[str]) -> bool:
    r = canonical_skill(required)
    if not r:
        return False
    if r in have:
        return True
    r_words = set(r.split())
    for h in have:
        # Whole-word containment: "spring" ~ "spring boot", "aws" ~ "aws lambda".
        if len(h) >= 2 and (set(h.split()) <= r_words or r_words <= set(h.split())):
            return True
    return False


def _fmt_years(value: float | None) -> str:
    if value is None:
        return "unknown"
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def match_job_to_profile(
    job: dict[str, Any],
    requirements: dict[str, Any] | None,
    profile: dict[str, Any],
    threshold: int,
) -> dict[str, Any]:
    """Return the same shape as score_job(), with a readable match_reason."""
    base = {**job, "matched_skills": [], "missing_skills": [], "experience_match": None,
            "years_of_experience": profile.get("total_experience_years"),
            "required_experience_years": None}
    required = (requirements or {}).get("required_skills") or []
    if requirements is None or not required:
        return {**base, "match_score": None, "eligible": False, "needs_review": True,
                "match_reason": "The job's required skills could not be read from its description."}

    have = {canonical_skill(s.get("name", "")) for s in profile.get("skills") or []} - {""}
    matched = [s for s in required if _skill_matches(s, have)]
    missing = [s for s in required if s not in matched]
    score = round(len(matched) / len(required) * 100)

    need = requirements.get("min_years")
    total = profile.get("total_experience_years")
    if need is None:
        experience_match = True  # the job states no minimum
    elif total is None:
        experience_match = None  # unknown: never treated as a match
    else:
        experience_match = float(total) >= float(need)

    if score < threshold:
        reason = (f"Missing skills: {', '.join(missing)} "
                  f"(match {score}%, needs {threshold}%).")
    elif experience_match is False:
        reason = (f"Needs {_fmt_years(need)} years of experience; "
                  f"your profile has {_fmt_years(total)}.")
    elif experience_match is None:
        reason = ("The job needs " + _fmt_years(need) + " years of experience, but your profile "
                  "has no total experience. Add it on the Profile screen.")
    else:
        reason = f"Skills match {score}%" + (f", {_fmt_years(need)}+ years required." if need else ".")

    return {
        **base,
        "match_score": score,
        "matched_skills": matched,
        "missing_skills": missing,
        "experience_match": experience_match,
        "required_experience_years": need,
        "eligible": score >= threshold and experience_match is True,
        "needs_review": experience_match is None,
        "match_reason": reason,
    }
