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

# Matching services — optional when running browser_agent standalone.
try:
    from app.services.ai_matching_service import calculate_ai_job_match
    from app.services.job_matching_service import calculate_job_match
    HAS_MATCHING = True
except ImportError:
    HAS_MATCHING = False

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

PROFILE_DIR = Path.home() / ".linkedin-ai-agent" / "browser-profile"

OUTPUT_FILE = Path(__file__).resolve().parents[2] / "linkedin_jobs.json"

# Uploaded resume files (kept under their original name so LinkedIn shows the same name).
RESUME_DIR = Path.home() / ".linkedin-ai-agent" / "resumes"


# ---------------------------------------------------------------------------
# VISIBLE CURSOR (cosmetic overlay for the headed browser)
#
# Playwright's synthetic mouse is invisible, so a small overlay element follows the
# real mouse events of the page (mousemove / mousedown). It is purely visual:
# pointer-events:none, never intercepts a click, and does not generate input itself.
# Set AGENT_VISIBLE_CURSOR=0 to disable it.
# ---------------------------------------------------------------------------

CURSOR_ENABLED = os.environ.get("AGENT_VISIBLE_CURSOR", "1") != "0"

_CURSOR_JS = """
(() => {
  if (window.top !== window || window.__aiCursor) return;
  const KEY = '__aiCursorPos';
  let pos = null;
  try { pos = JSON.parse(sessionStorage.getItem(KEY) || 'null'); } catch (e) {}
  const state = pos || { x: window.innerWidth / 2, y: window.innerHeight / 2 };
  let el = null;                  // the single overlay element (re-parented, never duplicated)
  let armed = false;
  let off = { x: 0, y: 0 };       // shift needed when the host is a transformed containing block
  let lastSave = 0;
  const TRANSITION = 'transform 70ms linear';
  const root = () => document.documentElement;
  // A modal <dialog> renders in the browser top layer, above any z-index, so while one
  // is open the overlay must live inside the topmost one; otherwise on the page itself.
  const hostFor = () => {
    const ds = document.querySelectorAll('dialog[open]');
    return ds.length ? ds[ds.length - 1] : root();
  };
  const place = () => {
    if (el) el.style.transform = 'translate(' + (state.x - off.x) + 'px,' + (state.y - off.y) + 'px)';
  };
  const create = () => {
    el = document.createElement('div');
    el.id = '__ai_cursor__';
    el.setAttribute('aria-hidden', 'true');
    el.style.cssText = 'position:fixed;left:0;top:0;width:22px;height:22px;margin:0;padding:0;'
      + 'z-index:2147483647;pointer-events:none;will-change:transform;transition:' + TRANSITION + ';';
    el.innerHTML = '<svg viewBox="0 0 24 24" width="22" height="22" style="display:block;'
      + 'filter:drop-shadow(0 1px 2px rgba(0,0,0,.55))"><path d="M3 2l7 18 2.6-7.4L20 10z" '
      + 'fill="#fff" stroke="#111" stroke-width="1.5" stroke-linejoin="round"/></svg>';
  };
  // (Re)parent the existing element under the right host. DOM work only happens when
  // the host changes (dialog opened/closed, page re-rendered), not on every mouse move.
  const attach = () => {
    const host = hostFor();
    if (!host) return;
    if (!el) create();
    if (el.isConnected && el.parentElement === host) return;
    el.style.transition = 'none';
    el.style.transform = 'translate(0px,0px)';
    host.appendChild(el);
    const r = el.getBoundingClientRect();   // non-zero only inside a transformed host
    off = { x: r.left, y: r.top };
    place();
    requestAnimationFrame(() => { if (el) el.style.transition = TRANSITION; });
    if (!armed) {   // the page removed it from <html> while re-rendering: put it back
      armed = true;
      new MutationObserver(() => { if (el && !el.isConnected) attach(); }).observe(root(), { childList: true });
    }
  };
  const save = () => {
    lastSave = performance.now();
    try { sessionStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {}
  };
  const moveTo = (x, y) => {
    state.x = x; state.y = y;
    const host = hostFor();
    if (!el || !el.isConnected || el.parentElement !== host) attach();
    place();
    if (performance.now() - lastSave > 250) save();
  };
  const ripple = (x, y) => {
    const host = (el && el.isConnected && el.parentElement) || root();
    if (!host) return;
    const r = document.createElement('div');
    r.style.cssText = 'position:fixed;left:' + (x - 14 - off.x) + 'px;top:' + (y - 14 - off.y) + 'px;'
      + 'width:28px;height:28px;box-sizing:border-box;border-radius:50%;border:2px solid #0a66c2;'
      + 'background:rgba(10,102,194,.25);pointer-events:none;z-index:2147483647;'
      + 'transform:scale(.3);opacity:1;transition:transform 320ms ease-out,opacity 320ms ease-out;';
    host.appendChild(r);
    requestAnimationFrame(() => { r.style.transform = 'scale(1.4)'; r.style.opacity = '0'; });
    setTimeout(() => r.remove(), 380);
  };
  window.__aiCursor = { moveTo, mount: attach };
  addEventListener('mousemove', e => moveTo(e.clientX, e.clientY), true);
  addEventListener('mousedown', e => { moveTo(e.clientX, e.clientY); ripple(e.clientX, e.clientY); }, true);
  // A dialog closing hides the overlay with it: move it back to the page right away.
  document.addEventListener('close', () => { if (el) attach(); }, true);
  addEventListener('pagehide', save);
  if (root()) { attach(); } else { document.addEventListener('DOMContentLoaded', attach, { once: true }); }
})();
"""


async def install_cursor(context) -> None:
    """
    Add the cursor overlay to every page of `context`: the init script re-runs on each
    navigation and reload, and the pages already open get it immediately.
    """
    if not CURSOR_ENABLED:
        return
    await context.add_init_script(_CURSOR_JS)
    for p in list(context.pages):
        try:
            await p.evaluate(_CURSOR_JS)
        except Exception:
            pass


async def cursor_move(locator, steps: int = 12) -> None:
    """
    Move the REAL Playwright mouse to the centre of `locator` in `steps` small moves,
    so the overlay glides there. Best effort: failures never affect the caller.
    """
    if not CURSOR_ENABLED:
        return
    try:
        await locator.scroll_into_view_if_needed(timeout=1_000)
        box = await locator.bounding_box(timeout=1_000)
        if box:
            await locator.page.mouse.move(
                box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=steps
            )
    except Exception:
        pass


async def cursor_click(locator, **click_kwargs) -> None:
    """Move the visible cursor to the target, then perform the normal locator click."""
    await cursor_move(locator)
    await locator.click(**click_kwargs)


def resume_file_path(user_id: int, resume_id: int, filename: str) -> Path:
    """Location of the stored original file for a resume record."""
    return RESUME_DIR / str(user_id) / str(resume_id) / (re.split(r"[\\/]", filename)[-1].strip(". ") or "resume")

SEARCH_KEYWORDS = "Java Backend Developer"
WORK_TYPE       = "2"   # 2 = Remote

# LinkedIn timePostedRange filter values.
# "r86400" = past 24 hours; "r604800" = past week; "" = any time.
DATE_POSTED_24H = "r86400"

# Default filter flags for this workflow.
DEFAULT_EASY_APPLY = True
DEFAULT_REMOTE_ONLY = False  # Remote is applied only when the user asks for it

# Minimum match score (0–100) to consider a job qualifying.
MATCH_THRESHOLD = 75

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

def _build_browser_search_url(
    keywords: str = SEARCH_KEYWORDS,
    date_posted: str = DATE_POSTED_24H,
    easy_apply: bool = DEFAULT_EASY_APPLY,
    remote_only: bool = DEFAULT_REMOTE_ONLY,
    start: int = 0,
) -> str:
    """
    Build the LinkedIn jobs search-page URL with the same filters used by
    the Voyager API calls, so the Playwright browser displays the same
    result set that iter_first_page_jobs() processes.

    Browser URL parameter mapping:
        keywords     → keywords
        remote_only  → f_WT=2  (Workplace Type: Remote)
        easy_apply   → f_AL=true
        date_posted  → f_TPR=<value>  (Time Posted Range, e.g. r86400)
    """
    params: dict[str, str] = {"keywords": keywords}
    if remote_only:
        params["f_WT"] = WORK_TYPE          # "2" = Remote
    if easy_apply:
        params["f_AL"] = "true"
    if date_posted:
        params["f_TPR"] = date_posted       # e.g. "r86400"
    if start:
        params["start"] = str(start)        # result offset for pages after the first
    return "https://www.linkedin.com/jobs/search/?" + urlencode(params)


