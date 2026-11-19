
import asyncio
import json
from pathlib import Path
from urllib.parse import urlencode

from playwright.async_api import async_playwright


PROFILE_DIR = Path.home() / ".linkedin-ai-agent" / "browser-profile"

SEARCH_PARAMS = {
    "keywords": "Java Backend Developer",
    "f_WT": "2",  # Remote jobs
}


async def scan_jobs(page):
    await page.goto(
        "https://www.linkedin.com/jobs/search/?" + urlencode(SEARCH_PARAMS),
        wait_until="domcontentloaded",
        timeout=60000,
    )

    await page.locator(
        ".job-card-container, .jobs-search-results__list-item"
    ).first.wait_for(timeout=20000)

    await page.wait_for_timeout(2000)

    jobs = await page.locator(
        ".job-card-container, .jobs-search-results__list-item"
    ).evaluate_all(
        """cards => cards.map(card => {
            const title = card.querySelector(
                '.job-card-list__title, .job-card-container__link'
            );
            const company = card.querySelector(
                '.job-card-container__primary-description, .artdeco-entity-lockup__subtitle'
            );
            const location = card.querySelector(
                '.job-card-container__metadata-item, .artdeco-entity-lockup__caption'
            );
            const link = card.querySelector('a[href*="/jobs/view/"]');

            return {
                title: title?.innerText?.trim() || "",
                company: company?.innerText?.trim() || "",
                location: location?.innerText?.trim() || "",
                url: link?.href || ""
            };
        }).filter(job => job.title)"""
    )

    return jobs


async def main():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1280, "height": 800},
        )

        try:
            page = browser.pages[0] if browser.pages else await browser.new_page()

            jobs = await scan_jobs(page)

            print(f"\nTotal jobs found: {len(jobs)}")
            print(json.dumps(jobs, indent=2, ensure_ascii=False))

            output = Path("linkedin_jobs.json")
            output.write_text(
                json.dumps(jobs, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"\nSaved to: {output.resolve()}")

            print("Browser will remain open. Press Ctrl+C to stop.")
            await asyncio.sleep(24 * 60 * 60)

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
