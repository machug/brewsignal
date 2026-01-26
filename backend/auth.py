"""
Supabase JWT Authentication for BrewSignal API

Validates JWT tokens from Supabase Auth and extracts user information.
Only active in cloud mode.
"""

import logging
from typing import Optional
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import PyJWKClient
from functools import lru_cache

from .config import Settings

logger = logging.getLogger(__name__)

# Security scheme
security = HTTPBearer(auto_error=False)


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()


@lru_cache()
def get_jwt_secret() -> Optional[str]:
    """Get JWT secret for verifying Supabase JWTs.

    Supabase uses HS256 with the JWT secret, not RS256 with JWKS.
    The secret is derived from the project's JWT secret in settings.
    """
    settings = get_settings()
    if not settings.is_cloud or not settings.supabase_anon_key:
        return None

    # Supabase JWT secret - for verification, we use the anon key's secret
    # The actual secret is in SUPABASE_JWT_SECRET env var if set,
    # otherwise we can extract from service role key or use anon key
    import os
    jwt_secret = os.environ.get("SUPABASE_JWT_SECRET")
    if jwt_secret:
        return jwt_secret

    # Fallback: if no explicit secret, auth won't work properly
    logger.warning("SUPABASE_JWT_SECRET not set - JWT verification may fail")
    return None


class AuthUser:
    """Authenticated user from Supabase JWT."""

    def __init__(self, user_id: str, email: Optional[str] = None, role: str = "authenticated"):
        self.user_id = user_id
        self.email = email
        self.role = role

    def __repr__(self):
        return f"AuthUser(user_id={self.user_id}, email={self.email})"


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[AuthUser]:
    """
    Extract and validate the current user from the JWT token.

    In local mode, returns None (no auth required).
    In cloud mode, validates the Supabase JWT and returns the user.
    """
    settings = get_settings()

    # In local mode, no auth required
    if not settings.is_cloud:
        return None

    # In cloud mode, require valid JWT
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    token = credentials.credentials
    jwt_secret = get_jwt_secret()

    if not jwt_secret:
        raise HTTPException(status_code=500, detail="Auth not configured - SUPABASE_JWT_SECRET required")

    try:
        # Decode and verify the token using HS256
        payload = jwt.decode(
            token,
            jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
            options={"verify_exp": True},
        )

        user_id = payload.get("sub")
        email = payload.get("email")
        role = payload.get("role", "authenticated")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: no user ID")

        return AuthUser(user_id=user_id, email=email, role=role)

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        logger.error(f"Auth error: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")


async def get_optional_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[AuthUser]:
    """
    Extract user if present, but don't require authentication.

    Useful for routes that work with or without auth.
    """
    settings = get_settings()

    # In local mode, no auth
    if not settings.is_cloud:
        return None

    # If no credentials, that's fine
    if not credentials:
        return None

    # Try to validate, but don't fail if invalid
    try:
        return await get_current_user(request, credentials)
    except HTTPException:
        return None


def require_auth(user: Optional[AuthUser] = Depends(get_current_user)) -> AuthUser:
    """
    Dependency that requires authentication in cloud mode.

    Usage:
        @router.get("/protected")
        async def protected_route(user: AuthUser = Depends(require_auth)):
            return {"user_id": user.user_id}
    """
    settings = get_settings()

    # In local mode, create a dummy user
    if not settings.is_cloud:
        return AuthUser(user_id="local", email=None, role="local")

    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    return user
