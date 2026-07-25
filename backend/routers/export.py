"""Markdown export endpoint — 3 scopes: all / today / pending.

Design:
- Read-only, no rate limiting beyond the global READ_LIMIT (600/min).
- Returns a `text/markdown` body with a filename hint so browsers download it.
- Datetimes are rendered in the SERVER's local timezone. This matches how the
  frontend renders them via `toLocaleString`, and how the LLM prompt writes
  future ISO timestamps.

Not designed for programmatic re-import — this is human-readable output.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import current_user_id, get_db
from models import Event, Record, Task

router = APIRouter(prefix="/api/export", tags=["export"])


# ── Formatting helpers ──────────────────────────────────────────────────────


def _local(dt: datetime | None) -> str:
    """Render a datetime in the server's local timezone as `YYYY-MM-DD HH:MM`.

    SQLite stores DateTime columns as naive UTC. We assume naive → UTC and
    then shift to local for display. Naive-in / aware-in are both handled.
    """
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


def _date_only(dt: datetime | None) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().strftime("%Y-%m-%d")


def _today_start_end() -> tuple[datetime, datetime]:
    """Return (start_of_today, start_of_tomorrow) as UTC-aware datetimes,
    based on the SERVER's local calendar day. Used to filter `today` scope."""
    now_local = datetime.now(timezone.utc).astimezone()
    start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(hour=23, minute=59, second=59)
    # Convert back to UTC for DB comparison (SQLite stores naive UTC).
    return start.astimezone(timezone.utc).replace(tzinfo=None), end.astimezone(timezone.utc).replace(tzinfo=None)  # type: ignore[return-value]


_PRIORITY_ZH = {"low": "低", "medium": "中", "high": "高"}
_STATUS_ZH = {"pending": "待办", "in_progress": "进行中", "done": "已完成"}


def _task_line(task: Task) -> str:
    """One task rendered as a checkbox line, with priority + due + timestamps."""
    checkbox = "[x]" if task.status == "done" else "[ ]"
    bits: list[str] = [f"- {checkbox} {task.title}"]
    meta: list[str] = []
    if task.priority and task.priority != "medium":
        meta.append(f"优先级 {_PRIORITY_ZH.get(task.priority, task.priority)}")
    if task.status == "in_progress":
        meta.append("进行中")
    if task.due_date:
        meta.append(f"截止 {_local(task.due_date)}")
    if meta:
        bits[0] += f" · ({' · '.join(meta)})"
    stamp_bits: list[str] = []
    stamp_bits.append(f"创建 {_local(task.created_at)}")
    if task.started_at:
        stamp_bits.append(f"开始 {_local(task.started_at)}")
    if task.completed_at:
        stamp_bits.append(f"完成 {_local(task.completed_at)}")
    if task.description:
        bits.append(f"    - {task.description}")
    bits.append(f"    - _{' · '.join(stamp_bits)}_")
    return "\n".join(bits)


def _event_line(event: Event) -> str:
    ts = _local(event.start_time or event.created_at)
    bits: list[str] = [f"- **{ts}** · {event.title}"]
    if event.description:
        bits.append(f"    - {event.description}")
    return "\n".join(bits)


def _record_line(rec: Record) -> str:
    kind = "🎙️ 语音" if rec.type == "voice" else "✍️ 文字"
    return f"- **{_local(rec.created_at)}** · {kind} · {rec.content}"


# ── Endpoint ────────────────────────────────────────────────────────────────


