"""
User-provided default answers for Easy Apply screening questions (README.md
manual flow), applied only to questions they clearly cover.

Anything not clearly covered returns None, so the question goes to the user.
Legal, visa, personal and background questions are never answered here.
"""
import re

from app.core.config import get_settings

# Never auto-answered: these need the user's own, case-by-case answer.
_SENSITIVE = re.compile(
    r"sponsor|visa|work permit|authori[sz]|citizen|clearance|convict|criminal|felon|"
    r"background check|drug|disab|veteran|gender|pronoun|race|ethnic|religio|"
    r"\bage\b|date of birth|pregnan|marital|relocat|security",
    re.I,
)
# Skills the user's default experience applies to.
_COVERED_SKILL = re.compile(
    r"\bjava\b|back[\s-]?end|front[\s-]?end|full[\s-]?stack|"
    r"software (development|engineering|developer|engineer)",
    re.I,
)
_CURRENT_SALARY = re.compile(r"current (salary|ctc|compensation|pay|package)", re.I)
_EXPECTED_SALARY = re.compile(
    r"expected (salary|ctc|compensation|pay|package)|salary expectation|desired (salary|compensation)",
    re.I,
)
_NOTICE = re.compile(r"notice period|serving (your |a )?notice|\bnotice\b.*\bdays?\b", re.I)
_TOTAL_EXPERIENCE = re.compile(
    r"total (years of )?(work |professional )?experience|overall (work |professional )?experience|"
    r"years of (professional|work|total|overall) experience",
    re.I,
)
_YEARS_OF_EXPERIENCE = re.compile(r"\byears?\b.*\bexperience\b|\bexperience\b.*\byears?\b", re.I)
_REMOTE = re.compile(r"\bremote(ly)?\b|work from home|\bwfh\b", re.I)
_START_SOON = re.compile(
    r"start immediately|join immediately|immediate joiner|available to (start|join)|"
    r"start (work|working)? ?(right away|asap|soon)",
    re.I,
)
_YES = re.compile(r"^\s*yes\s*$", re.I)
# "experience with X", "experience in X", "experience using X", "X experience" phrasing.
_NAMES_SKILL = re.compile(r"\bexperience\b[^?]*?\b(with|in|using|on|of working with)\s+\S", re.I)


def _offers_yes(input_type: str, options: list[str]) -> bool:
    """True for Yes/No style controls (radio, select, single checkbox)."""
    return input_type in ("radio", "select", "checkbox") and any(_YES.match(o or "") for o in options)


_LEVEL_RANK = {"diploma": 1, "bachelor": 2, "master": 3, "phd": 4}
_ASKED_LEVEL = (
    (re.compile(r"ph\.?\s?d|doctor(ate|al)", re.I), "phd"),
    (re.compile(r"master'?s?|\bm\.?\s?tech\b|\bm\.?\s?s\b|\bmba\b|post[\s-]?graduat", re.I), "master"),
    (re.compile(r"bachelor'?s?|\bb\.?\s?tech\b|\bb\.?\s?e\b|\bb\.?\s?s\b|undergraduate|graduat", re.I), "bachelor"),
    (re.compile(r"diploma", re.I), "diploma"),
)


def _years_text(value: float) -> str:
    """Whole years, rounded down so experience is never overstated (5.2 -> "5")."""
    return str(int(value))


def _profile_skill(question: str, profile: dict | None) -> dict | None:
    """The longest profile skill named in the question ("Spring Boot" over "Spring")."""
    if not profile:
        return None
    from app.services.profile_matching_service import canonical_skill

    q = " " + canonical_skill(question) + " "
    best = None
    for skill in profile.get("skills") or []:
        name = canonical_skill(skill.get("name", ""))
        if len(name) >= 2 and re.search(rf"(?<![a-z0-9+#]){re.escape(name)}(?![a-z0-9+#])", q):
            if best is None or len(name) > len(canonical_skill(best["name"])):
                best = skill
    return best


def _has_education(question: str, profile: dict | None) -> bool:
    """True when the profile shows the degree level the question asks about (or higher)."""
    if not profile or not profile.get("education"):
        return False
    asked = next((level for rx, level in _ASKED_LEVEL if rx.search(question)), None)
    if asked is None:
        return False
    best = max((_LEVEL_RANK.get(e.get("level"), 0) for e in profile["education"]), default=0)
    return best >= _LEVEL_RANK[asked]


def default_answer(
    question: str, input_type: str, options: list[str], profile: dict | None = None,
) -> str | None:
    """
    Return the user's answer for a clearly covered question, else None (ask the user).
    The resume profile (skills with years, education, total experience) is used first;
    the fixed .env answers cover salary, notice period and the defaults.
    """
    q = question or ""
    if not q.strip() or _SENSITIVE.search(q):
        return None
    s = get_settings()

    if _CURRENT_SALARY.search(q):
        return s.APPLY_CURRENT_SALARY
    if _EXPECTED_SALARY.search(q):
        return s.APPLY_EXPECTED_SALARY
    if _NOTICE.search(q):
        return s.APPLY_NOTICE_PERIOD

    skill = _profile_skill(q, profile)

    if _offers_yes(input_type, options):
        # "Have you completed ... Bachelor's Degree?" from the profile's education.
        if _has_education(q, profile):
            return "Yes"
        # "Do you have experience with Kafka?": a skill in the profile.
        if skill is not None and re.search(r"experience|worked|familiar|knowledge|proficien|skill", q, re.I):
            return "Yes"
        # "Do you have experience with Java?", "Are you comfortable working remotely?"
        if _COVERED_SKILL.search(q) or _REMOTE.search(q) or _START_SOON.search(q):
            return "Yes"
        return None

    # "...years of work experience do you have WITH MongoDB?" names one skill: it is
    # a skill question even though "years of work experience" also reads as total.
    if _YEARS_OF_EXPERIENCE.search(q) and (_NAMES_SKILL.search(q) or skill is not None):
        if skill is not None and skill.get("years") is not None:
            return _years_text(skill["years"])
        if _COVERED_SKILL.search(q):
            return s.APPLY_SKILL_EXPERIENCE_YEARS
        return None
    if _TOTAL_EXPERIENCE.search(q):
        total = (profile or {}).get("total_experience_years")
        return _years_text(total) if total is not None else s.APPLY_TOTAL_EXPERIENCE_YEARS
    if _YEARS_OF_EXPERIENCE.search(q) and _COVERED_SKILL.search(q):
        return s.APPLY_SKILL_EXPERIENCE_YEARS
    return None
