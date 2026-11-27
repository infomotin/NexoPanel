"""Pytest async configuration and isolated test fixtures for NexoPanel."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Configure test environment before importing app modules
os.environ["NEXOPANEL_ENVIRONMENT"] = "testing"
os.environ["NEXOPANEL_SKIP_OS_CHECK"] = "true"
os.environ["NEXOPANEL_DAEMON_USE_MOCK_EXECUTOR"] = "true"
os.environ["NEXOPANEL_DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["NEXOPANEL_MASTER_KEY"] = "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg="
os.environ["NEXOPANEL_DNS_LIVE_CHECK_ENABLED"] = "false"
os.environ["NEXOPANEL_UPDATE_CHECK_ENABLED"] = "false"

from app.core.config import settings
from app.db.bootstrap import seed_defaults
from app.db.session import Base, create_engine_and_session, get_db
from app.main import app


@pytest_asyncio.fixture
async def test_app(tmp_path: Path):
    settings.WEB_ROOT_BASE = tmp_path / "www"
    settings.BACKUP_DIR = tmp_path / "backups"
    settings.ALLOWED_FILE_ROOTS = [str(tmp_path / "www"), str(tmp_path / "backups")]
    settings.WEB_ROOT_BASE.mkdir(parents=True, exist_ok=True)
    settings.BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    engine, session_factory = create_engine_and_session("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        await seed_defaults(db, initial_admin_password="TestAdminPassword123!")

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield app
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest_asyncio.fixture
async def admin_headers(client: AsyncClient) -> dict[str, str]:
    resp = await client.post("/api/v1/auth/login", json={"username": "admin", "password": "TestAdminPassword123!"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
