"""Upstream update checker.

Compares the locally installed NexoPanel commit/version with the public GitHub
repository (``settings.GITHUB_REPO``) so the dashboard can surface a reliable
"update available" notification.  Results are cached to stay well inside the
unauthenticated GitHub API rate limit and to keep dashboard loads fast.
"""
from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings

_UPDATE_COMMAND = (
    "cd /opt/nexopanel && git pull --ff-only origin main && sudo bash scripts/install.sh"
)
_REINSTALL_COMMAND = (
    "curl -fsSL https://raw.githubusercontent.com/infomotin/NexoPanel/main/scripts/install.sh "
    "| sudo bash -s -- --repo https://github.com/infomotin/NexoPanel.git"
)

_CACHE: dict[str, Any] = {"timestamp": 0.0, "data": None}


def _repo_root() -> Path | None:
    """Return the git checkout root when the panel was installed from source."""
    candidate = Path(__file__).resolve().parents[3]
    return candidate if (candidate / ".git").exists() else None


async def _local_git_commit() -> str | None:
    root = _repo_root()
    if root is None:
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "-c",
            f"safe.directory={root}",
            "-C",
            str(root),
            "rev-parse",
            "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
    except (OSError, asyncio.TimeoutError):
        return None
    if proc.returncode != 0:
        return None
    commit = stdout.decode("utf-8", errors="replace").strip()
    return commit or None


async def _github_json(path: str) -> tuple[Any | None, str | None]:
    url = f"https://api.github.com/repos/{settings.GITHUB_REPO}{path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "NexoPanel-UpdateChecker",
    }
    if settings.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0)) as client:
            resp = await client.get(url, headers=headers)
    except Exception as exc:  # noqa: BLE001 - offline hosts must not break the dashboard
        return None, str(exc)
    if resp.status_code != 200:
        return None, f"GitHub API returned HTTP {resp.status_code}"
    try:
        return resp.json(), None
    except ValueError:
        return None, "GitHub API returned an invalid response"


def _version_tuple(value: str | None) -> tuple[int, ...]:
    if not value:
        return ()
    match = re.search(r"(\d+(?:\.\d+)*)", value)
    if not match:
        return ()
    return tuple(int(part) for part in match.group(1).split("."))


def _format_commit(item: dict[str, Any]) -> dict[str, Any]:
    commit = item.get("commit", {}) or {}
    author = commit.get("author", {}) or {}
    message = (commit.get("message") or "").splitlines()[0] if commit.get("message") else ""
    return {
        "sha": item.get("sha", ""),
        "short_sha": (item.get("sha") or "")[:7],
        "message": message,
        "author": (item.get("author") or {}).get("login") or author.get("name") or "unknown",
        "date": author.get("date"),
        "url": item.get("html_url"),
    }


async def _build_update_status() -> dict[str, Any]:
    repo_url = f"https://github.com/{settings.GITHUB_REPO}"
    local_commit = await _local_git_commit()

    commits_data, commits_error = await _github_json("/commits?per_page=10&sha=main")
    recent_commits = [_format_commit(item) for item in commits_data] if isinstance(commits_data, list) else []
    latest_commit = recent_commits[0]["sha"] if recent_commits else None

    release_data, _ = await _github_json("/releases/latest")
    latest_version = release_data.get("tag_name") if isinstance(release_data, dict) else None

    update_available = False
    commits_behind: int | None = None
    error = commits_error

    if local_commit and latest_commit:
        if local_commit == latest_commit:
            commits_behind = 0
        else:
            compare, compare_error = await _github_json(
                f"/compare/{local_commit}...{latest_commit}"
            )
            if isinstance(compare, dict):
                commits_behind = int(compare.get("behind_by") or 0)
                update_available = commits_behind > 0
            else:
                # The comparison failed but we know the commits differ; surface
                # the update rather than silently hiding it.
                update_available = True
                error = error or compare_error
    else:
        current = _version_tuple(settings.APP_VERSION)
        latest = _version_tuple(latest_version)
        if current and latest:
            update_available = latest > current
        elif local_commit is None and latest_version is None and error is None:
            error = "Local git metadata and upstream release information are unavailable"

    return {
        "enabled": settings.UPDATE_CHECK_ENABLED,
        "repo_url": repo_url,
        "current_version": settings.APP_VERSION,
        "current_commit": local_commit,
        "current_commit_short": local_commit[:7] if local_commit else None,
        "latest_version": latest_version,
        "latest_commit": latest_commit,
        "latest_commit_short": latest_commit[:7] if latest_commit else None,
        "latest_commit_message": recent_commits[0]["message"] if recent_commits else None,
        "latest_commit_date": recent_commits[0]["date"] if recent_commits else None,
        "update_available": update_available,
        "commits_behind": commits_behind,
        "recent_commits": recent_commits,
        "update_command": _UPDATE_COMMAND,
        "reinstall_command": _REINSTALL_COMMAND,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "error": error,
    }


async def check_for_updates(force: bool = False) -> dict[str, Any]:
    if not settings.UPDATE_CHECK_ENABLED:
        return {
            "enabled": False,
            "repo_url": f"https://github.com/{settings.GITHUB_REPO}",
            "current_version": settings.APP_VERSION,
            "update_available": False,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "error": None,
        }

    now = time.monotonic()
    cached = _CACHE.get("data")
    if not force and cached and now - float(_CACHE["timestamp"]) < settings.UPDATE_CHECK_TTL_SECONDS:
        return cached

    result = await _build_update_status()
    _CACHE["data"] = result
    _CACHE["timestamp"] = time.monotonic()
    return result
