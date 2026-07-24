"""AdventureX 2026 — 认知与行动辅助  API Server"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import AUTO_PROCESS, BASE_DIR
from database import init_db

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
    title="AdventureX 2026",
    description="认知与行动辅助 — 为受到抑郁、ADHD、解离等问题影响的人群提供生活辅助",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow all origins during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    return {"status": "ok", "service": "AdventureX 2026"}


# ── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
