"""Encryption helpers for credentials stored at rest.

Uses Fernet (AES-128-CBC + HMAC-SHA256) from the ``cryptography`` package.
A single master key is persisted to ``data/key.bin`` on first run. Every
sensitive field (password, .ROBLOSECURITY cookie) is encrypted individually
before being written to SQLite.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from .config import KEY_PATH, ensure_data_dir


def _load_or_create_key() -> bytes:
    """Return the master key, creating it on first use."""
    ensure_data_dir()
    if KEY_PATH.exists():
        return KEY_PATH.read_bytes()
    key = Fernet.generate_key()
    KEY_PATH.write_bytes(key)
    # Restrict key file to the owner only (0o600).
    os.chmod(KEY_PATH, 0o600)
    return key


_cipher = Fernet(_load_or_create_key())


def encrypt(value: str | None) -> str | None:
    """Encrypt a string. Returns None for None/empty input."""
    if value is None or value == "":
        return value
    token = _cipher.encrypt(value.encode("utf-8"))
    return token.decode("utf-8")


def decrypt(token: str | None) -> str | None:
    """Decrypt a Fernet token string. Returns None for None/empty input."""
    if token is None or token == "":
        return token
    try:
        return _cipher.decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        # Corrupted or key-rotated data - surface as None rather than crashing.
        return None


def reencrypt(token: str | None) -> str | None:
    """Decrypt then re-encrypt with the current key (key rotation helper)."""
    if token is None or token == "":
        return token
    plain = decrypt(token)
    return encrypt(plain) if plain is not None else None


def is_encrypted(value: str | None) -> bool:
    """Heuristic: looks like a base64 Fernet token."""
    if not value:
        return False
    try:
        base64.urlsafe_b64decode(value + "==")
        return True
    except Exception:
        return False
