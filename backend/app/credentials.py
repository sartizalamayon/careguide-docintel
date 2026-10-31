"""Encryption of stored user API keys (Fernet: AES-128-CBC + HMAC-SHA256)."""

import base64
import hashlib

from cryptography.fernet import Fernet

from app.config import get_settings


def _fernet() -> Fernet:
    settings = get_settings()
    secret = settings.CREDENTIALS_SECRET or settings.API_KEY
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def hint(key: str) -> str:
    """What the UI may show: the prefix and the last 4 characters."""
    prefix = key.split("_", 1)[0] + "_" if "_" in key[:6] else ""
    return f"{prefix}…{key[-4:]}"
