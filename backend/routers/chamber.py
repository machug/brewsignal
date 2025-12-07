"""Chamber temperature/humidity API endpoints."""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db, async_session_factory
from ..models import ChamberReading, ChamberReadingResponse, serialize_datetime_to_utc
from ..services.ha_client import get_ha_client
from .config import get_config_value

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chamber", tags=["chamber"])


@router.get("/current")
async def get_current_chamber():
    """Get current chamber temperature and humidity from HA."""
    async with async_session_factory() as db:
        ha_enabled = await get_config_value(db, "ha_enabled")
        if not ha_enabled:
            return {"error": "Home Assistant not enabled", "temperature": None, "humidity": None}

        ha_client = get_ha_client()
        if not ha_client:
            return {"error": "Home Assistant client not initialized", "temperature": None, "humidity": None}

        temp_entity = await get_config_value(db, "ha_chamber_temp_entity_id")
        humidity_entity = await get_config_value(db, "ha_chamber_humidity_entity_id")

        temperature = None
        humidity = None

        if temp_entity:
            state = await ha_client.get_state(temp_entity)
            if state and state.get("state") not in ("unavailable", "unknown"):
                try:
                    temperature = float(state["state"])
                except (ValueError, TypeError):
                    pass

        if humidity_entity:
            state = await ha_client.get_state(humidity_entity)
            if state and state.get("state") not in ("unavailable", "unknown"):
                try:
                    humidity = float(state["state"])
                except (ValueError, TypeError):
                    pass

        return {
            "temperature": temperature,
            "humidity": humidity,
            "timestamp": serialize_datetime_to_utc(datetime.now(timezone.utc))
        }


@router.get("/history", response_model=list[ChamberReadingResponse])
async def get_chamber_history(
    hours: int = Query(default=24, ge=1, le=720),
    db: AsyncSession = Depends(get_db)
):
    """Get historical chamber readings."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    result = await db.execute(
        select(ChamberReading)
        .where(ChamberReading.timestamp >= since)
        .order_by(desc(ChamberReading.timestamp))
        .limit(2000)
    )

    return result.scalars().all()
