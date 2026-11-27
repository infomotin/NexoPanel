"""SQLAlchemy 2.0 async engine configured for bundled SQLite 3 in WAL mode."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def _configure_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.execute("PRAGMA synchronous=NORMAL;")
    cursor.execute("PRAGMA busy_timeout=5000;")
    cursor.close()


def create_engine_and_session(database_url: str | None = None):
    url = database_url or settings.resolved_database_url
    if url.startswith("sqlite+aiosqlite:///"):
        db_file = Path(url.replace("sqlite+aiosqlite:///", ""))
        if str(db_file) != ":memory:":
            db_file.parent.mkdir(parents=True, exist_ok=True)

    engine = create_async_engine(
        url,
        echo=settings.DEBUG,
        future=True,
        connect_args={"check_same_thread": False} if "sqlite" in url else {},
    )
    if "sqlite" in url:
        event.listen(engine.sync_engine, "connect", _configure_sqlite_pragmas)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    return engine, session_factory


engine, AsyncSessionLocal = create_engine_and_session()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
