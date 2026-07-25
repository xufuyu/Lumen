"""自然语言问答端点。"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import current_lang, current_user_id, get_db, pick
from models import Event, Record, Task
from schemas import QueryRequest, QueryResponse, QuerySource
from services.llm import answer_query, answer_query_stream, classify_intent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/query", tags=["query"])


def _get(d: dict, *keys: str, default=None):
    """从字典中按优先级取值——先中文键，再英文键。"""
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


@router.post("/classify")
async def classify_question(body: QueryRequest, uid: str = Depends(current_user_id)):
    """快速判断输入是否为询问（<500ms），前端据此决定是否显示"思考中"。"""
    text = body.question.strip()
    if not text:
        return {"is_question": False}
    intent = await classify_intent(text, uid)
    return {"is_question": intent == "question"}


@router.post("/stream")
async def ask_question_stream(
    body: QueryRequest,
    db: AsyncSession = Depends(get_db),
    uid: str = Depends(current_user_id),
    lang: str = Depends(current_lang),
):
    """流式问答：SSE 逐块输出回答。"""
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail=pick(lang, "问题不能为空", "Question cannot be empty"))

    records = await _get_recent_records(db, uid, limit=20)
    events = await _get_recent_events(db, uid, limit=10)
    tasks = await _get_active_tasks(db, uid, limit=10)

    context_parts: dict[str, list] = {
        "records": [{"id": r["id"], "content": r["content"], "created_at": r["created_at"]} for r in records],
        "events": events,
        "tasks": tasks,
    }
    context_json = json.dumps(context_parts, ensure_ascii=False, default=str)

    async def event_generator():
        full_text = ""
        try:
            async for chunk in answer_query_stream(question, context_json, lang, uid):
                full_text += chunk
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"

            # 解析完整响应，提取元数据
            try:
                cleaned = full_text.strip()
                if cleaned.startswith("```"):
                    cleaned = "\n".join(cleaned.split("\n")[1:-1])
                data = json.loads(cleaned)
                is_question = _get(data, "是否问题", "is_question", default=True)
                answer = _get(data, "回答", "answer", default="")
                disclaimer = _get(data, "免责声明", "disclaimer")
                sources = []
                for src in _get(data, "来源", "sources", default=[]):
                    try:
                        sources.append({
                            "record_id": _get(src, "记录ID", "record_id", default=0),
                            "excerpt": _get(src, "摘录", "excerpt", default=""),
                            "created_at": _get(src, "创建时间", "created_at", default=""),
                        })
                    except Exception:
                        pass
                yield f"data: {json.dumps({'type': 'done', 'is_question': is_question, 'answer': answer, 'sources': sources, 'disclaimer': disclaimer}, ensure_ascii=False)}\n\n"
            except json.JSONDecodeError:
                # LLM 未返回合法 JSON，把原始文本当作回答
                yield f"data: {json.dumps({'type': 'done', 'is_question': True, 'answer': full_text, 'sources': [], 'disclaimer': None}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.exception("流式问答失败")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("", response_model=QueryResponse)
async def ask_question(
    body: QueryRequest,
    db: AsyncSession = Depends(get_db),
    uid: str = Depends(current_user_id),
    lang: str = Depends(current_lang),
):
    """用自然语言提问，基于用户的记录来回答。"""
    question = body.question.strip()

    if not question:
        raise HTTPException(status_code=400, detail=pick(lang, "问题不能为空", "Question cannot be empty"))

    # 1. 收集相关上下文（精简数量减少延迟）
    records = await _get_recent_records(db, uid, limit=20)
    events = await _get_recent_events(db, uid, limit=10)
    tasks = await _get_active_tasks(db, uid, limit=10)

    if not records and not events and not tasks:
        return QueryResponse(
            answer=pick(
                lang,
                "我还没有任何记录，无法回答你的问题。先记录一些日常活动吧，之后我就能帮你回忆了。",
                "I don't have any records yet, so I can't answer your question. Jot down some daily activities first, and I'll be able to help you recall.",
            ),
            sources=[],
            disclaimer=pick(lang, "目前数据库中没有记录。", "There are no records in the database yet."),
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
        raw = await answer_query(question, context_json, lang, uid)
        data = json.loads(_clean_json(raw))
    except Exception as e:
        logger.exception("问答 LLM 调用失败")
        raise HTTPException(status_code=500, detail=pick(lang, f"问答处理失败: {str(e)}", f"Query processing failed: {str(e)}"))

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
        answer=_get(data, "回答", "answer", default=pick(lang, "抱歉，我无法回答这个问题。", "Sorry, I can't answer that question.")),
        sources=sources,
        disclaimer=_get(data, "免责声明", "disclaimer"),
        is_question=_get(data, "是否问题", "is_question", default=True),
    )


async def _get_recent_records(db: AsyncSession, uid: str, limit: int = 50) -> list[dict]:
    """获取最近的非归档记录作为问答上下文。"""
    result = await db.execute(
        select(Record)
        .where(Record.user_id == uid, Record.status.in_(["processed", "unprocessed"]))
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


async def _get_recent_events(db: AsyncSession, uid: str, limit: int = 30) -> list[dict]:
    """获取最近的非删除事件作为问答上下文。"""
    result = await db.execute(
        select(Event)
        .where(Event.user_id == uid, Event.status.in_(["inferred", "confirmed", "modified"]))
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


async def _get_active_tasks(db: AsyncSession, uid: str, limit: int = 20) -> list[dict]:
    """获取活跃任务作为问答上下文。"""
    result = await db.execute(
        select(Task)
        .where(Task.user_id == uid, Task.status.in_(["pending", "in_progress"]))
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
