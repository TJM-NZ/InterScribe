import logging
import secrets

from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader

from app.config import settings

logger = logging.getLogger(__name__)

_header_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(key: str | None = Depends(_header_scheme)) -> None:
    if not settings.interscribe_api_key:
        return  # Auth disabled; startup warning already logged
    if not key or not secrets.compare_digest(key, settings.interscribe_api_key):
        raise HTTPException(
            status_code=403,
            detail={"error": "Invalid or missing API key", "code": "UNAUTHORIZED"},
        )
