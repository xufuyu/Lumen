"""Task management endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import current_user_id, get_db
from models import RecordTask, Task
from schemas import TaskCreate, TaskList, TaskOut, TaskStatus, TaskUpdate

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


async def _to_out(task: Task, db: AsyncSession) -> TaskOut:
    """Hydrate a TaskOut with source record IDs."""
    result = await db.execute(
        select(RecordTask.record_id).where(RecordTask.task_id == task.id)
    )
    source_ids = [rid for (rid,) in result.all()]

    return TaskOut(
        id=task.id,
        title=task.title,
        description=task.description,
        status=task.status,  # type: ignore[arg-type]
        priority=task.priority,  # type: ignore[arg-type]
        due_date=task.due_date,
        confidence=task.confidence,
        created_at=task.created_at,  # type: ignore[arg-type]
        completed_at=task.completed_at,
        source_record_ids=source_ids,
    )


@router.get("", response_model=TaskList)
async def list_tasks(
    status: str | None = None,
    sort: str = Query("priority", pattern="^(priority|due_date|created_at)$"),
    db: AsyncSession = Depends(get_db), uid: str = Depends(current_user_id),
):
    """List tasks, optionally filtered by status."""
    base = select(Task).where(Task.user_id == uid, Task.status != "deleted")

    if status:
        statuses = [s.strip() for s in status.split(",")]
        base = base.where(Task.status.in_(statuses))

    # Default: show pending + in_progress
    if not status:
        base = base.where(Task.status.in_(["pending", "in_progress"]))

    # Sort
    if sort == "priority":
        # Higher priority first, then by due_date
        base = base.order_by(Task.priority.desc(), Task.due_date.asc().nullslast())
    elif sort == "due_date":
        base = base.order_by(Task.due_date.asc().nullslast(), Task.priority.desc())
    else:
        base = base.order_by(Task.created_at.desc())

    result = await db.execute(base.limit(100))
    tasks = result.scalars().all()

    items = [await _to_out(t, db) for t in tasks]
    return TaskList(items=items, total=len(items))


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: int, db: AsyncSession = Depends(get_db), uid: str = Depends(current_user_id)):
    """Get a single task with source records."""
    result = await db.execute(select(Task).where(Task.user_id == uid, Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return await _to_out(task, db)


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(body: TaskCreate, db: AsyncSession = Depends(get_db), uid: str = Depends(current_user_id)):
    """Manually create a task (not inferred from records)."""
    task = Task(
        title=body.title,
        description=body.description,
        priority=body.priority.value,
        due_date=body.due_date,
        status="pending",
        confidence=1.0,  # User-created = high confidence
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return await _to_out(task, db)


@router.put("/{task_id}", response_model=TaskOut)
async def update_task(task_id: int, body: TaskUpdate, db: AsyncSession = Depends(get_db), uid: str = Depends(current_user_id)):
    """Update a task's details or status."""
    result = await db.execute(select(Task).where(Task.user_id == uid, Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if body.title is not None:
        task.title = body.title
    if body.description is not None:
        task.description = body.description
    if body.status is not None:
        task.status = body.status.value
        if body.status == TaskStatus.DONE:
            task.completed_at = datetime.now(timezone.utc)
        elif body.status in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS):
            task.completed_at = None
    if body.priority is not None:
        task.priority = body.priority.value
    if body.due_date is not None:
        task.due_date = body.due_date

    await db.commit()
    await db.refresh(task)
    return await _to_out(task, db)


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: int, db: AsyncSession = Depends(get_db), uid: str = Depends(current_user_id)):
    """Soft-delete a task."""
    result = await db.execute(select(Task).where(Task.user_id == uid, Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = "deleted"
    await db.commit()
    return None
