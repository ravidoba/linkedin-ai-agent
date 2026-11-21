"""Temporary: latest runs, to make sure none is in progress."""
import asyncio
import logging

logging.disable(logging.CRITICAL)

from sqlalchemy import text

from app.db.database import AsyncSessionLocal, engine


async def main() -> None:
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(text("select id, status, created_at from agent_runs order by id desc limit 3"))).all()
        print("LATEST RUNS", [tuple(r) for r in rows], flush=True)
    await engine.dispose()


asyncio.run(main())
