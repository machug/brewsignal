"""
Alert detection service for fermentation monitoring.

This service:
- Detects alert conditions (temperature out of range or running away, anomalies,
  stalled fermentation, low battery, sensor offline)
- Persists alerts to the database with proper lifecycle tracking
- Updates existing alerts when conditions persist
- Clears alerts when conditions resolve
"""
import asyncio
import json
import logging
import statistics
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services import push
from backend.services.recipe_stats import batch_expected_fg, batch_expected_og, batch_with_recipe_options
from backend.models import Batch, FermentationAlert, Reading, Recipe, RecipeHop

logger = logging.getLogger(__name__)


class AlertType:
    """Alert type constants."""
    TEMPERATURE_HIGH = "temperature_high"
    TEMPERATURE_LOW = "temperature_low"
    ANOMALY = "anomaly"
    STALL = "stall"
    # Temperature-controller safety alerts (tilt_ui-f50x, tilt_ui-8d49)
    SENSOR_STALE = "sensor_stale"
    MAX_ON_EXCEEDED = "max_on_exceeded"
    EQUIPMENT_CONFLICT = "equipment_conflict"
    # Informational: the automatic diacetyl rest rule changed the target (tilt_ui-ml8e)
    REST_STARTED = "rest_started"
    # Warning: the rule is on but has no OG/FG to work out its trigger
    REST_BLOCKED = "rest_blocked"
    # Sensing alerts (tilt_ui-lgtu)
    SENSOR_OFFLINE = "sensor_offline"
    BATTERY_LOW = "battery_low"
    TEMP_RUNAWAY = "temp_runaway"
    # Reminder: gravity reached the dry hop point (tilt_ui-n1w7)
    DRY_HOP_DUE = "dry_hop_due"
    # Info: gravity has been flat at the expected FG for 2 days (tilt_ui-v25i)
    CRASH_READY = "crash_ready"
    # Warning: a crash_ready alert came down because gravity moved (tilt_ui-y6za)
    CRASH_NOT_READY = "crash_not_ready"
    # Info: would be crash_ready, but the recipe's dry hop is not marked done (tilt_ui-8ih3)
    CRASH_WAIT_DRY_HOP = "crash_wait_dry_hop"


# Short push titles. Not listed = no push: rest_started is informational (the
# diacetyl rest worked as configured), so it never pings the phone.
PUSH_TITLES = {
    AlertType.TEMPERATURE_HIGH: "Temperature too high",
    AlertType.TEMPERATURE_LOW: "Temperature too low",
    AlertType.TEMP_RUNAWAY: "Temperature runaway",
    AlertType.ANOMALY: "Unusual reading",
    AlertType.STALL: "Fermentation stalled",
    AlertType.SENSOR_STALE: "Temperature sensor stale",
    AlertType.SENSOR_OFFLINE: "Sensor offline",
    AlertType.BATTERY_LOW: "Sensor battery low",
    AlertType.MAX_ON_EXCEEDED: "Heater/cooler on too long",
    AlertType.EQUIPMENT_CONFLICT: "Equipment conflict",
    AlertType.REST_BLOCKED: "Diacetyl rest cannot start",
    AlertType.DRY_HOP_DUE: "Dry hop now",
    AlertType.CRASH_READY: "Ready to cold crash",
    AlertType.CRASH_NOT_READY: "Not ready to cold crash after all",
    AlertType.CRASH_WAIT_DRY_HOP: "Ready to cold crash once dry hopped",
}


# Stall rule thresholds (tilt_ui-zbhm; tuned on synthetic curves, re-tune on real batches)
STALL_MAX_SLOPE = 2.5e-5  # SG/hour, i.e. 0.6 gravity points/day
STALL_MIN_DROP = 0.004  # must have fermented 4 points first
STALL_FG_MARGIN = 0.004  # and still be 4 points above expected FG

DRY_HOP_DEFAULT_PERCENT = 65.0  # of the way from OG to expected FG, when the batch sets no gravity

# Ready-to-crash rule (tilt_ui-v25i, tilt_ui-w2zj). The READY_WINDOW span is cut
# into READY_EDGE buckets; medians ride out Tilt noise.
# ponytail: fixed thresholds, re-tune on real batches (Tilt temp drift can move 1 pt)
READY_WINDOW = timedelta(hours=48)
READY_EDGE = timedelta(hours=4)
READY_MAX_CHANGE = 0.002  # every bucket median within this of the latest SG
READY_MAX_GAP = timedelta(hours=6)  # longer gap in the window = no evidence it held
CRASH_TEMP_DROP_C = 4.0  # wort this far below its temp at the alert = a crash we were not told about
READY_MIN_RECENT = 3  # readings behind the latest SG (from the last READY_EDGE, else the last 3)

# Sensing alert thresholds (tilt_ui-lgtu; from sensing-anomaly.md, not yet
# exercised on a real batch - re-tune with tilt_ui-xrq5.7)
TEMP_DEBOUNCE = timedelta(minutes=30)  # out of yeast range this long before alerting
RUNAWAY_MARGIN_C = 2.0  # above target by more than this...
RUNAWAY_RATE_C_PER_H = 1.5  # ...and rising at least this fast over RUNAWAY_WINDOW
RUNAWAY_WINDOW = timedelta(minutes=30)
BATTERY_LOW_PCT = 20  # raise below this
BATTERY_OK_PCT = 25  # clear at or above this (gap stops flapping)
OFFLINE_MIN = timedelta(minutes=30)  # offline = no stored reading for
OFFLINE_INTERVALS = 6  # max(OFFLINE_MIN, this many median report intervals)
OFFLINE_CHECK_SECONDS = 300

# When each (batch, temperature alert type) first went out of range. In memory
# only: a restart just restarts the 30 min wait.
_temp_out_since: dict[tuple[int, str], datetime] = {}


def _naive_utc(dt: datetime) -> datetime:
    """SQLite returns naive UTC, Postgres aware; compare everything as naive UTC."""
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


