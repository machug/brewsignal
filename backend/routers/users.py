"""User API endpoints for multi-tenant support."""

import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from ..auth import AuthUser, require_auth, get_optional_user
from ..database import claim_unclaimed_data_for_user, get_unclaimed_data_stats
from ..config import settings

router = APIRouter(prefix="/api/users", tags=["users"])


# In-memory token store for local mode (persisted per-session)
# For cloud mode, tokens are stored in Supabase user metadata
_local_ingest_tokens: dict[str, str] = {}  # user_id -> token


async def get_or_create_ingest_token(user_id: str) -> str:
    """Get existing ingest token or create a new one."""
    if settings.deployment_mode == "cloud":
        # Cloud mode: use Supabase to store token in user metadata
        from ..supabase_client import get_supabase_admin

        supabase = get_supabase_admin()
        if not supabase:
            raise HTTPException(500, "Supabase not configured")

        # Get user metadata
        try:
            response = supabase.auth.admin.get_user_by_id(user_id)
            user_meta = response.user.user_metadata or {}

            if "ingest_token" in user_meta:
                return user_meta["ingest_token"]

            # Generate new token
            token = secrets.token_urlsafe(32)
            supabase.auth.admin.update_user_by_id(
                user_id,
                {"user_metadata": {**user_meta, "ingest_token": token}}
            )
            return token
        except Exception as e:
            raise HTTPException(500, f"Failed to manage ingest token: {e}")
    else:
        # Local mode: use in-memory store
        if user_id not in _local_ingest_tokens:
            _local_ingest_tokens[user_id] = secrets.token_urlsafe(32)
        return _local_ingest_tokens[user_id]


async def regenerate_ingest_token(user_id: str) -> str:
    """Generate a new ingest token, invalidating the old one."""
    token = secrets.token_urlsafe(32)

    if settings.deployment_mode == "cloud":
        from ..supabase_client import get_supabase_admin

        supabase = get_supabase_admin()
        if not supabase:
            raise HTTPException(500, "Supabase not configured")

        try:
            response = supabase.auth.admin.get_user_by_id(user_id)
            user_meta = response.user.user_metadata or {}
            supabase.auth.admin.update_user_by_id(
                user_id,
                {"user_metadata": {**user_meta, "ingest_token": token}}
            )
        except Exception as e:
            raise HTTPException(500, f"Failed to regenerate token: {e}")
    else:
        _local_ingest_tokens[user_id] = token

    return token


async def get_user_id_from_token(token: str) -> Optional[str]:
    """Look up user_id from ingest token."""
    if settings.deployment_mode == "cloud":
        from ..supabase_client import get_supabase_admin

        supabase = get_supabase_admin()
        if not supabase:
            return None

        try:
            # List users and find one with matching token
            # Note: This is inefficient for many users - consider a tokens table
            response = supabase.auth.admin.list_users()
            for user in response:
                if user.user_metadata and user.user_metadata.get("ingest_token") == token:
                    return user.id
            return None
        except Exception:
            return None
    else:
        # Local mode: reverse lookup
        for user_id, stored_token in _local_ingest_tokens.items():
            if stored_token == token:
                return user_id
        return None


@router.post("/claim-data")
async def claim_data(user: AuthUser = Depends(require_auth)):
    """Claim all unclaimed data for the current user.

    This endpoint is called when a user first logs into a local RPi installation.
    All existing data without a user_id (created before auth was enabled) gets
    assigned to the logged-in user.

    This is idempotent - calling it multiple times is safe.

    Returns:
        Dictionary with counts of claimed records per table
    """
    results = await claim_unclaimed_data_for_user(user.user_id)

    total = sum(results.values())
    return {
        "status": "success",
        "user_id": user.user_id,
        "claimed": results,
        "total_claimed": total,
        "message": f"Claimed {total} records for user {user.user_id}" if total > 0 else "No unclaimed data found"
    }


@router.get("/me")
async def get_current_user(user: AuthUser = Depends(require_auth)):
    """Get the current authenticated user's info.

    Returns:
        User info including user_id, email, and role
    """
    return {
        "user_id": user.user_id,
        "email": user.email,
        "role": user.role,
    }


@router.get("/cloud-status")
async def get_cloud_status(user: AuthUser = Depends(get_optional_user)):
    """Get cloud sync status including unclaimed data counts.

    This endpoint works for both authenticated and unauthenticated users:
    - Authenticated: returns user info + unclaimed data stats
    - Unauthenticated: returns just unclaimed data stats

    Returns:
        Dictionary with connected status, user info, and unclaimed data counts
    """
    unclaimed = await get_unclaimed_data_stats()

    if user:
        return {
            "connected": True,
            "user_id": user.user_id,
            "email": user.email,
            "unclaimed": unclaimed,
            "has_unclaimed_data": any(v > 0 for v in unclaimed.values()),
        }

    return {
        "connected": False,
        "user_id": None,
        "email": None,
        "unclaimed": unclaimed,
        "has_unclaimed_data": any(v > 0 for v in unclaimed.values()),
    }


# Note: These endpoints are under /api/users but frontend calls /api/user
# Adding a separate router for /api/user path
user_router = APIRouter(prefix="/api/user", tags=["user"])


@user_router.get("/ingest-token")
async def get_ingest_token(user: AuthUser = Depends(require_auth)):
    """Get the user's ingest token for HTTP device endpoints.

    This token is used in the URL for GravityMon/iSpindel to send data:
    - Local: http://<ip>:8080/api/ingest/gravitymon (no token needed)
    - Cloud: https://api.brewsignal.io/api/ingest/{token}/gravitymon

    Returns:
        Dictionary with the ingest token
    """
    token = await get_or_create_ingest_token(user.user_id)
    return {"token": token}


@user_router.post("/ingest-token")
async def regenerate_token_endpoint(user: AuthUser = Depends(require_auth)):
    """Regenerate the user's ingest token.

    This invalidates the old token - devices using the old URL will no longer work.

    Returns:
        Dictionary with the new ingest token
    """
    token = await regenerate_ingest_token(user.user_id)
    return {"token": token}
