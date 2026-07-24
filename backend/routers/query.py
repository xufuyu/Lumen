"""自然语言问答端点。"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Event, Record, Task
from schemas import QueryRequest, QueryResponse, QuerySource
from services.llm import answer_query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/query", tags=["query"])


def _get(d: dict, *keys: str, default=None):
    """从字典中按优先级取值——先中文键，再英文键。"""
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


@router.post("", response_model=QueryResponse)
async def ask_question(body: QueryRequest, db: AsyncSession = Depends(get_db)):
    """用自然语言提问，基于用户的记录来回答。"""
    question = body.question.strip()

    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    # 1. 收集相关上下文
    records = await _get_recent_records(db, limit=50)
    events = await _get_recent_events(db, limit=30)
    tasks = await _get_active_tasks(db, limit=20)

    if not records and not events and not tasks:
        return QueryResponse(
            answer="我还没有任何记录，无法回答你的问题。先记录一些日常活动吧，之后我就能帮你回忆了。",
            sources=[],
            disclaimer="目前数据库中没有记录。",
        )

    # 2. 构建上下文 JSON
    context_parts: dict[str, list] = {
        "records": [
            {"id": r["id"], "content": r["content"], "created_at": r["created_at"]}
            for r in records
        ],
        "events": events,
        "tasks": tasks,
    }
    context_json = json.dumps(context_parts, ensure_ascii=False, default=str)

    # 3. 调用 LLM
    try:
        raw = await answer_query(question, context_json)
        data = json.loads(_clean_json(raw))
    except Exception as e:
        logger.exception("问答 LLM 调用失败")
        raise HTTPException(status_code=500, detail=f"问答处理失败: {str(e)}")

    # 4. 构建响应（兼容中英文字段名）
    sources = []
    for src in _get(data, "来源", "sources", default=[]):
        try:
            sources.append(
                QuerySource(
                    record_id=_get(src, "记录ID", "record_id", default=0),
                    excerpt=_get(src, "摘录", "excerpt", default=""),
                    created_at=_get(src, "创建时间", "created_at", default=""),  # type: ignore[arg-type]
                )
            )
        except Exception:
            pass

    return QueryResponse(
        answer=_get(data, "回答", "answer", default="抱歉，我无法回答这个问题。"),
        sources=sources,
        disclaimer=_get(data, "免责声明", "disclaimer"),
    )


async def _get_recent_records(db: AsyncSession, limit: int = 50) -> list[dict]:
    """获取最近的非归档记录作为问答上下文。"""
    result = await db.execute(
        select(Record)
        .where(Record.status.in_(["processed", "unprocessed"]))
        .order_by(Record.created_at.desc())
        .limit(limit)
    )
    records = result.scalars().all()
    return [
        {
            "id": r.id,
            "content": r.content,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in records
    ]


async def _get_recent_events(db: AsyncSession, limit: int = 30) -> list[dict]:
    """获取最近的非删除事件作为问答上下文。"""
    result = await db.execute(
        select(Event)
        .where(Event.status.in_(["inferred", "confirmed", "modified"]))
        .order_by(Event.created_at.desc())
        .limit(limit)
    )
    events = result.scalars().all()
    return [
        {
            "id": e.id,
            "title": e.title,
            "description": e.description,
            "start_time": e.start_time.isoformat() if e.start_time else None,
            "status": e.status,
            "confidence": e.confidence,
        }
        for e in events
    ]


async def _get_active_tasks(db: AsyncSession, limit: int = 20) -> list[dict]:
    """获取活跃任务作为问答上下文。"""
    result = await db.execute(
        select(Task)
        .where(Task.status.in_(["pending", "in_progress"]))
        .order_by(Task.created_at.desc())
        .limit(limit)
    )
    tasks = result.scalars().all()
    return [
        {
            "id": t.id,
            "title": t.title,
            "description": t.description,
            "status": t.status,
            "priority": t.priority,
            "due_date": t.due_date.isoformat() if t.due_date else None,
        }
        for t in tasks
    ]


def _clean_json(text: str) -> str:
    """去除 LLM JSON 输出中的 markdown 代码围栏。"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1])
    return text
