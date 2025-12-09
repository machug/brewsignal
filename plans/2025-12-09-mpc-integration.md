# MPC Temperature Control Integration Plan

**Date:** 2025-12-09
**Issue:** #69 - Integrate MPC into temperature controller to prevent overshoot
**Status:** Planning

## Problem Statement

The current temperature controller uses basic symmetric hysteresis which causes overshoot:
- Heater turns ON at `target - hysteresis` (e.g., 19.0°C)
- Heater stays ON until `target + hysteresis` (e.g., 21.0°C)
- This overshoots by 1°C because it doesn't predict when to turn off

**Production observation (Batch #2):**
- Target: 20.0°C, Hysteresis: ±1.0°C
- Current: 20.3°C, Heater: ON (will continue until 21.0°C)

## Solution: Model Predictive Control (MPC)

Use physics-based thermal model to predict temperature trajectory and prevent overshoot.

### MPC Advantages
- Predicts temperature N hours ahead
- Computes optimal ON/OFF timing to hit target without overshoot
- Uses `temp_rate` from Kalman filter (already available from PR #66)
- Physics-based instead of simple thresholds

### Existing Code
MPC implementation already exists: `backend/ml/control/mpc.py`
- `MPCTemperatureController` class
- `learn_thermal_model()` - learns from historical data
- `compute_action()` - returns optimal heater/cooler decisions
- `predict_trajectory()` - forecasts temperature

## Implementation Plan

### 1. Add MPC Configuration Settings
**File:** `backend/database.py`, `backend/routers/config.py`

Add config fields:
```python
mpc_enabled: bool = False  # Backward compatible default
mpc_horizon_hours: float = 4.0  # Prediction horizon
mpc_learning_window_hours: float = 24.0  # History for learning
```

### 2. Initialize MPC Controllers
**File:** `backend/temp_controller.py`

Add global state:
```python
_batch_mpc_controllers: dict[int, MPCTemperatureController] = {}
```

Lifecycle:
- Create MPC instance on first control check for batch
- Clean up when batch leaves fermenting/conditioning (similar to heater/cooler state cleanup)

### 3. Thermal Model Learning
**File:** `backend/temp_controller.py` (new helper function)

Query historical data:
```python
async def learn_mpc_model_for_batch(batch_id: int, device_id: str, db) -> bool:
    # Query last 24 hours of:
    # - readings (temp_calibrated or temp_filtered, timestamp)
    # - control_events (heater/cooler states)
    # - ambient_readings (ambient temp)

    # Call mpc.learn_thermal_model(temps, times, heater_states, ambient, cooler_states)
    # Return True if learning succeeded
```

Triggers:
- Learn once when MPC first used for batch (if ≥24 hours history)
- Optionally re-learn every 6 hours for model adaptation

### 4. Integrate MPC into Control Logic
**File:** `backend/temp_controller.py:control_batch_temperature()`

Replace this section (lines 412-473):
```python
# CURRENT: Basic hysteresis thresholds
heat_on_threshold = round(target_temp - hysteresis, 1)
cool_on_threshold = round(target_temp + hysteresis, 1)

if wort_temp <= heat_on_threshold:
    # Turn heater ON
elif wort_temp >= cool_on_threshold:
    # Turn cooler ON
else:
    # Maintain current states
```

With:
```python
# NEW: MPC-based control (with fallback)
mpc_enabled = await get_config_value(db, "mpc_enabled")

if mpc_enabled:
    # Get or create MPC controller
    if batch_id not in _batch_mpc_controllers:
        _batch_mpc_controllers[batch_id] = MPCTemperatureController(
            horizon_hours=await get_config_value(db, "mpc_horizon_hours") or 4.0
        )

    mpc = _batch_mpc_controllers[batch_id]

    # Learn model if not available
    if not mpc.has_model:
        await learn_mpc_model_for_batch(batch_id, device_id, db)

    # Compute optimal action
    if mpc.has_model:
        action = mpc.compute_action(
            current_temp=wort_temp,
            target_temp=target_temp,
            ambient_temp=ambient_temp or wort_temp,  # Fallback if ambient unavailable
            heater_currently_on=(current_heater_state == "on"),
            cooler_currently_on=(current_cooler_state == "on"),
        )

        # Use MPC decision
        desired_heater_state = "on" if action["heater_on"] else "off"
        desired_cooler_state = "on" if action["cooler_on"] else "off"

        logger.debug(f"Batch {batch_id}: MPC decision: heater={action['heater_on']}, "
                    f"cooler={action['cooler_on']}, reason={action['reason']}, "
                    f"predicted={action['predicted_temp']:.2f}°C")
    else:
        # MPC model learning failed, fall back to hysteresis
        logger.warning(f"Batch {batch_id}: MPC model unavailable, using hysteresis")
        mpc_enabled = False  # Use fallback below

if not mpc_enabled:
    # FALLBACK: Basic hysteresis (existing code)
    heat_on_threshold = round(target_temp - hysteresis, 1)
    cool_on_threshold = round(target_temp + hysteresis, 1)
    # ... existing logic ...
```

### 5. Apply Control Actions
Keep existing heater/cooler state change logic:
- Mutual exclusion (turn OFF opposite device first)
- Min cycle time enforcement
- Manual override handling

Just replace the **decision-making** (thresholds vs MPC), not the **actuation** logic.

### 6. Logging and Observability
**File:** `backend/temp_controller.py`

Add logging:
```python
# On model learning
logger.info(f"Batch {batch_id}: MPC model learned - "
           f"heating_rate={result['heating_rate']:.2f}°C/h, "
           f"cooling_rate={result['cooling_rate']:.2f}°C/h, "
           f"ambient_coeff={result['ambient_coeff']:.3f}")

# On control decisions
logger.debug(f"Batch {batch_id}: MPC action: heater={action['heater_on']}, "
            f"reason={action['reason']}, predicted={action['predicted_temp']:.2f}°C")

# On fallback
logger.warning(f"Batch {batch_id}: MPC unavailable - {reason}, using hysteresis")
```

Optionally extend `get_batch_control_status()`:
```python
return {
    ...
    "mpc_enabled": mpc_enabled,
    "mpc_model_available": mpc.has_model if mpc else False,
    "mpc_predicted_temp": action.get("predicted_temp") if action else None,
}
```

### 7. Cleanup on Batch Completion
**File:** `backend/temp_controller.py:temperature_control_loop()`

Add MPC cleanup (around line 557):
```python
for batch_id in list(_batch_mpc_controllers.keys()):
    if batch_id not in active_batch_ids:
        logger.debug(f"Cleaning up MPC controller for inactive batch {batch_id}")
        del _batch_mpc_controllers[batch_id]
```

## Data Requirements

### Control Events
Need to track heater/cooler states over time for model learning.

**Current state:** `control_events` table exists with:
- `action`: "heat_on", "heat_off", "cool_on", "cool_off"
- `batch_id`, `timestamp`, `wort_temp`, `ambient_temp`

**Needed for MPC:**
- Query control_events to reconstruct heater/cooler state history
- Join with readings to get temperature history
- Join with ambient_readings for ambient temperature

### Learning Query
```sql
SELECT
    r.timestamp,
    r.temp_calibrated,
    COALESCE(r.temp_filtered, r.temp_calibrated) as temp,
    a.temperature as ambient_temp
FROM readings r
LEFT JOIN ambient_readings a ON a.timestamp <= r.timestamp
WHERE r.batch_id = ? AND r.timestamp > NOW() - INTERVAL 24 HOUR
ORDER BY r.timestamp
```

Then reconstruct heater/cooler states from control_events.

## Testing Strategy

### Unit Tests
Already exist: `tests/test_mpc.py`
- Test MPC learning from synthetic data
- Test trajectory prediction
- Test mutual exclusion

### Integration Tests
1. **Heater-only mode** (batch with heater, no cooler)
   - Should prevent overshoot when heating
   - Should turn heater OFF early to coast to target

2. **Dual-mode** (batch with both heater and cooler)
   - Should handle both heating and cooling
   - Should respect mutual exclusion
   - Should prevent both overshoot and undershoot

3. **MPC disabled** (config `mpc_enabled=False`)
   - Should use basic hysteresis (existing behavior)

4. **Insufficient history** (new batch, < 24 hours data)
   - Should fall back to hysteresis
   - Should learn model once enough history available

### Production Validation
Deploy to Raspberry Pi and monitor:
- Temperature stays within ±0.5°C of target (vs ±1-2°C currently)
- No rapid heater/cooler cycling
- MPC logs show reasonable predictions
- Falls back gracefully when needed

## Rollback Plan

If MPC causes issues:
1. Set `mpc_enabled=False` via config API
2. System immediately reverts to basic hysteresis
3. No code changes needed

## Success Criteria

- [ ] MPC configuration settings added
- [ ] MPC controller instances initialized per batch
- [ ] Thermal model learning from historical data works
- [ ] `control_batch_temperature()` uses MPC when enabled
- [ ] Fallback to hysteresis when MPC unavailable
- [ ] MPC decisions logged for debugging
- [ ] Cleanup on batch completion
- [ ] Temperature overshoot reduced to ±0.5°C
- [ ] Works with heater-only, cooling-only, and dual-mode
- [ ] Backward compatible (can be toggled on/off)

## Dependencies

- ✅ PR #66 (ML Pipeline Integration) - Provides Kalman filter with `temp_rate`
- ✅ `backend/ml/control/mpc.py` - MPC implementation exists
- ⏳ This issue - Integration work

## References

- Issue #69: https://github.com/machug/tilt_ui/issues/69
- MPC Implementation: `backend/ml/control/mpc.py`
- Temperature Controller: `backend/temp_controller.py`
- ML Pipeline PR #66
