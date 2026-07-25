"""手动处理触发端点。"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import current_lang, current_user_id, get_db
from routers.sync import notify_user
from schemas import ProcessResponse
from services.processor import process_records

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/process", tags=["process"])


@router.post("", response_model=ProcessResponse)
async def trigger_processing(
    db: AsyncSession = Depends(get_db),
    uid: str = Depends(current_user_id),
    lang: str = Depends(current_lang),
):
    """手动触发处理管线，处理所有未处理的记录。"""
    try:
        result = await process_records(db, uid, lang)
        await notify_user(uid)
        return ProcessResponse(**result)
    except Exception as e:
        logger.exception("处理管线失败")
        raise HTTPException(
            status_code=502,
            detail=f"处理失败：{str(e)}。请检查 LLM 服务是否可用，稍后重试。",
        )