from __future__ import annotations

import asyncio
import json

from app.db.session import get_engine, get_sessionmaker
from app.services.attendance_outbox import sync_pending_outbox


async def _run() -> None:
    async with get_sessionmaker()() as db:
        result = await sync_pending_outbox(db)
    print(json.dumps(result, sort_keys=True))
    await get_engine().dispose()


if __name__ == "__main__":
    asyncio.run(_run())
