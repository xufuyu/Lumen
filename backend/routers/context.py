"""Context snapshot endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import current_lang, current_user_id, get_db, pick
from models import Context, RecordContext
from schemas import ContextOut

router = APIRouter(prefix="/api/context", tags=["context"])


@router.get("/current", response_model=ContextOut)
async def get_current_context(
    db: AsyncSession = Depends(get_db),
    uid: str = Depends(current_user_id),
    lang: str = Depends(current_lang),
):
    """Get the most recent context snapshot."""
    result = await db.execute(
        select(Context).where(Context.user_id == uid).order_by(Context.created_at.desc()).limit(1)
    )
    context = result.scalar_one_or_none()

    if not context:
        # Return an empty/placeholder context
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        return ContextOut(
            id=0,
            summary=pick(
                lang,
                "尚无足够的记录来生成当前状态摘要。开始记录你的日常，系统会帮你整理。",
                "Not enough records yet to summarize your current state. Start journaling and I'll organize it for you.",
            ),
            valid_from=now,
            valid_until=None,
            created_at=now,
            source_record_ids=[],
        )

    # Get linked record IDs
    recs_result = await db.execute(
        select(RecordContext.record_id).where(RecordContext.context_id == context.id)
    )
    source_ids = [rid for (rid,) in recs_result.all()]

    return ContextOut(
        id=context.id,
        summary=context.summary,
        valid_from=context.valid_from,
        valid_until=context.valid_until,
        created_at=context.created_at,
        source_record_ids=source_ids,
    )
