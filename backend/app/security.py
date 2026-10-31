"""API key authentication (SPEC §10, §12)."""

import hmac

from fastapi import Header

from app.config import get_settings
from app.errors import ApiError


def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    """FastAPI dependency. Constant-time comparison; 401 when the key is missing or wrong."""
    expected = get_settings().API_KEY.encode()
    if x_api_key is None or not hmac.compare_digest(x_api_key.encode(), expected):
        raise ApiError(401, "UNAUTHORIZED", "Missing or invalid API key.")
