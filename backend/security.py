"""Security: rate limiting, input validation, SQL injection protection.

Uses an in-memory sliding-window rate limiter keyed by (user_id, endpoint).
Lightweight enough for single-instance deployment without Redis.
"""

import time
from collections import defaultdict
from typing import Callable

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


# ── Rate limiter ────────────────────────────────────────────────────────────

# Track (user_id, rule_key) → list of timestamps in the current window
_WINDOWS: dict[str, list[float]] = defaultdict(list)

def _cleanup():
    """Remove expired entries older than the largest window (60s)."""
    now = time.time()
    threshold = now - 120
    stale = [k for k, v in _WINDOWS.items() if not v or v[-1] < threshold]
    for k in stale:
        del _WINDOWS[k]


# ── Progressive rate limiting ──────────────────────────────────────────────

DEMO_MSG_ZH = (
    "拾光 · Lumen 为 AdventureX 2026 赛场演示版本，请求频率已受限。"
    "正式版请访问 GitHub 仓库：github.com/xufuyu/Lumen"
)
DEMO_MSG_EN = (
    "Lumen is an AdventureX 2026 competition demo. Request rate limited. "
    "Full version: github.com/xufuyu/Lumen"
)

# Progressive tiers: (threshold, window_sec, retry_after_sec)
# Each tier applies a stricter limit
PROGRESSIVE_TIERS = [
    (600,  60,  3),    # Tier 0: 600 req/min → 3s cooldown (~10req/s per user)
    (3000, 300, 15),   # Tier 1: 3000 req/5min → 15s
    (6000, 600, 60),   # Tier 2: 6000 req/10min → 60s
]


def check_rate_limit(user_id: str, key: str, max_requests: int, window_sec: float) -> JSONResponse | None:
    """Progressive rate limiter. More usage → stricter limits.

    Returns a 429 JSONResponse if rate-limited, else None.
    """
    now = time.time()
    k = f"{user_id}:{key}"
    times = _WINDOWS[k]

    # Check progressive tiers
    for threshold, tier_window, retry_sec in PROGRESSIVE_TIERS:
        cutoff = now - tier_window
        count = sum(1 for t in times if t >= cutoff)
        if count >= threshold:
            # Build demo message with zh/en
            detail = f"{DEMO_MSG_ZH}\n\n{DEMO_MSG_EN}"
            return JSONResponse(
                status_code=429,
                content={"detail": detail, "retry_after": retry_sec, "demo": True},
                headers={"Retry-After": str(retry_sec)},
            )

    # Also check the base rate limit (most lenient)
    cutoff = now - window_sec
    while times and times[0] < cutoff:
        times.pop(0)
    if len(times) >= max_requests:
        retry_after = int(times[0] + window_sec - now) + 1
        detail = f"{DEMO_MSG_ZH}\n\n{DEMO_MSG_EN}"
        return JSONResponse(
            status_code=429,
            content={"detail": detail, "retry_after": retry_after, "demo": True},
            headers={"Retry-After": str(retry_after)},
        )

    times.append(now)
    return None


def make_rate_limiter(max_requests: int, window_sec: float, key: str) -> Callable:
    """Dependency factory: returns a callable that checks the rate limit."""
    async def limiter(request: Request):
        uid = request.headers.get("X-User-ID", "default")
        resp = check_rate_limit(uid, key, max_requests, window_sec)
        if resp:
            raise HTTPException(status_code=429, detail=resp.body.decode())
    return limiter


# ── Security middleware ─────────────────────────────────────────────────────

# Endpoints that trigger expensive AI calls → strict limits
AI_RATE_LIMITS = {
    ("POST", "/api/process"):       (30, 60, "process"),     # 30/min
    ("POST", "/api/query"):         (60, 60, "query"),       # 60/min
    ("POST", "/api/mood/generate"): (15, 60, "mood_gen"),    # 15/min
}

# Mutation endpoints
MUTATION_RATE_LIMITS = {
    ("POST",   "/api/records"):     (120, 60, "rec_create"),  # 120/min
    ("PUT",    "/api/records"):     (120, 60, "rec_update"),
    ("DELETE", "/api/records"):     (60,  60, "rec_delete"),
    ("POST",   "/api/tasks"):       (60,  60, "task_create"),
    ("PUT",    "/api/tasks"):       (120, 60, "task_update"),
    ("DELETE", "/api/tasks"):       (60,  60, "task_delete"),
    ("PUT",    "/api/timeline"):    (60,  60, "event_update"),
    ("DELETE", "/api/timeline"):    (30,  60, "event_delete"),
    ("POST",   "/api/merge"):       (15,  60, "merge"),
    ("POST",   "/api/user/merge"):  (10,  60, "user_merge"),
}

# Read-only endpoints
READ_LIMIT = (600, 60, "read")  # 600/min


class SecurityMiddleware(BaseHTTPMiddleware):
    """Rate-limit requests based on method + path + user_id."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method
        uid = request.headers.get("X-User-ID", "default")

        # Determine rate limit rule
        normalized = _normalize_path(path)

        # Check AI limits first
        limit = AI_RATE_LIMITS.get((method, path))
        if not limit:
            limit = MUTATION_RATE_LIMITS.get((method, normalized))

        if limit:
            max_req, window, rule_key = limit
            blocked = check_rate_limit(uid, rule_key, max_req, window)
        elif not path.startswith("/api/asr"):
            max_req, window, rule_key = READ_LIMIT
            blocked = check_rate_limit(uid, rule_key, max_req, window)
        else:
            blocked = None

        if blocked:
            return blocked

        # Periodic cleanup
        _cleanup()

        response = await call_next(request)
        return response


def _normalize_path(path: str) -> str:
    """Normalize paths like /api/records/123 → /api/records/{id} for rate limiting."""
    parts = path.split("/")
    if len(parts) > 3 and parts[-1].isdigit():
        base = "/".join(parts[:-1])
        if base in {"/api/records", "/api/tasks", "/api/timeline"}:
            return base
    return path


# ── SQL injection guard ─────────────────────────────────────────────────────

# Whitelist of allowed table names for dynamic SQL operations
ALLOWED_TABLES = frozenset({
    "records", "events", "tasks", "contexts", "moods",
    "record_events", "record_tasks", "record_contexts",
})


def validate_table_name(name: str) -> str:
    """Validate that a table name is in the allowed whitelist. Raises ValueError."""
    if name not in ALLOWED_TABLES:
        raise ValueError(f"Invalid table name: {name}")
    return name


# ── Input sanitization ──────────────────────────────────────────────────────

MAX_CONTENT_LENGTH = 10_000
MAX_TITLE_LENGTH = 500
MAX_QUESTION_LENGTH = 2_000
MAX_USER_ID_LENGTH = 64
ALLOWED_USER_ID = r"^[a-zA-Z0-9_-]{1,64}$"


def sanitize_user_id(uid: str) -> str:
    """Validate user_id format. Raises HTTPException on invalid input."""
    import re
    uid = uid.strip()
    if not re.match(ALLOWED_USER_ID, uid):
        raise HTTPException(
            status_code=400,
            detail="Invalid user ID format. Use 1-64 alphanumeric chars, hyphens, underscores.",
        )
    return uid
