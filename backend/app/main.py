"""NexoPanel FastAPI Application Entrypoint."""
from __future__ import annotations

import hmac
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

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


# The interactive API documentation exposes the complete endpoint inventory to
# unauthenticated visitors, so it is only served outside production.
_docs_enabled = settings.ENVIRONMENT != "production" or settings.DEBUG
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
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
            if not cookie_csrf or not header_csrf or not hmac.compare_digest(cookie_csrf, header_csrf):
                # An HTTPException raised inside middleware bypasses FastAPI's
                # exception handlers and surfaces as a 500, so return the 403
                # response directly.
                return JSONResponse(status_code=403, content={"detail": "CSRF validation failed"})
    return await call_next(request)


app.include_router(api_router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}


# Serve pre-built Nuxt 3 static SPA if present (single-port deployment on :8443)
_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / ".output" / "public"
if _FRONTEND_DIST.is_dir():
    if (_FRONTEND_DIST / "_nuxt").is_dir():
        app.mount("/_nuxt", StaticFiles(directory=str(_FRONTEND_DIST / "_nuxt")), name="nuxt-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API endpoint not found")
        candidate = _FRONTEND_DIST / full_path
        if candidate.is_file():
            headers = {"Cache-Control": "no-store, no-cache, must-revalidate"} if candidate.suffix == ".html" else {}
            return FileResponse(str(candidate), headers=headers)
        dir_index = candidate / "index.html"
        if dir_index.is_file():
            return FileResponse(str(dir_index), headers={"Cache-Control": "no-store, no-cache, must-revalidate"})
        index_html = _FRONTEND_DIST / "index.html"
        if index_html.is_file():
            return FileResponse(str(index_html), headers={"Cache-Control": "no-store, no-cache, must-revalidate"})
        raise HTTPException(status_code=404, detail="Frontend not built")
