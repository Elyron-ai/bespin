import os
import time
from collections import defaultdict
from threading import Lock

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.database import engine, Base, SessionLocal
from app.gateway import models as gateway_models  # noqa: F401 - import for table creation
from app.gateway.router import router as gateway_router
from app.gateway.billing_router import router as billing_router
from app.gateway.core_os_router import router as core_os_router
from app.console.router import router as console_router
from app.playground.router import router as playground_router
from app.gateway.billing_seed import seed_all_billing_data


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiter for sensitive endpoints.

    Limits requests based on client IP using a sliding window algorithm.
    Rate limit settings can be configured via environment variables:
    - RATE_LIMIT_TENANT_CREATE: Max tenant creation requests per window (default: 10)
    - RATE_LIMIT_WINDOW_SECONDS: Time window in seconds (default: 60)
    - RATE_LIMIT_DISABLED: Set to "1" to disable rate limiting (useful for testing)
    """

    def __init__(self, app, rate_limit: int = 10, window_seconds: int = 60):
        super().__init__(app)
        self.disabled = os.environ.get("RATE_LIMIT_DISABLED", "0") == "1"
        self.rate_limit = int(os.environ.get("RATE_LIMIT_TENANT_CREATE", rate_limit))
        self.window_seconds = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", window_seconds))
        self.requests: dict[str, list[float]] = defaultdict(list)
        self.lock = Lock()
        # Paths to rate limit
        self.rate_limited_paths = {"/v1/tenants": "POST"}

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP from request, checking X-Forwarded-For header."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Take the first IP in the chain (original client)
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _cleanup_old_requests(self, ip: str, current_time: float) -> None:
        """Remove requests older than the window."""
        cutoff = current_time - self.window_seconds
        self.requests[ip] = [t for t in self.requests[ip] if t > cutoff]

    def _is_rate_limited(self, ip: str) -> bool:
        """Check if IP is rate limited and record new request."""
        current_time = time.time()
        with self.lock:
            self._cleanup_old_requests(ip, current_time)
            if len(self.requests[ip]) >= self.rate_limit:
                return True
            self.requests[ip].append(current_time)
            return False

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting if disabled (e.g., in test environments)
        if self.disabled:
            return await call_next(request)

        # Check if this path+method should be rate limited
        path = request.url.path
        method = request.method

        for limited_path, limited_method in self.rate_limited_paths.items():
            if path == limited_path and method == limited_method:
                client_ip = self._get_client_ip(request)
                if self._is_rate_limited(client_ip):
                    return JSONResponse(
                        status_code=429,
                        content={
                            "detail": f"Rate limit exceeded. Maximum {self.rate_limit} requests per {self.window_seconds} seconds.",
                            "error": "rate_limit_exceeded",
                        },
                        headers={"Retry-After": str(self.window_seconds)},
                    )

        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # XSS protection (legacy but still useful)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Control referrer information
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions policy (restrict browser features)
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        # Cache control for API responses (prevent sensitive data caching)
        if not request.url.path.startswith("/console") and not request.url.path.startswith("/ui"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"

        return response


Base.metadata.create_all(bind=engine)

# Seed billing data on startup
def _seed_billing_data():
    """Seed default billing data (metered events, plans, capabilities)."""
    db = SessionLocal()
    try:
        seed_all_billing_data(db)
    finally:
        db.close()

_seed_billing_data()

app = FastAPI(title="Bespin Tool Invocation Gateway", version="0.1.0")

# Configure CORS origins from environment variable
# In production, set CORS_ORIGINS to a comma-separated list of allowed origins
# Example: CORS_ORIGINS=https://app.example.com,https://admin.example.com
cors_origins_env = os.environ.get("CORS_ORIGINS", "")
if cors_origins_env:
    cors_origins = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]
else:
    # Default to localhost origins for development only
    cors_origins = ["http://localhost:3000", "http://localhost:8000", "http://127.0.0.1:3000", "http://127.0.0.1:8000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Add security headers to all responses
app.add_middleware(SecurityHeadersMiddleware)

# Add rate limiting for sensitive endpoints (tenant creation)
app.add_middleware(RateLimitMiddleware)

app.include_router(gateway_router)
app.include_router(billing_router)
app.include_router(core_os_router)
app.include_router(console_router)
app.include_router(playground_router)

@app.get("/")
def read_root():
    return {"message": "Bespin Tool Invocation Gateway", "version": "0.1.0"}

@app.get("/healthz")
async def healthz():
    """Health check endpoint that verifies database connectivity."""
    from sqlalchemy import text
    try:
        # Verify database is accessible
        db = SessionLocal()
        try:
            # Execute a simple query to verify connection
            db.execute(text("SELECT 1"))
            return {"status": "ok", "database": "connected"}
        finally:
            db.close()
    except Exception as e:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unhealthy", "database": "disconnected", "error": str(e)},
        )
