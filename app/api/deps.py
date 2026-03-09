"""API dependencies: auth, pagination, rate limiting."""
import time
from collections import defaultdict, deque
from typing import Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.services.auth_service import AuthService

# Rate limiter: sliding window
_rate_limits: dict[str, deque] = defaultdict(lambda: deque())
RATE_LIMIT = 100
RATE_WINDOW = 60


async def get_current_user(request: Request, session: AsyncSession = Depends(get_session)):
    auth_header = request.headers.get("Authorization", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    elif auth_header.startswith("ApiKey "):
        token = auth_header[7:]
    # Also check cookie
    if not token:
        token = request.cookies.get("session_token")
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    auth = AuthService(session)
    # Try JWT first
    user_id = auth.verify_session_token(token)
    if user_id:
        user = await auth.get_user_by_id(user_id)
        if user:
            return user
    # Try API key
    user = await auth.authenticate_api_key(token)
    if user:
        return user
    raise HTTPException(status_code=401, detail="Unauthorized")


def check_rate_limit(request: Request):
    key = request.headers.get("Authorization", request.client.host if request.client else "unknown")
    now = time.time()
    window = _rate_limits[key]
    while window and window[0] < now - RATE_WINDOW:
        window.popleft()
    if len(window) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many requests", headers={"Retry-After": str(RATE_WINDOW)})
    window.append(now)


class PaginationParams:
    def __init__(self, page: int = 1, per_page: int = 20):
        self.page = max(1, page)
        self.per_page = min(max(1, per_page), 100)

    @property
    def offset(self):
        return (self.page - 1) * self.per_page


def api_response(data=None, error=None, meta=None):
    return {"data": data, "error": error, "meta": meta}