class AlertSeverity:
    """Alert severity constants."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


async def get_alert_context(
    session,
    batch_id: int,
    current_sg: Optional[float],
) -> dict:
    """Get context needed for alert detection (yeast temp range, progress)."""
    from sqlalchemy.orm import selectinload

    context = {
        "yeast_temp_min": None,
        "yeast_temp_max": None,
        "progress_percent": None,
        "og": None,
        "fg": None,
        "temp_target": None,
    }

    # Fetch batch with recipe and yeast eagerly loaded
    stmt = (
        select(Batch)
        .where(Batch.id == batch_id)
        .options(
            *batch_with_recipe_options(),
            selectinload(Batch.yeast_strain),
        )
    )
    result = await session.execute(stmt)
    batch = result.scalar_one_or_none()

    if not batch:
        return context

    # Get yeast temperature range (prefer batch override, then recipe yeast)
    if batch.yeast_strain:
        context["yeast_temp_min"] = batch.yeast_strain.temp_low
        context["yeast_temp_max"] = batch.yeast_strain.temp_high
    elif batch.recipe:
        culture = next(
            (c for c in batch.recipe.cultures if c.temp_min_c is not None or c.temp_max_c is not None),
            None,
        )
        if culture:
            context["yeast_temp_min"] = culture.temp_min_c
            context["yeast_temp_max"] = culture.temp_max_c

    # Target for the runaway rule: the batch override, else the global target
    # when this batch is under temperature control.
    context["temp_target"] = batch.temp_target
    if batch.temp_target is None and (batch.heater_entity_id or batch.cooler_entity_id):
        from backend.routers.config import get_config_value
        context["temp_target"] = await get_config_value(session, "temp_target")

    # Calculate progress if we have OG and current SG
    og = batch_expected_og(batch)
    fg = batch_expected_fg(batch)
    context["og"] = og
    context["fg"] = fg

    if og and fg and current_sg:
        expected_drop = og - fg
        if expected_drop > 0:
            actual_drop = og - current_sg
            progress = (actual_drop / expected_drop) * 100
            context["progress_percent"] = min(max(progress, 0), 100)

    return context


async def detect_and_persist_alerts(
    db: AsyncSession,
    batch_id: int,
    device_id: str,
    reading: Reading,
    live_reading: dict,
    yeast_temp_min: Optional[float] = None,
    yeast_temp_max: Optional[float] = None,
    progress_percent: Optional[float] = None,
    og: Optional[float] = None,
    fg: Optional[float] = None,
    temp_target: Optional[float] = None,
    now: Optional[datetime] = None,
) -> list[FermentationAlert]:
    """
    Detect alert conditions and persist to database.

    Args:
        db: Database session
        batch_id: The batch ID
        device_id: The device ID
        reading: The Reading ORM object that was just saved
        live_reading: The live reading dict with ML data
        yeast_temp_min: Minimum yeast temperature tolerance (Celsius)
        yeast_temp_max: Maximum yeast temperature tolerance (Celsius)
        progress_percent: Fermentation progress percentage (0-100)
        og: Batch OG (measured, else recipe) for the stall rule
        fg: Expected FG (recipe) for the stall rule
        temp_target: Control target (Celsius) for the runaway rule
        now: Clock override for tests

    Returns:
        List of active alerts for this batch
    """
    now = now or datetime.now(timezone.utc)
    current_alerts: list[FermentationAlert] = []

    # A reading arrived, so the sensor is not offline.
    await _clear_alert(db, batch_id, AlertType.SENSOR_OFFLINE, now)

    # Get current temperature
    current_temp = live_reading.get("temp") if live_reading else None

    # --- Temperature Alerts ---
    # Each side of the yeast range is judged alone (a strain may list only one
    # limit). The alert is raised only after the wort has been out of range
    # for TEMP_DEBOUNCE, so one odd reading or a brief swing does not alert.
    if current_temp is not None:
        sides = (
            (AlertType.TEMPERATURE_LOW, yeast_temp_min, "below", "minimum",
             yeast_temp_min is not None and current_temp < yeast_temp_min),
            (AlertType.TEMPERATURE_HIGH, yeast_temp_max, "above", "maximum",
             yeast_temp_max is not None and current_temp > yeast_temp_max),
        )
        for alert_type, limit, direction, limit_name, out_of_range in sides:
            key = (batch_id, alert_type)
            if not out_of_range:
                _temp_out_since.pop(key, None)
                await _clear_alert(db, batch_id, alert_type, now)
                continue
            if now - _temp_out_since.setdefault(key, now) < TEMP_DEBOUNCE:
                continue
            deviation = round(abs(current_temp - limit), 1)
            current_alerts.append(await _upsert_alert(
                db=db,
                batch_id=batch_id,
                device_id=device_id,
                alert_type=alert_type,
                severity=AlertSeverity.WARNING,
                message=f"Temperature is {deviation}°C {direction} yeast {limit_name} ({limit}°C)",
                context=json.dumps({
                    "current_temp": current_temp,
                    "yeast_temp_min": yeast_temp_min,
                    "yeast_temp_max": yeast_temp_max,
                    "deviation": deviation,
                }),
                trigger_reading_id=reading.id,
                now=now,
            ))

    # --- Temperature Runaway (tilt_ui-lgtu) ---
    # Well above target AND still climbing fast. Needs no yeast range. The
    # "climbing" test keeps a cold crash quiet (far above target, but falling).
    # Once raised it stays until the wort is back near target.
    if temp_target is None:
        # Target removed: nothing to judge against, so do not leave one stuck.
        await _clear_alert(db, batch_id, AlertType.TEMP_RUNAWAY, now)
    elif current_temp is not None:
        if current_temp <= temp_target + RUNAWAY_MARGIN_C:
            await _clear_alert(db, batch_id, AlertType.TEMP_RUNAWAY, now)
        else:
            # Anchor on the reading's own time: a late upload must be compared
            # with the readings around it, not with the wall clock.
            at = reading.timestamp or now
            ref = _naive_utc(at)
            past = (await db.execute(
                select(Reading.temp_calibrated, Reading.timestamp)
                .where(
                    Reading.batch_id == batch_id,
                    Reading.temp_calibrated.is_not(None),
                    Reading.timestamp <= at - RUNAWAY_WINDOW,
                    Reading.timestamp >= at - 2 * RUNAWAY_WINDOW,
                )
                .order_by(Reading.timestamp.desc())
                .limit(1)
            )).first()
            if past:
                hours = (ref - _naive_utc(past.timestamp)).total_seconds() / 3600
                rate = (current_temp - past.temp_calibrated) / hours
                if rate >= RUNAWAY_RATE_C_PER_H:
                    current_alerts.append(await _upsert_alert(
                        db=db,
                        batch_id=batch_id,
                        device_id=device_id,
                        alert_type=AlertType.TEMP_RUNAWAY,
                        severity=AlertSeverity.CRITICAL,
                        message=(
                            f"Temperature is {current_temp - temp_target:.1f}°C above target "
                            f"({temp_target}°C) and rising {rate:.1f}°C/hour"
                        ),
                        context=json.dumps({
                            "current_temp": current_temp,
                            "temp_target": temp_target,
                            "rate_c_per_hour": round(rate, 2),
                        }),
                        trigger_reading_id=reading.id,
                        now=now,
                    ))

    # --- Battery Alerts (tilt_ui-lgtu) ---
    # Only devices that report a battery level (RAPT, iSpindel, GravityMon).
    battery = live_reading.get("battery_percent") if live_reading else None
    if battery is not None:
        if battery < BATTERY_LOW_PCT:
            current_alerts.append(await _upsert_alert(
                db=db,
                batch_id=batch_id,
                device_id=device_id,
                alert_type=AlertType.BATTERY_LOW,
                severity=AlertSeverity.WARNING,
                message=f"Hydrometer battery is low ({battery:.0f}%)",
                context=json.dumps({"battery_percent": battery}),
                trigger_reading_id=reading.id,
                now=now,
            ))
        elif battery >= BATTERY_OK_PCT:
            await _clear_alert(db, batch_id, AlertType.BATTERY_LOW, now)

    # --- Anomaly Alerts (step change) ---
    # The detector flags a level shift once per event (tilt_ui-zbhm), so the
    # alert must NOT clear on the next normal reading or nobody would see it.
    # It stays until dismissed; a later step updates the same alert.
    if live_reading and live_reading.get("is_anomaly"):
        reasons = live_reading.get("anomaly_reasons") or []
        if "step_change_up" in reasons:
            message = "Gravity jumped up suddenly - dry hop, or the hydrometer was moved?"
        elif "step_change_down" in reasons:
            message = "Gravity dropped suddenly - was the hydrometer lifted or moved?"
        else:
            message = f"Anomaly detected: {reasons or 'unknown reason'}"
        alert = await _upsert_alert(
            db=db,
            batch_id=batch_id,
            device_id=device_id,
            alert_type=AlertType.ANOMALY,
            severity=AlertSeverity.WARNING,
            message=message,
            context=json.dumps({
                "anomaly_score": live_reading.get("anomaly_score"),
                "anomaly_reasons": reasons,
                "sg": live_reading.get("sg"),
                "temp": live_reading.get("temp"),
            }),
            trigger_reading_id=reading.id,
            now=now,
        )
        current_alerts.append(alert)

    # --- Stall Alerts (tilt_ui-zbhm) ---
    # Stalled = the trailing 12 h slope is flatter than 0.6 pt/day, AFTER the
    # beer has dropped at least 4 pt from OG (so lag phase never counts), and
    # it is still more than 4 pt above the expected FG. Without an FG the
    # alert is only INFO. Without OG or a full 12 h window: no judgement.
    slope_12h = live_reading.get("sg_slope_12h") if live_reading else None
    current_sg = live_reading.get("sg") if live_reading else None
    stalled = (
        slope_12h is not None
        and og is not None
        and current_sg is not None
        and slope_12h > -STALL_MAX_SLOPE
        and og - current_sg >= STALL_MIN_DROP
        and (fg is None or current_sg - fg > STALL_FG_MARGIN)
    )
    if stalled:
        alert = await _upsert_alert(
            db=db,
            batch_id=batch_id,
            device_id=device_id,
            alert_type=AlertType.STALL,
            severity=AlertSeverity.WARNING if fg is not None else AlertSeverity.INFO,
            message="Fermentation appears stalled - gravity has barely moved in 12 hours",
            context=json.dumps({
                "sg_slope_12h": slope_12h,
                "points_per_day": round(-slope_12h * 24 * 1000, 2),
                "og": og,
                "expected_fg": fg,
                "progress_percent": progress_percent,
                "sg": current_sg,
            }),
            trigger_reading_id=reading.id,
            now=now,
        )
        current_alerts.append(alert)
    else:
        await _clear_alert(db, batch_id, AlertType.STALL, now)

    alert = await _dry_hop_alert(db, batch_id, device_id, reading, current_sg, now)
    if alert:
        current_alerts.append(alert)

    alert = await _crash_ready_alert(db, batch_id, device_id, reading, fg, temp_target, now)
    if alert:
        current_alerts.append(alert)

    return current_alerts


def _pts(diff: float) -> float:
    """SG difference rounded to 0.1 point: 1.014 - 1.010 is 0.0040000000000000036
    as a float, which would fail an "at most 4 points" test."""
    return round(diff, 4)


async def _crash_ready_alert(
    db: AsyncSession,
    batch_id: int,
    device_id: str,
    reading: Reading,
    fg: Optional[float],
    temp_target: Optional[float],
    now: datetime,
) -> Optional[FermentationAlert]:
    """Ready-to-cold-crash notice (tilt_ui-v25i).

    Looks at the last READY_WINDOW of valid readings, cut into READY_EDGE
    buckets counted back from this reading. Raised when the data covers the
    whole window with no gap over READY_MAX_GAP (up to now), every bucket
    median is within READY_MAX_CHANGE of the latest SG, the slope fitted to
    the bucket medians falls slower than STALL_MAX_SLOPE, and the latest SG is
    no more than STALL_FG_MARGIN above the expected FG (below FG = finished
    dry, still ready). "Latest SG" is the median of the last READY_EDGE, or of
    the last READY_MIN_RECENT readings when the sensor reports less often.
    Blocked by no expected FG (flat and high is a stall) or a dry hop block.
    When the only block is a planned dry hop never marked done, a
    crash_wait_dry_hop notice says so instead; it stays until the dry hop is
    marked done, the plan changes or the crash starts. Ended by the crash or
    dismissed, it is final; after a plan change it may come back (tilt_ui-8ih3).

    A dismissal is final; leaving fermenting or a cold-crash target ends it for
    good (end_crash_ready). While up, it clears with a "rearm" marker when the
    latest SG moves more than READY_MAX_CHANGE from the alerted value (hop
    creep, a sugar addition), or at once when the FG is removed or a dry hop
    block appears; it may then return only READY_WINDOW after that reading
    (tilt_ui-zwwy, tilt_ui-w2zj)."""
    from backend.temp_controller import REST_MIN_ACTIVE_TARGET_C  # temp_controller imports this module

    batch = await db.get(Batch, batch_id)
    previous = (await db.execute(select(FermentationAlert).where(
        FermentationAlert.batch_id == batch_id,
        FermentationAlert.alert_type == AlertType.CRASH_READY,
    ).order_by(FermentationAlert.first_detected_at.desc(), FermentationAlert.id.desc()).limit(1))).scalar_one_or_none()
    ctx = json.loads(previous.context or "{}") if previous is not None else {}
    if batch is None or batch.status != "fermenting" or (
        temp_target is not None and temp_target < REST_MIN_ACTIVE_TARGET_C
    ):
        await end_crash_ready(db, batch_id, now)
        return None
    at = reading.timestamp or now
    ref = _naive_utc(at)
    rows = (await db.execute(
        select(Reading.sg_calibrated, Reading.timestamp, Reading.temp_calibrated).where(
            Reading.batch_id == batch_id,
            Reading.sg_calibrated.is_not(None),
            Reading.status == "valid",
            Reading.timestamp >= ref - READY_WINDOW - READY_MAX_GAP,
            Reading.timestamp <= ref,
        ).order_by(Reading.timestamp)
    )).all()
    points = [(_naive_utc(r.timestamp), r.sg_calibrated) for r in rows]
    window = [(t, sg) for t, sg in points if t >= ref - READY_WINDOW]
    recent = [sg for t, sg in window if t >= ref - READY_EDGE]
    if len(recent) < READY_MIN_RECENT:
        # Sparse sensor: its last few readings, if none of them sit across a
        # dropout (readings from before an outage are not "latest").
        tail = window[-READY_MIN_RECENT:]
        steps = [t for t, _ in tail] + [ref]
        fresh = all(b - a <= READY_MAX_GAP for a, b in zip(steps, steps[1:]))
        recent = [sg for _, sg in tail] if fresh else []
    new_sg = statistics.median(recent) if len(recent) >= READY_MIN_RECENT else None
    # Wort temperature: median of the last few valid readings, so one bad
    # temperature cannot end anything (tilt_ui-y6za).
    temp_tail = [(_naive_utc(r.timestamp), r.temp_calibrated) for r in rows if r.temp_calibrated is not None][-READY_MIN_RECENT:]
    temp_steps = [t for t, _ in temp_tail] + [ref]
    wort_temp = (
        statistics.median(c for _, c in temp_tail)
        if len(temp_tail) == READY_MIN_RECENT
        and all(b - a <= READY_MAX_GAP for a, b in zip(temp_steps, temp_steps[1:]))
        else None
    )
    if wort_temp is not None and wort_temp < REST_MIN_ACTIVE_TARGET_C:
        # A crash the app was not told about (fermenter moved to a fridge,
        # target left alone): no lager ferments this cold.
        await end_crash_ready(db, batch_id, now)
        return None
    dry_hop = await _crash_ready_dry_hop_block(db, batch, ref)
    # Its message names the FG; checked before the readiness guards so a gap
    # or a gravity move cannot hide a plan change.
    await _replan_wait(db, batch_id, now, None if dry_hop != "planned" or fg is None else fg)
    other_blocked = fg is None or await _crash_ready_rest_block(db, batch, ref, new_sg, pending=False)
    plan_blocked = other_blocked or dry_hop is not None
    dry_hopped = batch.dry_hop_done_at is not None

    if previous is not None and previous.cleared_at is None:
        # The FG margin is not re-checked here: "moved" already bounds drift,
        # and re-checking it would flap an alert raised right at the margin.
        moved = (
            new_sg is not None and ctx.get("sg") is not None
            and _pts(abs(new_sg - ctx["sg"])) > READY_MAX_CHANGE
        )
        # Any FG edit is the brewer's own plan change, like removing it.
        fg_changed = fg is not None and ctx.get("expected_fg") is not None and _pts(abs(fg - ctx["expected_fg"])) > 0
        plan_blocked = plan_blocked or fg_changed
        if not moved and not plan_blocked:
            previous.last_seen_at = now
            if wort_temp is not None and wort_temp > (ctx.get("temp") or -100.0):
                # Warmest seen while up: a crash is judged from here, not from
                # an earlier, cooler reading.
                previous.context = json.dumps({**ctx, "temp": wort_temp})
            return previous  # includes too few readings to judge a change
        _rearm(previous, ref, now)
        cooling = (
            wort_temp is not None and ctx.get("temp") is not None
            and ctx["temp"] - wort_temp > CRASH_TEMP_DROP_C
        )
        # Cooling hard (crash starting, target left alone) reads the hydrometer
        # high: that explains a rise, not a fall. The alert still comes down.
        if moved and not plan_blocked and cooling and new_sg > ctx["sg"]:
            # Maybe a crash we were not told about (cold reads high). Mark the
            # alert so its held SG can still become the FG if the crash is
            # confirmed (wort below 5 C); not saved now, as a cool night on an
            # uncontrolled batch looks the same (tilt_ui-r1hq).
            previous.context = json.dumps({**json.loads(previous.context or "{}"), "cooled": True})
            return None
        if moved and not plan_blocked:
            # Say why it went away: a quiet disappearance reads as "crash done".
            # A plan change (FG, dry hop) is the brewer's own act: no notice.
            return await _crash_not_ready_alert(
                db, batch_id, device_id, reading, ctx["sg"], new_sg, dry_hopped, now
            )
        return None
    not_ready = None
    if previous is not None:
        if not ctx.get("rearm"):
            return None  # dismissed, or ended by the crash: final
        not_ready = (await db.execute(select(FermentationAlert).where(
            FermentationAlert.batch_id == batch_id,
            FermentationAlert.alert_type == AlertType.CRASH_NOT_READY,
            FermentationAlert.cleared_at.is_(None),
        ).order_by(FermentationAlert.id.desc()).limit(1))).scalar_one_or_none()
        if not_ready is not None:
            held = json.loads(not_ready.context or "{}").get("held_sg")
            if plan_blocked:
                await _clear_alert(db, batch_id, AlertType.CRASH_NOT_READY, now)  # its promise no longer holds
                not_ready = None
            elif new_sg is not None and held is not None:
                # Keep the numbers current while gravity moves, either way (no new push).
                not_ready = await _crash_not_ready_alert(db, batch_id, device_id, reading, held, new_sg, dry_hopped, now)
            else:
                not_ready.last_seen_at = now
        cleared = datetime.fromisoformat(ctx["rearm_from"]) if "rearm_from" in ctx else _naive_utc(previous.cleared_at)
        if ref - cleared < READY_WINDOW:
            return not_ready  # wait a full new window after it cleared
    # An unmarked dry hop alone still runs the checks, to say why it waits.
    if (other_blocked or dry_hop not in (None, "planned") or new_sg is None
            or await _crash_ready_rest_block(db, batch, ref, new_sg)):
        return not_ready

    before = [p for p in points if p[0] < ref - READY_WINDOW]
    if not before and (not window or window[0][0] > ref - READY_WINDOW):
        return not_ready  # less than READY_WINDOW of data
    span = before[-1:] + window + [(ref, None)]
    if any(b[0] - a[0] > READY_MAX_GAP for a, b in zip(span, span[1:])):
        return not_ready  # an outage or pause in the window (or since): flat is not proven
    last_bucket = int(READY_WINDOW / READY_EDGE) - 1
    buckets: dict[int, list[tuple[datetime, float]]] = {}
    for t, sg in window:
        buckets.setdefault(min(int((ref - t) / READY_EDGE), last_bucket), []).append((t, sg))
    medians = {k: statistics.median(sg for _, sg in v) for k, v in buckets.items()}
    if any(_pts(abs(m - new_sg)) > READY_MAX_CHANGE for m in medians.values()):
        return not_ready  # moved somewhere in the window (rise and return, still falling)
    if len(medians) < 2:
        return not_ready
    # Medians, not raw readings: one stray reading must not tilt the slope. Each
    # median sits at its readings' mean time (buckets can be partly filled).
    hours = [statistics.fmean((t - ref).total_seconds() / 3600 for t, _ in buckets[k]) for k in medians]
    slope = statistics.linear_regression(hours, list(medians.values())).slope
    if round(slope, 9) < -STALL_MAX_SLOPE:  # rounded: an exact 0.6 pt/day fit lands a hair over
        return not_ready  # a slow steady fall: still fermenting
    # Checked after the window (not before) so a "not ready" warning still
    # clears when gravity settles flat but high: that is a stall, not a wait.
    await _clear_alert(db, batch_id, AlertType.CRASH_NOT_READY, now)
    if _pts(new_sg - fg) > STALL_FG_MARGIN:
        return None
    old_sg = medians[max(medians)]
    if dry_hop == "planned":
        if (await db.execute(select(FermentationAlert.id).where(
            FermentationAlert.batch_id == batch_id,
            FermentationAlert.alert_type == AlertType.CRASH_WAIT_DRY_HOP,
            FermentationAlert.cleared_at.is_not(None),
            FermentationAlert.context.not_like('%"replan": true%'),
        ).limit(1))).first():
            return None  # ended by the crash or dismissed: final, no repeat push
        return await _upsert_alert(
            db=db,
            batch_id=batch_id,
            device_id=device_id,
            alert_type=AlertType.CRASH_WAIT_DRY_HOP,
            severity=AlertSeverity.INFO,
            message=(
                f"Gravity held at {new_sg:.3f} for 48 hours (expected FG {fg:.3f}), "
                "but the recipe's dry hop is not marked done. Mark it dry hopped: "
                "the cold crash notice comes once gravity holds for 48 hours after that."
            ),
            context=json.dumps({"sg": new_sg, "sg_48h_ago": old_sg, "expected_fg": fg}),
            trigger_reading_id=reading.id,
            now=now,
        )
    return await _upsert_alert(
        db=db,
        batch_id=batch_id,
        device_id=device_id,
        alert_type=AlertType.CRASH_READY,
        severity=AlertSeverity.INFO,
        message=(
            f"Gravity has held at {new_sg:.3f} for 48 hours (expected FG {fg:.3f}). "
            "Check for diacetyl, then cold crash."
        ),
        context=json.dumps({"sg": new_sg, "sg_48h_ago": old_sg, "expected_fg": fg, "temp": wort_temp}),
        trigger_reading_id=reading.id,
        now=now,
    )


async def _crash_not_ready_alert(
    db: AsyncSession,
    batch_id: int,
    device_id: str,
    reading: Reading,
    held_sg: float,
    new_sg: float,
    dry_hopped: bool,
    now: datetime,
) -> FermentationAlert:
    """Warning + push: the ready-to-crash notice was withdrawn because gravity
    moved (tilt_ui-y6za). Cleared when crash_ready is raised again or ends."""
    points = abs(new_sg - held_sg) * 1000
    if _pts(abs(new_sg - held_sg)) <= READY_MAX_CHANGE:
        # Back near where it held (refresh of an up warning): no direction to explain.
        message = (
            f"Gravity moved after holding at {held_sg:.3f} and is now {new_sg:.3f}. "
            "Do not cold crash yet: wait until gravity holds for 48 hours again."
        )
    elif new_sg < held_sg:
        message = (
            f"Gravity fell {points:.1f} points after holding at {held_sg:.3f} (now {new_sg:.3f}). "
            + ("Likely hop creep after the dry hop, " if dry_hopped else "Likely late fermentation, ")
            + "which can bring diacetyl back. "
            "Do not cold crash yet: wait until gravity holds for 48 hours again."
        )
    else:
        message = (
            f"Gravity rose {points:.1f} points after holding at {held_sg:.3f} (now {new_sg:.3f}). "
            "An addition, or the hydrometer moved? "
            "Do not cold crash yet: wait until gravity holds for 48 hours again."
        )
    return await _upsert_alert(
        db=db,
        batch_id=batch_id,
        device_id=device_id,
        alert_type=AlertType.CRASH_NOT_READY,
        severity=AlertSeverity.WARNING,
        message=message,
        context=json.dumps({"held_sg": held_sg, "sg": new_sg}),
        trigger_reading_id=reading.id,
        now=now,
    )


def _rearm(alert: FermentationAlert, ref: datetime, now: datetime) -> None:
    """Clear a crash_ready alert that is no longer true. "rearm" tells this
    from a dismissal; the alert may come back READY_WINDOW after ``ref``."""
    alert.context = json.dumps({**json.loads(alert.context or "{}"), "rearm": True, "rearm_from": ref.isoformat()})
    alert.cleared_at = now


async def _replan_wait(db: AsyncSession, batch_id: int, now: datetime, fg: Optional[float] = None) -> None:
    """Clear an up crash_wait_dry_hop after a plan change, not an ending:
    "replan" lets it come back if the plan returns (FG set again, dry hop
    put back in the recipe). With ``fg``, only if the FG was edited so the
    SG the notice held at is now a stall (judged on the held SG, not the
    latest readings, so gravity drifting up and back cannot clear it)."""
    wait = (await db.execute(select(FermentationAlert).where(
        FermentationAlert.batch_id == batch_id,
        FermentationAlert.alert_type == AlertType.CRASH_WAIT_DRY_HOP,
        FermentationAlert.cleared_at.is_(None),
    ))).scalar_one_or_none()
    held = json.loads(wait.context or "{}").get("sg") if wait is not None else None
    if wait is not None and (fg is None or (held is not None and _pts(held - fg) > STALL_FG_MARGIN)):
        wait.cleared_at = now
        wait.context = json.dumps({**json.loads(wait.context or "{}"), "replan": True})


async def rearm_crash_ready(db: AsyncSession, batch_id: int, now: datetime) -> None:
    """Take down an up crash_ready alert now, without waiting for the next
    reading; it may come back READY_WINDOW later. Used when the dry hop goes
    in (tilt_ui-w2zj) and for the brewer's "Not yet" (tilt_ui-ifmj)."""
    alert = (await db.execute(select(FermentationAlert).where(
        FermentationAlert.batch_id == batch_id,
        FermentationAlert.alert_type == AlertType.CRASH_READY,
        FermentationAlert.cleared_at.is_(None),
    ))).scalar_one_or_none()
    if alert is not None:
        _rearm(alert, _naive_utc(now), now)


