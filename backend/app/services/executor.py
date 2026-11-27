"""NodeExecutor abstraction & privilege-separated Unix socket client."""
from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import settings


@dataclass
class ExecutionResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class NodeExecutor(ABC):
    """Node-scoped execution interface (LocalNodeExecutor now, RemoteNodeExecutor in future)."""

    def __init__(self, node_id: str = settings.LOCAL_NODE_ID) -> None:
        self.node_id = node_id

    @abstractmethod
    async def run_command(self, args: list[str], timeout: int = 120) -> ExecutionResult: ...

    @abstractmethod
    async def write_privileged_file(self, path: str, content: str, mode: int = 0o644) -> ExecutionResult: ...

    @abstractmethod
    async def create_symlink(self, target: str, link_path: str) -> ExecutionResult: ...

    @abstractmethod
    async def remove_file(self, path: str) -> ExecutionResult: ...

    @abstractmethod
    async def ensure_directory(self, path: str, owner: str = "www-data", group: str = "www-data", mode: int = 0o755) -> ExecutionResult: ...


class LocalNodeExecutor(NodeExecutor):
    """Executes privileged operations via root daemon Unix socket, or direct exec in dev/test."""

    def __init__(
        self,
        node_id: str = settings.LOCAL_NODE_ID,
        socket_path: Path | None = None,
        use_mock: bool | None = None,
    ) -> None:
        super().__init__(node_id=node_id)
        self.socket_path = socket_path or settings.DAEMON_SOCKET_PATH
        self.use_mock = settings.DAEMON_USE_MOCK_EXECUTOR if use_mock is None else use_mock

    async def _send_daemon_request(self, payload: dict[str, Any], timeout: int = 120) -> ExecutionResult:
        if self.use_mock:
            return ExecutionResult(returncode=0, stdout="[mock-executor] ok", stderr="")

        if self.socket_path.exists():
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(str(self.socket_path)),
                timeout=5,
            )
            try:
                writer.write((json.dumps(payload) + "\n").encode("utf-8"))
                await writer.drain()
                raw = await asyncio.wait_for(reader.readline(), timeout=timeout)
                resp = json.loads(raw.decode("utf-8"))
                return ExecutionResult(
                    returncode=int(resp.get("returncode", 1)),
                    stdout=resp.get("stdout", ""),
                    stderr=resp.get("stderr", ""),
                )
            finally:
                writer.close()
                await writer.wait_closed()

        # Fallback to direct non-shell subprocess if running in single-user dev mode
        if payload.get("op") == "exec":
            args: list[str] = payload["args"]
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return ExecutionResult(
                returncode=proc.returncode or 0,
                stdout=out_b.decode("utf-8", errors="replace"),
                stderr=err_b.decode("utf-8", errors="replace"),
            )
        return ExecutionResult(returncode=1, stdout="", stderr="Privileged daemon socket unavailable")

    async def run_command(self, args: list[str], timeout: int = 120) -> ExecutionResult:
        return await self._send_daemon_request({"op": "exec", "args": args, "timeout": timeout}, timeout=timeout)

    async def write_privileged_file(self, path: str, content: str, mode: int = 0o644) -> ExecutionResult:
        if self.use_mock:
            return ExecutionResult(returncode=0, stdout="", stderr="")
        if not self.socket_path.exists():
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return ExecutionResult(returncode=0, stdout="", stderr="")
        return await self._send_daemon_request({"op": "write_file", "path": path, "content": content, "mode": mode})

    async def create_symlink(self, target: str, link_path: str) -> ExecutionResult:
        return await self._send_daemon_request({"op": "symlink", "target": target, "link_path": link_path})

    async def remove_file(self, path: str) -> ExecutionResult:
        return await self._send_daemon_request({"op": "remove_file", "path": path})

    async def ensure_directory(
        self, path: str, owner: str = "www-data", group: str = "www-data", mode: int = 0o755
    ) -> ExecutionResult:
        if self.use_mock:
            return ExecutionResult(returncode=0, stdout="", stderr="")
        if not self.socket_path.exists():
            Path(path).mkdir(parents=True, exist_ok=True)
            return ExecutionResult(returncode=0, stdout="", stderr="")
        return await self._send_daemon_request(
            {"op": "ensure_dir", "path": path, "owner": owner, "group": group, "mode": mode}
        )


def get_node_executor(node_id: str = settings.LOCAL_NODE_ID) -> NodeExecutor:
    """Factory returning LocalNodeExecutor (or future RemoteNodeExecutor by node_id)."""
    return LocalNodeExecutor(node_id=node_id)
