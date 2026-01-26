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
    """Get JWT secret for HS256 verification."""
    import os
    return os.environ.get("SUPABASE_JWT_SECRET")


@lru_cache()
def get_jwk_client() -> Optional[PyJWKClient]:
    """Get JWK client for RS256 verification."""
    settings = get_settings()
    if not settings.is_cloud or not settings.supabase_url:
        return None

    jwks_url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
    return PyJWKClient(jwks_url, cache_keys=True)


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

    try:
        # Decode header to check algorithm
        unverified_header = jwt.get_unverified_header(token)
        alg = unverified_header.get("alg", "HS256")
        logger.info(f"JWT algorithm: {alg}")

        if alg == "RS256":
            # Use JWKS for RS256
            jwk_client = get_jwk_client()
            if not jwk_client:
                raise HTTPException(status_code=500, detail="Auth not configured - SUPABASE_URL required")
            signing_key = jwk_client.get_signing_key_from_jwt(token)
            key = signing_key.key
            algorithms = ["RS256"]
        else:
            # Use JWT secret for HS256
            jwt_secret = get_jwt_secret()
            if not jwt_secret:
                raise HTTPException(status_code=500, detail="Auth not configured - SUPABASE_JWT_SECRET required")
            key = jwt_secret
            algorithms = ["HS256"]

        # Decode and verify the token
        payload = jwt.decode(
            token,
            key,
            algorithms=algorithms,
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
