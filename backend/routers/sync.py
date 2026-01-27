"""Cloud sync API endpoints.

Syncs local data to Supabase cloud storage for backup and multi-device access.
Uses the user's JWT token to authenticate with Supabase REST API.
"""

import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..auth import AuthUser, require_auth
from ..config import get_settings
from ..database import async_session_factory
from ..models import Batch, Device, Recipe

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sync", tags=["sync"])

# Security scheme to get raw token
security = HTTPBearer(auto_error=False)


async def get_auth_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[str]:
    """Extract raw JWT token from request."""
    if credentials:
        return credentials.credentials
    return None


@router.post("/push")
async def push_to_cloud(
    user: AuthUser = Depends(require_auth),
    token: Optional[str] = Depends(get_auth_token),
):
    """Push local data to Supabase cloud.

    Syncs the user's claimed data (recipes, batches, devices) to Supabase.
    Uses upsert logic based on local IDs to handle repeated syncs safely.

    Returns:
        Dictionary with sync results (counts per table, errors)
    """
    settings = get_settings()

    # Require Supabase configuration
    if not settings.supabase_url:
        raise HTTPException(
            status_code=500,
            detail="Supabase not configured - set SUPABASE_URL"
        )

    # Require authentication token for cloud API calls
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Authentication token required for cloud sync"
        )

    # Build Supabase REST API base URL
    supabase_rest_url = f"{settings.supabase_url}/rest/v1"

    results = {
        "recipes": {"synced": 0, "errors": []},
        "batches": {"synced": 0, "errors": []},
        "devices": {"synced": 0, "errors": []},
    }

    async with httpx.AsyncClient() as client:
        headers = {
            "Authorization": f"Bearer {token}",
            "apikey": settings.supabase_anon_key or "",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",  # Upsert mode
        }

        async with async_session_factory() as session:
            # Sync devices first (no dependencies)
            devices = await _fetch_user_devices(session, user.user_id)
            for device in devices:
                try:
                    await _sync_device(client, supabase_rest_url, headers, device, user.user_id)
                    results["devices"]["synced"] += 1
                except Exception as e:
                    logger.error(f"Failed to sync device {device.id}: {e}")
                    results["devices"]["errors"].append({"id": device.id, "error": str(e)})

            # Sync recipes (no dependencies on batches)
            recipes = await _fetch_user_recipes(session, user.user_id)
            for recipe in recipes:
                try:
                    await _sync_recipe(client, supabase_rest_url, headers, recipe, user.user_id)
                    results["recipes"]["synced"] += 1
                except Exception as e:
                    logger.error(f"Failed to sync recipe {recipe.id}: {e}")
                    results["recipes"]["errors"].append({"id": recipe.id, "error": str(e)})

            # Sync batches (depends on recipes and devices)
            batches = await _fetch_user_batches(session, user.user_id)
            for batch in batches:
                try:
                    await _sync_batch(client, supabase_rest_url, headers, batch, user.user_id)
                    results["batches"]["synced"] += 1
                except Exception as e:
                    logger.error(f"Failed to sync batch {batch.id}: {e}")
                    results["batches"]["errors"].append({"id": batch.id, "error": str(e)})

    total_synced = sum(r["synced"] for r in results.values())
    total_errors = sum(len(r["errors"]) for r in results.values())

    return {
        "status": "success" if total_errors == 0 else "partial",
        "user_id": user.user_id,
        "results": results,
        "total_synced": total_synced,
        "total_errors": total_errors,
    }


async def _fetch_user_devices(session, user_id: str) -> list[Device]:
    """Fetch all devices owned by user."""
    from sqlalchemy import or_
    settings = get_settings()

    # In local mode, include "local" user devices and unclaimed
    if settings.is_local:
        condition = or_(
            Device.user_id == user_id,
            Device.user_id == "local",
            Device.user_id.is_(None),
        )
    else:
        condition = Device.user_id == user_id

    result = await session.execute(
        select(Device).where(condition)
    )
    return list(result.scalars().all())


