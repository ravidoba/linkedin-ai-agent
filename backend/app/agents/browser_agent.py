"""
LinkedIn Job Scanner — browser_agent.py

How it works
------------
LinkedIn's new /jobs/search-results page is a Server-Driven UI that only
renders the job list in a real Chrome session with full JavaScript execution.
Playwright Chromium (even with anti-detection patches) consistently receives
only the job detail pane — the list panel is never rendered in its DOM.

This scanner therefore uses a two-pronged approach:

  APPROACH A — Direct Voyager API (primary, fastest, most reliable):
    Use Playwright to launch the browser, extract the session cookies
    (li_at and JSESSIONID), then call LinkedIn's Voyager job-search REST
    API directly via httpx.  This returns structured JSON with all job
    fields — no DOM scraping needed.

  APPROACH B — DOM extraction from the existing open session (fallback):
    If the user already has the LinkedIn jobs page open in a browser tab
    that Playwright can connect to, extract job data from the loaded DOM
    via CDP remote debugging.

  APPROACH C — Pagination via Voyager API:
    After extracting the first page (25 jobs), optionally paginate to get
    more results.

Usage (from the backend/ directory in WSL Ubuntu):
    DISPLAY=:0 .venv/bin/python -m app.agents.browser_agent

Requirements:
    pip install httpx  (should already be in the venv)
"""

import asyncio
import json
import os
import re
from pathlib import Path
from urllib.parse import urlencode, urljoin, parse_qs, urlparse

from playwright.async_api import TimeoutError as PWTimeout, async_playwright

# httpx for direct API calls.
try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

PROFILE_DIR = Path.home() / ".linkedin-ai-agent" / "browser-profile"

OUTPUT_FILE = Path(__file__).resolve().parents[2] / "linkedin_jobs.json"

SEARCH_KEYWORDS = "Java Backend Developer"
WORK_TYPE       = "2"   # 2 = Remote

# How many results to fetch per Voyager API page (max 25).
PAGE_SIZE = 25

# How many pages to fetch (1 page = up to 25 jobs).
MAX_PAGES = 1

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _normalise(raw: dict) -> dict:
    job_id   = str(raw.get("job_id")   or "").strip()
    title    = str(raw.get("title")    or "").strip()
    company  = str(raw.get("company")  or "").strip()
    location = str(raw.get("location") or "").strip()
    url      = str(raw.get("url")      or "").strip()

    if url:
        url = urljoin("https://www.linkedin.com", url)

    if not job_id and url:
        m = re.search(r"/jobs/view/(\d+)", url)
        if m:
            job_id = m.group(1)
        else:
            qs = parse_qs(urlparse(url).query)
            job_id = (qs.get("currentJobId") or [""])[0]

    if job_id:
        url = f"https://www.linkedin.com/jobs/view/{job_id}/"

    return dict(job_id=job_id, title=title, company=company,
                location=location, url=url)


def deduplicate(jobs: list[dict]) -> list[dict]:
    seen: set = set()
    unique: list[dict] = []
    for raw in jobs:
        job = _normalise(raw)
        if not job["title"]:
            continue
        key = (f"id:{job['job_id']}" if job["job_id"]
               else (job["title"].casefold(), job["company"].casefold()))
        if key in seen:
            continue
        seen.add(key)
        unique.append(job)
    return unique


# ---------------------------------------------------------------------------
# STEP 1 — Get session cookies via Playwright
# ---------------------------------------------------------------------------

