from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status

from app.core.config import settings

PASSWORD_ALGORITHM = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 390000


def hash_password(password: str) -> str:
    salt = secrets.token_urlsafe(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_ITERATIONS,
    )
    return f"{PASSWORD_ALGORITHM}${PASSWORD_ITERATIONS}${salt}${base64.urlsafe_b64encode(digest).decode('ascii')}"


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        algorithm, iterations, salt, expected = password_hash.split("$", 3)
        if algorithm != PASSWORD_ALGORITHM:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        )
        actual = base64.urlsafe_b64encode(digest).decode("ascii")
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError):
        return False


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    expires_at = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload = {
        "sub": subject,
        "exp": int(expires_at.timestamp()),
        "typ": "access",
    }
    return _encode_jwt(payload)


def decode_access_token(token: str) -> dict[str, Any]:
    payload = _decode_jwt(token)
    if payload.get("typ") != "access":
        raise _credentials_error()
    expires_at = payload.get("exp")
    if not isinstance(expires_at, int) or expires_at < int(datetime.now(UTC).timestamp()):
        raise _credentials_error("Token süresi doldu.")
    return payload


def _encode_jwt(payload: dict[str, Any]) -> str:
    header = {"alg": settings.jwt_algorithm, "typ": "JWT"}
    if settings.jwt_algorithm != "HS256":
        raise ValueError("Only HS256 JWT signing is supported by the MVP auth helper.")
    signing_input = ".".join(
        [
            _base64url_json(header),
            _base64url_json(payload),
        ]
    )
    signature = _sign(signing_input)
    return f"{signing_input}.{signature}"


def _decode_jwt(token: str) -> dict[str, Any]:
    try:
        header_segment, payload_segment, signature = token.split(".", 2)
    except ValueError:
        raise _credentials_error() from None

    signing_input = f"{header_segment}.{payload_segment}"
    if not hmac.compare_digest(signature, _sign(signing_input)):
        raise _credentials_error()

    try:
        header = _base64url_decode_json(header_segment)
        payload = _base64url_decode_json(payload_segment)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        raise _credentials_error() from None

    if header.get("alg") != settings.jwt_algorithm or header.get("typ") != "JWT":
        raise _credentials_error()
    return payload


def _sign(signing_input: str) -> str:
    digest = hmac.new(
        settings.jwt_secret_key.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return _base64url_encode(digest)


def _base64url_json(value: dict[str, Any]) -> str:
    return _base64url_encode(json.dumps(value, separators=(",", ":")).encode("utf-8"))


def _base64url_decode_json(value: str) -> dict[str, Any]:
    padded = value + "=" * (-len(value) % 4)
    decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
    parsed = json.loads(decoded.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("JWT segment must be a JSON object.")
    return parsed


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _credentials_error(detail: str = "Geçersiz veya eksik kimlik bilgisi.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )
