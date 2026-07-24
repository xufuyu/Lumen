"""拾光 · Lumen (AdventureX 2026) — API Server"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from config import AUTO_PROCESS, BASE_DIR
from database import init_db
from security import SecurityMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ── Lifespan ────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown logic."""
    # Ensure data directory exists
    data_dir = BASE_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # Initialize database tables
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database ready.")

    yield

    logger.info("Shutting down.")


# ── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="拾光 · Lumen",
    description="拾光 · Lumen — 把碎片记录自动整理成时间线、待办和状态摘要的个人助手，面向需要认知辅助的人群及所有想让生活更有条理的人",
    version="0.1.0",
    lifespan=lifespan,
)

# Security middleware — rate limiting (must be added first to wrap all requests)
app.add_middleware(SecurityMiddleware)

# CORS
import os
_ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "X-User-ID"],
)


# ── Routers ─────────────────────────────────────────────────────────────────

from routers.records import router as records_router  # noqa: E402
from routers.timeline import router as timeline_router  # noqa: E402
from routers.tasks import router as tasks_router  # noqa: E402
from routers.context import router as context_router  # noqa: E402
from routers.query import router as query_router  # noqa: E402
from routers.process import router as process_router  # noqa: E402
from routers.mood import router as mood_router  # noqa: E402
from routers.asr import router as asr_router  # noqa: E402
from routers.merge import router as merge_router  # noqa: E402
from routers.user import router as user_router  # noqa: E402
from routers.sync import router as sync_router  # noqa: E402

app.include_router(sync_router)
app.include_router(user_router)
app.include_router(records_router)
app.include_router(timeline_router)
app.include_router(tasks_router)
app.include_router(context_router)
app.include_router(query_router)
app.include_router(process_router)
app.include_router(mood_router)
app.include_router(asr_router)
app.include_router(merge_router)


# ── Health check ────────────────────────────────────────────────────────────


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "拾光 · Lumen"}


# ── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
