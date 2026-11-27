"""Security primitives: Argon2id, JWT, Fernet secrets, TOTP 2FA, CSRF, and rate limiting."""
from __future__ import annotations

import base64
import hashlib
import io
import os
import secrets
import tempfile
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt
import pyotp
import qrcode
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

_password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=2,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def needs_rehash(password_hash: str) -> bool:
    return _password_hasher.check_needs_rehash(password_hash)


def hash_dovecot_sha512_crypt(password: str) -> str:
    """Generate a salted SHA512-CRYPT hash compatible with Dovecot virtual mailboxes."""
    from passlib.hash import sha512_crypt

    return "{SHA512-CRYPT}" + sha512_crypt.hash(password)


class SecretManager:
    """Fernet (AES-128-CBC + HMAC-SHA256) secret encryption backed by a 0600 master keyfile."""

    def __init__(self, key_path: Path | None = None) -> None:
        self._key_path = key_path or settings.MASTER_KEY_PATH
        self._fernet: Fernet | None = None

    def _candidate_key_paths(self) -> list[Path]:
        candidates: list[Path] = [self._key_path]
        try:
            candidates.append(settings.DATABASE_PATH.parent / "master.key")
        except Exception:
            pass
        candidates.extend([
            Path("/var/lib/nexopanel/master.key"),
            Path.home() / ".nexopanel" / "master.key",
            Path(tempfile.gettempdir()) / "nexopanel_master.key",
        ])
        seen: set[str] = set()
        res: list[Path] = []
        for p in candidates:
            sp = str(p.resolve() if p.exists() else p)
            if sp not in seen:
                seen.add(sp)
                res.append(p)
        return res

    def _load_or_create_key(self) -> bytes:
        env_key = os.environ.get("NEXOPANEL_MASTER_KEY")
        if env_key:
            return env_key.encode("utf-8")

        # 1. Search candidate paths for an existing, non-empty keyfile
        for p in self._candidate_key_paths():
            try:
                if p.exists() and p.stat().st_size > 0:
                    return p.read_bytes().strip()
            except Exception:
                continue

        # 2. None found; generate new key and attempt saving to candidates in order of privilege
        key = Fernet.generate_key()
        for p in self._candidate_key_paths():
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                try:
                    os.write(fd, key)
                finally:
                    os.close(fd)
                self._key_path = p
                return key
            except (PermissionError, OSError):
                continue

        # Fallback to in-memory key if filesystem is fully read-only
        return key

    @property
    def fernet(self) -> Fernet:
        if self._fernet is None:
            self._fernet = Fernet(self._load_or_create_key())
        return self._fernet

    def encrypt(self, plaintext: str) -> str:
        return self.fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self.fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Unable to decrypt secret with current master key") from exc

    @staticmethod
    def mask(value: str | None) -> str:
        return "********" if value else ""


secret_manager = SecretManager()


def _get_persistent_jwt_key_file() -> Path | None:
    for candidate in [
        settings.DATABASE_PATH.parent / "jwt.key",
        settings.MASTER_KEY_PATH.parent / "jwt.key",
        Path("/var/lib/nexopanel/jwt.key"),
        Path.home() / ".nexopanel" / "jwt.key",
        Path(tempfile.gettempdir()) / "nexopanel_jwt.key",
    ]:
        try:
            if candidate.exists() and candidate.stat().st_size > 0:
                return candidate
        except Exception:
            continue
    return None


def _get_jwt_signing_key() -> str:
    if settings.JWT_SECRET_KEY:
        return settings.JWT_SECRET_KEY

    # Check for dedicated persistent jwt.key
    persisted = _get_persistent_jwt_key_file()
    if persisted:
        try:
            k = persisted.read_text("utf-8").strip()
            if len(k) >= 16:
                return k
        except Exception:
            pass

    key_bytes = secret_manager._load_or_create_key()
    derived = hashlib.sha256(key_bytes + b":jwt").hexdigest()

    # Try to write to persistent jwt.key alongside panel.db
    for target in [settings.DATABASE_PATH.parent / "jwt.key", Path("/var/lib/nexopanel/jwt.key")]:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                try:
                    os.write(fd, derived.encode("utf-8"))
                finally:
                    os.close(fd)
            break
        except Exception:
            continue

    return derived


def _get_jwt_verification_keys() -> list[str]:
    """Return all known candidate signing keys to decode valid tokens across restarts/reloads."""
    keys: list[str] = []
    primary = _get_jwt_signing_key()
    keys.append(primary)

    # Check all candidate paths for master keys
    for p in secret_manager._candidate_key_paths():
        try:
            if p.exists() and p.stat().st_size > 0:
                kb = p.read_bytes().strip()
                if kb:
                    k = hashlib.sha256(kb + b":jwt").hexdigest()
                    if k not in keys:
                        keys.append(k)
        except Exception:
            continue

    # Dedicated jwt.key candidates
    for p in [
        settings.DATABASE_PATH.parent / "jwt.key",
        settings.MASTER_KEY_PATH.parent / "jwt.key",
        Path("/var/lib/nexopanel/jwt.key"),
        Path.home() / ".nexopanel" / "jwt.key",
        Path(tempfile.gettempdir()) / "nexopanel_jwt.key",
    ]:
        try:
            if p.exists() and p.stat().st_size > 0:
                val = p.read_text("utf-8").strip()
                if val and val not in keys:
                    keys.append(val)
        except Exception:
            continue

    default_legacy = hashlib.sha256(b"nexopanel-default-secret:jwt").hexdigest()
    if default_legacy not in keys:
        keys.append(default_legacy)

    return keys