async def _crash_ready_dry_hop_block(db: AsyncSession, batch: Batch, ref: datetime) -> Optional[str]:
    """Why a dry hop blocks crash_ready, or None: "due" (its reminder is up),
    "settling" (done less than READY_WINDOW ago: extraction and hop creep need
    time; the old window is pre-dry-hop) or "planned" (in the recipe, not
    marked done, reminder not up)."""
    if (await db.execute(select(FermentationAlert.id).where(
        FermentationAlert.batch_id == batch.id,
        FermentationAlert.alert_type == AlertType.DRY_HOP_DUE,
        FermentationAlert.cleared_at.is_(None),
    ).limit(1))).first():
        return "due"
    if batch.dry_hop_done_at is not None:
        return "settling" if ref - _naive_utc(batch.dry_hop_done_at) < READY_WINDOW else None
    if batch.recipe_id is not None and any(
        (h.timing or {}).get("use") in ("dry_hop", "add_to_fermentation")
        for h in (await db.execute(select(RecipeHop).where(RecipeHop.recipe_id == batch.recipe_id))).scalars()
    ):
        return "planned"
    return None


async def _crash_ready_rest_block(
    db: AsyncSession, batch: Batch, ref: datetime, sg: Optional[float], pending: bool = True,
) -> bool:
    """The automatic diacetyl rest started (raised the target) less than
    READY_WINDOW ago, or (``pending``) is still to come: the yeast needs that
    time warm to clean up diacetyl before a crash (tilt_ui-n8n5).

    Not a block: a rule that will never fire (controller not running it, no
    heater/cooler, blocked, gravity settled above its trigger), a rule that
    does not raise the target (already at or above the rest temperature: it
    has been warm all along), a rule switched off, or a rest the brewer ended
    early by lowering the target. ``pending`` is off for an alert already up,
    so gravity noise around the trigger cannot pull it down and put it back."""
    from backend.models import ControlEvent
    from backend.temp_controller import controller_running, get_rest_rule_status  # temp_controller imports this module

    if batch.rest_trigger_percent is None or batch.rest_temp_target is None:
        return False  # rule off (also if switched off after it fired)
    if batch.rest_fired_at is not None:
        if batch.temp_target is not None and batch.temp_target < batch.rest_temp_target:
            return False  # brewer ended the rest early (e.g. a clean forced VDK test)
        if ref - _naive_utc(batch.rest_fired_at) >= READY_WINDOW:
            return False
        # A real rest logs "rest_start"; a no-op firing (already warm) does not.
        # Only this firing's event: a re-armed rule (rest edited) can fire again.
        return (await db.execute(select(ControlEvent.id).where(
            ControlEvent.batch_id == batch.id, ControlEvent.action == "rest_start",
            ControlEvent.timestamp >= _naive_utc(batch.rest_fired_at) - timedelta(minutes=1),
        ).limit(1))).first() is not None
    if not pending or not await controller_running(db):
        return False
    status = await get_rest_rule_status(db, batch, controller_on=True)
    if status is None or status["state"] not in ("waiting", "holding") or not status["will_raise"]:
        return False
    # Flat above the trigger: the rule fires only at or below it, so never (a
    # stale "holding" from one noisy dip counts the same).
    return not (sg is not None and status["trigger_sg"] is not None and _pts(sg - status["trigger_sg"]) > 0)