def _build_voyager_url(start: int = 0, keywords: str = SEARCH_KEYWORDS,
                       date_posted: str = DATE_POSTED_24H,
                       easy_apply: bool = DEFAULT_EASY_APPLY,
                       remote_only: bool = DEFAULT_REMOTE_ONLY) -> str:
    """Build the Voyager jobs search API URL."""
    # This is the standard Voyager REST endpoint for job search.
    # decorationId controls which fields are returned.
    selected_filters: dict = {}
    if remote_only:
        selected_filters["workplaceType"] = ["2"]   # 2 = Remote
    if date_posted:
        selected_filters["timePostedRange"] = [date_posted]

    query: dict = {
        "origin": "JOB_SEARCH_PAGE_QUERY_EXPANSION",
        "keywords": keywords,
        "locationUnion": {"geoId": 92000000},  # Worldwide
        "selectedFilters": selected_filters,
        "spellCorrectionEnabled": True,
    }
    if easy_apply:
        query["easyApply"] = True

    params = {
        "decorationId": (
            "com.linkedin.voyager.dash.deco.jobs.njoyn.NjoyNJobPosting-1"
        ),
        "count": PAGE_SIZE,
        "start": start,
        "q": "jobSearch",
        "query": json.dumps(query),
    }
    return "https://www.linkedin.com/voyager/api/jobs/jobPostings?" + urlencode(
        params
    )


def _build_graphql_url(start: int = 0, keywords: str = SEARCH_KEYWORDS,
                       date_posted: str = DATE_POSTED_24H,
                       easy_apply: bool = DEFAULT_EASY_APPLY,
                       remote_only: bool = DEFAULT_REMOTE_ONLY) -> str:
    """
    Build the Voyager GraphQL job-search URL.
    This is the endpoint used by the new jobs search page.
    """
    filter_parts: list[str] = []
    if remote_only:
        filter_parts.append(f"workplaceType:List({WORK_TYPE})")
    if date_posted:
        filter_parts.append(f"timePostedRange:List({date_posted})")

    filters_str = ",".join(filter_parts)
    easy_apply_str = ",easyApply:true" if easy_apply else ""

    variables = (
        f"(count:{PAGE_SIZE},start:{start},"
        f"query:(origin:JOB_SEARCH_PAGE_QUERY_EXPANSION,"
        f"keywords:{keywords},"
        f"selectedFilters:({filters_str}){easy_apply_str},"
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


def _extract_description_text(node: dict) -> str:
    """
    Extract plain-text description from a Voyager job-posting detail node.
    Tries the structured attribute text first, then falls back to raw text.
    Returns an empty string when not found.
    """
    # Structured: description.text (normalized+json format)
    desc = _safe_text(node, "description", "text")
    if desc:
        return desc
    # Alternate key used in some decorations
    desc = _safe_text(node, "descriptionText", "text")
    if desc:
        return desc
    desc = _safe_text(node, "descriptionText")
    if desc:
        return desc
    return ""


async def fetch_job_description(job_id: str, cookies: dict | None = None) -> str:
    """
    Fetch the full job description for a single job ID via the Voyager
    job-posting detail endpoint.  Reuses the same httpx + cookie pattern
    as call_voyager_api.

    Returns the description text, or "" if unavailable or on error.
    Does not raise.
    """
    if not HAS_HTTPX or not job_id or not (cookies and cookies.get("li_at")):
        return ""

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
        "Csrf-Token": jsessionid,
        "Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items() if v),
        "Referer": f"https://www.linkedin.com/jobs/view/{job_id}/",
    }

    # Voyager job-posting detail endpoint (single posting by ID).
    url = (
        f"https://www.linkedin.com/voyager/api/jobs/jobPostings/{job_id}"
        "?decorationId=com.linkedin.voyager.deco.jobs.web.shared"
        ".WebFullJobPosting-14"
    )

    try:
        async with httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=True,
            headers=headers,
        ) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                body = resp.json()
                # The normalized response wraps the posting under "data".
                posting = body.get("data") or body
                desc = _extract_description_text(posting)
                if desc:
                    return desc
                # Walk the included array for a node with a description.
                for item in body.get("included", []):
                    if isinstance(item, dict):
                        desc = _extract_description_text(item)
                        if desc:
                            return desc
            else:
                print(
                    f"[desc] job_id={job_id} HTTP {resp.status_code}",
                    flush=True,
                )
    except Exception as exc:
        print(f"[desc] job_id={job_id} error: {exc}", flush=True)

    return ""



    """
    Return True only for job *result-card* nodes from the list panel.

    LinkedIn uses distinct type names for the scrollable card list
    (e.g. JobCard, jobseekerJobCard, jobseekerJobResult, NjoyNJobCard)
    versus the detail-panel posting node (JobPosting, fsd_jobPosting).
    Matching on the card/result types avoids collecting the single
    detail-panel object that LinkedIn always includes in the response.
    """
    card_type_fragments = (
        "jobCard",
        "JobCard",
        "jobseekerJobCard",
        "jobseekerJobResult",
        "NjoyNJobCard",
        "jobResult",          # Voyager REST list items
    )
    card_urn_fragments = (
        "fsd_jobCard",
    )
    return (
        any(f in type_val for f in card_type_fragments)
        or any(f in entity_urn for f in card_urn_fragments)
    )


def _parse_jobs_from_response(body: object) -> list[dict]:
    """
    Walk the entire API response recursively.
    Collect only result-card nodes (list panel), not the detail-panel posting.
    Stop descending into a matched card to avoid double-counting nested nodes.
    """
    jobs: list[dict] = []

    def _walk(node: object) -> None:
        if isinstance(node, dict):
            type_val   = str(node.get("$type", "") or "")
            entity_urn = str(node.get("entityUrn", "") or "")

            if _is_result_card(type_val, entity_urn):
                job = _parse_job_posting(node)
                if job:
                    jobs.append(job)
                # Do not descend further into a matched card node.
                return

            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(body)

    # Deduplicate within this response by job ID (preferred) then title.
    seen: set = set()
    unique: list[dict] = []
    for j in jobs:
        k = j["job_id"] if j["job_id"] else j["title"]
        if k and k not in seen:
            seen.add(k)
            unique.append(j)
    return unique


