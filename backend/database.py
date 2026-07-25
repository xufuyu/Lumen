"""SQLite database setup with SQLAlchemy async engine."""

import logging

from fastapi import Header, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from config import DATABASE_URL
from security import validate_table_name

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
            validate_table_name(table)
            try:
                await conn.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default'"
                ))
                logger.info(f"Migration: added user_id to {table}")
            except Exception:
                pass  # column already exists

        # Migration: add started_at to tasks (records when the task first entered in_progress)
        try:
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN started_at DATETIME"))
            logger.info("Migration: added started_at to tasks")
        except Exception:
            pass  # column already exists


async def current_user_id(
    request: Request,
    x_user_id: str = Header(default="default", alias="X-User-ID"),
) -> str:
    """Extract user_id from X-User-ID header. Falls back to 'default'."""
    return x_user_id.strip() or "default"


SUPPORTED_LANGS = {"zh-CN", "en"}


async def current_lang(
    x_user_language: str = Header(default="zh-CN", alias="X-User-Language"),
) -> str:
    """Extract UI language from X-User-Language header. Falls back to 'zh-CN'.

    The frontend sends the current i18n locale with every request; the backend
    uses it to localize LLM output and user-facing messages.
    """
    lang = x_user_language.strip()
    return lang if lang in SUPPORTED_LANGS else "zh-CN"


def pick(lang: str, zh: str, en: str) -> str:
    """Pick a user-facing message by UI language."""
    return en if lang == "en" else zh
