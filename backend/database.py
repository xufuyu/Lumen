"""SQLite database setup with SQLAlchemy async engine."""

import logging

from fastapi import Header, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from config import DATABASE_URL

logger = logging.getLogger(__name__)

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:  # type: ignore[misc]
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Create all tables and apply migrations. Call once at startup."""
    from models import Record, Event, Task, Context, Mood  # noqa: F401
    from models import RecordEvent, RecordTask, RecordContext  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Migration: add user_id columns if missing
        for table in ["records", "events", "tasks", "contexts", "moods"]:
            try:
                await conn.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default'"
                ))
                logger.info(f"Migration: added user_id to {table}")
            except Exception:
                pass  # column already exists


async def current_user_id(
    request: Request,
    x_user_id: str = Header(default="default", alias="X-User-ID"),
) -> str:
    """Extract user_id from X-User-ID header. Falls back to 'default'."""
    return x_user_id.strip() or "default"