async def call_voyager_api(cookies: dict, start: int = 0,
                          keywords: str = SEARCH_KEYWORDS,
                          date_posted: str = DATE_POSTED_24H,
                          easy_apply: bool = DEFAULT_EASY_APPLY,
                          remote_only: bool = DEFAULT_REMOTE_ONLY) -> list[dict]:
    """
    Call LinkedIn's Voyager job-search API and return parsed jobs.
    Tries the GraphQL endpoint first, falls back to the REST endpoint.
    date_posted: Voyager timePostedRange value ("r86400" = last 24 h, "" = any).
    easy_apply:  restrict to Easy Apply jobs only.
    remote_only: restrict to Remote jobs only (workplaceType=2).
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
        graphql_url = _build_graphql_url(start, keywords=keywords,
                                         date_posted=date_posted,
                                         easy_apply=easy_apply,
                                         remote_only=remote_only)
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
        rest_url = _build_voyager_url(start, keywords=keywords,
                                      date_posted=date_posted,
                                      easy_apply=easy_apply,
                                      remote_only=remote_only)
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

async def scan_jobs(keywords: str = SEARCH_KEYWORDS,
                   date_posted: str = DATE_POSTED_24H,
                   easy_apply: bool = DEFAULT_EASY_APPLY,
                   remote_only: bool = DEFAULT_REMOTE_ONLY) -> list[dict]:
    """
    Scan LinkedIn jobs.
    date_posted: Voyager timePostedRange value ("r86400" = last 24 h, "" = any).
    easy_apply:  restrict to Easy Apply jobs only.
    remote_only: restrict to Remote jobs only.
    Raises ValueError if date_posted is not a recognised value.
    """
    _valid_date_posted = {"r86400", "r604800", "r2592000", ""}
    if date_posted not in _valid_date_posted:
        raise ValueError(
            f"Unrecognised date_posted value {date_posted!r}. "
            f"Expected one of {sorted(_valid_date_posted)}."
        )
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
        print(f"[step2] Searching for: {keywords!r}", flush=True)
        print(f"[step2] Date filter  : {date_posted or '(none)'}", flush=True)
        print(f"[step2] Easy Apply   : {easy_apply}", flush=True)
        print(f"[step2] Remote only  : {remote_only}", flush=True)
        for page_num in range(MAX_PAGES):
            start = page_num * PAGE_SIZE
            print(
                f"[step2] Fetching page {page_num + 1}/{MAX_PAGES} "
                f"(start={start})…",
                flush=True,
            )
            page_jobs = await call_voyager_api(cookies, start=start,
                                               keywords=keywords,
                                               date_posted=date_posted,
                                               easy_apply=easy_apply,
                                               remote_only=remote_only)
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
# RESUME–JOB MATCHING
# ---------------------------------------------------------------------------

async def score_job(
    job: dict,
    resume_text: str,
    threshold: int = MATCH_THRESHOLD,
) -> dict:
    """
    Score a single job dict against resume_text using the existing matching
    services.  Tries calculate_ai_job_match first; falls back to the
    keyword-based calculate_job_match if the AI service is unavailable.

    Returns the job dict extended with:
        match_score   : int 0–100, or None when unscorable
        matched_skills: list[str]
        missing_skills: list[str]
        eligible      : bool — True when match_score >= threshold
        needs_review  : bool
        match_reason  : str  — explanation / fallback marker

    Never assigns an invented score. Sets match_score=None and
    needs_review=True when resume or description is missing.
    """
    description = job.get("description", "").strip()
    resume = resume_text.strip() if resume_text else ""

    if not resume or not description:
        return {
            **job,
            "match_score": None,
            "matched_skills": [],
            "missing_skills": [],
            "eligible": False,
            "needs_review": True,
            "match_reason": (
                "Resume is missing." if not resume
                else "Job description is missing."
            ),
        }

    if not HAS_MATCHING:
        return {
            **job,
            "match_score": None,
            "matched_skills": [],
            "missing_skills": [],
            "eligible": False,
            "needs_review": True,
            "match_reason": "Matching service unavailable.",
        }

    # Primary: AI matching (async).
    try:
        result = await calculate_ai_job_match(resume, description)
    except Exception as exc:
        print(f"[match] AI matching failed: {exc} — using keyword fallback",
              flush=True)
        result = None

    # Fallback: keyword-based matching (sync).
    if result is None or result.get("needs_review") and not result.get("match_score"):
        result = calculate_job_match(resume, description)

    score = result.get("match_score")
    # Two independent conditions: required-skills % >= threshold AND experience
    # requirement confirmed. Unknown experience (including the keyword fallback,
    # which has no experience data) is uncertain, never a match.
    experience_match = result.get("experience_match")
    needs_review = bool(result.get("needs_review", False)) or experience_match is None
    eligible = (
        isinstance(score, (int, float))
        and score >= threshold
        and experience_match is True
        and not needs_review
    )

    return {
        **job,
        "match_score": score,
        "matched_skills": result.get("matched_skills", []),
        "missing_skills": result.get("missing_skills", []),
        "experience_match": experience_match,
        "years_of_experience": result.get("years_of_experience"),
        "required_experience_years": result.get("required_experience_years"),
        "eligible": eligible,
        "needs_review": needs_review,
        "match_reason": result.get("explanation", ""),
    }


# ---------------------------------------------------------------------------
# JOB DISMISSAL
# ---------------------------------------------------------------------------

def should_dismiss(match_score: int | float | None,
                   threshold: int = MATCH_THRESHOLD) -> bool:
    """
    Return True only when match_score is a confirmed numeric value below
    threshold.  Never dismisses when score is None (unscorable / needs review).

    Decision table:
        score >= threshold  → False  (keep for Easy Apply)
        score <  threshold  → True   (eligible for dismissal)
        score is None       → False  (keep, mark for review)
    """
    if match_score is None:
        return False
    return float(match_score) < threshold


async def dismiss_job(page, job_id: str) -> bool:
    """
    Dismiss a single LinkedIn job card identified by job_id.

    Strategy (derived from verified DOM structure):
      1. Locate the job title anchor whose href contains /jobs/view/{job_id}/.
      2. Walk up the DOM (via JavaScript) to find the nearest ancestor that
         also contains a dismiss button (aria-label starting with "Dismiss ").
      3. Click that button only — never any other card's button.

    Returns True on successful click, False when the control is not found
    or any error occurs.  Never raises.

    The page parameter must be an open Playwright Page on the LinkedIn
    jobs search results page.  No new browser sessions are launched here.
    """
    if not job_id:
        print("[dismiss] No job_id provided — skipping.", flush=True)
        return False

    try:
        # JavaScript: find the card ancestor that owns both the job link
        # and a dismiss button, then return the aria-label of the button
        # so we can verify it before clicking.
        card_js = """
        (jobId) => {
            // Current Jobs UI: the card itself owns its dismiss button.
            const card = document.querySelector(
                `[role="button"][componentkey="job-card-component-ref-${jobId}"]`
            );
            if (card) {
                const own = card.querySelector('button[aria-label^="Dismiss "]');
                return own ? own.getAttribute('aria-label') : null;
            }
            const anchor = document.querySelector(
                `a[href*="/jobs/view/${jobId}/"]`
            );
            if (!anchor) return null;

            // Walk up until we find an ancestor containing a dismiss button.
            let el = anchor.parentElement;
            while (el && el !== document.body) {
                const btn = el.querySelector('button[aria-label^="Dismiss "]');
                if (btn) {
                    return btn.getAttribute('aria-label');
                }
                el = el.parentElement;
            }
            return null;
        }
        """
        aria_label = await page.evaluate(card_js, job_id)

        if not aria_label:
            print(
                f"[dismiss] job_id={job_id}: dismiss button not found in DOM.",
                flush=True,
            )
            return False

        # Confirm the button belongs to this card by checking aria-label.
        if not aria_label.startswith("Dismiss "):
            print(
                f"[dismiss] job_id={job_id}: unexpected aria-label {aria_label!r}.",
                flush=True,
            )
            return False

        # Locate and click the specific button by its exact aria-label.
        btn_selector = f'button[aria-label="{aria_label}"]'
        card_loc = page.locator(
            f'[role="button"][componentkey="job-card-component-ref-{job_id}"]'
        )
        # Scope to the card: several cards can share the same job title.
        if await card_loc.count():
            btn = card_loc.first.locator(btn_selector).first
        else:
            btn = page.locator(btn_selector).first
        if not await btn.is_visible():
            print(
                f"[dismiss] job_id={job_id}: button not visible — skipping.",
                flush=True,
            )
            return False

        await cursor_click(btn)
        print(f"[dismiss] job_id={job_id}: dismissed ({aria_label!r}).",
              flush=True)
        return True

    except Exception as exc:
        print(f"[dismiss] job_id={job_id}: error — {exc}", flush=True)
        return False


_RESUME_MODAL_SEL = (
    'div[data-test-modal], dialog[open], '
    '[role="dialog"][aria-label*="Easy Apply"], [role="dialog"]'
)

# Inspects the resume cards shown in the Easy Apply modal. Returns "match" when exactly
# one card is shown and its visible file name equals `name`, "mismatch" when the single
# card has a different name, "ambiguous" when several are shown, "absent" when none.
# The selection indicator is deliberately not used (it is not reliably detectable).
_RESUME_STATE_JS = """
(name) => {
  const modal = document.querySelector('div[data-test-modal]')
    || document.querySelector('dialog[open]')
    || document.querySelector('[role="dialog"]');
  if (!modal) return 'absent';
  const norm = s => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
  const target = norm(name);
  // Resume cards = visible leaf elements whose text is a document file name.
  const visible = e => e.offsetWidth > 4 && e.offsetHeight > 4;
  const names = Array.from(modal.querySelectorAll('*'))
    .filter(e => e.children.length === 0 && visible(e)
      && /^[^\\n]+\\.(pdf|docx?)$/i.test(norm(e.textContent)))
    .map(e => norm(e.textContent));
  if (names.length === 0) return 'absent';
  if (names.length > 1) return 'ambiguous';      // several cards (or duplicate names)
  return names[0] === target ? 'match' : 'mismatch';
}
"""


async def _attach_resume(page, resume_file: Path) -> str:
    """
    Make sure `resume_file` is the resume attached in the open Easy Apply modal.

    Returns "kept" (exactly one resume card, and its file name equals the stored one),
    "no_section" (this step shows no resume section) or "failed" (a different, several
    or no matching resume; the caller stops for user review). It never clicks a card
    and never uploads, so the correct resume is not duplicated and no other resume
    is silently used.
    """
    name = resume_file.name
    try:
        state = await page.evaluate(_RESUME_STATE_JS, name)
    except Exception as exc:
        print(f"[resume] could not inspect the resume step — {exc}", flush=True)
        return "failed"
    print(f"[resume] state for {name!r}: {state}", flush=True)

    if state == "match":
        return "kept"
    if state == "absent":
        # No resume card. A bare resume section (Upload button / file input) still
        # needs the user; a step without any resume control is simply not the resume step.
        modal = page.locator(_RESUME_MODAL_SEL).first
        has_upload = (
            await modal.get_by_role("button", name="Upload resume", exact=True).count() > 0
            or await modal.locator('input[type="file"]').count() > 0
        )
        return "failed" if has_upload else "no_section"
    # "mismatch" or "ambiguous": do not guess which resume is used.
    return "failed"


_OPTION_CODE_RE = re.compile(r"^(?P<name>.*?)\s*\(\s*\+?(?P<code>\d[\d\s-]*)\s*\)\s*$")
_CODE_ONLY_RE = re.compile(r"^\+?\s*(?P<code>\d[\d\s-]*)$")


def _split_country(text: str) -> tuple[str, str]:
    """Normalise "India (+91)" / "India" / "+91" into (name, dialing code digits)."""
    t = re.sub(r"\s+", " ", (text or "").strip().lower())
    m = _CODE_ONLY_RE.match(t)
    if m:
        return "", re.sub(r"\D", "", m.group("code"))
    m = _OPTION_CODE_RE.match(t)
    if m:
        return m.group("name").strip(), re.sub(r"\D", "", m.group("code"))
    return t, ""


def _resolve_option(value: str, options: list[str]) -> str | None:
    """
    Pick the dropdown option that `value` unambiguously identifies, or None.
    Order: exact text, normalised text, name (+ code when given), dialing code only.
    Ambiguous or unknown values return None; nothing is guessed.
    """
    opts = [o for o in options if o and not o.strip().lower().startswith("select")]
    value = (value or "").strip()
    if not value:
        return None

    exact = [o for o in opts if o == value]
    if len(exact) == 1:
        return exact[0]

    name, code = _split_country(value)
    norm = re.sub(r"\s+", " ", value.lower())
    normalised = [o for o in opts if re.sub(r"\s+", " ", o.strip().lower()) == norm]
    if len(normalised) == 1:
        return normalised[0]

    if name:
        hits = [
            o for o in opts
            if _split_country(o)[0] == name and (not code or _split_country(o)[1] == code)
        ]
    else:
        hits = [o for o in opts if code and _split_country(o)[1] == code]
    return hits[0] if len(hits) == 1 else None


async def fill_easy_apply_fields(page, applicant_data: dict) -> dict:
    """
    Fill basic contact and resume fields in an already-open LinkedIn Easy
    Apply modal.  The modal must be visible before calling this function;
    use open_easy_apply() first.

    applicant_data keys (all optional — omit or set to "" to skip):
        first_name   : str
        last_name    : str
        email        : str
        phone        : str
        phone_country: str  — country-code label, e.g. "India (+91)"
        city         : str
        resume_path  : str  — absolute local path to a resume file

    Returns a dict:
        filled  : list[str]  — field names successfully filled/kept
        skipped : list[str]  — fields not found or already correct
        missing : list[str]  — fields in applicant_data that could not
                               be filled due to missing data or controls

    Never clicks Next, Review, or Submit.
    Never overwrites a field that already has the correct value.
    Skips any field whose value is absent in applicant_data.
    """
    filled:  list[str] = []
    skipped: list[str] = []
    missing: list[str] = []

    # Scope all selectors inside the modal only.
    # LinkedIn's Easy Apply modal is the innermost dialog/overlay element.
    # We use page.locator scoped to it throughout.
    MODAL_SEL = (
        'div[data-test-modal], '
        'dialog[open], '
        '[role="dialog"][aria-label*="Easy Apply"], '
        '[role="dialog"]'
    )

    async def _modal():
        """Return the first visible modal locator."""
        return page.locator(MODAL_SEL).first

    # Fields whose supplied value is user-verified and may replace a wrong
    # prefilled value; other (account-derived) values only fill empty controls.
    overrides = set(applicant_data.get("_override_fields") or [])
    required_missing: list[str] = []   # required contact fields still empty
    contact_control_ids: list[str] = []  # so callers don't treat them as screening questions

    _CONTROL_STATE_JS = """
    el => {
        const tag = el.tagName.toLowerCase();
        let value = el.value || '';
        if (tag === 'select') {
            const t = ((el.selectedOptions[0] || {}).text || '').trim();
            value = (!el.value || t.toLowerCase().startsWith('select')) ? '' : t;
        }
        return {
            id: el.id || '',
            value: value.trim(),
            required: !!el.required || el.getAttribute('aria-required') === 'true',
            options: tag === 'select'
                ? Array.from(el.options).map(o => (o.text || '').trim()) : [],
        };
    }
    """

    async def _set_contact_field(label_text: str, value: str,
                                  field_name: str, is_select: bool) -> None:
        """
        Handle one contact control found by its label (scoped to the modal):
        keep a prefilled value, fill an empty control, replace a wrong prefilled
        value only with user-verified data, and report required fields left empty.
        A control that is not on this step is simply skipped.
        """
        value = (value or "").strip()
        current, required = "", False
        try:
            modal = await _modal()
            matches = modal.get_by_label(label_text, exact=False)
            if await matches.count() == 0:
                skipped.append(field_name)  # not on this step
                return
            loc = matches.first
            state = await loc.evaluate(_CONTROL_STATE_JS)
            if state["id"]:
                contact_control_ids.append(state["id"])
            current, required = state["value"], state["required"]

            target = value
            if is_select and value:
                # Name, dialing code or "Name (+code)": resolve to one real option.
                target = _resolve_option(value, state["options"]) or ""
                if not target:
                    print(f"[fill] {field_name}: {value!r} matches no single option "
                          "(unknown or ambiguous) — not guessing.", flush=True)

            if current and (not target or current.lower() == target.lower()
                            or field_name not in overrides):
                skipped.append(field_name)  # keep the valid existing selection/value
                return
            if not target:
                if required:
                    required_missing.append(field_name)
                if value:
                    missing.append(field_name)  # supplied but unresolved: ask again
                skipped.append(field_name)
                return

            await cursor_move(loc)
            if is_select:
                await loc.select_option(label=target, timeout=3_000)
            else:
                await loc.fill(target, timeout=3_000)
            after = (await loc.evaluate(_CONTROL_STATE_JS))["value"]
            if not after or (is_select and after.lower() != target.lower()):
                raise ValueError(f"control shows {after!r} after filling")
            filled.append(field_name)
        except Exception as exc:
            print(f"[fill] {field_name}: could not fill — {exc}", flush=True)
            missing.append(field_name)
            if required and not current:
                required_missing.append(field_name)  # still empty: ask the user

    async def _fill_text_by_label(label_text: str, value: str,
                                   field_name: str) -> None:
        await _set_contact_field(label_text, value, field_name, False)

    async def _select_by_label(label_text: str, option_text: str,
                                field_name: str) -> None:
        """Select a <select> element associated with label_text."""
        await _set_contact_field(label_text, option_text, field_name, True)

    # --- First name ---
    await _fill_text_by_label("First name", applicant_data.get("first_name", ""),
                               "first_name")

    # --- Last name ---
    await _fill_text_by_label("Last name", applicant_data.get("last_name", ""),
                               "last_name")

    # --- Email ---
    await _fill_text_by_label("Email address", applicant_data.get("email", ""),
                               "email")

    # --- Phone country code (select) ---
    await _select_by_label("Phone country code",
                            applicant_data.get("phone_country", ""),
                            "phone_country")

    # --- Phone number ---
    await _fill_text_by_label("Mobile phone number",
                               applicant_data.get("phone", ""), "phone")

    # --- City / location ---
    await _fill_text_by_label("City", applicant_data.get("city", ""), "city")

    # --- Resume upload ---
    # "resume" reports the attachment state to the caller:
    # attached | kept | no_section | failed | None (no resume requested).
    resume_state: str | None = None
    resume_path = applicant_data.get("resume_path", "")
    if resume_path:
        resume_file = Path(resume_path)
        if resume_file.is_file():
            resume_state = await _attach_resume(page, resume_file)
            if resume_state in ("attached", "kept"):
                filled.append("resume_path")
            elif resume_state == "no_section":
                skipped.append("resume_path")  # this step has no resume section
            else:
                missing.append("resume_path")
        else:
            print(f"[fill] resume_path: file not found — {resume_path!r}",
                  flush=True)
            resume_state = "failed"
            missing.append("resume_path")
    else:
        skipped.append("resume_path")

    print(
        f"[fill] filled={filled} skipped={skipped} missing={missing}",
        flush=True,
    )
    return {"filled": filled, "skipped": skipped, "missing": missing,
            "resume": resume_state,
            "required_missing": required_missing,
            "contact_control_ids": contact_control_ids}


_YES_VALUES = {"yes", "y", "true", "checked"}
_NO_VALUES = {"no", "n", "false", "unchecked"}
_SELECTED_TEXT_JS = "el => ((el.selectedOptions[0] || {}).text || '').trim()"


async def _apply_screening_answer(
    page, q_text: str, input_type: str, options: list[str],
    control_id: str, answer: str,
) -> bool:
    """
    Apply `answer` to one screening control and verify the result.

    Returns True when the control shows the answer afterwards (an already-correct
    value is kept untouched). Returns False when the answer cannot be matched to a
    single option or the control does not show it after filling, so the caller
    reports it as pending instead of guessing.
    """
    answer = (answer or "").strip()
    if not answer:
        return False
    if control_id:
        ctl = page.locator(f'[id="{control_id}"]').first
    else:
        ctl = page.locator(_RESUME_MODAL_SEL).first.get_by_label(q_text, exact=False).first
    tag = await ctl.evaluate("el => el.tagName.toLowerCase()")

    if input_type == "select":
        real = await ctl.evaluate(
            "el => Array.from(el.options).map(o => (o.text || '').trim())"
        )
        target = _resolve_option(answer, real)
        if target is None:
            return False
        if (await ctl.evaluate(_SELECTED_TEXT_JS)).lower() != target.lower():
            await cursor_move(ctl)
            await ctl.select_option(label=target, timeout=3_000)
        return (await ctl.evaluate(_SELECTED_TEXT_JS)).lower() == target.lower()

    if input_type in ("radio", "checkbox") and tag == "fieldset":
        target = _resolve_option(answer, options)
        if target is None:
            return False
        option = ctl.get_by_label(target, exact=True).first
        if not await option.is_checked():
            await cursor_move(ctl)
            await option.check(force=True, timeout=3_000)
        return await option.is_checked()

    if input_type == "checkbox":  # single checkbox
        low = answer.lower()
        if low not in _YES_VALUES and low not in _NO_VALUES:
            return False
        want = low in _YES_VALUES
        if await ctl.is_checked() != want:
            await (ctl.check if want else ctl.uncheck)(force=True, timeout=3_000)
        return await ctl.is_checked() == want

    # text / textarea
    if (await ctl.input_value(timeout=3_000)).strip().casefold() != answer.casefold():
        await cursor_move(ctl)
        await ctl.fill(answer, timeout=3_000)
    return (await ctl.input_value(timeout=3_000)).strip().casefold() == answer.casefold()


# Scans the open Easy Apply modal for REQUIRED controls that are unanswered or
# invalid. Required = native `required`, aria-required, or a visible "*" /
# "(required)" marker on the label/legend. Placeholder dropdown options and
# unchecked required boxes/groups count as unanswered. File inputs (resume) and
# hidden/invisible controls are ignored. Contact fields are filtered by the caller.
_REQUIRED_UNANSWERED_JS = """
() => {
  const modal = document.querySelector('div[data-test-modal]')
    || document.querySelector('dialog[open]')
    || document.querySelector('[role="dialog"][aria-label*="Easy Apply"]')
    || document.querySelector('[role="dialog"]');
  if (!modal) return [];
  const GROUP_INPUTS = 'input[type="radio"], input[type="checkbox"]';
  const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const isPlaceholder = o => !o || /^select/i.test(o);
  const marked = t => /\\*/.test(t || '') || /\\(required\\)\\s*$/i.test((t || '').trim());
  const ensureId = (el, prefix) => {
    if (!el.id) {
      let i = 0;
      while (document.getElementById(prefix + i)) i++;
      el.id = prefix + i;
    }
    return el.id;
  };
  const labels = Array.from(modal.querySelectorAll('label'));
  const out = [];
  const groups = new Set();

  for (const fs of modal.querySelectorAll('fieldset')) {
    const inputs = Array.from(fs.querySelectorAll(GROUP_INPUTS));
    if (!inputs.length) continue;
    groups.add(fs);
    if (!visible(fs)) continue;
    const legend = fs.querySelector('legend');
    const text = ((legend ? legend.textContent : fs.getAttribute('aria-label')) || '').trim();
    const required = fs.getAttribute('aria-required') === 'true'
      || inputs.some(i => i.required || i.getAttribute('aria-required') === 'true')
      || marked(text);
    if (!required || inputs.some(i => i.checked)) continue;
    out.push({
      question: text || fs.id,
      input_type: inputs[0].getAttribute('type'),
      control_id: ensureId(fs, 'ea-screening-group-'),
      options: inputs.map(inp => {
        const lbl = labels.find(l => l.htmlFor === inp.id);
        return (lbl ? lbl.textContent : inp.value || '').trim();
      }),
    });
  }

  for (const c of modal.querySelectorAll('input, select, textarea')) {
    const tag = c.tagName.toLowerCase();
    const type = (c.getAttribute('type') || tag).toLowerCase();
    if (['hidden', 'file', 'submit', 'button', 'image', 'reset', 'radio'].includes(type)) continue;
    const fs = c.closest('fieldset');
    if (fs && groups.has(fs)) continue;
    const label = c.id ? labels.find(l => l.htmlFor === c.id) : null;
    if (!visible(type === 'checkbox' && label ? label : c)) continue;
    const text = (label ? label.textContent : (c.getAttribute('aria-label') || '')).trim();
    const required = c.required || c.getAttribute('aria-required') === 'true' || marked(text);
    if (!required) continue;

    let unanswered;
    if (tag === 'select') {
      const opt = c.selectedOptions[0];
      unanswered = !c.value || !opt || opt.disabled || isPlaceholder((opt.text || '').trim());
    } else if (type === 'checkbox') {
      unanswered = !c.checked;
    } else {
      unanswered = !(c.value || '').trim();
    }
    if (!unanswered && c.getAttribute('aria-invalid') !== 'true') continue;

    let options = [];
    let inputType = 'text';
    if (tag === 'select') {
      inputType = 'select';
      options = Array.from(c.options).map(o => o.text.trim()).filter(o => !isPlaceholder(o));
    } else if (tag === 'textarea') {
      inputType = 'textarea';
    } else if (type === 'checkbox') {
      inputType = 'checkbox';
      options = ['Yes', 'No'];
    }
    out.push({
      question: text || c.name || c.id,
      input_type: inputType,
      control_id: ensureId(c, 'ea-screening-field-'),
      options: options,
    });
  }
  return out;
}
"""


async def find_unanswered_required(page) -> list[dict]:
    """
    Required screening controls in the open Easy Apply step that still lack a valid
    answer, shaped like pending_questions entries. Raises if the page cannot be
    inspected, so the caller never advances on unverified state.
    """
    return await page.evaluate(_REQUIRED_UNANSWERED_JS)


async def handle_screening_questions(
    page,
    resume_text: str,
    db,
    user_id: int | None = None,
) -> dict:
    """
    Extract visible screening questions from the active Easy Apply modal,
    match them against saved answers and resume data, fill verified answers,
    and collect unanswered questions for user confirmation.

    Parameters
    ----------
    page        : open Playwright Page with the Easy Apply modal visible
    resume_text : plain text of the applicant's resume (used read-only)
    db          : AsyncSession — used to read/write screening answers via
                  screening_service; pass None to skip DB lookups

    Returns
    -------
    {
        "answered_questions" : list[dict]  — {question, answer, input_type}
        "pending_questions"  : list[dict]  — {question, input_type, options}
        "errors"             : list[str]
    }

    Rules
    -----
    - Never invents answers or auto-selects "Yes".
    - Only fills an answer when it comes from a saved user-confirmed record
      or is explicitly present as a numeric/factual value in the resume text.
    - Leaves ambiguous or unknown questions in pending_questions.
    - Does not click Next, Review, or Submit.
    """
    # Lazy import to keep browser_agent usable standalone.
    try:
        from app.services.screening_service import (
            get_screening_answer,
        )
        # Saved answers are per user; without a user nothing is looked up.
        HAS_SCREENING_DB = db is not None and user_id is not None
    except ImportError:
        HAS_SCREENING_DB = False

    answered:  list[dict] = []
    pending:   list[dict] = []
    errors:    list[str]  = []

    MODAL_SEL = (
        'div[data-test-modal], '
        'dialog[open], '
        '[role="dialog"][aria-label*="Easy Apply"], '
        '[role="dialog"]'
    )

    try:
        modal = page.locator(MODAL_SEL).first
        if not await modal.is_visible(timeout=5_000):
            errors.append("Easy Apply modal is not visible.")
            return {
                "answered_questions": answered,
                "pending_questions": pending,
                "errors": errors,
            }
    except Exception as exc:
        errors.append(f"Modal check failed: {exc}")
        return {
            "answered_questions": answered,
            "pending_questions": pending,
            "errors": errors,
        }

    # --- Extract questions via JavaScript ---
    # Collects every label text + associated input type + available options
    # from the modal, without touching the DOM destructively.
    extract_js = """
    () => {
        const modalSels = [
            'div[data-test-modal]',
            'dialog[open]',
            '[role="dialog"][aria-label*="Easy Apply"]',
            '[role="dialog"]',
        ];
        let modal = null;
        for (const s of modalSels) {
            const el = document.querySelector(s);
            if (el) { modal = el; break; }
        }
        if (!modal) return [];

        const questions = [];
        const GROUP_INPUTS = 'input[type="radio"], input[type="checkbox"]';
        const isPlaceholder = o => !o || /^select/i.test(o);
        let n = 0;

        // Radio / checkbox groups: the question is the fieldset legend and the
        // options are the labels of its inputs. Give the group an id if it has none
        // so later steps can locate it.
        const groups = new Set();
        for (const fs of modal.querySelectorAll('fieldset')) {
            const inputs = Array.from(fs.querySelectorAll(GROUP_INPUTS));
            if (!inputs.length) continue;
            groups.add(fs);
            const legend = fs.querySelector('legend');
            const text = ((legend ? legend.textContent : fs.getAttribute('aria-label')) || '').trim();
            if (!text) continue;
            if (!fs.id) fs.id = 'ea-screening-group-' + (n++);
            questions.push({
                question: text,
                input_type: inputs[0].getAttribute('type'),
                control_id: fs.id,
                options: inputs.map(inp => {
                    const lbl = fs.querySelector(`label[for="${CSS.escape(inp.id)}"]`);
                    return (lbl ? lbl.textContent : inp.value || '').trim();
                }),
            });
        }

        // Standalone controls found through their <label>.
        for (const label of modal.querySelectorAll('label')) {
            const text = (label.textContent || '').trim();
            if (!text) continue;
            const fs = label.closest('fieldset');
            if (fs && groups.has(fs)) continue;   // option label of a group

            let control = null;
            if (label.htmlFor) {
                control = Array.from(modal.querySelectorAll('[id]'))
                    .find(e => e.id === label.htmlFor) || null;
            }
            if (!control) {
                control = label.nextElementSibling;
            }
            if (!control) continue;

            const tag   = control.tagName.toLowerCase();
            const itype = (control.getAttribute('type') || tag).toLowerCase();
            if (tag === 'input' && (itype === 'radio' || itype === 'file' || itype === 'hidden')) continue;
            if (!['input', 'select', 'textarea', 'fieldset'].includes(tag)) continue;
            if (!control.id) control.id = 'ea-screening-field-' + (n++);

            let options = [];
            let inputType = 'text';
            if (tag === 'select') {
                inputType = 'select';
                options = Array.from(control.options)
                    .map(o => o.text.trim()).filter(o => !isPlaceholder(o));
            } else if (tag === 'textarea') {
                inputType = 'textarea';
            } else if (tag === 'input' && itype === 'checkbox') {
                inputType = 'checkbox';
                options = ['Yes', 'No'];   // a single checkbox is checked or not
            }

            questions.push({
                question: text,
                input_type: inputType,
                control_id: control.id,
                options: options,
            });
        }
        return questions;
    }
    """

    try:
        raw_questions: list[dict] = await page.evaluate(extract_js)
    except Exception as exc:
        errors.append(f"Question extraction failed: {exc}")
        raw_questions = []

    if not raw_questions:
        return {
            "answered_questions": answered,
            "pending_questions": pending,
            "errors": errors,
        }

    # Deduplicate by question text (labels can appear twice in some flows).
    seen_questions: set[str] = set()

    for q in raw_questions:
        q_text     = q.get("question", "").strip()
        input_type = q.get("input_type", "text")
        options    = q.get("options", [])
        control_id = q.get("control_id", "")

        if not q_text or q_text in seen_questions:
            continue
        seen_questions.add(q_text)

        answer: str | None = None
        provenance = ""

        # 1. Check saved user-confirmed answers first.
        if HAS_SCREENING_DB:
            try:
                saved = await get_screening_answer(
                    db, user_id, q_text, input_type=input_type, options=options
                )
                if saved and saved.provenance == "user":
                    answer = saved.answer_text
                    provenance = "saved_user"
            except Exception as exc:
                errors.append(f"DB lookup failed for '{q_text[:60]}': {exc}")

        # 2. No saved answer — do NOT auto-generate one.
        #    Leave it pending so the user can confirm.
        if answer is None:
            pending.append({
                "question": q_text,
                "input_type": input_type,
                "options": options,
                "control_id": control_id,
            })
            continue

        # 3. Apply the verified answer; anything not applied and verified goes
        #    back to the user through pending_questions.
        try:
            applied = await _apply_screening_answer(
                page, q_text, input_type, options, control_id, answer
            )
        except Exception as exc:
            errors.append(f"Fill failed for '{q_text[:60]}': {exc}")
            applied = False

        if applied:
            answered.append({
                "question": q_text,
                "answer": answer,
                "input_type": input_type,
                "provenance": provenance,
            })
        else:
            pending.append({
                "question": q_text,
                "input_type": input_type,
                "options": options,
                "control_id": control_id,
            })

    print(
        f"[screening] answered={len(answered)} "
        f"pending={len(pending)} errors={len(errors)}",
        flush=True,
    )
    return {
        "answered_questions": answered,
        "pending_questions": pending,
        "errors": errors,
    }


async def open_easy_apply(page, job_id: str) -> bool:
    """
    Open the Easy Apply application form for a specific LinkedIn job.

    Steps (derived from verified DOM structure):
      1. Click the job title anchor (a[href*="/jobs/view/{job_id}/"]) to
         load the job's detail panel.
      2. Wait for the "Easy Apply to this job" button to appear in the panel.
      3. Click it.
      4. Verify the application dialog opened by waiting for a heading or
         container element that LinkedIn renders inside the modal.

    Returns True when the form is confirmed open, False otherwise.
    Never raises; all errors are caught and logged.

    The caller is responsible for ensuring the job has a qualifying match
    score before calling this function.  This function does not check scores.

    The page parameter must be an open Playwright Page on the LinkedIn
    jobs search results page.  No new browser sessions are launched here.
    """
    if not job_id:
        print("[easy_apply] No job_id provided — skipping.", flush=True)
        return False

    # Selector for the job title link that activates the detail panel.
    job_link_selector = f'a[href*="/jobs/view/{job_id}/"]'
    # Selector for the Easy Apply CTA button in the detail panel.
    easy_apply_btn_selector = 'button[aria-label="Easy Apply to this job"]'
    # Post-click: LinkedIn's modal renders an h3 with the job title inside a
    # focusable overlay.  We wait for ANY of these stable post-click signals.
    modal_selectors = [
        'div[data-test-modal]',                        # classic modal wrapper
        '[aria-label^="Easy Apply"][role="dialog"]',   # dialog with EA label
        'h3.t-24.t-bold',                              # job title in EA modal
        'dialog[open]',                                # current UI: native <dialog>
    ]

    try:
        # Step 1: click the job card (current Jobs UI) or the job title link
        # (older UI) to load its detail panel.
        link = page.locator(
            f'[role="button"][componentkey="job-card-component-ref-{job_id}"]'
        ).first
        if not await link.is_visible(timeout=2_000):
            link = page.locator(job_link_selector).first
        if not await link.is_visible(timeout=5_000):
            print(
                f"[easy_apply] job_id={job_id}: job link not visible.",
                flush=True,
            )
            return False
        await cursor_click(link)

        # Step 2: wait for the Easy Apply button to appear in the detail panel.
        try:
            await page.wait_for_selector(
                easy_apply_btn_selector, timeout=8_000
            )
        except Exception:
            print(
                f"[easy_apply] job_id={job_id}: "
                "'Easy Apply to this job' button not found — "
                "job may not support Easy Apply.",
                flush=True,
            )
            return False

        # Step 3: click Easy Apply.
        btn = page.locator(easy_apply_btn_selector).first
        if not await btn.is_visible():
            print(
                f"[easy_apply] job_id={job_id}: Easy Apply button not visible.",
                flush=True,
            )
            return False
        await cursor_click(btn)

        # Step 4: verify the modal opened — try each known modal selector.
        for sel in modal_selectors:
            try:
                await page.wait_for_selector(sel, timeout=5_000)
                print(
                    f"[easy_apply] job_id={job_id}: "
                    f"form opened (matched {sel!r}).",
                    flush=True,
                )
                return True
            except Exception:
                continue

        print(
            f"[easy_apply] job_id={job_id}: "
            "Easy Apply clicked but modal did not appear.",
            flush=True,
        )
        return False

    except Exception as exc:
        print(f"[easy_apply] job_id={job_id}: error — {exc}", flush=True)
        return False


# ---------------------------------------------------------------------------
# SEQUENTIAL ITERATION — first-page jobs one at a time
# ---------------------------------------------------------------------------

async def iter_first_page_jobs(
    keywords: str = SEARCH_KEYWORDS,
    date_posted: str = DATE_POSTED_24H,
    easy_apply: bool = DEFAULT_EASY_APPLY,
    remote_only: bool = DEFAULT_REMOTE_ONLY,
    seen_ids: set[str] | None = None,
    fetch_descriptions: bool = True,
    cookies: dict | None = None,
):
    """
    Async generator that yields first-page job cards one at a time in order.

    When `cookies` is supplied (e.g. extracted from an already-open
    Playwright browser context by the caller), get_session_cookies() is
    skipped so no second persistent browser instance is launched.
    When `cookies` is None, cookies are obtained via get_session_cookies()
    as before (standalone / CLI usage).

    Yields dicts with keys: job_id, title, company, location, url, description.
    Does not navigate to page 2.
    """
    if seen_ids is None:
        seen_ids = set()

    _valid_date_posted = {"r86400", "r604800", "r2592000", ""}
    if date_posted not in _valid_date_posted:
        raise ValueError(
            f"Unrecognised date_posted value {date_posted!r}. "
            f"Expected one of {sorted(_valid_date_posted)}."
        )

    # Obtain cookies — reuse caller-supplied ones to avoid a second browser.
    if cookies is None:
        cookies = await get_session_cookies()

    if not cookies.get("li_at"):
        print(
            "[iter] WARNING: No li_at cookie — cannot fetch jobs.",
            flush=True,
        )
        return

    all_jobs = await call_voyager_api(
        cookies,
        start=0,
        keywords=keywords,
        date_posted=date_posted,
        easy_apply=easy_apply,
        remote_only=remote_only,
    )
    jobs = deduplicate(all_jobs)
    print(f"[iter] First-page cards: {len(jobs)}", flush=True)

    for job in jobs:
        job_id = job["job_id"]
        if job_id and job_id in seen_ids:
            print(f"[iter] Skipping duplicate job_id={job_id}", flush=True)
            continue
        if job_id:
            seen_ids.add(job_id)

        # Attach description (empty string when unavailable).
        description = ""
        if fetch_descriptions and job_id:
            description = await fetch_job_description(job_id, cookies)
        job = {**job, "description": description}

        yield job


# ---------------------------------------------------------------------------
# DOM SEARCH — LinkedIn's normal Jobs search UI in the existing browser page
# ---------------------------------------------------------------------------

class SearchError(Exception):
    """LinkedIn search could not be completed (not the same as zero results).

    kind: auth_expired | access_restricted | navigation_timeout | search_failed
    """

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


_CARD_SELECTOR = '[role="button"][componentkey^="job-card-component-ref-"]'

_CARDS_JS = """
() => Array.from(document.querySelectorAll('[role="button"][componentkey^="job-card-component-ref-"]'))
  .map(card => {
    const ps = Array.from(card.querySelectorAll('p'));
    const titleP = ps[0];
    const title = titleP ? (titleP.innerText || '').trim() : '';
    const text = card.innerText || '';
    return {
      job_id: card.getAttribute('componentkey').replace('job-card-component-ref-', ''),
      title,
      company: ps[1] ? ps[1].innerText.trim() : '',
      location: ps[2] ? ps[2].innerText.trim() : '',
      linkedin_applied: /(^|\\n)\\s*Applied\\b/.test(text),
    };
  })
