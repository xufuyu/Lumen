"""处理管线：原始记录 → 事件、任务、上下文。"""

import json
import logging
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Context, Event, Record, RecordContext, RecordEvent, RecordTask, Task
from services.llm import (
    extract_structured,
    generate_context,
    generate_tasks,
    generate_timeline,
)
from services.fuzzy_match import fuzzy_match, classify_match, normalize

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_json(text: str) -> dict | list:
    """解析 LLM 输出的 JSON，自动处理 markdown 代码围栏。"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1])
    return json.loads(text)


def _get(d: dict, *keys: str, default=None):
    """从字典中按优先级获取值——先试中文键，再试英文键。"""
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def _voice_emotion(rec: Record) -> str | None:
    """从 record.meta_json 里安全提取 voice_emotion（无则 None）。"""
    if not rec.meta_json:
        return None
    try:
        meta = json.loads(rec.meta_json)
        v = meta.get("voice_emotion")
        return v if isinstance(v, str) and v else None
    except (json.JSONDecodeError, TypeError):
        return None


def _record_to_dict(rec: Record) -> dict:
    """把 Record 打成 LLM 用的 dict，带 voice_emotion（如有）。"""
    d = {
        "id": rec.id,
        "content": rec.content,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
    }
    emo = _voice_emotion(rec)
    if emo:
        d["voice_emotion"] = emo
    return d


def _emotion_summary(records: list[Record]) -> str:
    """把一批记录里的 voice_emotion 汇总成 "sad×3 / neutral×2" 字符串。"""
    counts = Counter(
        e for e in (_voice_emotion(r) for r in records) if e
    )
    if not counts:
        return ""
    parts = [f"{k}×{v}" for k, v in counts.most_common()]
    return f"最近 {sum(counts.values())} 条语音记录：" + " / ".join(parts)


# ── 值映射 ────────────────────────────────────────────────────────────────────

_PRIORITY_MAP = {"低": "low", "中": "medium", "高": "high", "low": "low", "medium": "medium", "high": "high"}
_STATUS_MAP = {
    "已完成": "done", "完成": "done", "done": "done",
    "进行中": "in_progress", "in_progress": "in_progress",
    "待办": "pending", "pending": "pending",
}


def _map_priority(val: str) -> str:
    return _PRIORITY_MAP.get(val, "medium")


def _map_status(val: str | None) -> str:
    """将 LLM 输出的状态映射为内部枚举值。默认为 pending。"""
    if val is None:
        return "pending"
    return _STATUS_MAP.get(val, "pending")


def _parse_dt(val: str | None) -> datetime | None:
    """安全解析 ISO 时间字符串。"""
    if not val:
        return None
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


# ── 主处理流程 ────────────────────────────────────────────────────────────────


async def process_records(db: AsyncSession, uid: str = "default") -> dict:
    """处理所有未处理的记录。

    返回包含处理计数的摘要字典。
    """
    # 1. 找到当前用户所有未处理的记录
    result = await db.execute(
        select(Record).where(Record.user_id == uid, Record.status == "unprocessed").order_by(Record.created_at)
    )
    unprocessed: list[Record] = list(result.scalars().all())

    if not unprocessed:
        return {
            "processed": 0,
            "events_created": 0,
            "events_updated": 0,
            "tasks_created": 0,
            "tasks_updated": 0,
            "context_updated": False,
            "merge_candidates": [],
            "auto_completed_tasks": [],
        }

    # 标记为处理中
    for rec in unprocessed:
        rec.status = "processing"
    await db.commit()

    # 2. 构建 LLM 用的记录 JSON（带 voice_emotion）
    records_json = json.dumps(
        [_record_to_dict(r) for r in unprocessed],
        ensure_ascii=False,
    )

    # 3. 获取已有任务用于去重
    existing_result = await db.execute(select(Task).where(Task.user_id == uid, Task.status.in_(["pending", "in_progress"])))
    existing_tasks: list[Task] = list(existing_result.scalars().all())
    existing_tasks_json = json.dumps(
        [{"id": t.id, "title": t.title, "status": t.status} for t in existing_tasks],
        ensure_ascii=False,
    )

    # 4. 调用 LLM 管线
    events_created = 0
    events_updated = 0
    tasks_created = 0
    tasks_updated = 0
    merge_candidates: list[dict] = []  # 需要用户确认的相似任务
    auto_completed_tasks: list[dict] = []  # 自动标记完成的任务（可撤销）

    try:
        # 生成时间线事件
        timeline_raw = await generate_timeline(records_json)
        events_data = _safe_json(timeline_raw)

        if isinstance(events_data, list):
            for ev_data in events_data:
                source_ids = _get(ev_data, "来源记录ID", "source_record_ids", default=[])
                event = Event(user_id=uid, 
                    title=_get(ev_data, "标题", "title", default="未命名事件"),
                    description=_get(ev_data, "描述", "description"),
                    start_time=_parse_dt(_get(ev_data, "开始时间", "start_time")),
                    end_time=_parse_dt(_get(ev_data, "结束时间", "end_time")),
                    confidence=_get(ev_data, "确信度", "confidence", default=0.5),
                    status="inferred",
                )
                db.add(event)
                await db.flush()

                for rid in source_ids:
                    if any(r.id == rid for r in unprocessed):
                        db.add(RecordEvent(record_id=rid, event_id=event.id))

                events_created += 1

        # 生成任务
        tasks_raw = await generate_tasks(records_json, existing_tasks_json)
        tasks_data = _safe_json(tasks_raw)

        if isinstance(tasks_data, list):
            # 加载全部非删除任务，用于状态更新匹配
            all_tasks_result = await db.execute(
                select(Task).where(Task.user_id == uid, Task.status != "deleted")
            )
            all_tasks: dict[str, Task] = {}
            for t in all_tasks_result.scalars().all():
                key = normalize(t.title)
                if key not in all_tasks:
                    all_tasks[key] = t

            # 构建已有标题列表供模糊匹配
            existing_titles = list(all_tasks.keys())

            for t_data in tasks_data:
                raw_title = _get(t_data, "标题", "title", default="未命名任务")
                source_ids = _get(t_data, "来源记录ID", "source_record_ids", default=[])
                task_status = _map_status(_get(t_data, "状态", "status"))

                # ── 状态更新：[更新] 原标题 → 更新已有任务 ──
                UPDATE_PREFIX = "[更新] "
                if raw_title.startswith(UPDATE_PREFIX):
                    original_title = raw_title[len(UPDATE_PREFIX):].strip()
                    match_key = normalize(original_title)

                    # 1) 精确匹配
                    existing = all_tasks.get(match_key)
                    # 2) 精确匹配失败 → 模糊匹配
                    if not existing:
                        matched_title, score = fuzzy_match(original_title, existing_titles)
                        if matched_title and classify_match(score) == "auto_merge":
                            existing = all_tasks.get(normalize(matched_title))

                    if existing and existing.status != task_status:
                        existing.status = task_status
                        if task_status == "done":
                            existing.completed_at = _now()
                        elif task_status == "pending":
                            existing.completed_at = None
                        for rid in source_ids:
                            if any(r.id == rid for r in unprocessed):
                                existing_rec = await db.execute(
                                    select(RecordTask).where(
                                        RecordTask.record_id == rid,
                                        RecordTask.task_id == existing.id,
                                    )
                                )
                                if not existing_rec.first():
                                    db.add(RecordTask(record_id=rid, task_id=existing.id))
                        tasks_updated += 1
                    elif not existing:
                        # 找不到匹配的任务，退化为新建
                        task = Task(user_id=uid, 
                            title=original_title,
                            description=_get(t_data, "描述", "description"),
                            priority=_map_priority(_get(t_data, "优先级", "priority", default="中")),
                            due_date=_parse_dt(_get(t_data, "截止日期", "due_date")),
                            confidence=_get(t_data, "确信度", "confidence", default=0.5),
                            status=task_status,
                        )
                        db.add(task)
                        await db.flush()
                        for rid in source_ids:
                            if any(r.id == rid for r in unprocessed):
                                db.add(RecordTask(record_id=rid, task_id=task.id))
                        if task_status in ("pending", "in_progress"):
                            tasks_created += 1

                # ── 新任务 ──
                else:
                    # 检查是否与已有任务相似
                    matched_title, score = fuzzy_match(raw_title, existing_titles)
                    match_type = classify_match(score) if matched_title else "new_item"

                    if match_type == "auto_merge":
                        # 高分 → 自动合并到已有任务
                        matched_task = all_tasks.get(normalize(matched_title))
                        if matched_task:
                            status_changed = False
                            # 允许 pending → in_progress / done 的自动更新
                            if matched_task.status in ("pending", "in_progress") and task_status != matched_task.status:
                                matched_task.status = task_status
                                status_changed = True
                                if task_status == "done":
                                    matched_task.completed_at = _now()
                            # 链接记录
                            for rid in source_ids:
                                if any(r.id == rid for r in unprocessed):
                                    existing_rec = await db.execute(
                                        select(RecordTask).where(
                                            RecordTask.record_id == rid,
                                            RecordTask.task_id == matched_task.id,
                                        )
                                    )
                                    if not existing_rec.first():
                                        db.add(RecordTask(record_id=rid, task_id=matched_task.id))
                            if status_changed:
                                tasks_updated += 1
                                if task_status == "done":
                                    auto_completed_tasks.append({
                                        "task_id": matched_task.id,
                                        "title": matched_task.title,
                                        "old_status": "pending",
                                    })
                            continue

                    elif match_type == "ask_user":
                        # 中分 → 先当新任务创建，但标记为需确认
                        task = Task(user_id=uid, 
                            title=raw_title,
                            description=_get(t_data, "描述", "description"),
                            priority=_map_priority(_get(t_data, "优先级", "priority", default="中")),
                            due_date=_parse_dt(_get(t_data, "截止日期", "due_date")),
                            confidence=min(_get(t_data, "确信度", "confidence", default=0.5), 0.5),
                            status=task_status,
                        )
                        db.add(task)
                        await db.flush()
                        for rid in source_ids:
                            if any(r.id == rid for r in unprocessed):
                                db.add(RecordTask(record_id=rid, task_id=task.id))
                        if task_status in ("pending", "in_progress"):
                            tasks_created += 1

                        # 记录 merge 候选
                        merge_candidates.append({
                            "new_task_id": task.id,
                            "new_title": raw_title,
                            "existing_title": matched_title,
                            "score": round(score, 2),
                            "record_id": source_ids[0] if source_ids else None,
                        })
                        continue

                    # new_item → 正常创建
                    task = Task(user_id=uid,
                        title=raw_title,
                        description=_get(t_data, "描述", "description"),
                        priority=_map_priority(_get(t_data, "优先级", "priority", default="中")),
                        due_date=_parse_dt(_get(t_data, "截止日期", "due_date")),
                        confidence=_get(t_data, "确信度", "confidence", default=0.5),
                        status=task_status,
                    )
                    db.add(task)
                    await db.flush()

                    for rid in source_ids:
                        if any(r.id == rid for r in unprocessed):
                            db.add(RecordTask(record_id=rid, task_id=task.id))

                    if task_status in ("pending", "in_progress"):
                        tasks_created += 1
                    elif task_status == "done":
                        tasks_created += 1
                        if task.completed_at is None:
                            task.completed_at = _now()
                        auto_completed_tasks.append({
                            "task_id": task.id,
                            "title": task.title,
                            "old_status": "new",
                        })

        # 标记所有记录为已处理
        for rec in unprocessed:
            rec.status = "processed"
            rec.updated_at = _now()

        await db.commit()

    except Exception:
        logger.exception("LLM 管线处理失败")
        for rec in unprocessed:
            rec.status = "unprocessed"
        await db.commit()
        raise

    # 5. 更新上下文快照（尽力而为，不因失败阻断整个管线）
    context_updated = False
    try:
        await _update_context(db, uid)
        context_updated = True
    except Exception:
        logger.exception("上下文更新失败")

    return {
        "processed": len(unprocessed),
        "events_created": events_created,
        "events_updated": events_updated,
        "tasks_created": tasks_created,
        "tasks_updated": tasks_updated,
        "context_updated": context_updated,
        "merge_candidates": merge_candidates,
        "auto_completed_tasks": auto_completed_tasks,
    }


async def _update_context(db: AsyncSession, uid: str = "default") -> None:
    """根据最近的事件和任务生成新的上下文快照。"""
    # 获取最近事件（最近 7 天）
    events_result = await db.execute(
        select(Event)
        .where(Event.user_id == uid, Event.status.in_(["inferred", "confirmed", "modified"]))
        .order_by(Event.created_at.desc())
        .limit(30)
    )
    events = list(events_result.scalars().all())

    # 获取待办/进行中的任务
    tasks_result = await db.execute(
        select(Task)
        .where(Task.user_id == uid, Task.status.in_(["pending", "in_progress"]))
        .order_by(Task.created_at.desc())
        .limit(20)
    )
    tasks = list(tasks_result.scalars().all())

    # 获取最近语音记录的声学情绪分布（作为 context 生成的额外信号）
    recent_records_result = await db.execute(
        select(Record)
        .where(Record.user_id == uid, Record.type == "voice", Record.status.in_(["processed", "processing"]))
        .order_by(Record.created_at.desc())
        .limit(10)
    )
    recent_voice = list(recent_records_result.scalars().all())
    voice_emo_summary = _emotion_summary(recent_voice)

    events_json = json.dumps(
        [{"id": e.id, "标题": e.title, "描述": e.description, "开始时间": e.start_time.isoformat() if e.start_time else None} for e in events],
        ensure_ascii=False,
        default=str,
    )
    tasks_json = json.dumps(
        [{"id": t.id, "标题": t.title, "状态": t.status, "优先级": t.priority, "截止日期": t.due_date.isoformat() if t.due_date else None} for t in tasks],
        ensure_ascii=False,
        default=str,
    )

    context_raw = await generate_context(events_json, tasks_json, voice_emo_summary)
    context_data = _safe_json(context_raw)

    context = Context(user_id=uid, 
        summary=_get(context_data, "摘要", "summary", default=""),
        valid_from=_now(),
    )
    db.add(context)
    await db.flush()

    # 链接所有贡献了上下文的记录
    record_ids: set[int] = set()
    for e in events:
        recs_result = await db.execute(
            select(RecordEvent.record_id).where(RecordEvent.event_id == e.id)
        )
        record_ids.update(r for (r,) in recs_result.all())
    for t in tasks:
        recs_result = await db.execute(
            select(RecordTask.record_id).where(RecordTask.task_id == t.id)
        )
        record_ids.update(r for (r,) in recs_result.all())

    for rid in record_ids:
        db.add(RecordContext(record_id=rid, context_id=context.id))

    await db.commit()
