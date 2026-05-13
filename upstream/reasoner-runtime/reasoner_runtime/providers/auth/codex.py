from __future__ import annotations

import base64
import contextlib
import errno
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

_JWT_AUTH_CLAIM = "https://api.openai.com/auth"
_DEFAULT_AUTH_PATH = Path.home() / ".codex" / "auth.json"


class CodexAuthError(RuntimeError):
    """Raised when codex OAuth credentials cannot be loaded."""


class CodexCredentials(BaseModel):
    access_token: str = Field(min_length=1)
    refresh_token: str = Field(min_length=1)
    account_id: str = Field(min_length=1)
    expires_at: datetime
    id_token: str | None = None

    def expired(self, *, skew_seconds: int = 60, now: datetime | None = None) -> bool:
        reference = now if now is not None else datetime.now(UTC)
        return self.expires_at - timedelta(seconds=skew_seconds) <= reference


@runtime_checkable
class CodexAuthSource(Protocol):
    def fetch(self) -> CodexCredentials: ...


def parse_account_id_from_jwt(access_token: str) -> str:
    payload = _decode_jwt_payload(access_token)
    auth_claim = payload.get(_JWT_AUTH_CLAIM)
    if not isinstance(auth_claim, dict):
        raise CodexAuthError(
            "access_token is missing the chatgpt account claim"
            f" '{_JWT_AUTH_CLAIM}'"
        )
    account_id = auth_claim.get("chatgpt_account_id")
    if not isinstance(account_id, str) or not account_id:
        raise CodexAuthError("chatgpt_account_id claim is empty")
    return account_id


def _decode_jwt_payload(access_token: str) -> dict[str, Any]:
    parts = access_token.split(".")
    if len(parts) < 2:
        raise CodexAuthError("access_token is not a JWT")
    payload_segment = parts[1]
    padding = "=" * (-len(payload_segment) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload_segment + padding)
    except (ValueError, base64.binascii.Error) as error:
        raise CodexAuthError(f"failed to base64-decode JWT payload: {error}") from error
    try:
        return json.loads(decoded)
    except json.JSONDecodeError as error:
        raise CodexAuthError(f"failed to parse JWT payload JSON: {error}") from error


def _expires_at_from_access_token(access_token: str) -> datetime:
    payload = _decode_jwt_payload(access_token)
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)):
        raise CodexAuthError("access_token JWT is missing the 'exp' claim")
    return datetime.fromtimestamp(int(exp), tz=UTC)


def parse_codex_auth_file(raw: dict[str, Any]) -> CodexCredentials:
    tokens = raw.get("tokens")
    if not isinstance(tokens, dict):
        raise CodexAuthError("codex auth file is missing the 'tokens' object")

    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    if not isinstance(access_token, str) or not access_token:
        raise CodexAuthError("codex auth file is missing 'tokens.access_token'")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise CodexAuthError("codex auth file is missing 'tokens.refresh_token'")

    account_id_raw = tokens.get("account_id")
    account_id = (
        account_id_raw
        if isinstance(account_id_raw, str) and account_id_raw
        else parse_account_id_from_jwt(access_token)
    )

    id_token_raw = tokens.get("id_token")
    id_token = id_token_raw if isinstance(id_token_raw, str) and id_token_raw else None

    expires_at = _expires_at_from_access_token(access_token)

    return CodexCredentials(
        access_token=access_token,
        refresh_token=refresh_token,
        account_id=account_id,
        expires_at=expires_at,
        id_token=id_token,
    )


def load_codex_credentials(path: Path) -> CodexCredentials:
    try:
        with _open_shared(path) as handle:
            raw = json.load(handle)
    except FileNotFoundError as error:
        raise CodexAuthError(
            f"codex auth file not found at {path} — run `codex login` first"
        ) from error
    except json.JSONDecodeError as error:
        raise CodexAuthError(f"codex auth file at {path} is not valid JSON: {error}") from error
    if not isinstance(raw, dict):
        raise CodexAuthError(f"codex auth file at {path} is not a JSON object")
    return parse_codex_auth_file(raw)


@contextlib.contextmanager
def _open_shared(path: Path):
    handle = open(path, "r", encoding="utf-8")
    try:
        _flock(handle, exclusive=False)
        yield handle
    finally:
        _flock_unlock(handle)
        handle.close()


def _flock(handle: Any, *, exclusive: bool) -> None:
    try:
        import fcntl
    except ImportError:
        return
    op = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
    try:
        fcntl.flock(handle.fileno(), op)
    except OSError as error:
        if error.errno not in {errno.ENOTSUP, errno.EINVAL}:
            raise


def _flock_unlock(handle: Any) -> None:
    try:
        import fcntl
    except ImportError:
        return
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


@dataclass(frozen=True)
class CodexCliAuthSource:
    path: Path = field(default_factory=lambda: _DEFAULT_AUTH_PATH)

    def fetch(self) -> CodexCredentials:
        creds = load_codex_credentials(self.path)
        if creds.expired():
            raise CodexAuthError(
                f"codex token expired at {creds.expires_at.isoformat()} "
                "— run `codex login` to refresh"
            )
        return creds
