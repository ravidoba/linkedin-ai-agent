"""Check what user-agent and automation flags Playwright sends."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

PROFILE_DIR = Path.home() / ".linkedin-ai-agent" / "browser-profile"

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()
        
        # Check what UA and CDP flags are set.
        ua = await page.evaluate("navigator.userAgent")
        webdriver = await page.evaluate("navigator.webdriver")
        platform = await page.evaluate("navigator.platform")
        
        print(f"User-Agent: {ua}")
        print(f"webdriver:  {webdriver}")
        print(f"platform:   {platform}")
        
        # Check if we can see the full page on a neutral URL.
        await page.goto("https://httpbin.org/headers", timeout=15000)
        headers = await page.inner_text("body")
        print(f"\nhttpbin headers:\n{headers[:500]}")
        
        await browser.close()

asyncio.run(main())