async def get_session_cookies() -> dict:
    """
    Launch a minimal Playwright session to extract the LinkedIn session
    cookies (li_at and JSESSIONID) from the persistent profile.
    Returns a dict of cookie name → value.
    """
    if "DISPLAY" not in os.environ:
        os.environ["DISPLAY"] = ":0"

    async with async_playwright() as pw:
        browser = await pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 800, "height": 600},
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
            ignore_default_args=["--enable-automation"],
        )
        try:
            page = browser.pages[0] if browser.pages else await browser.new_page()

            # Navigate to LinkedIn to ensure the session is active.
            print("[cookies] Navigating to linkedin.com to activate session…",
                  flush=True)
            try:
                await page.goto(
                    "https://www.linkedin.com/",
                    wait_until="domcontentloaded",
                    timeout=30_000,
                )
            except PWTimeout:
                pass

            await page.wait_for_timeout(3000)

            # Extract all cookies for linkedin.com.
            raw_cookies = await browser.cookies("https://www.linkedin.com")
            cookies = {c["name"]: c["value"] for c in raw_cookies}

            important = {k: cookies.get(k, "") for k in
                         ["li_at", "JSESSIONID", "liap", "li_gc"]}
            print(f"[cookies] li_at present    : {bool(important['li_at'])}",
                  flush=True)
            print(f"[cookies] JSESSIONID present: {bool(important['JSESSIONID'])}",
                  flush=True)

            return cookies

        finally:
            await browser.close()


# ---------------------------------------------------------------------------
# STEP 2 — Call Voyager jobs search API directly
# ---------------------------------------------------------------------------

def _build_voyager_url(start: int = 0) -> str:
    """Build the Voyager jobs search API URL."""
    # This is the standard Voyager REST endpoint for job search.
    # decorationId controls which fields are returned.
    params = {
        "decorationId": (
            "com.linkedin.voyager.dash.deco.jobs.njoyn.NjoyNJobPosting-1"
        ),
        "count": PAGE_SIZE,
        "start": start,
        "q": "jobSearch",
        "query": json.dumps({
            "origin": "JOB_SEARCH_PAGE_QUERY_EXPANSION",
            "keywords": SEARCH_KEYWORDS,
            "locationUnion": {"geoId": 92000000},  # Worldwide
            "selectedFilters": {
                "workplaceType": ["2"],   # 2 = Remote
            },
            "spellCorrectionEnabled": True,
        }),
    }
    return "https://www.linkedin.com/voyager/api/jobs/jobPostings?" + urlencode(
        params
    )


def _build_graphql_url(start: int = 0) -> str:
    """
    Build the Voyager GraphQL job-search URL.
    This is the endpoint used by the new jobs search page.
    """
    variables = (
        f"(count:{PAGE_SIZE},start:{start},"
        f"query:(origin:JOB_SEARCH_PAGE_QUERY_EXPANSION,"
        f"keywords:{SEARCH_KEYWORDS},"
        f"selectedFilters:(workplaceType:List({WORK_TYPE})),"
        f"spellCorrectionEnabled:true))"
    )
    return (
        "https://www.linkedin.com/voyager/api/graphql"
        f"?includeWebMetadata=true"
        f"&variables={variables}"
        f"&queryId=voyagerJobsDashJobCards.65543f58c3ffae7ee77af86e59e98d05"
    )


def _safe_text(obj, *keys) -> str:
    for key in keys:
        if isinstance(obj, dict):
            obj = obj.get(key)
        elif isinstance(obj, list) and isinstance(key, int) and key < len(obj):
            obj = obj[key]
        else:
            return ""
        if obj is None:
            return ""
    if isinstance(obj, (dict, list)):
        return ""
    return str(obj).strip()


def _job_id_from_urn(urn: str) -> str:
    m = re.search(r":(\d+)$", urn or "")
    return m.group(1) if m else ""


