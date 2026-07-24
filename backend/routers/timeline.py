"""Timeline / Events endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import current_user_id, get_db
from models import Event, RecordEvent
from schemas import EventList, EventOut, EventStatus, EventUpdate

router = APIRouter(prefix="/api/timeline", tags=["timeline"])


async def _to_out(event: Event, db: AsyncSession) -> EventOut:
    """Hydrate an EventOut with source record IDs."""
    result = await db.execute(
        select(RecordEvent.record_id).where(RecordEvent.event_id == event.id)
    )
    source_ids = [rid for (rid,) in result.all()]

    return EventOut(
        id=event.id,
        title=event.title,
        description=event.description,
        start_time=event.start_time,
        end_time=event.end_time,
        confidence=event.confidence,
        status=event.status,  # type: ignore[arg-type]
        created_at=event.created_at,  # type: ignore[arg-type]
        source_record_ids=source_ids,
    )


@router.get("", response_model=EventList)
async def list_events(
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List timeline events, ordered by start_time descending."""
    base = select(Event).where(Event.user_id == uid, (Event.status != "deleted")

    if status:
        statuses = [s.strip() for s in status.split(",")]
        base = base.where(Event.status.in_(statuses))

    if from_date:
        try:
            dt_from = datetime.fromisoformat(from_date)
            base = base.where(Event.start_time >= dt_from)
        except ValueError:
            pass

    if to_date:
        try:
            dt_to = datetime.fromisoformat(to_date)
            base = base.where(Event.start_time <= dt_to)
        except ValueError:
            pass

    result = await db.execute(
        base.order_by(Event.start_time.desc().nullslast(), Event.created_at.desc()).limit(limit)
    )
    events = result.scalars().all()

    items = [await _to_out(e, db) for e in events]
    return EventList(items=items, total=len(items))


@router.get("/{event_id}", response_model=EventOut)
async def get_event(event_id: int, db: AsyncSession = Depends(get_db), uid: str = Depends(current_user_id)):
    """Get a single event with its source records."""
    result = await db.execute(select(Event).where(Event.user_id == uid, (Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return await _to_out(event, db)


@router.put("/{event_id}", response_model=EventOut)
async def update_event(
    event_id: int, body: EventUpdate, db: AsyncSession = Depends(get_db)
):
    """Confirm, modify, or delete an event."""
    result = await db.execute(select(Event).where(Event.user_id == uid, (Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    if body.title is not None:
        event.title = body.title
        if event.status == "inferred":
            event.status = "modified"
    if body.description is not None:
        event.description = body.description
        if event.status == "inferred":
            event.status = "modified"
    if body.start_time is not None:
        event.start_time = body.start_time
    if body.end_time is not None:
        event.end_time = body.end_time
    if body.status is not None:
        event.status = body.status.value

    await db.commit()
    await db.refresh(event)
    return await _to_out(event, db)


@router.delete("/{event_id}", status_code=204)
async def delete_event(event_id: int, db: AsyncSession = Depends(get_db), uid: str = Depends(current_user_id)):
    """Soft-delete an event."""
    result = await db.execute(select(Event).where(Event.user_id == uid, (Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    event.status = "deleted"
    await db.commit()
    return None
