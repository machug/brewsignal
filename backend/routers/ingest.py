"""HTTP endpoints for hydrometer data ingestion."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services import ingest_manager
from .users import get_user_id_from_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ingest", tags=["ingest"])


@router.post("/generic")
async def ingest_generic(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_device_token: Optional[str] = Header(None, alias="X-Device-Token"),
):
    """Auto-detect payload format and ingest.

    Accepts JSON payloads from any supported device type.
    The adapter router will detect the format and parse accordingly.
    """
    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(400, f"Invalid JSON: {e}")

    reading = await ingest_manager.ingest(
        db=db,
        payload=payload,
        source_protocol="http",
        auth_token=x_device_token,
    )

    if not reading:
        raise HTTPException(400, "Unknown payload format or auth failed")

    return {
        "status": "ok",
        "device_type": reading.device_type,
        "device_id": reading.device_id,
    }


@router.post("/ispindel")
async def ingest_ispindel(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_device_token: Optional[str] = Header(None, alias="X-Device-Token"),
):
    """Receive iSpindel HTTP POST.

    iSpindel devices should configure their HTTP endpoint to POST here.
    """
    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(400, f"Invalid JSON: {e}")

    reading = await ingest_manager.ingest(
        db=db,
        payload=payload,
        source_protocol="http",
        auth_token=x_device_token,
    )

    if not reading:
        raise HTTPException(400, "Invalid iSpindel payload or auth failed")

    return {"status": "ok"}


@router.post("/gravitymon")
async def ingest_gravitymon(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_device_token: Optional[str] = Header(None, alias="X-Device-Token"),
):
    """Receive GravityMon HTTP POST."""
    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(400, f"Invalid JSON: {e}")

    reading = await ingest_manager.ingest(
        db=db,
        payload=payload,
        source_protocol="http",
        auth_token=x_device_token,
    )

    if not reading:
        raise HTTPException(400, "Invalid GravityMon payload or auth failed")

    return {"status": "ok"}


# Token-authenticated endpoints for cloud mode
# URL format: /api/ingest/{token}/gravitymon


@router.post("/{token}/gravitymon")
async def ingest_gravitymon_with_token(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Receive GravityMon HTTP POST with token authentication.

    For cloud mode, GravityMon/iSpindel can't easily set auth headers.
    Instead, the token is embedded in the URL path.
    """
    # Validate token and get user_id
    user_id = await get_user_id_from_token(token)
    if not user_id:
        raise HTTPException(401, "Invalid ingest token")

    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(400, f"Invalid JSON: {e}")

    reading = await ingest_manager.ingest(
        db=db,
        payload=payload,
        source_protocol="http",
        user_id=user_id,
    )

    if not reading:
        raise HTTPException(400, "Invalid GravityMon payload")

    return {"status": "ok"}


@router.post("/{token}/ispindel")
async def ingest_ispindel_with_token(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Receive iSpindel HTTP POST with token authentication."""
    user_id = await get_user_id_from_token(token)
    if not user_id:
        raise HTTPException(401, "Invalid ingest token")

    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(400, f"Invalid JSON: {e}")

    reading = await ingest_manager.ingest(
        db=db,
        payload=payload,
        source_protocol="http",
        user_id=user_id,
    )

    if not reading:
        raise HTTPException(400, "Invalid iSpindel payload")

    return {"status": "ok"}


@router.post("/{token}/generic")
async def ingest_generic_with_token(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Auto-detect payload format with token authentication."""
    user_id = await get_user_id_from_token(token)
    if not user_id:
        raise HTTPException(401, "Invalid ingest token")

    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(400, f"Invalid JSON: {e}")

    reading = await ingest_manager.ingest(
        db=db,
        payload=payload,
        source_protocol="http",
        user_id=user_id,
    )

    if not reading:
        raise HTTPException(400, "Unknown payload format")

    return {
        "status": "ok",
        "device_type": reading.device_type,
        "device_id": reading.device_id,
    }
