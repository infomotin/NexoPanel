"""NexoPanel FastAPI Application Entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import settings
from app.core.os_gate import enforce_os_gate_or_exit
from app.db.bootstrap import init_db_schema, seed_defaults
from app.db.session import AsyncSessionLocal


@asynccontextmanager
async def lifespan(_app: FastAPI):
    enforce_os_gate_or_exit(skip_check=settings.SKIP_OS_CHECK)
    await init_db_schema()
    async with AsyncSessionLocal() as db:
        await seed_defaults(db)
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def csrf_protection_middleware(request: Request, call_next):
    """Enforce Double-Submit CSRF verification on mutating cookie-authenticated requests."""
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        has_cookie_auth = "access_token" in request.cookies
        has_bearer = request.headers.get("Authorization", "").startswith("Bearer ")
        if has_cookie_auth and not has_bearer and not request.url.path.endswith("/auth/login"):
            cookie_csrf = request.cookies.get(settings.CSRF_COOKIE_NAME)
            header_csrf = request.headers.get(settings.CSRF_HEADER_NAME)
            if not cookie_csrf or not header_csrf or cookie_csrf != header_csrf:
                raise HTTPException(status_code=403, detail="CSRF validation failed")
    return await call_next(request)


app.include_router(api_router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}