def _parse_job_posting(node: dict) -> dict | None:
    """Parse a job posting node into a normalised job dict."""
    entity_urn = str(node.get("entityUrn", "") or "")
    job_id = _job_id_from_urn(entity_urn)

    # Title.
    title = (
        _safe_text(node, "title", "text")
        or _safe_text(node, "title")
        or _safe_text(node, "jobPostingTitle")
        or ""
    )

    # Company.
    company = (
        _safe_text(node, "primaryDescription", "text")
        or _safe_text(node, "companyName")
        or _safe_text(node, "subtitle", "text")
        or ""
    )

    # Location.
    location = (
        _safe_text(node, "secondaryDescription", "text")
        or _safe_text(node, "formattedLocation")
        or _safe_text(node, "location")
        or ""
    )

    if not title and not job_id:
        return None

    return dict(
        job_id=job_id,
        title=title,
        company=company,
        location=location,
        url=(f"https://www.linkedin.com/jobs/view/{job_id}/"
             if job_id else ""),
    )


def _parse_jobs_from_response(body: object) -> list[dict]:
    """
    Walk the entire API response recursively.
    Collect any node that looks like a job card/posting.
    """
    jobs: list[dict] = []

    def _walk(node: object) -> None:
        if isinstance(node, dict):
            type_val   = str(node.get("$type", "") or "")
            entity_urn = str(node.get("entityUrn", "") or "")

            is_job = (
                "jobPosting"           in type_val
                or "jobCard"           in type_val
                or "jobResult"         in type_val
                or "jobseekerJobResult" in type_val
                or "fsd_jobPosting"    in entity_urn
                or "fsd_jobCard"       in entity_urn
            )
            if is_job:
                job = _parse_job_posting(node)
                if job:
                    jobs.append(job)

            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(body)

    # Deduplicate within this response.
    seen: set = set()
    unique: list[dict] = []
    for j in jobs:
        k = j["job_id"] or j["title"]
        if k and k not in seen:
            seen.add(k)
            unique.append(j)
    return unique


async def call_voyager_api(cookies: dict, start: int = 0) -> list[dict]:
    """
    Call LinkedIn's Voyager job-search API and return parsed jobs.
    Tries the GraphQL endpoint first, falls back to the REST endpoint.
    """
    if not HAS_HTTPX:
        print("[api] httpx not installed — skipping direct API call", flush=True)
        return []

    # Build cookie header string.
    cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items()
                              if v and k in ["li_at", "JSESSIONID", "liap",
                                             "li_gc", "bcookie", "bscookie",
                                             "lidc", "_ga", "lang"])
    if not cookies.get("li_at"):
        print("[api] No li_at cookie — cannot call Voyager API", flush=True)
        return []

    # Strip quotes from JSESSIONID if present.
    jsessionid = cookies.get("JSESSIONID", "").strip('"')

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/159.0.0.0 Safari/537.36"
        ),
        "Accept": "application/vnd.linkedin.normalized+json+2.1",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Li-Lang": "en_US",
        "X-RestLi-Protocol-Version": "2.0.0",
        "X-Li-Track": json.dumps({
            "clientVersion": "1.13.9426",
            "mpVersion": "1.13.9426",
            "osName": "web",
            "timezoneOffset": 0,
            "timezone": "UTC",
            "deviceFormFactor": "DESKTOP",
            "mpName": "voyager-web",
        }),
        "Csrf-Token": jsessionid,
        "Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items() if v),
        "Referer": "https://www.linkedin.com/jobs/search/",
    }

    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        headers=headers,
    ) as client:

        # Try GraphQL endpoint first.
        graphql_url = _build_graphql_url(start)
        print(f"[api] GraphQL: {graphql_url[:120]}…", flush=True)
        try:
            resp = await client.get(graphql_url)
            print(f"[api] GraphQL status: {resp.status_code}", flush=True)
            if resp.status_code == 200:
                body = resp.json()
                jobs = _parse_jobs_from_response(body)
                if jobs:
                    print(f"[api] GraphQL returned {len(jobs)} job(s)", flush=True)
                    return jobs
                # Save the response for diagnosis.
                (Path(__file__).resolve().parents[2] / "voyager_response.json"
                 ).write_text(json.dumps(body, indent=2, ensure_ascii=False,
                                        default=str), encoding="utf-8")
                print(
                    "[api] GraphQL 200 but no jobs found. "
                    "Response saved to voyager_response.json",
                    flush=True,
                )
        except Exception as exc:
            print(f"[api] GraphQL error: {exc}", flush=True)

        # Fallback: REST endpoint.
        rest_url = _build_voyager_url(start)
        print(f"[api] REST: {rest_url[:120]}…", flush=True)
        try:
            resp = await client.get(rest_url)
            print(f"[api] REST status: {resp.status_code}", flush=True)
            if resp.status_code == 200:
                body = resp.json()
                jobs = _parse_jobs_from_response(body)
                if jobs:
                    print(f"[api] REST returned {len(jobs)} job(s)", flush=True)
                    return jobs
                (Path(__file__).resolve().parents[2] / "voyager_rest_response.json"
                 ).write_text(json.dumps(body, indent=2, ensure_ascii=False,
                                        default=str), encoding="utf-8")
                print(
                    "[api] REST 200 but no jobs found. "
                    "Response saved to voyager_rest_response.json",
                    flush=True,
                )
            else:
                print(f"[api] REST {resp.status_code}: {resp.text[:300]}",
                      flush=True)
        except Exception as exc:
            print(f"[api] REST error: {exc}", flush=True)

    return []