"""

_DESCRIPTION_JS = """
() => {
  const heading = Array.from(document.querySelectorAll('h2'))
    .find(h => h.innerText.trim().toLowerCase() === 'about the job');
  let el = heading;
  while (el && el !== document.body) {
    const box = el.querySelector('[data-testid="expandable-text-box"]');
    if (box) return box.innerText.trim();
    el = el.parentElement;
  }
  const box = document.querySelector('[data-testid="expandable-text-box"]');
  return box ? box.innerText.trim() : '';
}
"""

_AUTH_URL_RE = re.compile(r"linkedin\.com/(login|authwall|uas/login|signup|checkpoint/lg)", re.I)
_RESTRICTED_URL_RE = re.compile(r"linkedin\.com/checkpoint/", re.I)
_RESTRICTED_TEXT_RE = re.compile(
    r"security verification|unusual activity|let's do a quick security check|"
    r"temporarily restricted|you've reached the (weekly|monthly|daily) limit",
    re.I,
)
_ZERO_RESULTS_RE = re.compile(r"no matching jobs found|no results found|\b0 results\b", re.I)


def _check_access(url: str) -> None:
    if _AUTH_URL_RE.search(url):
        raise SearchError("auth_expired", "LinkedIn session expired. Sign in to LinkedIn in the agent browser and retry.")
    if _RESTRICTED_URL_RE.search(url):
        raise SearchError("access_restricted", "LinkedIn is showing a security checkpoint. Complete it manually in the agent browser and retry.")


_MAX_SEARCH_PAGES = 20  # safety cap on pages walked in one scan
LOGIN_WAIT_TIMEOUT_S = int(os.environ.get("LINKEDIN_LOGIN_WAIT_SECONDS", "120"))
_LOGIN_POLL_S = 2


async def _is_logged_in(page) -> bool:
    """True when the session cookie exists and the page is past the login/landing screens."""
    url = page.url
    if _AUTH_URL_RE.search(url):
        return False
    if urlparse(url).path in ("", "/"):  # logged-out landing page (members are redirected to /feed/)
        return False
    cookies = await page.context.cookies("https://www.linkedin.com")
    return any(c.get("name") == "li_at" and c.get("value") for c in cookies)


async def _ensure_logged_in(page) -> None:
    """
    Open linkedin.com and, if the user is not signed in, wait (bounded) for them to
    sign in manually in this same browser, then return so the workflow continues.

    Raises SearchError: auth_expired on timeout, access_restricted on a security
    checkpoint or restriction (never bypassed).
    """
    try:
        await page.goto("https://www.linkedin.com", wait_until="domcontentloaded", timeout=30_000)
    except Exception as exc:
        if "Timeout" in type(exc).__name__ or "timeout" in str(exc).lower():
            raise SearchError("navigation_timeout", "LinkedIn did not load within 30 seconds.") from exc
        raise SearchError("search_failed", f"Could not open LinkedIn: {exc}") from exc

    loop = asyncio.get_running_loop()
    deadline = loop.time() + LOGIN_WAIT_TIMEOUT_S
    announced = False
    while True:
        url = page.url
        if _RESTRICTED_URL_RE.search(url) and not _AUTH_URL_RE.search(url):
            raise SearchError("access_restricted", "LinkedIn is showing a security checkpoint. Complete it manually in the agent browser and retry.")
        try:
            body = await page.inner_text("body", timeout=3_000)
        except Exception:
            body = ""
        if _RESTRICTED_TEXT_RE.search(body):
            raise SearchError("access_restricted", "LinkedIn restricted access. Resolve it manually in the agent browser and retry.")
        if await _is_logged_in(page):
            return
        if not announced:
            print(f"[auth] Not logged in. Sign in to LinkedIn in the agent browser (waiting up to {LOGIN_WAIT_TIMEOUT_S}s).", flush=True)
            announced = True
        if loop.time() >= deadline:
            raise SearchError(
                "auth_expired",
                f"LinkedIn login required: not signed in within {LOGIN_WAIT_TIMEOUT_S} seconds. "
                "Sign in to LinkedIn in the agent browser and retry.",
            )
        await asyncio.sleep(_LOGIN_POLL_S)


async def iter_search_page_jobs(
    page,
    keywords: str = SEARCH_KEYWORDS,
    date_posted: str = DATE_POSTED_24H,
    easy_apply: bool = DEFAULT_EASY_APPLY,
    remote_only: bool = DEFAULT_REMOTE_ONLY,
    seen_ids: set[str] | None = None,
    fetch_descriptions: bool = True,
    start_page: int = 0,
    progress: dict | None = None,
):
    """
    Async generator over job cards rendered by LinkedIn's Jobs search UI in
    the given (already authenticated) Playwright page, page by page
    (start_page is 0-based; progress["page"] tracks the current page).

    Opens each card in the detail panel to read its description, leaving the
    page on the search results so open_easy_apply() can act on that card.
    Returns without yielding when LinkedIn reports zero results.
    Raises SearchError when the search itself could not be completed.
    """
    if seen_ids is None:
        seen_ids = set()

    await _ensure_logged_in(page)

    # Pagination: LinkedIn pages are selected with the `start` URL offset (PAGE_SIZE per
    # page). The caller's `progress["page"]` is kept current so a paused scan can resume
    # on the same page; already processed ids are skipped through `seen_ids`.
    page_index = start_page
    prev_page_ids: set[str] = set()
    while page_index < _MAX_SEARCH_PAGES:
        if progress is not None:
            progress["page"] = page_index
        search_url = _build_browser_search_url(
            keywords=keywords, date_posted=date_posted,
            easy_apply=easy_apply, remote_only=remote_only,
            start=page_index * PAGE_SIZE,
        )
        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30_000)
        except Exception as exc:
            if page_index > 0:
                # Later pages: stop safely, keeping what was already scanned.
                print(f"[search] page {page_index + 1} could not be opened — stopping: {exc}", flush=True)
                return
            if "Timeout" in type(exc).__name__ or "timeout" in str(exc).lower():
                raise SearchError("navigation_timeout", "LinkedIn jobs search page did not load within 30 seconds.") from exc
            raise SearchError("search_failed", f"Could not open LinkedIn jobs search: {exc}") from exc
        _check_access(page.url)

        try:
            await page.wait_for_selector(_CARD_SELECTOR, timeout=20_000)
        except Exception:
            _check_access(page.url)
            body = await page.inner_text("body")
            if _RESTRICTED_TEXT_RE.search(body):
                raise SearchError("access_restricted", "LinkedIn restricted access to job search. Resolve it manually in the agent browser.")
            if page_index > 0 or _ZERO_RESULTS_RE.search(body):
                print(f"[search] No results on page {page_index + 1}.", flush=True)
                return
            raise SearchError("search_failed", "LinkedIn job results did not render on the search page.")

        cards = await page.evaluate(_CARDS_JS)
        page_ids = {c.get("job_id", "") for c in cards if c.get("job_id")}
        if page_index > 0 and page_ids == prev_page_ids:
            print("[search] Next page repeated the previous results — stopping.", flush=True)
            return
        prev_page_ids = page_ids
        print(f"[search] Page {page_index + 1} cards: {len(cards)}", flush=True)

        for card in cards:
            job_id = card.get("job_id", "")
            if not job_id or job_id in seen_ids:
                continue
            seen_ids.add(job_id)
            # The current Jobs UI may drop f_WT on redirect; enforce Remote from the card.
            if remote_only and "(remote)" not in card.get("location", "").lower():
                print(f"[search] job_id={job_id}: not remote ({card.get('location')!r}) — skipped.", flush=True)
                continue
            job = _normalise(card)
            job["linkedin_applied"] = bool(card.get("linkedin_applied"))

            description = ""
            if fetch_descriptions:
                try:
                    # Bounded: an overlay (e.g. an open dialog) must not stall the scan.
                    await cursor_click(
                        page.locator(f'[role="button"][componentkey="job-card-component-ref-{job_id}"]').first,
                        timeout=10_000,
                    )
                    # The detail panel title links to /jobs/view/{id}/ once it shows this job.
                    await page.wait_for_selector(f'a[href*="/jobs/view/{job_id}/"]', timeout=10_000)
                    await page.wait_for_function(f"() => ({_DESCRIPTION_JS})().length > 0", timeout=10_000)
                    description = await page.evaluate(_DESCRIPTION_JS)
                except Exception as exc:
                    print(f"[search] job_id={job_id}: description unavailable — {exc}", flush=True)
                _check_access(page.url)
            yield {**job, "description": description}

        page_index += 1


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
    import sys
    # Accept optional keywords as a CLI argument; fall back to SEARCH_KEYWORDS.
    # Optional second arg overrides date filter (e.g. "" for any time).
    keywords = " ".join(sys.argv[1:2]).strip() or SEARCH_KEYWORDS
    date_posted = sys.argv[2].strip() if len(sys.argv) > 2 else DATE_POSTED_24H

    print("=" * 60, flush=True)
    print("LinkedIn Job Scanner", flush=True)
    print(f"Profile  : {PROFILE_DIR}", flush=True)
    print(f"Output   : {OUTPUT_FILE}", flush=True)
    print(f"Keywords : {keywords}", flush=True)
    print(f"Date     : {date_posted or '(any time)'}", flush=True)
    print(f"EasyApply: {DEFAULT_EASY_APPLY}", flush=True)
    print(f"Remote   : {DEFAULT_REMOTE_ONLY}", flush=True)
    print("=" * 60, flush=True)

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    jobs: list[dict] = []
    i = 0
    async for job in iter_first_page_jobs(
        keywords=keywords,
        date_posted=date_posted,
        easy_apply=DEFAULT_EASY_APPLY,
        remote_only=DEFAULT_REMOTE_ONLY,
    ):
        i += 1
        print(
            f"\n  #{i:03d}  {job['title']}\n"
            f"       Company    : {job['company'] or '(empty)'}\n"
            f"       Location   : {job['location'] or '(empty)'}\n"
            f"       ID         : {job['job_id']}\n"
            f"       URL        : {job['url']}\n"
            f"       Description: {len(job.get('description', ''))} chars",
            flush=True,
        )
        jobs.append(job)

    print("\n" + "=" * 60, flush=True)
    print(f"TOTAL UNIQUE JOBS FOUND: {len(jobs)}", flush=True)
    print("=" * 60, flush=True)

    save_jobs(jobs)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
