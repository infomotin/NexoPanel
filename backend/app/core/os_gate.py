"""Strict OS and architecture runtime gatekeeper."""
from __future__ import annotations

import platform
import sys
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_OS_VERSIONS: dict[str, set[str]] = {
    "ubuntu": {"22.04", "24.04"},
    "debian": {"12"},
}

SUPPORTED_ARCHITECTURES: set[str] = {"x86_64", "amd64", "aarch64", "arm64"}


class UnsupportedOSError(RuntimeError):
    """Raised when NexoPanel is started on an unsupported OS or architecture."""


@dataclass(frozen=True)
class OSReleaseInfo:
    distro_id: str
    version_id: str
    pretty_name: str
    arch: str


def parse_os_release(path: Path = Path("/etc/os-release")) -> OSReleaseInfo:
    """Parse /etc/os-release into structured OSReleaseInfo."""
    if not path.exists():
        raise UnsupportedOSError(f"Cannot locate {path}; NexoPanel requires Ubuntu 22.04/24.04 or Debian 12.")

    data: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        data[key.strip()] = val.strip().strip('"').strip("'")

    distro_id = data.get("ID", "").lower()
    version_id = data.get("VERSION_ID", "").strip()
    pretty_name = data.get("PRETTY_NAME", f"{distro_id} {version_id}")
    arch = platform.machine().lower()

    return OSReleaseInfo(
        distro_id=distro_id,
        version_id=version_id,
        pretty_name=pretty_name,
        arch=arch,
    )


def validate_host_environment(
    os_release_path: Path = Path("/etc/os-release"),
    skip_check: bool = False,
) -> OSReleaseInfo | None:
    """Enforce exact match against supported OS IDs, VERSION_IDs, and architectures."""
    if skip_check:
        return None

    info = parse_os_release(os_release_path)

    if info.arch not in SUPPORTED_ARCHITECTURES:
        raise UnsupportedOSError(
            f"Unsupported CPU architecture '{info.arch}'. Supported: x86_64, aarch64."
        )

    supported_versions = SUPPORTED_OS_VERSIONS.get(info.distro_id)
    if not supported_versions or info.version_id not in supported_versions:
        raise UnsupportedOSError(
            f"Unsupported OS '{info.pretty_name}' (ID={info.distro_id}, VERSION_ID={info.version_id}). "
            "Supported targets: Ubuntu 22.04 LTS, Ubuntu 24.04 LTS, Debian 12 (Bookworm)."
        )

    return info


def enforce_os_gate_or_exit(skip_check: bool = False) -> OSReleaseInfo | None:
    """Validate OS at startup and abort with non-zero exit code on failure."""
    try:
        return validate_host_environment(skip_check=skip_check)
    except UnsupportedOSError as exc:
        print(f"[FATAL] NexoPanel OS Gatekeeper: {exc}", file=sys.stderr)
        raise SystemExit(78) from exc
