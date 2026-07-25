"""情绪指数端点。"""

import json
import logging
from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import current_lang, current_user_id, get_db, pick
from models import Mood, Record
from schemas import MoodGenerateResponse, MoodOut
from services.llm import generate_mood

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mood", tags=["mood"])


def _safe_json(text: str) -> dict | list:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1])
    return json.loads(text)


def _get(d: dict, *keys: str, default=None):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def _voice_emotion(rec: Record) -> str | None:
    if not rec.meta_json:
        return None
    try:
        meta = json.loads(rec.meta_json)
        v = meta.get("voice_emotion")
        return v if isinstance(v, str) and v else None
    except (json.JSONDecodeError, TypeError):
        return None


def _record_to_dict(rec: Record) -> dict:
    d = {
        "id": rec.id,
        "content": rec.content,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
    }
    emo = _voice_emotion(rec)
    if emo:
        d["voice_emotion"] = emo
    return d


@router.post("/generate", response_model=MoodGenerateResponse)
async def generate_mood_snapshot(
    db: AsyncSession = Depends(get_db),
    uid: str = Depends(current_user_id),
    lang: str = Depends(current_lang),
):
    """根据最近的记录生成情绪指数快照。"""
    # 获取近期已处理的记录
    result = await db.execute(
        select(Record)
        .where(Record.user_id == uid, Record.status.in_(["processed"]))
        .order_by(Record.created_at.desc())
        .limit(30)
    )
    records = list(result.scalars().all())

    if len(records) < 2:
        return MoodGenerateResponse(
            mood=None,
            message=pick(
                lang,
                "记录太少（至少 2 条已处理的记录），暂时无法生成情绪指数。继续记录吧。",
                "Not enough records (at least 2 processed notes needed) to generate a mood index yet. Keep journaling.",
            ),
        )

    records_json = json.dumps(
        [_record_to_dict(r) for r in records],
        ensure_ascii=False,
    )

    # 声学情绪分布摘要（作为独立信号注入 LLM）
    emo_counts = Counter(e for e in (_voice_emotion(r) for r in records) if e)
    voice_emo_summary = ""
    if emo_counts:
        parts = [f"{k}×{v}" for k, v in emo_counts.most_common()]
        voice_emo_summary = f"{sum(emo_counts.values())} 条语音（共 {len(records)} 条记录）：" + " / ".join(parts)

    try:
        raw = await generate_mood(records_json, voice_emo_summary, lang, uid)
        data = _safe_json(raw)
    except Exception:
        logger.exception("情绪指数 LLM 调用失败")
        return MoodGenerateResponse(
            mood=None,
            message=pick(lang, "情绪指数生成失败，请稍后重试。", "Failed to generate the mood index. Please try again later."),
        )

    mood = Mood(
        user_id=uid,
        score=_get(data, "评分", "score", default=5.0),
        label=_get(data, "标签", "label", default="平稳"),
        summary=_get(data, "摘要", "summary", default=""),
        key_factors=json.dumps(_get(data, "关键因素", "key_factors", default=[]), ensure_ascii=False),
    )
    db.add(mood)
    await db.commit()
    await db.refresh(mood)

    return MoodGenerateResponse(
        mood=MoodOut(
            id=mood.id,
            score=mood.score,
            label=mood.label,
            summary=mood.summary,
            key_factors=json.loads(mood.key_factors) if mood.key_factors else [],
            created_at=mood.created_at,  # type: ignore[arg-type]
        ),
        message=pick(lang, "情绪指数已生成。", "Mood index generated."),
    )


@router.get("/latest", response_model=MoodGenerateResponse)
async def get_latest_mood(
    db: AsyncSession = Depends(get_db),
    uid: str = Depends(current_user_id),
    lang: str = Depends(current_lang),
):
    """获取最近一次情绪指数。"""
    result = await db.execute(
        select(Mood).where(Mood.user_id == uid).order_by(Mood.created_at.desc()).limit(1)
    )
    mood = result.scalar_one_or_none()

    if not mood:
        return MoodGenerateResponse(
            mood=None,
            message=pick(
                lang,
                "还没有生成过情绪指数。记录一些内容后，系统会帮你分析。",
                "No mood index yet. Jot down some notes and I'll analyze them for you.",
            ),
        )

    return MoodGenerateResponse(
        mood=MoodOut(
            id=mood.id,
            score=mood.score,
            label=mood.label,
            summary=mood.summary,
            key_factors=json.loads(mood.key_factors) if mood.key_factors else [],
            created_at=mood.created_at,  # type: ignore[arg-type]
        ),
        message="",
    )