async def crash_ready_held_sg(db: AsyncSession, batch_id: int) -> Optional[float]:
    """The SG the latest ready-to-crash notice held at: if it is up, or if it
    came down only because the wort was cooling ("cooled", still waiting to
    re-raise) and no valid reading since has fallen more than READY_MAX_CHANGE
    below it (a fall means fermentation went on, so the old SG is not final).
    This is the warm, settled final gravity: once the crash starts, cold wort
    and dissolved CO2 make a hydrometer read several points high (tilt_ui-r1hq)."""
    alert = (await db.execute(select(FermentationAlert).where(
        FermentationAlert.batch_id == batch_id,
        FermentationAlert.alert_type == AlertType.CRASH_READY,
    ).order_by(FermentationAlert.first_detected_at.desc(), FermentationAlert.id.desc()).limit(1))).scalar_one_or_none()
    if alert is None:
        return None
    ctx = json.loads(alert.context or "{}")
    held = ctx.get("sg")
    if held is None or alert.cleared_at is None:
        return held
    if not (ctx.get("cooled") and ctx.get("rearm") and ctx.get("rearm_from")):
        return None
    lowest = (await db.execute(select(func.min(Reading.sg_calibrated)).where(
        Reading.batch_id == batch_id,
        Reading.status == "valid",
        Reading.timestamp >= datetime.fromisoformat(ctx["rearm_from"]),
    ))).scalar()
    return None if lowest is not None and _pts(held - lowest) > READY_MAX_CHANGE else held


