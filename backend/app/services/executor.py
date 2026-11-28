"""NodeExecutor abstraction & privilege-separated Unix socket client."""
from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
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
    async def run_command(
        self, args: list[str], timeout: int = 120, stdin: str | None = None
    ) -> ExecutionResult: ...

    @abstractmethod
    async def write_privileged_file(self, path: str, content: str, mode: int = 0o644) -> ExecutionResult: ...

    @abstractmethod
    async def create_symlink(self, target: str, link_path: str) -> ExecutionResult: ...

    @abstractmethod
    async def remove_file(self, path: str) -> ExecutionResult: ...

    @abstractmethod
    async def ensure_directory(self, path: str, owner: str = "www-data", group: str = "www-data", mode: int = 0o755) -> ExecutionResult: ...

    # --- File manager helpers (the API worker is unprivileged) -------------
    @abstractmethod
    async def write_bytes(
        self,
        path: str,
        data: bytes,
        mode: int = 0o644,
        *,
        append: bool = False,
        owner: str | None = None,
        group: str | None = None,
    ) -> ExecutionResult: ...

    @abstractmethod
    async def read_bytes(self, path: str, max_bytes: int = 32 * 1024 * 1024) -> bytes: ...

    @abstractmethod
    async def move_item(self, source: str, destination: str, *, owner: str | None = None, group: str | None = None) -> ExecutionResult: ...

    @abstractmethod
    async def copy_item(self, source: str, destination: str, *, owner: str | None = None, group: str | None = None) -> ExecutionResult: ...

    @abstractmethod
    async def chmod_item(self, path: str, mode: int) -> ExecutionResult: ...

    @abstractmethod
    async def remove_item(self, path: str) -> ExecutionResult: ...

    @abstractmethod
    async def install_file(
        self, source: str, destination: str, mode: int = 0o644, *, owner: str | None = None, group: str | None = None
    ) -> ExecutionResult: ...

    @abstractmethod
    async def install_tree(self, source: str, destination: str, *, owner: str | None = None, group: str | None = None) -> ExecutionResult: ...

    @abstractmethod
    async def read_log_file(self, path: str, lines: int = 100, filter_text: str | None = None) -> ExecutionResult: ...

    @abstractmethod
    async def clear_log_file(self, path: str) -> ExecutionResult: ...

    @abstractmethod
    async def drop_caches(self) -> ExecutionResult: ...


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
            stdin_data = payload.get("stdin")
            try:
                proc = await asyncio.create_subprocess_exec(
                    *args,
                    stdin=asyncio.subprocess.PIPE if stdin_data is not None else None,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                out_b, err_b = await asyncio.wait_for(
                    proc.communicate(input=stdin_data.encode("utf-8") if stdin_data is not None else None),
                    timeout=timeout,
                )
                return ExecutionResult(
                    returncode=proc.returncode or 0,
                    stdout=out_b.decode("utf-8", errors="replace"),
                    stderr=err_b.decode("utf-8", errors="replace"),
                )
            except FileNotFoundError:
                return ExecutionResult(
                    returncode=127,
                    stdout="",
                    stderr=f"Executable not found: {args[0]}",
                )
            except Exception as exc:
                return ExecutionResult(
                    returncode=1,
                    stdout="",
                    stderr=str(exc),
                )
        return ExecutionResult(returncode=1, stdout="", stderr="Privileged daemon socket unavailable")

    async def run_command(
        self, args: list[str], timeout: int = 120, stdin: str | None = None
    ) -> ExecutionResult:
        payload: dict[str, Any] = {"op": "exec", "args": args, "timeout": timeout}
        if stdin is not None:
            payload["stdin"] = stdin
        return await self._send_daemon_request(payload, timeout=timeout)

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
        self,
        path: str,
        owner: str = "www-data",
        group: str = "www-data",
        mode: int = 0o755,
        scope: str | None = None,
    ) -> ExecutionResult:
        if self.use_mock:
            return ExecutionResult(returncode=0, stdout="", stderr="")
        if not self.socket_path.exists():
            Path(path).mkdir(parents=True, exist_ok=True)
            return ExecutionResult(returncode=0, stdout="", stderr="")
        payload: dict[str, Any] = {
            "op": "ensure_dir",
            "path": path,
            "owner": owner,
            "group": group,
            "mode": mode,
        }
        if scope:
            payload["scope"] = scope
        return await self._send_daemon_request(payload)

    # --- File manager helpers --------------------------------------------

    async def write_bytes(
        self,
        path: str,
        data: bytes,
        mode: int = 0o644,
        *,
        append: bool = False,
        owner: str | None = None,
        group: str | None = None,
    ) -> ExecutionResult:
        if self.use_mock:
            return ExecutionResult(returncode=0, stdout="written", stderr="")
        if not self.socket_path.exists():
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("ab" if append else "wb") as fh:
                fh.write(data)
            return ExecutionResult(returncode=0, stdout="written", stderr="")
        return await self._send_daemon_request(
            {
                "op": "write_bytes",
                "path": path,
                "content_b64": base64.b64encode(data).decode("ascii"),
                "mode": mode,
                "append": append,
                "owner": owner,
                "group": group,
            }
        )

    async def read_bytes(self, path: str, max_bytes: int = 32 * 1024 * 1024) -> bytes:
        if self.use_mock:
            return b""
        if not self.socket_path.exists():
            return Path(path).read_bytes()
        res = await self._send_daemon_request({"op": "read_file", "path": path})
        if not res.ok:
            raise RuntimeError(res.stderr or "privileged read failed")
        try:
            data = base64.b64decode(res.stdout.encode("ascii"), validate=True)
        except Exception as exc:  # pragma: no cover - defensive
            raise RuntimeError("invalid privileged read payload") from exc
        if len(data) > max_bytes:
            raise RuntimeError("file too large")
        return data

    async def move_item(self, source: str, destination: str, *, owner: str | None = None, group: str | None = None) -> ExecutionResult:
        if self.use_mock:
            return ExecutionResult(returncode=0, stdout="moved", stderr="")
        if not self.socket_path.exists():
            shutil.move(source, destination)
            return ExecutionResult(returncode=0, stdout="moved", stderr="")
        return await self._send_daemon_request(
            {"op": "move_item", "source": source, "destination": destination, "owner": owner, "group": group}
        )

    async def copy_item(self, source: str, destination: str, *, owner: str | None = None, group: str | None = None) -> ExecutionResult:
        if self.use_mock:
            return ExecutionResult(returncode=0, stdout="copied", stderr="")
        if not self.socket_path.exists():
            src, dst = Path(source), Path(destination)
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True, symlinks=False)
            else:
                shutil.copy2(src, dst)
            return ExecutionResult(returncode=0, stdout="copied", stderr="")
        return await self._send_daemon_request(
            {"op": "copy_item", "source": source, "destination": destination, "owner": owner, "group": group}
        )

    async def chmod_item(self, path: str, mode: int) -> ExecutionResult:
        if self.use_mock:
            return ExecutionResult(returncode=0, stdout="chmod", stderr="")
        if not self.socket_path.exists():
            os.chmod(path, mode)
            return ExecutionResult(returncode=0, stdout="chmod", stderr="")
        return await self._send_daemon_request({"op": "chmod_item", "path": path, "mode": mode})

    async def remove_item(self, path: str) -> ExecutionResult:
        if self.use_mock:
            return ExecutionResult(returncode=0, stdout="removed", stderr="")
        if not self.socket_path.exists():
            target = Path(path)
            if target.is_symlink() or target.is_file():
                target.unlink()
            elif target.is_dir():
                shutil.rmtree(target)
            return ExecutionResult(returncode=0, stdout="removed", stderr="")
        return await self._send_daemon_request({"op": "remove_item", "path": path})

    async def install_file(
        self, source: str, destination: str, mode: int = 0o644, *, owner: str | None = None, group: str | None = None
    ) -> ExecutionResult:
        if self.use_mock:
            return ExecutionResult(returncode=0, stdout="installed", stderr="")
        if not self.socket_path.exists():
            shutil.copyfile(source, destination)
            os.chmod(destination, mode)
            return ExecutionResult(returncode=0, stdout="installed", stderr="")
        return await self._send_daemon_request(
            {
                "op": "install_file",
                "source": source,
                "destination": destination,
                "mode": mode,
                "owner": owner,
                "group": group,
            }
        )

    async def install_tree(self, source: str, destination: str, *, owner: str | None = None, group: str | None = None) -> ExecutionResult:
        if self.use_mock:
            return ExecutionResult(returncode=0, stdout="installed", stderr="")
        if not self.socket_path.exists():
            shutil.copytree(source, destination, dirs_exist_ok=True, symlinks=False)
            return ExecutionResult(returncode=0, stdout="installed", stderr="")
        return await self._send_daemon_request(
            {"op": "install_tree", "source": source, "destination": destination, "owner": owner, "group": group}
        )

    async def read_log_file(self, path: str, lines: int = 100, filter_text: str | None = None) -> ExecutionResult:
        if self.use_mock:
            return ExecutionResult(returncode=0, stdout="[system] log mock entry 1\n[system] log mock entry 2", stderr="")
        if self.socket_path.exists():
            return await self._send_daemon_request({"op": "read_log_file", "path": path, "lines": lines, "filter": filter_text})
        p = Path(path)
        if not p.exists():
            return ExecutionResult(returncode=1, stdout="", stderr="Log file not found")
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                all_lines = [l.rstrip("\r\n") for l in f]
                if filter_text:
                    q = filter_text.lower()
                    all_lines = [l for l in all_lines if q in l.lower()]
                res = all_lines[-lines:] if len(all_lines) > lines else all_lines
                return ExecutionResult(returncode=0, stdout="\n".join(res), stderr="")
        except OSError as exc:
            return ExecutionResult(returncode=1, stdout="", stderr=str(exc))

    async def clear_log_file(self, path: str) -> ExecutionResult:
        if self.use_mock:
            return ExecutionResult(returncode=0, stdout="cleared", stderr="")
        if self.socket_path.exists():
            return await self._send_daemon_request({"op": "clear_log_file", "path": path})
        p = Path(path)
        if not p.exists():
            return ExecutionResult(returncode=1, stdout="", stderr="Log file not found")
        try:
            p.write_text("", encoding="utf-8")
            return ExecutionResult(returncode=0, stdout="cleared", stderr="")
        except OSError as exc:
            return ExecutionResult(returncode=1, stdout="", stderr=str(exc))

    async def drop_caches(self) -> ExecutionResult:
        if self.use_mock:
            return ExecutionResult(returncode=0, stdout="caches dropped", stderr="")
        if self.socket_path.exists():
            return await self._send_daemon_request({"op": "drop_caches"})
        return ExecutionResult(returncode=0, stdout="caches dropped", stderr="")


def get_node_executor(node_id: str = settings.LOCAL_NODE_ID) -> NodeExecutor:
    """Factory returning LocalNodeExecutor (or future RemoteNodeExecutor by node_id)."""
    return LocalNodeExecutor(node_id=node_id)
