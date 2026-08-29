import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from app.auth import require_api_key
from app.config import settings
from app.database import get_db
from app.limiter import limiter
from app.routers import condensation, phase1, phase2, videos

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.interscribe_api_key:
        logger.warning(
            "INTERSCRIBE_API_KEY is not set — all API endpoints are unauthenticated. "
            "Generate a key with: python -c \"import secrets; print(secrets.token_hex(32))\" "
            "and set INTERSCRIBE_API_KEY in .env."
        )
    yield


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


app = FastAPI(title="InterScribe", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(SecurityHeadersMiddleware)

_auth = [Depends(require_api_key)]

app.include_router(videos.router, dependencies=_auth)
app.include_router(phase1.router, dependencies=_auth)
app.include_router(phase2.router, dependencies=_auth)
app.include_router(condensation.router, dependencies=_auth)


@app.get("/health")
def health(db=Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}
