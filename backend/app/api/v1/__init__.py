"""API v1 router aggregation."""
from fastapi import APIRouter

from app.api.v1 import apps, auth, backups, db_admin, dns, files, mail, rbac, sites, ssl, system, terminal

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(rbac.router)
api_router.include_router(sites.router)
api_router.include_router(apps.router)
api_router.include_router(files.router)
api_router.include_router(dns.router)
api_router.include_router(mail.router)
api_router.include_router(ssl.router)
api_router.include_router(db_admin.router)
api_router.include_router(terminal.router)
api_router.include_router(backups.router)
api_router.include_router(system.router)