async def _fetch_user_recipes(session, user_id: str) -> list[Recipe]:
    """Fetch all recipes owned by user with nested relationships."""
    from sqlalchemy import or_
    settings = get_settings()

    if settings.is_local:
        condition = or_(
            Recipe.user_id == user_id,
            Recipe.user_id == "local",
            Recipe.user_id.is_(None),
        )
    else:
        condition = Recipe.user_id == user_id

    result = await session.execute(
        select(Recipe)
        .where(condition)
        .options(
            selectinload(Recipe.fermentables),
            selectinload(Recipe.hops),
            selectinload(Recipe.cultures),
            selectinload(Recipe.miscs),
            selectinload(Recipe.mash_steps),
            selectinload(Recipe.fermentation_steps),
        )
    )
    return list(result.scalars().all())


async def _fetch_user_batches(session, user_id: str) -> list[Batch]:
    """Fetch all batches owned by user."""
    from sqlalchemy import or_
    settings = get_settings()

    if settings.is_local:
        condition = or_(
            Batch.user_id == user_id,
            Batch.user_id == "local",
            Batch.user_id.is_(None),
        )
    else:
        condition = Batch.user_id == user_id

    result = await session.execute(
        select(Batch)
        .where(condition)
        .where(Batch.deleted_at.is_(None))  # Exclude soft-deleted
    )
    return list(result.scalars().all())


async def _sync_device(
    client: httpx.AsyncClient,
    base_url: str,
    headers: dict,
    device: Device,
    user_id: str,
):
    """Sync a single device to Supabase."""
    data = {
        "id": device.id,  # Use same ID (string)
        "user_id": user_id,
        "device_type": device.device_type,
        "name": device.name,
        "display_name": device.display_name,
        "beer_name": device.beer_name,
        "original_gravity": device.original_gravity,
        "native_gravity_unit": device.native_gravity_unit,
        "native_temp_unit": device.native_temp_unit,
        "calibration_type": device.calibration_type,
        "calibration_data": device._calibration_data,
        "color": device.color,
        "mac": device.mac,
        "paired": device.paired,
        "paired_at": device.paired_at.isoformat() if device.paired_at else None,
        "created_at": device.created_at.isoformat() if device.created_at else None,
    }

    response = await client.post(
        f"{base_url}/devices",
        headers=headers,
        json=data,
    )

    if response.status_code not in (200, 201):
        raise Exception(f"Supabase error: {response.status_code} - {response.text}")