def set_measured_fg(batch: Batch, fg: float) -> None:
    """Set the measured FG, and ABV and attenuation when the OG is known."""
    batch.measured_fg = fg
    if batch.measured_og and batch.measured_og > 1.0:  # 1.000 would divide by zero
        batch.measured_abv = (batch.measured_og - fg) * 131.25
        batch.measured_attenuation = ((batch.measured_og - fg) / (batch.measured_og - 1.0)) * 100


async def end_crash_ready(db: AsyncSession, batch_id: int, now: datetime) -> bool:
    """Batch left fermenting or started its crash: clear the notice and cancel
    any pending re-raise, so it is final. Returns True if anything changed.

    If the notice was up, its held SG becomes the batch's measured FG (when
    none is set): readings taken during the crash read high (tilt_ui-r1hq).
    A notice that came down only because the wort was cooling counts too
    (see crash_ready_held_sg)."""
    changed = False
    held = await crash_ready_held_sg(db, batch_id)
    if held is not None:
        batch = await db.get(Batch, batch_id)
        if batch is not None and batch.measured_fg is None and batch.status not in ("planning", "brewing", "archived"):
            set_measured_fg(batch, held)
            changed = True
    changed = await _clear_alert(db, batch_id, AlertType.CRASH_READY, now) or changed
    changed = await _clear_alert(db, batch_id, AlertType.CRASH_NOT_READY, now) or changed
    changed = await _clear_alert(db, batch_id, AlertType.CRASH_WAIT_DRY_HOP, now) or changed
    for alert in (await db.execute(select(FermentationAlert).where(
        FermentationAlert.batch_id == batch_id,
        FermentationAlert.alert_type == AlertType.CRASH_READY,
        FermentationAlert.context.like('%"rearm": true%'),
    ))).scalars():
        alert.context = json.dumps({**json.loads(alert.context), "rearm": False})
        changed = True
    for alert in (await db.execute(select(FermentationAlert).where(
        FermentationAlert.batch_id == batch_id,
        FermentationAlert.alert_type == AlertType.CRASH_WAIT_DRY_HOP,
        FermentationAlert.context.like('%"replan": true%'),
    ))).scalars():
        alert.context = json.dumps({**json.loads(alert.context), "replan": False})
        changed = True
    return changed


