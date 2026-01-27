"""User API endpoints for multi-tenant support."""

from fastapi import APIRouter, Depends

from ..auth import AuthUser, require_auth, get_optional_user
from ..database import claim_unclaimed_data_for_user, get_unclaimed_data_stats

router = APIRouter(prefix="/api/users", tags=["users"])


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