# ---------------------------------------------------------------------------
# SCAN
# ---------------------------------------------------------------------------

async def scan_jobs() -> list[dict]:
    # 1. Get session cookies from the persistent profile.
    print("[step1] Extracting session cookies…", flush=True)
    cookies = await get_session_cookies()

    if not cookies.get("li_at"):
        print(
            "[step1] WARNING: No li_at cookie found.\n"
            "        The browser profile may not have an active LinkedIn session.\n"
            "        Open the browser manually, log in to LinkedIn, then re-run.",
            flush=True,
        )

    # 2. Call Voyager API for each requested page.
    all_jobs: list[dict] = []
    if HAS_HTTPX and cookies.get("li_at"):
        for page_num in range(MAX_PAGES):
            start = page_num * PAGE_SIZE
            print(
                f"[step2] Fetching page {page_num + 1}/{MAX_PAGES} "
                f"(start={start})…",
                flush=True,
            )
            page_jobs = await call_voyager_api(cookies, start=start)
            all_jobs.extend(page_jobs)
            if len(page_jobs) < PAGE_SIZE:
                print(f"[step2] Got {len(page_jobs)} < {PAGE_SIZE} — "
                      "reached end of results.", flush=True)
                break
    else:
        if not HAS_HTTPX:
            print("[step2] httpx not available — skipping API call", flush=True)

    jobs = deduplicate(all_jobs)
    print(f"[scan] Total unique jobs from API: {len(jobs)}", flush=True)
    return jobs


# ---------------------------------------------------------------------------
# SAVE
# ---------------------------------------------------------------------------

def save_jobs(jobs: list[dict]) -> None:
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(jobs, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\n[save] Wrote {len(jobs)} jobs → {OUTPUT_FILE}", flush=True)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

async def main() -> None:
    print("=" * 60, flush=True)
    print("LinkedIn Job Scanner", flush=True)
    print(f"Profile : {PROFILE_DIR}", flush=True)
    print(f"Output  : {OUTPUT_FILE}", flush=True)
    print("=" * 60, flush=True)

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    jobs = await scan_jobs()

    print("\n" + "=" * 60, flush=True)
    print(f"TOTAL UNIQUE JOBS FOUND: {len(jobs)}", flush=True)
    print("=" * 60, flush=True)

    for i, job in enumerate(jobs, 1):
        print(
            f"\n  #{i:03d}  {job['title']}\n"
            f"       Company : {job['company'] or '(empty)'}\n"
            f"       Location: {job['location'] or '(empty)'}\n"
            f"       ID      : {job['job_id']}\n"
            f"       URL     : {job['url']}",
            flush=True,
        )

    save_jobs(jobs)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
