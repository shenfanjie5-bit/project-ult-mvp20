from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from reasoner_runtime.providers.auth import (
    CodexAuthError,
    CodexCliAuthSource,
    CodexCredentials,
    parse_account_id_from_jwt,
    parse_codex_auth_file,
)


_ACCOUNT_ID = "cbd0eb9f-1165-4e41-a20e-61b165b3bf13"


def _b64url(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).rstrip(b"=")
    return encoded.decode("ascii")


def _make_jwt(*, account_id: str = _ACCOUNT_ID, exp: int) -> str:
    header = _b64url({"alg": "RS256", "typ": "JWT"})
    payload = _b64url(
        {
            "exp": exp,
            "https://api.openai.com/auth": {
                "chatgpt_account_id": account_id,
                "chatgpt_plan_type": "pro",
            },
        }
    )
    return f"{header}.{payload}.signature"


def _auth_file_payload(*, exp: int) -> dict[str, Any]:
    return {
        "auth_mode": "chatgpt",
        "last_refresh": "2026-04-18T18:21:18Z",
        "OPENAI_API_KEY": None,
        "tokens": {
            "access_token": _make_jwt(exp=exp),
            "refresh_token": "rt_initial",
            "account_id": _ACCOUNT_ID,
            "id_token": "id_initial",
        },
    }


def test_parse_account_id_from_jwt_extracts_chatgpt_account_id() -> None:
    token = _make_jwt(exp=int((datetime.now(UTC) + timedelta(days=1)).timestamp()))

    assert parse_account_id_from_jwt(token) == _ACCOUNT_ID


def test_parse_account_id_from_jwt_rejects_missing_claim() -> None:
    header = _b64url({"alg": "RS256", "typ": "JWT"})
    payload = _b64url({"exp": 1, "other": {}})
    token = f"{header}.{payload}.sig"

    with pytest.raises(CodexAuthError):
        parse_account_id_from_jwt(token)


def test_parse_codex_auth_file_builds_credentials() -> None:
    exp = int((datetime.now(UTC) + timedelta(hours=2)).timestamp())
    raw = _auth_file_payload(exp=exp)

    creds = parse_codex_auth_file(raw)

    assert creds.access_token == raw["tokens"]["access_token"]
    assert creds.refresh_token == "rt_initial"
    assert creds.account_id == _ACCOUNT_ID
    assert int(creds.expires_at.timestamp()) == exp


def test_codex_credentials_expired_with_skew() -> None:
    now = datetime.now(UTC)
    creds = CodexCredentials(
        access_token=_make_jwt(exp=int((now + timedelta(seconds=30)).timestamp())),
        refresh_token="rt",
        account_id=_ACCOUNT_ID,
        expires_at=now + timedelta(seconds=30),
    )

    assert creds.expired(skew_seconds=60, now=now) is True
    assert creds.expired(skew_seconds=10, now=now) is False


def test_codex_cli_auth_source_returns_unexpired_creds(tmp_path: Path) -> None:
    auth_path = tmp_path / "auth.json"
    exp = int((datetime.now(UTC) + timedelta(hours=2)).timestamp())
    auth_path.write_text(json.dumps(_auth_file_payload(exp=exp)))

    source = CodexCliAuthSource(path=auth_path)

    creds = source.fetch()

    assert creds.account_id == _ACCOUNT_ID
    assert creds.expired() is False


def test_codex_cli_auth_source_raises_on_expired_token(tmp_path: Path) -> None:
    auth_path = tmp_path / "auth.json"
    expired_payload = _auth_file_payload(
        exp=int((datetime.now(UTC) - timedelta(minutes=5)).timestamp())
    )
    auth_path.write_text(json.dumps(expired_payload))

    source = CodexCliAuthSource(path=auth_path)

    with pytest.raises(CodexAuthError, match="codex login"):
        source.fetch()


def test_codex_cli_auth_source_does_not_mutate_auth_file(tmp_path: Path) -> None:
    auth_path = tmp_path / "auth.json"
    exp = int((datetime.now(UTC) + timedelta(hours=2)).timestamp())
    payload_before = _auth_file_payload(exp=exp)
    auth_path.write_text(json.dumps(payload_before))

    source = CodexCliAuthSource(path=auth_path)
    source.fetch()

    payload_after = json.loads(auth_path.read_text())
    assert payload_after == payload_before


def test_codex_cli_auth_source_missing_file_raises_with_actionable_hint(tmp_path: Path) -> None:
    source = CodexCliAuthSource(path=tmp_path / "absent.json")

    with pytest.raises(CodexAuthError, match="codex login"):
        source.fetch()
