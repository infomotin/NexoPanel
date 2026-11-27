"""Engine-aware MariaDB/MySQL & PostgreSQL helpers shared by database features.

The database clients run with superuser privileges over the local socket, so the
session string-escaping semantics must always be pinned *before* interpolating
user-controlled values:

* MariaDB/MySQL's default sql_mode treats a backslash as an escape character,
  allowing a password containing a backslash to break out of the quoted literal.
* PostgreSQL's ``standard_conforming_strings`` is pinned to ``on`` so that quote
  doubling is always the correct (and only) escape.
"""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.validators import (
    escape_sql_string_literal,
    validate_db_host,
    validate_db_identifier,
    validate_mysql_charset,
)
from app.db.models import PanelSetting
from app.services.executor import ExecutionResult, NodeExecutor

MARIADB_SESSION_PREFIX = "SET SESSION sql_mode = CONCAT(@@SESSION.sql_mode, ',NO_BACKSLASH_ESCAPES');"
POSTGRES_SESSION_PREFIX = "SET standard_conforming_strings = on;"


def mariadb_sql(statement: str) -> str:
    return f"{MARIADB_SESSION_PREFIX} {statement}"


def postgres_sql(statement: str) -> str:
    return f"{POSTGRES_SESSION_PREFIX} {statement}"


async def provision_database(
    executor: NodeExecutor,
    *,
    engine: str,
    db_name: str,
    db_user: str,
    db_password: str,
    db_host: str = "localhost",
    charset: str = "utf8mb4",
) -> ExecutionResult:
    """Create the database, its owning user and the grants for that user."""
    db_name = validate_db_identifier(db_name)
    db_user = validate_db_identifier(db_user)
    db_host = validate_db_host(db_host)
    charset = validate_mysql_charset(charset)
    safe_pw = escape_sql_string_literal(db_password)

    if engine == "mariadb":
        sql = mariadb_sql(
            f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET {charset}; "
            f"CREATE USER IF NOT EXISTS '{db_user}'@'{db_host}' IDENTIFIED BY '{safe_pw}'; "
            f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO '{db_user}'@'{db_host}'; "
            "FLUSH PRIVILEGES;"
        )
        return await executor.run_command(["/usr/bin/mariadb", "-e", sql])

    # PostgreSQL: CREATE DATABASE cannot run inside a transaction block, and a
    # multi-statement `psql -c` string is executed as one implicit transaction.
    # Create the role first, then the database, then grant in separate calls.
    role_sql = postgres_sql(
        f"DO $$ BEGIN CREATE USER {db_user} WITH PASSWORD '{safe_pw}'; "
        f"EXCEPTION WHEN duplicate_object THEN ALTER USER {db_user} WITH PASSWORD '{safe_pw}'; END $$;"
    )
    res = await executor.run_command(["/usr/bin/psql", "-U", "postgres", "-c", role_sql])
    if not res.ok:
        return res

    res = await executor.run_command(
        ["/usr/bin/psql", "-U", "postgres", "-c", f"CREATE DATABASE {db_name} OWNER {db_user};"]
    )
    if not res.ok and "already exists" not in (res.stderr or "").lower():
        return res

    return await executor.run_command(
        [
            "/usr/bin/psql",
            "-U",
            "postgres",
            "-c",
            f"GRANT ALL PRIVILEGES ON DATABASE {db_name} TO {db_user};",
        ]
    )


async def drop_database(
    executor: NodeExecutor,
    *,
    engine: str,
    db_name: str,
    db_user: str | None = None,
    db_host: str = "localhost",
) -> ExecutionResult:
    """Drop a database and, when known, its owning account."""
    db_name = validate_db_identifier(db_name)
    if engine == "mariadb":
        sql = f"DROP DATABASE IF EXISTS `{db_name}`;"
        if db_user:
            sql += f" DROP USER IF EXISTS '{validate_db_identifier(db_user)}'@'{validate_db_host(db_host)}';"
        return await executor.run_command(["/usr/bin/mariadb", "-e", sql])

    res = await executor.run_command(
        ["/usr/bin/psql", "-U", "postgres", "-c", f"DROP DATABASE IF EXISTS {db_name};"]
    )
    if res.ok and db_user:
        # Best-effort: the role may still own objects in other databases.
        await executor.run_command(
            [
                "/usr/bin/psql",
                "-U",
                "postgres",
                "-c",
                f"DROP USER IF EXISTS {validate_db_identifier(db_user)};",
            ]
        )
    return res


async def import_sql(
    executor: NodeExecutor, *, engine: str, db_name: str, sql_content: str
) -> ExecutionResult:
    """Stream a SQL dump to the database client over stdin.

    Using stdin instead of ``-e`` keeps the argument list bounded for large
    dumps; the daemon already permits an optional ``stdin`` payload for exec.
    """
    if engine == "mariadb":
        return await executor.run_command(["/usr/bin/mariadb", db_name], timeout=600, stdin=sql_content)
    return await executor.run_command(
        ["/usr/bin/psql", "-U", "postgres", "-d", db_name], timeout=600, stdin=sql_content
    )


async def dump_database(
    executor: NodeExecutor, *, engine: str, db_name: str
) -> ExecutionResult:
    if engine == "mariadb":
        return await executor.run_command(["/usr/bin/mariadb-dump", db_name], timeout=600)
    return await executor.run_command(["/usr/bin/pg_dump", "-U", "postgres", db_name], timeout=600)


async def record_database_password(
    db: AsyncSession,
    *,
    engine: str,
    db_name: str,
    password: str,
    note: str | None = None,
) -> None:
    """Persist the encrypted password under the same key the DB admin page reads."""
    from app.core.security import secret_manager

    key = f"db_meta:{engine}:{db_name}"
    row = (await db.execute(select(PanelSetting).where(PanelSetting.key == key))).scalar_one_or_none()
    meta: dict = {}
    if row:
        try:
            meta = json.loads(row.value)
        except Exception:
            meta = {}
    meta["password_enc"] = secret_manager.encrypt(password)
    if note is not None:
        meta["note"] = note
    if row:
        row.value = json.dumps(meta)
    else:
        db.add(PanelSetting(key=key, value=json.dumps(meta), is_secret=True))
