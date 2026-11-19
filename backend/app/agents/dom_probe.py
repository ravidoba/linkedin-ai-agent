"""
dom_probe_v4.py — Capture the exact Voyager API calls LinkedIn makes.

Navigates to the jobs page and records ALL Voyager API calls including
their full request URLs.  Saves them so we can replicate the calls.

Run from WSL (backend/ as cwd):
    DISPLAY=:0 .venv/bin/python -m app.agents.dom_probe
"""

import asyncio
import json
from pathlib import Path
from urllib.parse import urlencode

from playwright.async_api import TimeoutError as PWTimeout, async_playwright

PROFILE_DIR = Path.home() / ".linkedin-ai-agent" / "browser-profile"
OUT_DIR = Path(__file__).resolve().parents[2]  # backend/

SEARCH_URL = (
    "https://www.linkedin.com/jobs/search/?"
    + urlencode({"keywords": "Java Backend Developer", "f_WT": "2"})
)


async def probe():
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    all_responses: list[dict] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1280, "height": 900},
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
            ignore_default_args=["--enable-automation"],
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()

        await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        # Capture ALL requests and responses.
        async def on_request(request):
            url = request.url
            if "voyager" in url or "graphql" in url or "jobs" in url.lower():
                print(f"[REQ] {request.method} {url[:150]}", flush=True)

        async def on_response(response):
            url = response.url
            ct  = response.headers.get("content-type", "")
            if "json" not in ct:
                return
            try:
                body = await response.json()
                all_responses.append({"url": url, "body": body})
            except Exception:
                pass

        page.on("request", on_request)
        page.on("response", on_response)

        print(f"Navigating to: {SEARCH_URL}", flush=True)
        try:
            await page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=60_000)
        except Exception as exc:
            print(f"nav error: {exc}", flush=True)

        print(f"Landed: {page.url}", flush=True)
        print("Waiting 90s for all API calls…", flush=True)
        await page.wait_for_timeout(90_000)

        # Analyse responses.
        print(f"\nTotal JSON responses: {len(all_responses)}", flush=True)

        # Find job-related ones.
        job_responses = []
        for r in all_responses:
            body_str = json.dumps(r["body"])
            if any(k in body_str for k in [
                "jobPosting", "jobCard", "jobResult", "fsd_jobPosting",
                "jobseekerJobResult", "jobSearchBlend", "voyagerJobsDash",
                "jobPostingTitle", "companyName",
            ]):
                job_responses.append(r)
                print(f"\n[JOB RESPONSE] URL: {r['url'][:150]}")
                print(f"  Body snippet: {body_str[:600]}")

        print(f"\nTotal job-related responses: {len(job_responses)}", flush=True)

        # Save ALL responses for inspection.
        (OUT_DIR / "all_api_responses.json").write_text(
            json.dumps([
                {"url": r["url"], "body": r["body"]}
                for r in all_responses
            ], indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        print("All responses saved to all_api_responses.json", flush=True)

        # Save job responses separately.
        if job_responses:
            (OUT_DIR / "job_api_responses.json").write_text(
                json.dumps(job_responses, indent=2, ensure_ascii=False,
                           default=str),
                encoding="utf-8",
            )
            print("Job responses saved to job_api_responses.json", flush=True)

        # Full page snapshot.
        full_html = await page.content()
        (OUT_DIR / "dom_snapshot.html").write_text(full_html, encoding="utf-8")
        print(f"DOM snapshot: {len(full_html)} chars", flush=True)

        await browser.close()
        print("Probe complete.", flush=True)


if __name__ == "__main__":
    asyncio.run(probe())
