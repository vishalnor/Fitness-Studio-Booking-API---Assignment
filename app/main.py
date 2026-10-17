"""FastAPI application entrypoint."""
import logging
import time

from fastapi import FastAPI, Request

from .database import Base, engine
from .ratelimit import rate_limit_middleware
from .routers import auth, bookings, classes

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("fitness")

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Fitness Studio Booking API",
    description="Sign up, log in, browse classes, and book slots. Class times are stored in IST.",
    version="1.0.0",
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    logger.info(
        "%s %s -> %s (%.1f ms)",
        request.method, request.url.path, response.status_code, (time.perf_counter() - start) * 1000,
    )
    return response


app.middleware("http")(rate_limit_middleware)

app.include_router(auth.router)
app.include_router(classes.router)
app.include_router(bookings.router)


@app.get("/", tags=["health"])
def health():
    return {"status": "ok", "docs": "/docs"}
