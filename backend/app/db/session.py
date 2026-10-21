import os
from collections.abc import AsyncIterator
from functools import lru_cache

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    if not os.getenv("DATABASE_URL", "").strip():
        raise HTTPException(
            status_code=503,
            detail="Database is not configured. Set DATABASE_URL to enable authentication.",
        )
    async with get_sessionmaker()() as session:
        yield session
