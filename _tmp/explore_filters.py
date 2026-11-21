"""Temporary: search, click Jobs, then record the filter bar and each filter's options."""
import asyncio
import logging

logging.disable(logging.CRITICAL)

from app.main import app  # noqa: F401
from app.agents.browser_agent import _ensure_logged_in
from app.services.apply_workflow import _get_context, close_browser_session

# Visible clickable elements in a vertical band (the filter bar) or inside open popovers.
BAND_JS = """([top, bottom]) => {
  const out = [];
  for (const e of document.querySelectorAll('button, a, label, [role="radio"], [role="checkbox"], [role="switch"], [role="option"], input[type="radio"], input[type="checkbox"]')) {
    const r = e.getBoundingClientRect();
    if (!r.width || r.top < top || r.top > bottom) continue;
    const t = (e.innerText || e.getAttribute('aria-label') || '').replace(/\\s+/g, ' ').trim();
    if (!t && e.tagName !== 'INPUT') continue;
    out.push([e.tagName.toLowerCase(), e.getAttribute('role'), t.slice(0, 40), e.getAttribute('aria-label'),
              e.getAttribute('aria-pressed') || e.getAttribute('aria-checked') || e.getAttribute('aria-expanded'),
              Math.round(r.left), Math.round(r.top)]);
  }
  return out;
}"""
POPOVER_JS = """() => {
  const pops = Array.from(document.querySelectorAll('[role="dialog"], [role="listbox"], [role="menu"], [data-test-modal], .artdeco-dropdown__content, [aria-modal="true"], fieldset'))
    .filter(p => p.getClientRects().length && (p.innerText || '').trim());
  return pops.map(p => ({role: p.getAttribute('role'), aria: p.getAttribute('aria-label'),
    text: (p.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 300),
    controls: Array.from(p.querySelectorAll('button, label, input, [role="radio"], [role="checkbox"], [role="option"]'))
      .map(c => [c.tagName.toLowerCase(), c.getAttribute('type'), (c.innerText || c.getAttribute('aria-label') || c.value || '').replace(/\\s+/g, ' ').trim().slice(0, 40)])
      .filter(c => c[2]).slice(0, 25)}));
}"""


async def dump(page, label: str) -> None:
    print(f"=== {label} | {page.url[:160]}", flush=True)
    for row in await page.evaluate(BAND_JS, [50, 175]):
        print("   ", row, flush=True)


async def main() -> None:
    ctx = await _get_context()
    try:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await _ensure_logged_in(page)
        box = page.get_by_role("combobox", name="Search").or_(page.get_by_placeholder("Search")).first
        await box.click(timeout=10_000)
        await box.fill("Java remote")
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(6_000)
        await dump(page, "RESULTS (all)")

        # The "Jobs" pill in the filter bar (not the top navigation "Jobs" icon).
        pills = page.locator("label, button, a").filter(has_text="Jobs")
        clicked = False
        for i in range(await pills.count()):
            el = pills.nth(i)
            box_ = await el.bounding_box()
            if box_ and 55 < box_["y"] < 110 and (await el.inner_text()).strip() == "Jobs":
                await el.click()
                clicked = True
                break
        print("clicked Jobs pill:", clicked, flush=True)
        await page.wait_for_timeout(8_000)
        await dump(page, "JOBS VIEW")
        await page.screenshot(path="../_tmp/jobs_view.png")

        # Open each filter that matters and record its options (then close it with Escape).
        for name in ("Date posted", "Past 24 hours", "Remote", "Workplace type", "On-site/remote", "Easy Apply"):
            btn = page.locator("button, label, a").filter(has_text=name).first
            if not await btn.count() or not await btn.is_visible():
                print(f"--- filter '{name}': not found", flush=True)
                continue
            print(f"--- filter '{name}': aria-pressed/expanded = "
                  f"{await btn.get_attribute('aria-pressed')} / {await btn.get_attribute('aria-expanded')}", flush=True)
            if name == "Easy Apply":
                continue  # a toggle; do not click during exploration
            await btn.click()
            await page.wait_for_timeout(2_000)
            for pop in await page.evaluate(POPOVER_JS):
                print("     popover:", pop["role"], pop["aria"], "|", pop["text"][:160], flush=True)
                print("       controls:", pop["controls"], flush=True)
            await page.screenshot(path=f"../_tmp/filter_{name.replace('/', '_').replace(' ', '_')}.png")
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(1_000)
    finally:
        await close_browser_session()


asyncio.run(main())