async def _sync_recipe(
    client: httpx.AsyncClient,
    base_url: str,
    headers: dict,
    recipe: Recipe,
    user_id: str,
):
    """Sync a single recipe to Supabase with nested ingredients."""
    # Main recipe data
    data = {
        "id": recipe.id,  # Use same integer ID
        "user_id": user_id,
        "name": recipe.name,
        "type": recipe.type,
        "author": recipe.author,
        "batch_size_liters": recipe.batch_size_liters,
        "boil_time_minutes": recipe.boil_time_minutes,
        "efficiency_percent": recipe.efficiency_percent,
        "og": recipe.og,
        "fg": recipe.fg,
        "abv": recipe.abv,
        "ibu": recipe.ibu,
        "color_srm": recipe.color_srm,
        "carbonation_vols": recipe.carbonation_vols,
        "style_id": recipe.style_id,
        "yeast_name": recipe.yeast_name,
        "yeast_lab": recipe.yeast_lab,
        "yeast_product_id": recipe.yeast_product_id,
        "yeast_temp_min": recipe.yeast_temp_min,
        "yeast_temp_max": recipe.yeast_temp_max,
        "yeast_attenuation": recipe.yeast_attenuation,
        "notes": recipe.notes,
        "created_at": recipe.created_at.isoformat() if recipe.created_at else None,
        "updated_at": recipe.updated_at.isoformat() if recipe.updated_at else None,
    }

    response = await client.post(
        f"{base_url}/recipes",
        headers=headers,
        json=data,
    )

    if response.status_code not in (200, 201):
        raise Exception(f"Supabase error: {response.status_code} - {response.text}")

    # Sync nested fermentables
    for ferm in recipe.fermentables:
        ferm_data = {
            "id": ferm.id,
            "recipe_id": recipe.id,
            "name": ferm.name,
            "type": ferm.type,
            "grain_group": ferm.grain_group,
            "amount_kg": ferm.amount_kg,
            "percentage": ferm.percentage,
            "yield_percent": ferm.yield_percent,
            "color_srm": ferm.color_srm,
            "origin": ferm.origin,
            "supplier": ferm.supplier,
            "notes": ferm.notes,
        }
        await client.post(f"{base_url}/recipe_fermentables", headers=headers, json=ferm_data)

    # Sync nested hops
    for hop in recipe.hops:
        hop_data = {
            "id": hop.id,
            "recipe_id": recipe.id,
            "name": hop.name,
            "origin": hop.origin,
            "form": hop.form,
            "alpha_acid_percent": hop.alpha_acid_percent,
            "beta_acid_percent": hop.beta_acid_percent,
            "amount_grams": hop.amount_grams,
            "timing": hop.timing,
            "format_extensions": hop.format_extensions,
        }
        await client.post(f"{base_url}/recipe_hops", headers=headers, json=hop_data)

    # Sync nested cultures (yeast)
    for culture in recipe.cultures:
        culture_data = {
            "id": culture.id,
            "recipe_id": recipe.id,
            "name": culture.name,
            "type": culture.type,
            "form": culture.form,
            "producer": culture.producer,
            "product_id": culture.product_id,
            "temp_min_c": culture.temp_min_c,
            "temp_max_c": culture.temp_max_c,
            "attenuation_min_percent": culture.attenuation_min_percent,
            "attenuation_max_percent": culture.attenuation_max_percent,
            "amount": culture.amount,
            "amount_unit": culture.amount_unit,
        }
        await client.post(f"{base_url}/recipe_cultures", headers=headers, json=culture_data)


async def _sync_batch(
    client: httpx.AsyncClient,
    base_url: str,
    headers: dict,
    batch: Batch,
    user_id: str,
):
    """Sync a single batch to Supabase."""
    data = {
        "id": batch.id,  # Use same integer ID
        "user_id": user_id,
        "recipe_id": batch.recipe_id,
        "device_id": batch.device_id,
        "batch_number": batch.batch_number,
        "name": batch.name,
        "status": batch.status,
        "brew_date": batch.brew_date.isoformat() if batch.brew_date else None,
        "start_time": batch.start_time.isoformat() if batch.start_time else None,
        "end_time": batch.end_time.isoformat() if batch.end_time else None,
        "fermenting_started_at": batch.fermenting_started_at.isoformat() if batch.fermenting_started_at else None,
        "conditioning_started_at": batch.conditioning_started_at.isoformat() if batch.conditioning_started_at else None,
        "completed_at": batch.completed_at.isoformat() if batch.completed_at else None,
        "measured_og": batch.measured_og,
        "measured_fg": batch.measured_fg,
        "measured_abv": batch.measured_abv,
        "measured_attenuation": batch.measured_attenuation,
        "notes": batch.notes,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
        "updated_at": batch.updated_at.isoformat() if batch.updated_at else None,
    }

    response = await client.post(
        f"{base_url}/batches",
        headers=headers,
        json=data,
    )

    if response.status_code not in (200, 201):
        raise Exception(f"Supabase error: {response.status_code} - {response.text}")


@router.get("/status")
async def get_sync_status(user: AuthUser = Depends(require_auth)):
    """Get sync status for the current user.

    Returns counts of syncable data and last sync timestamp.
    """
    async with async_session_factory() as session:
        devices = await _fetch_user_devices(session, user.user_id)
        recipes = await _fetch_user_recipes(session, user.user_id)
        batches = await _fetch_user_batches(session, user.user_id)

    return {
        "user_id": user.user_id,
        "local_counts": {
            "devices": len(devices),
            "recipes": len(recipes),
            "batches": len(batches),
        },
        "last_synced_at": None,  # TODO: Track in config table
    }
