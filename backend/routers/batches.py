"""Batch API endpoints."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..auth import AuthUser, require_auth
from ..config import get_settings
from ..database import get_db

logger = logging.getLogger(__name__)
from ..models import (
    Batch,
    BatchCreate,
    BatchPredictionsResponse,
    BatchProgressResponse,
    BatchResponse,
    BatchUpdate,
    ControlEvent,
    ControlEventResponse,
    FermentationAlert,
    FermentationAlertResponse,
    Reading,
    ReadingResponse,
    Recipe,
    TastingNote,
    TastingNoteCreate,
    TastingNoteUpdate,
    TastingNoteResponse,
    YeastStrain,
)
from ..state import latest_readings
from ..mqtt_manager import publish_batch_discovery, remove_batch_discovery

router = APIRouter(prefix="/api/batches", tags=["batches"])


def user_owns_batch(user: AuthUser):
    """Create a SQLAlchemy condition for batch ownership.

    In LOCAL deployment mode, includes:
    - Batches explicitly owned by the user
    - Batches owned by the dummy "local" user (pre-auth data)
    - Unclaimed batches (user_id IS NULL) for backward compatibility
    This allows authenticated users to see all local data before claiming it.

    In CLOUD deployment mode, strictly filters by user_id.
    """
    settings = get_settings()
    if settings.is_local:
        # LOCAL mode: single-user Pi, no ownership filtering needed
        return True
    # Cloud mode: strict user isolation
    return Batch.user_id == user.user_id


async def get_user_batch(batch_id: int, user: AuthUser, db: AsyncSession) -> Batch:
    """Fetch a batch with user ownership verification.

    Raises 404 if batch not found or not owned by user.
    """
    result = await db.execute(
        select(Batch).where(Batch.id == batch_id, user_owns_batch(user))
    )
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch


@router.get("", response_model=list[BatchResponse])
async def list_batches(
    status: Optional[str] = Query(None, description="Filter by status"),
    device_id: Optional[str] = Query(None, description="Filter by device"),
    include_deleted: bool = Query(False, description="Include soft-deleted batches"),
    deleted_only: bool = Query(False, description="Show only deleted batches (for maintenance)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """List batches with optional filters. By default excludes deleted batches."""
    query = (
        select(Batch)
        .options(selectinload(Batch.recipe).selectinload(Recipe.style), selectinload(Batch.yeast_strain), selectinload(Batch.tasting_notes), selectinload(Batch.reflections))
        .where(user_owns_batch(user))  # User isolation (LOCAL mode includes unclaimed)
        .order_by(Batch.created_at.desc())
    )

    # Soft delete filter (default: hide deleted)
    if deleted_only:
        query = query.where(Batch.deleted_at.is_not(None))
    elif not include_deleted:
        query = query.where(Batch.deleted_at.is_(None))

    if status:
        query = query.where(Batch.status == status)
    if device_id:
        query = query.where(Batch.device_id == device_id)

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/active", response_model=list[BatchResponse])
async def list_active_batches(
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Active batches: planning, brewing, or fermenting status, not deleted."""
    query = (
        select(Batch)
        .options(selectinload(Batch.recipe).selectinload(Recipe.style), selectinload(Batch.yeast_strain), selectinload(Batch.tasting_notes), selectinload(Batch.reflections))
        .where(
            user_owns_batch(user),  # User isolation (LOCAL mode includes unclaimed)
            Batch.deleted_at.is_(None),
            Batch.status.in_(["planning", "brewing", "fermenting"])
        )
        .order_by(Batch.created_at.desc())
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/completed", response_model=list[BatchResponse])
async def list_completed_batches(
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Historical batches: completed or conditioning, not deleted."""
    query = (
        select(Batch)
        .options(selectinload(Batch.recipe).selectinload(Recipe.style), selectinload(Batch.yeast_strain), selectinload(Batch.tasting_notes), selectinload(Batch.reflections))
        .where(
            user_owns_batch(user),  # User isolation (LOCAL mode includes unclaimed)
            Batch.deleted_at.is_(None),
            Batch.status.in_(["completed", "conditioning"])
        )
        .order_by(Batch.updated_at.desc())
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{batch_id}", response_model=BatchResponse)
async def get_batch(
    batch_id: int,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific batch by ID."""
    query = (
        select(Batch)
        .options(selectinload(Batch.recipe).selectinload(Recipe.style), selectinload(Batch.yeast_strain), selectinload(Batch.tasting_notes), selectinload(Batch.reflections))
        .where(Batch.id == batch_id, user_owns_batch(user))  # User isolation
    )
    result = await db.execute(query)
    batch = result.scalar_one_or_none()

    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch


@router.post("", response_model=BatchResponse, status_code=201)
async def create_batch(
    batch: BatchCreate,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Create a new batch."""
    # Check for heater entity conflicts if a heater is specified
    # Exclude soft-deleted batches from conflict check, scope to current user
    if batch.heater_entity_id:
        conflict_result = await db.execute(
            select(Batch).where(
                user_owns_batch(user),  # Only check user's batches
                Batch.status == "fermenting",
                Batch.heater_entity_id == batch.heater_entity_id,
                Batch.deleted_at.is_(None),
            )
        )
        conflicting_batch = conflict_result.scalar_one_or_none()
        if conflicting_batch:
            raise HTTPException(
                status_code=400,
                detail=f"Heater entity '{batch.heater_entity_id}' is already in use by fermenting batch '{conflicting_batch.name}' (ID: {conflicting_batch.id}). Each heater can only control one fermenting batch at a time."
            )

    # Check for device_id conflicts if a device is specified and status is fermenting
    # Exclude soft-deleted batches from conflict check, scope to current user
    if batch.device_id and batch.status == "fermenting":
        conflict_result = await db.execute(
            select(Batch).where(
                user_owns_batch(user),  # Only check user's batches
                Batch.status == "fermenting",
                Batch.device_id == batch.device_id,
                Batch.deleted_at.is_(None),
            )
        )
        conflicting_batch = conflict_result.scalar_one_or_none()
        if conflicting_batch:
            raise HTTPException(
                status_code=400,
                detail=f"Device (Tilt) '{batch.device_id}' is already assigned to fermenting batch '{conflicting_batch.name}' (ID: {conflicting_batch.id}). Each device can only track one fermenting batch at a time."
            )

    # Get next batch number
    result = await db.execute(select(func.max(Batch.batch_number)))
    max_num = result.scalar() or 0

    # Get recipe for batch name default and yeast info
    batch_name = batch.name
    yeast_strain_id = batch.yeast_strain_id
    recipe = None
    if batch.recipe_id:
        recipe = await db.get(Recipe, batch.recipe_id)
        if recipe:
            if not batch_name:
                batch_name = recipe.name
            # Auto-populate yeast_strain_id from recipe's yeast info if not provided
            if not yeast_strain_id and recipe.yeast_name:
                # Try to find matching yeast strain by name
                yeast_result = await db.execute(
                    select(YeastStrain).where(
                        YeastStrain.name.ilike(f"%{recipe.yeast_name}%")
                    ).limit(1)
                )
                yeast_strain = yeast_result.scalar_one_or_none()
                if yeast_strain:
                    yeast_strain_id = yeast_strain.id

    db_batch = Batch(
        user_id=user.user_id,  # Set owner
        recipe_id=batch.recipe_id,
        device_id=batch.device_id,
        yeast_strain_id=yeast_strain_id,
        batch_number=max_num + 1,
        name=batch_name,
        status=batch.status,
        brew_date=batch.brew_date,
        measured_og=batch.measured_og,
        notes=batch.notes,
        heater_entity_id=batch.heater_entity_id,
        temp_target=batch.temp_target,
        temp_hysteresis=batch.temp_hysteresis,
    )

    # Auto-set start_time if status is fermenting
    if batch.status == "fermenting":
        db_batch.start_time = datetime.now(timezone.utc)

    db.add(db_batch)
    await db.commit()
    await db.refresh(db_batch)

    # Publish MQTT discovery if batch starts in fermenting status
    if batch.status == "fermenting":
        await publish_batch_discovery(
            batch_id=db_batch.id,
            batch_name=db_batch.name or f"Batch #{db_batch.batch_number}",
            device_id=db_batch.device_id,
        )

    # Always load relationships for response (tasting_notes, reflections need eager load)
    query = (
        select(Batch)
        .options(
            selectinload(Batch.recipe).selectinload(Recipe.style),
            selectinload(Batch.yeast_strain),
            selectinload(Batch.tasting_notes),
            selectinload(Batch.reflections),
        )
        .where(Batch.id == db_batch.id)
    )
    result = await db.execute(query)
    db_batch = result.scalar_one()

    return db_batch


@router.put("/{batch_id}", response_model=BatchResponse)
async def update_batch(
    batch_id: int,
    update: BatchUpdate,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Update a batch."""
    # Fetch batch with user isolation
    result = await db.execute(
        select(Batch).where(Batch.id == batch_id, user_owns_batch(user))
    )
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    # Check for heater entity conflicts if changing heater and batch is/will be fermenting
    new_status = update.status if update.status is not None else batch.status
    new_heater = update.heater_entity_id if update.heater_entity_id is not None else batch.heater_entity_id
    new_device_id = update.device_id if update.device_id is not None else batch.device_id

    if new_heater and new_status == "fermenting":
        # Only check for conflicts if the heater entity is actually changing
        # Exclude soft-deleted batches from conflict check, scope to user
        if update.heater_entity_id is not None and update.heater_entity_id != batch.heater_entity_id:
            conflict_result = await db.execute(
                select(Batch).where(
                    user_owns_batch(user),  # User isolation
                    Batch.status == "fermenting",
                    Batch.heater_entity_id == new_heater,
                    Batch.id != batch_id,
                    Batch.deleted_at.is_(None),
                )
            )
            conflicting_batch = conflict_result.scalar_one_or_none()
            if conflicting_batch:
                raise HTTPException(
                    status_code=400,
                    detail=f"Heater entity '{new_heater}' is already in use by fermenting batch '{conflicting_batch.name}' (ID: {conflicting_batch.id}). Each heater can only control one fermenting batch at a time."
                )

    # Check for device_id conflicts if changing device and batch is/will be fermenting
    # Exclude soft-deleted batches from conflict check, scope to user
    if new_device_id and new_status == "fermenting":
        # Only check for conflicts if the device_id is actually changing
        if update.device_id is not None and update.device_id != batch.device_id:
            conflict_result = await db.execute(
                select(Batch).where(
                    user_owns_batch(user),  # User isolation
                    Batch.status == "fermenting",
                    Batch.device_id == new_device_id,
                    Batch.id != batch_id,
                    Batch.deleted_at.is_(None),
                )
            )
            conflicting_batch = conflict_result.scalar_one_or_none()
            if conflicting_batch:
                raise HTTPException(
                    status_code=400,
                    detail=f"Device (Tilt) '{new_device_id}' is already assigned to fermenting batch '{conflicting_batch.name}' (ID: {conflicting_batch.id}). Each device can only track one fermenting batch at a time."
                )

    # Update fields if provided
    if update.recipe_id is not None:
        batch.recipe_id = update.recipe_id
    if update.name is not None:
        batch.name = update.name
    if update.status is not None:
        old_status = batch.status
        batch.status = update.status
        # Auto-set timestamps on status change
        if update.status == "fermenting" and old_status != "fermenting":
            batch.start_time = datetime.now(timezone.utc)
        elif update.status in ["conditioning", "completed"] and old_status == "fermenting":
            batch.end_time = datetime.now(timezone.utc)

        # Clean up runtime state when batch leaves fermenting status
        if old_status == "fermenting" and update.status != "fermenting":
            from ..temp_controller import cleanup_batch_state
            cleanup_batch_state(batch_id)

        # MQTT: Publish discovery when entering fermenting status
        if update.status == "fermenting" and old_status != "fermenting":
            await publish_batch_discovery(
                batch_id=batch_id,
                batch_name=batch.name or f"Batch #{batch.batch_number}",
                device_id=batch.device_id,
            )
        # MQTT: Remove discovery when completing/archiving batch
        elif update.status in ["completed", "archived"]:
            await remove_batch_discovery(batch_id)

        # Auto-populate measured_fg from last reading when completing (if not already set)
        if update.status == "completed" and batch.measured_fg is None and batch.measured_og:
            # Get the last reading for this batch to capture final gravity
            last_reading_query = (
                select(Reading)
                .where(Reading.batch_id == batch_id)
                .order_by(Reading.timestamp.desc())
                .limit(1)
            )
            last_reading_result = await db.execute(last_reading_query)
            last_reading = last_reading_result.scalar_one_or_none()
            if last_reading:
                # Use filtered SG if available, otherwise calibrated
                final_sg = last_reading.sg_filtered or last_reading.sg_calibrated
                if final_sg:
                    batch.measured_fg = final_sg
                    batch.measured_abv = (batch.measured_og - final_sg) * 131.25
                    batch.measured_attenuation = ((batch.measured_og - final_sg) / (batch.measured_og - 1.0)) * 100

        # Release device when batch is completed or archived
        if update.status in ["completed", "archived"]:
            batch.device_id = None
    if update.device_id is not None:
        batch.device_id = update.device_id
    if update.yeast_strain_id is not None:
        batch.yeast_strain_id = update.yeast_strain_id
    if update.brew_date is not None:
        batch.brew_date = update.brew_date
    if update.start_time is not None:
        batch.start_time = update.start_time
    if update.end_time is not None:
        batch.end_time = update.end_time
    if update.measured_og is not None:
        batch.measured_og = update.measured_og
    if update.measured_fg is not None:
        batch.measured_fg = update.measured_fg
        # Calculate ABV and attenuation when FG is set
        if batch.measured_og:
            batch.measured_abv = (batch.measured_og - update.measured_fg) * 131.25
            batch.measured_attenuation = ((batch.measured_og - update.measured_fg) / (batch.measured_og - 1.0)) * 100
    if update.notes is not None:
        batch.notes = update.notes
    # Temperature control fields
    if update.heater_entity_id is not None:
        batch.heater_entity_id = update.heater_entity_id
    if update.cooler_entity_id is not None:
        batch.cooler_entity_id = update.cooler_entity_id
    if update.temp_target is not None:
        batch.temp_target = update.temp_target
    if update.temp_hysteresis is not None:
        batch.temp_hysteresis = update.temp_hysteresis
    # Reading control
    if update.readings_paused is not None:
        batch.readings_paused = update.readings_paused
    # Timer state
    if update.timer_phase is not None:
        batch.timer_phase = update.timer_phase
    if update.timer_started_at is not None:
        batch.timer_started_at = update.timer_started_at
    if update.timer_duration_seconds is not None:
        batch.timer_duration_seconds = update.timer_duration_seconds
    if update.timer_paused_at is not None:
        batch.timer_paused_at = update.timer_paused_at
    # Brew day observation fields
    if update.actual_mash_temp is not None:
        batch.actual_mash_temp = update.actual_mash_temp
    if update.actual_mash_ph is not None:
        batch.actual_mash_ph = update.actual_mash_ph
    if update.strike_water_volume is not None:
        batch.strike_water_volume = update.strike_water_volume
    if update.pre_boil_gravity is not None:
        batch.pre_boil_gravity = update.pre_boil_gravity
    if update.pre_boil_volume is not None:
        batch.pre_boil_volume = update.pre_boil_volume
    if update.post_boil_volume is not None:
        batch.post_boil_volume = update.post_boil_volume
    if update.actual_efficiency is not None:
        batch.actual_efficiency = update.actual_efficiency
    if update.brew_day_notes is not None:
        batch.brew_day_notes = update.brew_day_notes
    # Packaging info
    if update.packaged_at is not None:
        batch.packaged_at = update.packaged_at
    if update.packaging_type is not None:
        batch.packaging_type = update.packaging_type
    if update.packaging_volume is not None:
        batch.packaging_volume = update.packaging_volume
    if update.carbonation_method is not None:
        batch.carbonation_method = update.carbonation_method
    if update.priming_sugar_type is not None:
        batch.priming_sugar_type = update.priming_sugar_type
    if update.priming_sugar_amount is not None:
        batch.priming_sugar_amount = update.priming_sugar_amount
    if update.packaging_notes is not None:
        batch.packaging_notes = update.packaging_notes

    await db.commit()
    await db.refresh(batch)

    # Always reload batch with eager loading to avoid MissingGreenlet errors
    # Load recipe relationship for response with eager loading of nested style
    stmt = select(Batch).where(Batch.id == batch_id).options(
        selectinload(Batch.recipe).selectinload(Recipe.style),
        selectinload(Batch.yeast_strain),
        selectinload(Batch.tasting_notes),
        selectinload(Batch.reflections),
    )
    result = await db.execute(stmt)
    batch = result.scalar_one()

    return batch


@router.post("/{batch_id}/delete")
async def soft_delete_batch(
    batch_id: int,
    hard_delete: bool = Query(False, description="Cascade delete readings"),
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Soft delete or hard delete a batch.

    - Soft delete (default): Sets deleted_at timestamp, preserves all data
    - Hard delete: Cascade removes all readings via relationship
    """
    batch = await get_user_batch(batch_id, user, db)

    # Remove MQTT discovery before deleting
    await remove_batch_discovery(batch_id)

    if hard_delete:
        # Hard delete: cascade removes readings via relationship
        await db.delete(batch)
        await db.commit()
        return {"status": "deleted", "type": "hard", "batch_id": batch_id}
    else:
        # Soft delete: set timestamp
        batch.deleted_at = datetime.now(timezone.utc)
        await db.commit()
        return {"status": "deleted", "type": "soft", "batch_id": batch_id}


@router.post("/{batch_id}/restore")
async def restore_batch(
    batch_id: int,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Restore a soft-deleted batch."""
    batch = await get_user_batch(batch_id, user, db)
    if not batch.deleted_at:
        raise HTTPException(status_code=400, detail="Batch is not deleted")

    batch.deleted_at = None
    await db.commit()
    return {"status": "restored", "batch_id": batch_id}


@router.get("/{batch_id}/progress", response_model=BatchProgressResponse)
async def get_batch_progress(
    batch_id: int,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Get fermentation progress for a batch."""
    # Get batch with recipe and user isolation
    query = (
        select(Batch)
        .options(selectinload(Batch.recipe).selectinload(Recipe.style), selectinload(Batch.yeast_strain), selectinload(Batch.tasting_notes), selectinload(Batch.reflections))
        .where(Batch.id == batch_id, user_owns_batch(user))
    )
    result = await db.execute(query)
    batch = result.scalar_one_or_none()

    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    # Get current SG and temperature from latest reading
    # Temperature is in Celsius (converted from Tilt's Fahrenheit broadcast on ingestion)
    # Frontend will convert based on user preference
    current_sg = None
    current_temp = None
    if batch.device_id and batch.device_id in latest_readings:
        reading = latest_readings[batch.device_id]
        current_sg = reading.get("sg")
        current_temp = reading.get("temp")

    # For completed batches, use measured_fg or last reading as the final gravity
    if batch.status == "completed":
        if batch.measured_fg:
            current_sg = batch.measured_fg
        elif current_sg is None:
            # Get last reading from database if measured_fg not set
            last_reading_query = (
                select(Reading)
                .where(Reading.batch_id == batch_id)
                .order_by(Reading.timestamp.desc())
                .limit(1)
            )
            last_reading_result = await db.execute(last_reading_query)
            last_reading = last_reading_result.scalar_one_or_none()
            if last_reading:
                current_sg = last_reading.sg_filtered or last_reading.sg_calibrated

    # Calculate targets from recipe
    targets = {}
    if batch.recipe:
        targets = {
            "og": batch.recipe.og,
            "fg": batch.recipe.fg,
            "attenuation": None,
            "abv": batch.recipe.abv,
        }
        if batch.recipe.og and batch.recipe.fg:
            targets["attenuation"] = round(
                ((batch.recipe.og - batch.recipe.fg) / (batch.recipe.og - 1.0)) * 100, 1
            )

    # Calculate measured values
    measured = {
        "og": batch.measured_og,
        "current_sg": current_sg,
        "attenuation": None,
        "abv": None,
        # For completed batches, use measured_fg if available, otherwise current_sg (last reading)
        "fg": batch.measured_fg if batch.measured_fg else (current_sg if batch.status == "completed" else None),
    }
    # For completed batches with stored values, use those
    if batch.status == "completed" and batch.measured_abv is not None:
        measured["abv"] = round(batch.measured_abv, 1)
        measured["attenuation"] = round(batch.measured_attenuation, 1) if batch.measured_attenuation else None
    elif batch.measured_og and current_sg:
        measured["attenuation"] = round(
            ((batch.measured_og - current_sg) / (batch.measured_og - 1.0)) * 100, 1
        )
        measured["abv"] = round((batch.measured_og - current_sg) * 131.25, 1)

    # Calculate progress
    progress = {
        "percent_complete": None,
        "sg_remaining": None,
        "estimated_days_remaining": None,
    }
    og = batch.measured_og or (targets.get("og") if targets else None)
    fg = targets.get("fg") if targets else None
    if og and fg and current_sg:
        total_drop = og - fg
        current_drop = og - current_sg
        if total_drop > 0:
            # Clamp to 0-100% (negative when current SG > OG at fermentation start)
            progress["percent_complete"] = round(max(0, min(100, (current_drop / total_drop) * 100)), 1)
            progress["sg_remaining"] = round(max(0, current_sg - fg), 4)

    # Temperature status
    temperature = {
        "current": current_temp,
        "yeast_min": batch.recipe.yeast_temp_min if batch.recipe else None,
        "yeast_max": batch.recipe.yeast_temp_max if batch.recipe else None,
        "status": "unknown",
    }
    if current_temp and batch.recipe:
        ymin = batch.recipe.yeast_temp_min
        ymax = batch.recipe.yeast_temp_max
        if ymin and ymax:
            if ymin <= current_temp <= ymax:
                temperature["status"] = "in_range"
            elif current_temp < ymin:
                temperature["status"] = "too_cold"
            else:
                temperature["status"] = "too_hot"

    return BatchProgressResponse(
        batch_id=batch.id,
        recipe_name=batch.recipe.name if batch.recipe else batch.name,
        status=batch.status,
        targets=targets,
        measured=measured,
        progress=progress,
        temperature=temperature,
    )


@router.get("/{batch_id}/predictions", response_model=BatchPredictionsResponse)
async def get_batch_predictions(
    batch_id: int,
    model: str = Query("auto", description="Prediction model: exponential, gompertz, logistic, or auto (best fit)"),
    db: AsyncSession = Depends(get_db),
):
    """Get ML predictions for a batch.

    Args:
        batch_id: The batch ID to get predictions for
        model: Model type to use for predictions:
            - "auto": Try all models, return best R² (default)
            - "exponential": Simple exponential decay
            - "gompertz": S-curve with lag phase
            - "logistic": Symmetric S-curve

    Returns:
        Dictionary containing:
        - available (bool): Whether predictions are available
        - predicted_fg (float): Predicted final gravity
        - predicted_og (float): Predicted original gravity
        - estimated_completion (str): ISO timestamp of predicted completion
        - hours_to_completion (float): Hours until fermentation completes
        - model_type (str): Type of model used ("exponential", "gompertz", "logistic")
        - r_squared (float): Model fit quality (0.0-1.0)
        - num_readings (int): Number of readings used for prediction
        - error (str): Error message if available=False
        - reason (str): Reason why predictions unavailable
    """
    from ..main import get_ml_manager

    # Get batch with recipe eagerly loaded
    result = await db.execute(
        select(Batch)
        .options(selectinload(Batch.recipe))
        .where(Batch.id == batch_id, Batch.deleted_at.is_(None))
    )
    batch = result.scalar_one_or_none()

    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    # For completed/archived batches without device_id, use a synthetic ID based on batch
    # This allows viewing historical predictions even after device is released
    device_id = batch.device_id
    if not device_id:
        if batch.status in ["completed", "archived"]:
            device_id = f"batch-{batch_id}"  # Synthetic ID for historical batches
        else:
            return {"available": False, "error": "No device linked"}

    # Query ML manager for predictions
    ml_mgr = get_ml_manager()
    if not ml_mgr:
        return {"available": False}

    # Get expected FG from recipe to constrain predictions
    expected_fg = batch.recipe.fg if batch.recipe else None

    # Get device state with expected FG for prediction bounds and selected model
    device_state = ml_mgr.get_device_state(device_id, expected_fg=expected_fg, model=model)

    # Auto-reload from database if pipeline is empty or has insufficient history
    if not device_state or device_state.get("history_count", 0) < 10:
        await ml_mgr.reload_from_database(device_id, batch_id, db)
        device_state = ml_mgr.get_device_state(device_id, expected_fg=expected_fg, model=model)

    if not device_state or not device_state.get("predictions"):
        return {"available": False}

    predictions = device_state["predictions"]

    # predictions can be None (insufficient history) or dict with fitted=False (fit failed)
    if not predictions.get("fitted"):
        return {"available": False, "reason": predictions.get("reason", "unknown")}

    # Use blended prediction (linear/curve blend based on confidence)
    # Fall back to curve-only hours_to_completion if blended not available
    blended_hours = predictions.get("blended_hours_to_completion")
    curve_hours = predictions.get("hours_to_completion")
    linear_hours = predictions.get("hours_to_target_linear")
    confidence = predictions.get("confidence")

    # Primary estimate uses blended prediction
    hours_to_completion = blended_hours if blended_hours is not None else curve_hours

    # Calculate completion date from blended hours
    # Note: hours_to_completion is relative to NOW, not batch start time
    completion_date = None
    if hours_to_completion is not None and hours_to_completion > 0:
        completion_date = datetime.now(timezone.utc) + timedelta(hours=hours_to_completion)

    return {
        "available": True,
        "predicted_fg": predictions.get("predicted_fg"),
        "predicted_og": predictions.get("predicted_og"),
        "estimated_completion": completion_date.isoformat() if completion_date else None,
        "hours_to_completion": hours_to_completion,
        "hours_to_target_linear": linear_hours,
        "curve_hours_to_completion": curve_hours,
        "confidence": confidence,
        "model_type": predictions.get("model_type"),
        "r_squared": predictions.get("r_squared"),
        "num_readings": device_state.get("history_count", 0)
    }


@router.post("/{batch_id}/reload-predictions")
async def reload_batch_predictions(batch_id: int, db: AsyncSession = Depends(get_db)):
    """Reload ML predictions from database history.

    Forces the ML pipeline to recalculate predictions based on current
    database state. Useful after:
    - Data corrections in the database
    - Calibration changes
    - Suspecting stale predictions

    Returns:
        Dictionary with reload status and metrics
    """
    from ..main import get_ml_manager

    # Get batch
    result = await db.execute(
        select(Batch).where(Batch.id == batch_id, Batch.deleted_at.is_(None))
    )
    batch = result.scalar_one_or_none()

    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    # For completed/archived batches without device_id, use a synthetic ID
    device_id = batch.device_id
    if not device_id:
        if batch.status in ["completed", "archived"]:
            device_id = f"batch-{batch_id}"
        else:
            raise HTTPException(status_code=400, detail="Batch has no device linked")

    # Get ML manager
    ml_mgr = get_ml_manager()
    if not ml_mgr:
        raise HTTPException(status_code=503, detail="ML manager not available")

    # Reload from database
    reload_result = await ml_mgr.reload_from_database(
        device_id=device_id,
        batch_id=batch_id,
        db_session=db
    )

    if not reload_result["success"]:
        raise HTTPException(
            status_code=400,
            detail=reload_result.get("error", "Failed to reload predictions")
        )

    return {
        "success": True,
        "readings_loaded": reload_result["readings_loaded"],
        "message": f"Successfully reloaded {reload_result['readings_loaded']} readings"
    }


@router.get("/{batch_id}/control-events", response_model=list[ControlEventResponse])
async def get_batch_control_events(
    batch_id: int,
    hours: int = Query(24, ge=1, le=720, description="Hours of history to retrieve (max 30 days)"),
    db: AsyncSession = Depends(get_db),
):
    """Get control event history for a batch.

    Returns heating/cooling control events (heat_on, heat_off, cool_on, cool_off)
    for visualization on the fermentation chart.

    Args:
        batch_id: The batch ID to retrieve events for
        hours: Number of hours of history (default 24, max 720 for 30 days)

    Returns:
        List of control events ordered chronologically (oldest first)
    """
    # Verify batch exists
    batch = await db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    # Calculate time range
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Query control events for this batch
    query = (
        select(ControlEvent)
        .where(
            ControlEvent.batch_id == batch_id,
            ControlEvent.timestamp >= cutoff_time
        )
        .order_by(ControlEvent.timestamp.asc())  # Chronological order (oldest first)
    )

    result = await db.execute(query)
    events = result.scalars().all()

    return events


# ============================================================================
# Fermentation Alerts Endpoints
# ============================================================================

@router.get("/{batch_id}/alerts", response_model=list[FermentationAlertResponse])
async def get_batch_alerts(
    batch_id: int,
    include_cleared: bool = Query(False, description="Include cleared/resolved alerts"),
    db: AsyncSession = Depends(get_db),
):
    """Get fermentation alerts for a batch.

    By default returns only active alerts (cleared_at is null).
    Set include_cleared=true to also return historical/resolved alerts.

    Returns:
        List of fermentation alerts ordered by severity (critical first) then by detection time (newest first)
    """
    # Verify batch exists
    batch = await db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    # Build query
    query = select(FermentationAlert).where(FermentationAlert.batch_id == batch_id)

    # Filter by active status unless include_cleared
    if not include_cleared:
        query = query.where(FermentationAlert.cleared_at.is_(None))

    # Order by severity (critical > warning > info) then by newest first
    # SQLite doesn't have CASE, so we order by last_seen_at descending for now
    query = query.order_by(FermentationAlert.last_seen_at.desc())

    result = await db.execute(query)
    alerts = result.scalars().all()

    return alerts


@router.post("/{batch_id}/alerts/{alert_id}/dismiss")
async def dismiss_alert(
    batch_id: int,
    alert_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Dismiss/clear an active alert.

    Sets cleared_at timestamp to mark the alert as resolved.
    The alert will no longer appear in active alerts list.

    Returns:
        Success status with alert details
    """
    # Get alert and verify it belongs to the batch
    alert = await db.get(FermentationAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    if alert.batch_id != batch_id:
        raise HTTPException(status_code=400, detail="Alert does not belong to this batch")

    if alert.cleared_at is not None:
        raise HTTPException(status_code=400, detail="Alert is already cleared")

    # Clear the alert
    alert.cleared_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "status": "dismissed",
        "alert_id": alert_id,
        "alert_type": alert.alert_type,
        "cleared_at": alert.cleared_at.isoformat()
    }


@router.post("/{batch_id}/alerts/dismiss-all")
async def dismiss_all_alerts(
    batch_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Dismiss all active alerts for a batch.

    Sets cleared_at timestamp on all active alerts for the batch.

    Returns:
        Count of alerts dismissed
    """
    # Verify batch exists
    batch = await db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    # Get all active alerts for this batch
    query = select(FermentationAlert).where(
        FermentationAlert.batch_id == batch_id,
        FermentationAlert.cleared_at.is_(None)
    )
    result = await db.execute(query)
    alerts = result.scalars().all()

    if not alerts:
        return {"status": "no_alerts", "count": 0}

    # Clear all alerts
    now = datetime.now(timezone.utc)
    for alert in alerts:
        alert.cleared_at = now

    await db.commit()

    return {
        "status": "dismissed",
        "count": len(alerts),
        "cleared_at": now.isoformat()
    }


@router.get("/{batch_id}/readings", response_model=list[ReadingResponse])
async def get_batch_readings(
    batch_id: int,
    hours: Optional[int] = Query(default=None, description="Time window in hours"),
    limit: int = Query(default=5000, le=10000, description="Maximum readings to return"),
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Get ALL readings for a batch, regardless of which device took them.

    This allows viewing historical data even after switching devices mid-ferment.
    Readings are returned in chronological order (oldest first).
    """
    # Verify batch exists and user owns it
    batch = await get_user_batch(batch_id, user, db)

    # Build query for all readings linked to this batch
    query = select(Reading).where(Reading.batch_id == batch_id)

    # Apply time window filter if specified
    if hours:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        query = query.where(Reading.timestamp >= cutoff)

    # Order by timestamp and apply limit
    query = query.order_by(Reading.timestamp.asc()).limit(limit)

    result = await db.execute(query)
    readings = result.scalars().all()

    return [ReadingResponse.model_validate(r) for r in readings]


# ==============================================================================
# Tasting Notes Endpoints
# ==============================================================================


async def _store_tasting_memory(
    db: AsyncSession,
    note: TastingNote,
    batch: Batch,
    user_id: str,
) -> None:
    """Store tasting note as a memory in mem0 (non-blocking, graceful failure)."""
    try:
        from backend.services.memory import add_memory
        from backend.routers.assistant import get_llm_config

        # Only store if there's meaningful content
        has_notable_content = (
            note.overall_notes
            or note.ai_suggestions
            or (note.to_style is False and note.style_deviation_notes)
        )
        if not has_notable_content:
            return

        llm_config = await get_llm_config(db)
        if not llm_config.is_configured():
            logger.debug("LLM not configured, skipping memory storage for tasting note")
            return

        days_str = f"day {note.days_since_packaging}" if note.days_since_packaging else "unknown days"
        messages = [
            {
                "role": "user",
                "content": f"I just tasted batch '{batch.name}' ({days_str} since packaging). Total score: {note.total_score}/25."
            },
            {"role": "assistant", "content": "What are your observations?"},
            {
                "role": "user",
                "content": f"""Overall: {note.overall_notes or 'N/A'}
To style: {'Yes' if note.to_style else 'No - ' + (note.style_deviation_notes or 'No notes')}"""
            }
        ]
        await add_memory(
            messages=messages,
            user_id=user_id,
            llm_config=llm_config,
            metadata={
                "type": "tasting",
                "batch_id": batch.id,
                "batch_name": batch.name,
                "total_score": note.total_score,
                "days_since_packaging": note.days_since_packaging,
            }
        )
        logger.info(f"Stored tasting memory for batch {batch.id}")
    except Exception as e:
        # Non-blocking: log and continue, don't fail the request
        logger.warning(f"Failed to store tasting memory: {e}")


@router.get("/{batch_id}/tasting-notes", response_model=list[TastingNoteResponse])
async def list_tasting_notes(
    batch_id: int,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Get all tasting notes for a batch, ordered by tasting date (newest first)."""
    # Verify batch exists and user owns it
    await get_user_batch(batch_id, user, db)

    query = (
        select(TastingNote)
        .where(TastingNote.batch_id == batch_id)
        .order_by(TastingNote.tasted_at.desc())
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/{batch_id}/tasting-notes", response_model=TastingNoteResponse, status_code=201)
async def create_tasting_note(
    batch_id: int,
    note: TastingNoteCreate,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Create a new tasting note for a batch."""
    # Verify batch exists and user owns it
    batch = await get_user_batch(batch_id, user, db)

    # Calculate total score based on scoring version
    scoring_version = note.scoring_version or 1
    if scoring_version == 2:
        # BJCP: sum of all subcategory scores + overall (max 50)
        total = sum(filter(None, [
            note.aroma_malt, note.aroma_hops,
            note.aroma_fermentation, note.aroma_other,
            note.appearance_color, note.appearance_clarity,
            note.appearance_head,
            note.flavor_malt, note.flavor_hops,
            note.flavor_bitterness, note.flavor_fermentation,
            note.flavor_balance, note.flavor_finish,
            note.mouthfeel_body, note.mouthfeel_carbonation,
            note.mouthfeel_warmth,
            note.overall_score,
        ]))
    else:
        # Legacy: sum of 5 category scores (max 25)
        scores = [note.appearance_score, note.aroma_score, note.flavor_score,
                  note.mouthfeel_score, note.overall_score]
        total = sum(s for s in scores if s is not None) if any(s is not None for s in scores) else None

    db_note = TastingNote(
        batch_id=batch_id,
        user_id=user.user_id,
        tasted_at=note.tasted_at or datetime.now(timezone.utc),
        days_since_packaging=note.days_since_packaging,
        serving_temp_c=note.serving_temp_c,
        glassware=note.glassware,
        appearance_score=note.appearance_score,
        appearance_notes=note.appearance_notes,
        aroma_score=note.aroma_score,
        aroma_notes=note.aroma_notes,
        flavor_score=note.flavor_score,
        flavor_notes=note.flavor_notes,
        mouthfeel_score=note.mouthfeel_score,
        mouthfeel_notes=note.mouthfeel_notes,
        overall_score=note.overall_score,
        overall_notes=note.overall_notes,
        total_score=total,
        scoring_version=scoring_version,
        to_style=note.to_style,
        style_deviation_notes=note.style_deviation_notes,
        # BJCP v2 subcategory scores
        aroma_malt=note.aroma_malt,
        aroma_hops=note.aroma_hops,
        aroma_fermentation=note.aroma_fermentation,
        aroma_other=note.aroma_other,
        appearance_color=note.appearance_color,
        appearance_clarity=note.appearance_clarity,
        appearance_head=note.appearance_head,
        flavor_malt=note.flavor_malt,
        flavor_hops=note.flavor_hops,
        flavor_bitterness=note.flavor_bitterness,
        flavor_fermentation=note.flavor_fermentation,
        flavor_balance=note.flavor_balance,
        flavor_finish=note.flavor_finish,
        mouthfeel_body=note.mouthfeel_body,
        mouthfeel_carbonation=note.mouthfeel_carbonation,
        mouthfeel_warmth=note.mouthfeel_warmth,
    )
    db.add(db_note)
    await db.commit()
    await db.refresh(db_note)

    # Store memory in background (non-blocking)
    asyncio.create_task(_store_tasting_memory(db, db_note, batch, user.user_id))

    return db_note


@router.get("/{batch_id}/tasting-notes/{note_id}", response_model=TastingNoteResponse)
async def get_tasting_note(
    batch_id: int,
    note_id: int,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific tasting note."""
    # Verify batch exists and user owns it
    await get_user_batch(batch_id, user, db)

    query = select(TastingNote).where(
        TastingNote.id == note_id,
        TastingNote.batch_id == batch_id
    )
    result = await db.execute(query)
    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(status_code=404, detail="Tasting note not found")
    return note


@router.put("/{batch_id}/tasting-notes/{note_id}", response_model=TastingNoteResponse)
async def update_tasting_note(
    batch_id: int,
    note_id: int,
    update: TastingNoteUpdate,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Update a tasting note."""
    # Verify batch exists and user owns it
    await get_user_batch(batch_id, user, db)

    query = select(TastingNote).where(
        TastingNote.id == note_id,
        TastingNote.batch_id == batch_id
    )
    result = await db.execute(query)
    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(status_code=404, detail="Tasting note not found")

    # Update fields
    update_data = update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(note, key, value)

    # Recalculate total_score based on scoring version (including any updates)
    scoring_version = note.scoring_version or 1
    if scoring_version == 2:
        # BJCP: sum of all subcategory scores + overall (max 50)
        note.total_score = sum(filter(None, [
            note.aroma_malt, note.aroma_hops,
            note.aroma_fermentation, note.aroma_other,
            note.appearance_color, note.appearance_clarity,
            note.appearance_head,
            note.flavor_malt, note.flavor_hops,
            note.flavor_bitterness, note.flavor_fermentation,
            note.flavor_balance, note.flavor_finish,
            note.mouthfeel_body, note.mouthfeel_carbonation,
            note.mouthfeel_warmth,
            note.overall_score,
        ]))
    else:
        # Legacy: sum of 5 category scores (max 25)
        scores = [note.appearance_score, note.aroma_score, note.flavor_score,
                  note.mouthfeel_score, note.overall_score]
        note.total_score = sum(s for s in scores if s is not None) if any(s is not None for s in scores) else None

    await db.commit()
    await db.refresh(note)
    return note


@router.delete("/{batch_id}/tasting-notes/{note_id}", status_code=204)
async def delete_tasting_note(
    batch_id: int,
    note_id: int,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Delete a tasting note."""
    # Verify batch exists and user owns it
    await get_user_batch(batch_id, user, db)

    query = select(TastingNote).where(
        TastingNote.id == note_id,
        TastingNote.batch_id == batch_id
    )
    result = await db.execute(query)
    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(status_code=404, detail="Tasting note not found")

    await db.delete(note)
    await db.commit()
