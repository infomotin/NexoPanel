"""Authenticated Web Terminal over WebSockets (/api/v1/terminal/ws).

Architecture notes:
- PTY subprocess: bash -l running as the authenticated API user.
- Two concurrent async tasks:
    read_pty  – continuously reads bytes from the PTY master fd and forwards
                them to the browser as UTF-8 text.
    write_ws  – receives text frames from the browser, dispatches resize
                messages via TIOCSWINSZ, pong heartbeats, and raw keystrokes
                to the PTY master fd.
- Keepalive: the browser sends {"type":"ping"} every HEARTBEAT_SECONDS; the
  server echoes {"type":"pong"}.  This prevents both the browser WebSocket
  implementation and any intervening proxy from closing an "idle" connection
  while a long-running command (apt-get, systemd, make …) is executing.
- The idle timeout only disconnects after TERMINAL_IDLE_TIMEOUT_SECONDS of
  silence from both the PTY AND the browser – i.e. the PTY subprocess has
  exited AND no input has been received.
"""
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

# How often the server sends a keepalive ping to the browser (seconds).
# Must be shorter than any proxy read-timeout (typically 60 s).
_SERVER_PING_INTERVAL = 20


@router.websocket("/ws")
async def terminal_websocket(websocket: WebSocket) -> None:
    # Authenticate with the HttpOnly session cookie only: a token in the query
    # string would be written to proxy/access logs and browser history.
    token = websocket.cookies.get("access_token")
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
        # Child: become the PTY session leader and exec bash
        os.setsid()
        os.dup2(slave_fd, 0)
        os.dup2(slave_fd, 1)
        os.dup2(slave_fd, 2)
        os.close(master_fd)
        os.close(slave_fd)
        os.execv("/bin/bash", ["/bin/bash", "-l"])

    os.close(slave_fd)
    loop = asyncio.get_running_loop()

    # Shared stop event: set by either side when the session should terminate.
    stop_event = asyncio.Event()

    async def read_pty() -> None:
        """Forward PTY output → browser. Also sends periodic server-side pings
        so the WebSocket stays alive while long commands are running."""
        ping_counter = 0
        try:
            while not stop_event.is_set():
                try:
                    data = await asyncio.wait_for(
                        loop.run_in_executor(None, os.read, master_fd, 4096),
                        timeout=_SERVER_PING_INTERVAL,
                    )
                    if not data:
                        # PTY EOF – subprocess exited
                        break
                    await websocket.send_text(data.decode("utf-8", errors="replace"))
                    ping_counter = 0  # reset idle ping counter on real activity
                except asyncio.TimeoutError:
                    # No PTY output for _SERVER_PING_INTERVAL seconds.
                    # Send a keepalive ping so the browser + proxy stay awake.
                    ping_counter += 1
                    try:
                        await websocket.send_text(json.dumps({"type": "ping"}))
                    except Exception:
                        break
                    # If nothing has happened for a very long time AND the PTY
                    # is idle, honour the configured idle timeout.
                    if ping_counter * _SERVER_PING_INTERVAL >= settings.TERMINAL_IDLE_TIMEOUT_SECONDS:
                        break
        finally:
            stop_event.set()

    async def write_ws() -> None:
        """Receive browser frames → PTY input / resize / heartbeat handling."""
        try:
            while not stop_event.is_set():
                try:
                    msg = await asyncio.wait_for(
                        websocket.receive_text(),
                        timeout=settings.TERMINAL_IDLE_TIMEOUT_SECONDS + _SERVER_PING_INTERVAL,
                    )
                except asyncio.TimeoutError:
                    # Browser didn't send anything for a very long time
                    # (longer than idle timeout + ping interval).
                    break
                except WebSocketDisconnect:
                    break

                if not msg:
                    continue

                # JSON control frames
                if msg.startswith("{"):
                    try:
                        data = json.loads(msg)
                    except json.JSONDecodeError:
                        os.write(master_fd, msg.encode("utf-8"))
                        continue

                    msg_type = data.get("type") or ("resize" if "resize" in data else None)

                    if msg_type == "ping":
                        # Browser heartbeat – echo pong
                        try:
                            await websocket.send_text(json.dumps({"type": "pong"}))
                        except Exception:
                            break
                    elif msg_type == "resize" or "resize" in data:
                        rows = int(data.get("rows", 24))
                        cols = int(data.get("cols", 80))
                        try:
                            fcntl.ioctl(master_fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
                        except OSError:
                            pass
                    # other JSON (e.g. unknown types) – silently ignore
                else:
                    # Raw keystroke data
                    try:
                        os.write(master_fd, msg.encode("utf-8"))
                    except OSError:
                        break
        finally:
            stop_event.set()

    reader_task = asyncio.create_task(read_pty())
    writer_task = asyncio.create_task(write_ws())

    # Wait until either side signals completion
    await stop_event.wait()

    reader_task.cancel()
    writer_task.cancel()

    # Clean up PTY and child process
    try:
        os.close(master_fd)
    except OSError:
        pass
    try:
        os.kill(pid, 9)
    except OSError:
        pass
    try:
        os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
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