@router.get("", response_class=PlainTextResponse)
async def export_markdown(
    scope: str = Query("all", pattern="^(all|today|pending)$"),
    format: str = Query("md", pattern="^(md)$"),
    db: AsyncSession = Depends(get_db),
    uid: str = Depends(current_user_id),
):
    """Export user data as a markdown document.

    - `scope=all` → 全部记录/任务/事件（不含已删除）
    - `scope=today` → 今日创建、今日到期、今日完成、今日发生的项
    - `scope=pending` → 状态为 pending / in_progress 的任务
    """
    if format != "md":
        raise HTTPException(status_code=400, detail="Only 'md' format is currently supported.")

    # Query the three collections independently, then trim per scope.
    tasks_q = select(Task).where(Task.user_id == uid, Task.status != "deleted").order_by(Task.due_date.asc().nullslast(), Task.created_at.desc())
    events_q = select(Event).where(Event.user_id == uid, Event.status != "deleted").order_by(Event.start_time.desc().nullslast(), Event.created_at.desc())
    records_q = select(Record).where(Record.user_id == uid).order_by(Record.created_at.desc())

    tasks = list((await db.execute(tasks_q)).scalars().all())
    events = list((await db.execute(events_q)).scalars().all())
    records = list((await db.execute(records_q)).scalars().all())

    scope_label: str
    if scope == "today":
        scope_label = "今日"
        start, end = _today_start_end()
        def _today(d: datetime | None) -> bool:
            return d is not None and start <= d <= end
        tasks = [t for t in tasks if _today(t.created_at) or _today(t.due_date) or _today(t.completed_at)]
        events = [e for e in events if _today(e.start_time) or _today(e.created_at)]
        records = [r for r in records if _today(r.created_at)]
    elif scope == "pending":
        scope_label = "未完成"
        tasks = [t for t in tasks if t.status in ("pending", "in_progress")]
        events = []      # pending scope is about tasks — omit events
        records = []     # ...and records
    else:
        scope_label = "全部"

    # ── Compose markdown ───────────────────────────────────────────────────
    now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    lines: list[str] = [
        f"# 拾光 · Lumen 导出（{scope_label}）",
        "",
        f"> 导出时间：{now}",
        f"> 用户标识：`{uid}`",
        f"> 范围：{scope} · 任务 {len(tasks)} · 事件 {len(events)} · 记录 {len(records)}",
        "",
    ]

    if tasks:
        lines.append("## 待办 / To Do")
        lines.append("")
        pending_tasks = [t for t in tasks if t.status in ("pending", "in_progress")]
        done_tasks = [t for t in tasks if t.status == "done"]
        if pending_tasks:
            for t in pending_tasks:
                lines.append(_task_line(t))
            lines.append("")
        if done_tasks and scope != "pending":
            lines.append("### 已完成")
            lines.append("")
            for t in done_tasks:
                lines.append(_task_line(t))
            lines.append("")

    if events:
        lines.append("## 时间线 / Timeline")
        lines.append("")
        for e in events:
            lines.append(_event_line(e))
        lines.append("")

    if records:
        lines.append("## 原始记录 / Notes")
        lines.append("")
        for r in records:
            lines.append(_record_line(r))
        lines.append("")

    if not tasks and not events and not records:
        lines.append("_（此范围下暂无内容）_")

    body = "\n".join(lines)
    filename = f"lumen-{scope}-{datetime.now(timezone.utc).astimezone().strftime('%Y%m%d')}.md"
    return PlainTextResponse(
        body,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/count")
async def export_count(
    db: AsyncSession = Depends(get_db),
    uid: str = Depends(current_user_id),
):
    """Cheap head-count for each scope, so the export dialog can preview 条数."""
    tasks = list((await db.execute(select(Task).where(Task.user_id == uid, Task.status != "deleted"))).scalars().all())
    events = list((await db.execute(select(Event).where(Event.user_id == uid, Event.status != "deleted"))).scalars().all())
    records = list((await db.execute(select(Record).where(Record.user_id == uid))).scalars().all())

    start, end = _today_start_end()
    def _today(d: datetime | None) -> bool:
        return d is not None and start <= d <= end

    today_tasks = [t for t in tasks if _today(t.created_at) or _today(t.due_date) or _today(t.completed_at)]
    today_events = [e for e in events if _today(e.start_time) or _today(e.created_at)]
    today_records = [r for r in records if _today(r.created_at)]
    pending_tasks = [t for t in tasks if t.status in ("pending", "in_progress")]

    def _total(items: Iterable) -> int:
        return sum(1 for _ in items)

    return {
        "all": {"tasks": len(tasks), "events": len(events), "records": len(records), "total": _total(tasks) + _total(events) + _total(records)},
        "today": {"tasks": len(today_tasks), "events": len(today_events), "records": len(today_records), "total": _total(today_tasks) + _total(today_events) + _total(today_records)},
        "pending": {"tasks": len(pending_tasks), "total": len(pending_tasks)},
    }
