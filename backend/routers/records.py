"""Record CRUD endpoints."""

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Record, RecordEvent, RecordTask
from schemas import RecordCreate, RecordList, RecordOut, RecordUpdate

router = APIRouter(prefix="/api/records", tags=["records"])


# 允许的 7 类声学情绪 —— 用集合过滤脏输入
_ALLOWED_EMOTIONS = {
    "neutral", "happy", "sad", "angry", "fearful", "disgusted", "surprised",
}


async def _to_out(record: Record, db: AsyncSession) -> RecordOut:
    """Hydrate a RecordOut with linked IDs."""
    # Get linked event IDs
    ev_result = await db.execute(
        select(RecordEvent.event_id).where(RecordEvent.record_id == record.id)
    )
    event_ids = [eid for (eid,) in ev_result.all()]

    # Get linked task IDs
    tk_result = await db.execute(
        select(RecordTask.task_id).where(RecordTask.record_id == record.id)
    )
    task_ids = [tid for (tid,) in tk_result.all()]

    return RecordOut(
        id=record.id,
        content=record.content,
        type=record.type,  # type: ignore[arg-type]
        status=record.status,  # type: ignore[arg-type]
        created_at=record.created_at,  # type: ignore[arg-type]
        updated_at=record.updated_at,  # type: ignore[arg-type]
        linked_event_ids=event_ids,
        linked_task_ids=task_ids,
    )


@router.post("", response_model=RecordOut, status_code=201)
async def create_record(body: RecordCreate, db: AsyncSession = Depends(get_db)):
    """Create a new record. It will be auto-processed in the background."""
    meta: dict = {}
    if body.voice_emotion and body.voice_emotion in _ALLOWED_EMOTIONS:
        meta["voice_emotion"] = body.voice_emotion
    record = Record(
        content=body.content,
        type=body.type.value,
        status="unprocessed",
        meta_json=json.dumps(meta, ensure_ascii=False) if meta else "{}",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return await _to_out(record, db)


@router.get("", response_model=RecordList)
async def list_records(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List records with pagination and optional status filter."""
    base = select(Record)
    count_base = select(func.count(Record.id))

    if status:
        base = base.where(Record.status == status)
        count_base = count_base.where(Record.status == status)

    total_result = await db.execute(count_base)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(
        base.order_by(Record.created_at.desc()).offset(offset).limit(page_size)
    )
    records = result.scalars().all()

    items = [await _to_out(r, db) for r in records]
    return RecordList(items=items, total=total, page=page, page_size=page_size)


@router.get("/{record_id}", response_model=RecordOut)
async def get_record(record_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single record with linked event and task IDs."""
    result = await db.execute(select(Record).where(Record.id == record_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return await _to_out(record, db)


@router.put("/{record_id}", response_model=RecordOut)
async def update_record(
    record_id: int, body: RecordUpdate, db: AsyncSession = Depends(get_db)
):
    """Edit a record's content or status."""
    result = await db.execute(select(Record).where(Record.id == record_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    if body.content is not None:
        record.content = body.content
        # Re-trigger processing when content changes
        record.status = "unprocessed"
    if body.status is not None:
        record.status = body.status.value

    await db.commit()
    await db.refresh(record)
    return await _to_out(record, db)


@router.delete("/{record_id}", status_code=204)
async def delete_record(record_id: int, db: AsyncSession = Depends(get_db)):
    """Soft-delete a record by archiving it."""
    result = await db.execute(select(Record).where(Record.id == record_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    record.status = "archived"
    await db.commit()
    return None
