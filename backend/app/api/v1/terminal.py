"""Authenticated Web Terminal over WebSockets (/api/v1/terminal/ws)."""
from __future__ import annotations

import asyncio
import json
import os
import sys

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.audit import record_audit_event
from app.core.config import settings
from app.core.security import decode_token
from app.db.models import User
from app.db.session import AsyncSessionLocal

router = APIRouter(prefix="/terminal", tags=["Web Terminal"])


@router.websocket("/ws")
async def terminal_websocket(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token") or websocket.cookies.get("access_token")
    if not token:
        await websocket.close(code=4401)
        return

    try:
        payload = decode_token(token)
    except Exception:
        await websocket.close(code=4401)
        return

    perms = set(payload.get("perms", []))
    if "*" not in perms and "terminal:execute" not in perms:
        await websocket.close(code=4403)
        return

    await websocket.accept()
    user_id = payload.get("uid")

    async with AsyncSessionLocal() as db:
        actor = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        await record_audit_event(
            db,
            actor=actor,
            request=None,
            permission="terminal:execute",
            action="terminal_session_start",
            target_resource="pty:localhost",
        )
        await db.commit()

    if sys.platform == "win32":
        await websocket.send_text("NexoPanel PTY terminal requires Linux POSIX pty/termios.\r\n")
        await websocket.close()
        return

    import fcntl
    import pty
    import struct
    import termios

    master_fd, slave_fd = pty.openpty()
    pid = os.fork()
    if pid == 0:
        os.setsid()
        os.dup2(slave_fd, 0)
        os.dup2(slave_fd, 1)
        os.dup2(slave_fd, 2)
        os.close(master_fd)
        os.close(slave_fd)
        os.execv("/bin/bash", ["/bin/bash", "-l"])

    os.close(slave_fd)
    loop = asyncio.get_running_loop()

    async def read_pty() -> None:
        while True:
            data = await loop.run_in_executor(None, os.read, master_fd, 4096)
            if not data:
                break
            await websocket.send_text(data.decode("utf-8", errors="replace"))

    reader_task = asyncio.create_task(read_pty())
    try:
        while True:
            msg = await asyncio.wait_for(websocket.receive_text(), timeout=settings.TERMINAL_IDLE_TIMEOUT_SECONDS)
            if msg.startswith("{") and '"resize"' in msg:
                data = json.loads(msg)
                rows = int(data.get("rows", 24))
                cols = int(data.get("cols", 80))
                fcntl.ioctl(master_fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
            else:
                os.write(master_fd, msg.encode("utf-8"))
    except (WebSocketDisconnect, TimeoutError):
        pass
    finally:
        reader_task.cancel()
        os.close(master_fd)
        try:
            os.kill(pid, 9)
        except OSError:
            pass
        async with AsyncSessionLocal() as db:
            actor = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
            await record_audit_event(
                db,
                actor=actor,
                request=None,
                permission="terminal:execute",
                action="terminal_session_end",
                target_resource="pty:localhost",
            )
            await db.commit()