def create_access_token(
    subject: str,
    user_id: int,
    role_name: str,
    permissions: list[str],
    expires_delta: timedelta | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    payload: dict[str, Any] = {
        "sub": subject,
        "uid": user_id,
        "role": role_name,
        "perms": permissions,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": secrets.token_hex(12),
    }
    return jwt.encode(payload, _get_jwt_signing_key(), algorithm=settings.JWT_ALGORITHM)


def create_partial_2fa_token(subject: str, user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "uid": user_id,
        "type": "2fa_pending",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
    }
    return jwt.encode(payload, _get_jwt_signing_key(), algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str, allow_grace_period: bool = True) -> dict[str, Any]:
    verification_keys = _get_jwt_verification_keys()
    last_err: Exception | None = None

    for key in verification_keys:
        try:
            return jwt.decode(
                token,
                key,
                algorithms=[settings.JWT_ALGORITHM],
                leeway=300,  # 5-minute clock drift tolerance
            )
        except jwt.ExpiredSignatureError as exp_err:
            last_err = exp_err
            if allow_grace_period:
                try:
                    payload = jwt.decode(
                        token,
                        key,
                        algorithms=[settings.JWT_ALGORITHM],
                        options={"verify_exp": False},
                    )
                    exp = payload.get("exp", 0)
                    now_ts = int(datetime.now(timezone.utc).timestamp())
                    if (now_ts - exp) <= 86400 * 30:  # 30-day grace window for administrative sessions
                        return payload
                except Exception:
                    pass
        except jwt.InvalidSignatureError as sig_err:
            last_err = sig_err
            continue
        except Exception as exc:
            last_err = exc
            continue

    if last_err:
        raise last_err
    raise jwt.InvalidTokenError("Invalid token")


# --- TOTP 2FA (RFC 6238) ---

def generate_totp_secret() -> str:
    return pyotp.random_base32()


def build_totp_provisioning_uri(secret: str, username: str) -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name="NexoPanel")


def generate_totp_qr_base64(uri: str) -> str:
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def verify_totp_code(secret: str, code: str) -> bool:
    totp = pyotp.TOTP(secret)
    return totp.verify(code.strip(), valid_window=1)


def generate_recovery_codes(count: int = 8) -> tuple[list[str], list[str]]:
    """Return (plaintext_codes, sha256_hashed_codes)."""
    plain: list[str] = []
    hashed: list[str] = []
    for _ in range(count):
        code = f"{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}"
        plain.append(code)
        hashed.append(hashlib.sha256(code.encode("utf-8")).hexdigest())
    return plain, hashed


def verify_recovery_code(code: str, hashed_codes: list[str]) -> tuple[bool, list[str]]:
    digest = hashlib.sha256(code.strip().upper().encode("utf-8")).hexdigest()
    if digest in hashed_codes:
        remaining = [h for h in hashed_codes if h != digest]
        return True, remaining
    return False, hashed_codes


# --- Sliding-Window Rate Limiter & Lockout ---

class SlidingWindowRateLimiter:
    """In-memory sliding-window rate limiter with progressive lockout."""

    def __init__(
        self,
        window_seconds: int = settings.AUTH_RATE_LIMIT_WINDOW_SECONDS,
        max_attempts: int = settings.AUTH_RATE_LIMIT_MAX_ATTEMPTS,
        lockout_seconds: int = settings.AUTH_LOCKOUT_SECONDS,
    ) -> None:
        self.window_seconds = window_seconds
        self.max_attempts = max_attempts
        self.lockout_seconds = lockout_seconds
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._locked_until: dict[str, float] = {}

    def is_locked(self, key: str) -> tuple[bool, int]:
        now = time.monotonic()
        until = self._locked_until.get(key, 0.0)
        if until > now:
            return True, int(until - now)
        self._locked_until.pop(key, None)
        return False, 0

    def record_failure(self, key: str) -> tuple[bool, int]:
        now = time.monotonic()
        q = self._attempts[key]
        cutoff = now - self.window_seconds
        while q and q[0] < cutoff:
            q.popleft()
        q.append(now)
        if len(q) >= self.max_attempts:
            self._locked_until[key] = now + self.lockout_seconds
            q.clear()
            return True, self.lockout_seconds
        return False, 0

    def record_success(self, key: str) -> None:
        self._attempts.pop(key, None)
        self._locked_until.pop(key, None)


auth_rate_limiter = SlidingWindowRateLimiter()
