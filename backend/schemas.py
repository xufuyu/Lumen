"""Pydantic schemas for request/response validation."""

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field, AfterValidator


def _ensure_utc(v: datetime) -> datetime:
    """SQLite 存取时丢失 tzinfo，这里补回 UTC，让 FastAPI 序列化带 +00:00 后缀。

    JavaScript 的 new Date() 见到无时区的 ISO 字符串会当本地时间解析，
    导致 UTC+8 用户看到“8 小时前”。补上 tzinfo 后 JS 会正确转成本地时间。
    """
    if v.tzinfo is None:
        return v.replace(tzinfo=timezone.utc)
    return v


UTCDatetime = Annotated[datetime, AfterValidator(_ensure_utc)]


# ── Enums ───────────────────────────────────────────────────────────────────


class RecordType(str, Enum):
    TEXT = "text"
    VOICE = "voice"


class RecordStatus(str, Enum):
    UNPROCESSED = "unprocessed"
    PROCESSING = "processing"
    PROCESSED = "processed"
    ARCHIVED = "archived"


class EventStatus(str, Enum):
    INFERRED = "inferred"
    CONFIRMED = "confirmed"
    MODIFIED = "modified"
    DELETED = "deleted"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    DELETED = "deleted"


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ── Record ──────────────────────────────────────────────────────────────────


class RecordCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)
    type: RecordType = RecordType.TEXT
    # 语音输入时由 ASR 返回的声学情绪（7 类之一，可空）：
    # neutral / happy / sad / angry / fearful / disgusted / surprised
    voice_emotion: str | None = None


class RecordUpdate(BaseModel):
    content: str | None = Field(None, min_length=1, max_length=10000)
    status: RecordStatus | None = None


class RecordOut(BaseModel):
    id: int
    content: str
    type: RecordType
    status: RecordStatus
    created_at: UTCDatetime
    updated_at: UTCDatetime
    linked_event_ids: list[int] = []
    linked_task_ids: list[int] = []

    model_config = {"from_attributes": True}


class RecordList(BaseModel):
    items: list[RecordOut]
    total: int
    page: int
    page_size: int


# ── ASR 润色 ────────────────────────────────────────────────────────────────


class PolishRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


class PolishResponse(BaseModel):
    polished: str
    changed: bool  # 与原文是否不同（方便前端决定是否替换）


# ── Event ───────────────────────────────────────────────────────────────────


class EventUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    start_time: UTCDatetime | None = None
    end_time: UTCDatetime | None = None
    status: EventStatus | None = None


class EventOut(BaseModel):
    id: int
    title: str
    description: str | None
    start_time: UTCDatetime | None
    end_time: UTCDatetime | None
    confidence: float
    status: EventStatus
    created_at: UTCDatetime
    source_record_ids: list[int] = []

    model_config = {"from_attributes": True}


class EventList(BaseModel):
    items: list[EventOut]
    total: int


# ── Task ────────────────────────────────────────────────────────────────────


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    priority: TaskPriority = TaskPriority.MEDIUM
    due_date: UTCDatetime | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_date: UTCDatetime | None = None


class TaskOut(BaseModel):
    id: int
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    due_date: UTCDatetime | None
    confidence: float
    created_at: UTCDatetime
    started_at: UTCDatetime | None = None
    completed_at: UTCDatetime | None
    source_record_ids: list[int] = []

    model_config = {"from_attributes": True}


class TaskList(BaseModel):
    items: list[TaskOut]
    total: int


# ── Context ─────────────────────────────────────────────────────────────────


class ContextOut(BaseModel):
    id: int
    summary: str
    valid_from: UTCDatetime
    valid_until: UTCDatetime | None
    created_at: UTCDatetime
    source_record_ids: list[int] = []

    model_config = {"from_attributes": True}


# ── Query ───────────────────────────────────────────────────────────────────


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


class QuerySource(BaseModel):
    record_id: int
    excerpt: str
    created_at: UTCDatetime


class QueryResponse(BaseModel):
    answer: str
    sources: list[QuerySource]
    disclaimer: str | None = None
    is_question: bool = True


# ── Mood ───────────────────────────────────────────────────────────────────


class MoodOut(BaseModel):
    id: int
    score: float
    label: str
    summary: str
    key_factors: list[str] = []
    created_at: UTCDatetime

    model_config = {"from_attributes": True}


class MoodGenerateResponse(BaseModel):
    mood: MoodOut | None
    message: str


# ── Process ─────────────────────────────────────────────────────────────────


class ProcessResponse(BaseModel):
    processed: int
    events_created: int
    events_updated: int
    tasks_created: int
    tasks_updated: int
    context_updated: bool
    merge_candidates: list[dict] = []
    auto_completed_tasks: list[dict] = []


# ── Merge ───────────────────────────────────────────────────────────────────


class MergeAction(BaseModel):
    new_task_id: int
    action: str  # "merge" | "keep_separate"


class MergeCandidateOut(BaseModel):
    new_task_id: int
    new_title: str
    existing_title: str
    score: float
    record_id: int | None
