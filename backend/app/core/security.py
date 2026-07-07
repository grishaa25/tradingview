"""Supabase Auth JWT verification.

The frontend authenticates with Supabase directly; requests to this API carry
the Supabase access token as `Authorization: Bearer <jwt>`. We verify it with
the project's JWT secret (Settings -> API -> JWT Secret) — no auth tables or
password handling live in this backend.
"""

from jose import JWTError, jwt

from app.core.config import get_settings


class AuthError(Exception):
    pass


def verify_supabase_jwt(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except JWTError as exc:
        raise AuthError(str(exc)) from exc
