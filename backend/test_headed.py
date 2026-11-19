"""Quick test: can we open a headed Chromium via WSLg?"""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

PROFILE_DIR = Path.home() / ".linkedin-ai-agent" / "browser-profile"

async def main():
    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                headless=False,
                viewport={"width": 800, "height": 600},
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            page = browser.pages[0] if browser.pages else await browser.new_page()
            print("Headed browser opened successfully")
            await page.goto("https://www.linkedin.com/jobs/search-results", wait_until="domcontentloaded", timeout=30000)
            print(f"URL: {page.url}")
            await asyncio.sleep(3)
            counts = await page.evaluate("""() => ({
                jobViewLinks: document.querySelectorAll('a[href*="/jobs/view/"]').length,
                occludable: document.querySelectorAll('[data-occludable-job-id]').length,
                ulItems: document.querySelectorAll('ul > li').length,
            })""")
            print(f"Counts after 3s: {counts}")
            await asyncio.sleep(5)
            counts2 = await page.evaluate("""() => ({
                jobViewLinks: document.querySelectorAll('a[href*="/jobs/view/"]').length,
                occludable: document.querySelectorAll('[data-occludable-job-id]').length,
                ulItems: document.querySelectorAll('ul > li').length,
            })""")
            print(f"Counts after 8s: {counts2}")
            await browser.close()
            print("Done")
        except Exception as e:
            print(f"ERROR: {e}")

asyncio.run(main())
