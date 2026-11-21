"""Temporary: read-only search through the workflow, showing each clicked step."""
import asyncio
import logging

logging.disable(logging.CRITICAL)

from sqlalchemy import select

from app.main import app  # noqa: F401
from app.db.database import AsyncSessionLocal, engine
from app.models.user import User
from app.services import apply_workflow as w


async def main() -> None:
    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User).limit(1))
        uid = user.id
        w.emit_activity(uid, "searching_jobs", "running", "marker")
        start = w._activity_sequence[uid]
        try:
            result = await w.run_apply_workflow(db=db, user=user, intent="search", max_results=8,
                                                keywords="Java", remote_only=True, date_posted="r86400")
            ctx = w._context
            page = ctx.pages[0] if ctx and ctx.pages else None
            if page is not None:
                print("FINAL URL:", page.url[:220], flush=True)
                await page.screenshot(path="../_tmp/click_search.png")
        finally:
            await w.close_browser_session()
        for e in w._activity[uid]:
            if e["id"] > start and e["type"] == "searching_jobs":
                print("STEP:", e["status"], "|", e["message"][:160], flush=True)
        print("RESULT:", result.get("status"), "|", result.get("message"), flush=True)
        for job in result.get("jobs", []):
            print("   -", job.get("title"), "|", job.get("company"), "|", job.get("location"), flush=True)
    await engine.dispose()


asyncio.run(main())
