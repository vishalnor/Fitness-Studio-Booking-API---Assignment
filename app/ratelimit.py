"""In-memory sliding-window rate limiter (per client IP).

Auth endpoints get a much tighter limit to slow down password guessing and
signup spam. State is per-process; use Redis or similar if running multiple workers.
"""
import os
import threading
import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse

WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
GENERAL_LIMIT = int(os.getenv("RATE_LIMIT_GENERAL", "100"))
AUTH_LIMIT = int(os.getenv("RATE_LIMIT_AUTH", "10"))
AUTH_PATHS = {"/signup", "/login", "/refresh"}


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window: int) -> int:
        """Record a hit. Return 0 if allowed, else seconds until the client may retry."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= window:
                hits.popleft()
            if len(hits) >= limit:
                return max(1, int(window - (now - hits[0])) + 1)
            hits.append(now)
            if not hits:
                del self._hits[key]
            return 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = SlidingWindowLimiter()


async def rate_limit_middleware(request: Request, call_next):
    ip = request.client.host if request.client else "unknown"
    is_auth = request.url.path in AUTH_PATHS
    bucket = f"{'auth' if is_auth else 'general'}:{ip}"
    limit = AUTH_LIMIT if is_auth else GENERAL_LIMIT
    retry_after = limiter.check(bucket, limit, WINDOW_SECONDS)
    if retry_after:
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Please slow down."},
            headers={"Retry-After": str(retry_after)},
        )
    return await call_next(request)
