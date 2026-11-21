"""Temporary, read-only: type the search like a user and list the page's controls."""
import asyncio
import json
import logging

logging.disable(logging.CRITICAL)

from app.main import app  # noqa: F401
from app.agents.browser_agent import _ensure_logged_in
from app.services.apply_workflow import _get_context, close_browser_session

CONTROLS_JS = """() => {
  const vis = e => e.getClientRects().length > 0;
  const txt = e => (e.innerText || e.getAttribute('aria-label') || '').replace(/\\s+/g, ' ').trim().slice(0, 60);
  const pick = e => ({tag: e.tagName.toLowerCase(), role: e.getAttribute('role'), text: txt(e),
    aria: (e.getAttribute('aria-label') || '').slice(0, 60), pressed: e.getAttribute('aria-pressed'),
    expanded: e.getAttribute('aria-expanded'), id: e.id || null, type: e.getAttribute('type'),
    ph: e.getAttribute('placeholder')});
  return {
    url: location.href,
    inputs: Array.from(document.querySelectorAll('input')).filter(vis).map(pick).slice(0, 10),
    buttons: Array.from(document.querySelectorAll('button, a[role="button"], [role="radio"], [role="tab"], [role="checkbox"], a'))
      .filter(vis).map(pick).filter(b => b.text && b.text.length < 40).slice(0, 80),
  };
}"""


async def main() -> None:
    ctx = await _get_context()
    try:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await _ensure_logged_in(page)
        print("FEED", page.url, flush=True)
        box = page.get_by_role("combobox", name="Search").or_(page.get_by_placeholder("Search")).first
        await box.click(timeout=10_000)
        await box.fill("Java remote")
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(8_000)
        data = await page.evaluate(CONTROLS_JS)
        with open("../_tmp/controls_after_search.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
        print("AFTER SEARCH", data["url"][:150], flush=True)
        for b in data["buttons"]:
            print("   ", b["tag"], b["role"], "|", b["text"], "| pressed:", b["pressed"], "| expanded:", b["expanded"], flush=True)
        await page.screenshot(path="../_tmp/after_search.png")
    finally:
        await close_browser_session()


asyncio.run(main())
