"""Web authentication middleware."""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse

PROTECTED_PATHS = ["/monitor/", "/settings", "/alerts", "/selector"]
PUBLIC_PATHS = ["/", "/login", "/logout", "/health", "/api/", "/static/"]


class WebAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        # Allow public paths
        for pp in PUBLIC_PATHS:
            if path.startswith(pp) or path == pp:
                return await call_next(request)
        # Check protected paths
        for pp in PROTECTED_PATHS:
            if path.startswith(pp):
                token = request.cookies.get("session_token")
                if not token:
                    return RedirectResponse("/login")
        return await call_next(request)