async def _dry_hop_alert(
    db: AsyncSession,
    batch_id: int,
    device_id: str,
    reading: Reading,
    current_sg: Optional[float],
    now: datetime,
) -> Optional[FermentationAlert]:
    """Dry hop reminder (tilt_ui-n1w7). OG/FG come from the batch's expected
    numbers, so a recipe edit does not move a running batch (tilt_ui-4x2f.3). Once raised it stays until marked done:
    it is only raised or refreshed here, never cleared by gravity noise."""
    from backend.temp_controller import rest_trigger_sg  # temp_controller imports this module

    row = (await db.execute(
        select(Batch).options(*batch_with_recipe_options()).where(Batch.id == batch_id)
        .execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if row is None or row.status != "fermenting" or row.dry_hop_done_at is not None:
        await _clear_alert(db, batch_id, AlertType.DRY_HOP_DUE, now)
        return None
    if current_sg is None or row.recipe_id is None:
        return None
    trigger = row.dry_hop_trigger_sg or rest_trigger_sg(
        batch_expected_og(row), batch_expected_fg(row), DRY_HOP_DEFAULT_PERCENT
    )
    if trigger is None or current_sg > trigger:
        # Not (or no longer) at the trigger: keep an alert that is already up.
        return (await db.execute(select(FermentationAlert).where(
            FermentationAlert.batch_id == batch_id,
            FermentationAlert.alert_type == AlertType.DRY_HOP_DUE,
            FermentationAlert.cleared_at.is_(None),
        ))).scalar_one_or_none()
    hops = [
        h for h in (await db.execute(select(RecipeHop).where(RecipeHop.recipe_id == row.recipe_id))).scalars()
        if (h.timing or {}).get("use") in ("dry_hop", "add_to_fermentation")
    ]
    if not hops:
        return None
    def dose(h) -> str:  # liquid extracts are dosed by volume
        return f"{h.amount_ml:g} mL" if not h.amount_grams and h.amount_ml else f"{h.amount_grams:g} g"
    names = ", ".join(f"{h.name} {dose(h)}" for h in hops)
    return await _upsert_alert(
        db=db,
        batch_id=batch_id,
        device_id=device_id,
        alert_type=AlertType.DRY_HOP_DUE,
        severity=AlertSeverity.WARNING,
        message=f"Dry hop now: {names} (gravity {current_sg:.3f}, planned at {trigger:.3f})",
        context=json.dumps({
            "trigger_sg": trigger,
            "sg": current_sg,
            "hops": [{"name": h.name, "amount_grams": h.amount_grams, "amount_ml": h.amount_ml} for h in hops],
        }),
        trigger_reading_id=reading.id,
        now=now,
    )


async def _upsert_alert(
    db: AsyncSession,
    batch_id: int,
    device_id: str,
    alert_type: str,
    severity: str,
    message: str,
    context: Optional[str],
    trigger_reading_id: Optional[int],
    now: datetime,
) -> FermentationAlert:
    """
    Create a new alert or update an existing active alert.

    If an active alert of this type exists for this batch, update its last_seen_at.
    Otherwise, create a new alert.
    """
    # Look for existing active alert of this type
    stmt = select(FermentationAlert).where(
        FermentationAlert.batch_id == batch_id,
        FermentationAlert.alert_type == alert_type,
        FermentationAlert.cleared_at.is_(None),
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        # Update existing alert
        existing.last_seen_at = now
        existing.message = message  # Update message with latest values
        existing.context = context
        existing.trigger_reading_id = trigger_reading_id
        logger.debug(f"Updated existing {alert_type} alert for batch {batch_id}")
        return existing
    else:
        # Create new alert
        alert = FermentationAlert(
            batch_id=batch_id,
            device_id=device_id,
            alert_type=alert_type,
            severity=severity,
            message=message,
            context=context,
            trigger_reading_id=trigger_reading_id,
            first_detected_at=now,
            last_seen_at=now,
        )
        db.add(alert)
        logger.info(f"Created new {alert_type} alert for batch {batch_id}: {message}")
        title = PUSH_TITLES.get(alert_type)
        if title:
            batch = await db.get(Batch, batch_id)
            if batch and batch.name:
                title = f"{title}: {batch.name}"
            push.notify_soon(title, message, f"/batches/{batch_id}")
        return alert


async def _clear_alert(
    db: AsyncSession,
    batch_id: int,
    alert_type: str,
    now: datetime,
) -> bool:
    """
    Clear an active alert of the given type.

    Returns True if an alert was cleared, False if no active alert existed.
    """
    stmt = select(FermentationAlert).where(
        FermentationAlert.batch_id == batch_id,
        FermentationAlert.alert_type == alert_type,
        FermentationAlert.cleared_at.is_(None),
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        existing.cleared_at = now
        logger.info(f"Cleared {alert_type} alert for batch {batch_id}")
        return True
    return False


async def check_offline_sensors(db: AsyncSession, now: Optional[datetime] = None) -> int:
    """Raise/clear sensor_offline for every active batch with a device (tilt_ui-lgtu).

    Offline = no stored reading for max(OFFLINE_MIN, OFFLINE_INTERVALS x the
    device's median report interval). Must run on a timer: the ingest path
    cannot notice a reading that never came. A batch with fewer than 3
    readings gets no judgement (its report interval is not known yet, and an
    hourly reporter would trip the 30 min floor). Returns how many batches
    are offline.
    """
    now = now or datetime.now(timezone.utc)
    ref = _naive_utc(now)
    batches = (await db.execute(
        select(Batch.id, Batch.device_id).where(
            Batch.status.in_(("fermenting", "conditioning")),
            Batch.deleted_at.is_(None),
            Batch.device_id.is_not(None),
        )
    )).all()
    # A batch that finished or lost its device must not keep the alert forever.
    watched = [b.id for b in batches]
    for orphan in (await db.execute(
        select(FermentationAlert).where(
            FermentationAlert.alert_type == AlertType.SENSOR_OFFLINE,
            FermentationAlert.cleared_at.is_(None),
            FermentationAlert.batch_id.not_in(watched),
        )
    )).scalars().all():
        orphan.cleared_at = now
    offline = 0
    for batch_id, device_id in batches:
        stamps = [_naive_utc(t) for t in (await db.execute(
            select(Reading.timestamp)
            .where(Reading.batch_id == batch_id)
            .order_by(Reading.timestamp.desc())
            .limit(21)
        )).scalars().all()]
        if len(stamps) < 3:
            await _clear_alert(db, batch_id, AlertType.SENSOR_OFFLINE, now)
            continue
        gaps = [a - b for a, b in zip(stamps, stamps[1:])]
        limit = max(OFFLINE_MIN, OFFLINE_INTERVALS * statistics.median(gaps))
        age = ref - stamps[0]
        # The temperature controller already raises a critical sensor_stale
        # alert for batches it controls; do not double up.
        stale = (await db.execute(
            select(FermentationAlert.id).where(
                FermentationAlert.batch_id == batch_id,
                FermentationAlert.alert_type == AlertType.SENSOR_STALE,
                FermentationAlert.cleared_at.is_(None),
            ).limit(1)
        )).first()
        if age > limit and not stale:
            offline += 1
            await _upsert_alert(
                db=db,
                batch_id=batch_id,
                device_id=device_id,
                alert_type=AlertType.SENSOR_OFFLINE,
                severity=AlertSeverity.WARNING,
                message=f"No reading from the hydrometer for {_format_age(age)}",
                context=json.dumps({
                    "last_reading_at": stamps[0].isoformat() + "Z",
                    "limit_minutes": round(limit.total_seconds() / 60),
                }),
                trigger_reading_id=None,
                now=now,
            )
        else:
            await _clear_alert(db, batch_id, AlertType.SENSOR_OFFLINE, now)
    await db.commit()
    return offline


def _format_age(age: timedelta) -> str:
    minutes = int(age.total_seconds() // 60)
    return f"{minutes} minutes" if minutes < 120 else f"{minutes // 60} hours"


async def offline_watch_loop(session_factory, interval_seconds: float = OFFLINE_CHECK_SECONDS) -> None:
    """Run check_offline_sensors forever. Sleeps first so the scanner can report after startup."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            async with session_factory() as db:
                await check_offline_sensors(db)
        except Exception:
            logger.exception("Offline sensor check failed")


async def get_active_alerts(
    db: AsyncSession,
    batch_id: int,
) -> list[FermentationAlert]:
    """Get all active (non-cleared) alerts for a batch."""
    stmt = (
        select(FermentationAlert)
        .where(
            FermentationAlert.batch_id == batch_id,
            FermentationAlert.cleared_at.is_(None),
        )
        .order_by(FermentationAlert.first_detected_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_alert_history(
    db: AsyncSession,
    batch_id: int,
    include_cleared: bool = True,
    limit: int = 50,
) -> list[FermentationAlert]:
    """Get alert history for a batch."""
    stmt = (
        select(FermentationAlert)
        .where(FermentationAlert.batch_id == batch_id)
    )
    if not include_cleared:
        stmt = stmt.where(FermentationAlert.cleared_at.is_(None))

    stmt = stmt.order_by(FermentationAlert.first_detected_at.desc()).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())
