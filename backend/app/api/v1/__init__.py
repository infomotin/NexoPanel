"""API v1 router aggregation."""
from fastapi import APIRouter

from app.api.v1 import apps, auth, backups, cron, db_admin, dns, docker, files, firewall, ftp, mail, processes, rbac, sites, ssl, system, terminal

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(rbac.router)
api_router.include_router(sites.router)
api_router.include_router(apps.router)
api_router.include_router(files.router)
api_router.include_router(ftp.router)
api_router.include_router(dns.router)
api_router.include_router(mail.router)
api_router.include_router(ssl.router)
api_router.include_router(db_admin.router)
api_router.include_router(terminal.router)
api_router.include_router(backups.router)
api_router.include_router(system.router)
api_router.include_router(firewall.router)
api_router.include_router(cron.router)
api_router.include_router(processes.router)
api_router.include_router(docker.router)
