"""API key authentication (SPEC §10, §12)."""

import hmac

from fastapi import Depends, Header

from app.config import get_settings
from app.errors import ApiError


def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    """FastAPI dependency. Constant-time comparison; 401 when the key is missing or wrong."""
    expected = get_settings().API_KEY.encode()
    if x_api_key is None or not hmac.compare_digest(x_api_key.encode(), expected):
        raise ApiError(401, "UNAUTHORIZED", "Missing or invalid API key.")


def current_user(x_user_email: str | None = Header(default=None, alias="X-User-Email")) -> str | None:
    """The signed-in user's email, set by the web app's server-side proxy after Google sign-in.

    The browser never talks to the API directly (the proxy holds X-API-Key), so this header can be trusted
    on requests that also passed require_api_key.
    """
    email = (x_user_email or "").strip().lower()
    return email if "@" in email else None


def require_user(email: str | None = Depends(current_user)) -> str:
    if email is None:
        raise ApiError(401, "SIGN_IN_REQUIRED", "Sign in with Google to manage your API key.")
    return email
