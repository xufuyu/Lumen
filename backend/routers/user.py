"""User data migration & merge endpoints."""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database import current_user_id, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/user", tags=["user"])

USER_TABLES = ["records", "events", "tasks", "contexts", "moods"]


class MergeRequest(BaseModel):
    new_user_id: str = Field(..., min_length=1, max_length=64)


@router.post("/merge")
async def merge_user_data(
    body: MergeRequest,
    db: AsyncSession = Depends(get_db),
    old_uid: str = Depends(current_user_id),
):
    """Copy all data from old user_id to new user_id (merge, not replace)."""
    new_uid = body.new_user_id.strip()

    if not new_uid or new_uid == old_uid:
        return {"merged": 0, "message": "Same ID, nothing to merge."}

    total = 0
    for table in USER_TABLES:
        result = await db.execute(
            text(f"UPDATE {table} SET user_id = :new WHERE user_id = :old"),
            {"new": new_uid, "old": old_uid},
        )
        total += result.rowcount or 0

    await db.commit()
    logger.info(f"Merged {total} rows from '{old_uid}' → '{new_uid}'")
    return {"merged": total, "message": f"Merged {total} records from '{old_uid}' into '{new_uid}'."}
