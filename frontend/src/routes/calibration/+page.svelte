<script lang="ts">
	import { onMount } from 'svelte';
	import { configState, formatTemp, getTempUnit } from '$lib/stores/config.svelte';
	import { convertTempPointToCelsius, convertTempPointFromCelsius } from '$lib/utils/temperature';

	interface Device {
		id: string;
		color: string;
		beer_name: string;
		mac: string | null;
		last_seen: string | null;
		device_type: string;
		paired: boolean;
		calibration_type: string;
		calibration_data: CalibrationData | null;
	}

	interface CalibrationData {
		points?: [number, number][];      // SG points: [raw, actual]
		temp_points?: [number, number][]; // Temp points: [raw, actual]
	}

	interface CalibrationRequest {
		calibration_type: 'linear' | 'none';
		calibration_data: CalibrationData | null;
	}

	let devices = $state<Device[]>([]);
	let selectedDeviceId = $state<string | null>(null);
	let calibrationData = $state<CalibrationData | null>(null);
	let calibrationType = $state<string>('none');
	let loading = $state(true);
	let loadingPoints = $state(false);
	let saving = $state(false);

	// Form state for adding new points
	let sgRawValue = $state('');
	let sgActualValue = $state('');
	let tempRawValue = $state('');
	let tempActualValue = $state('');

	// Reactive temp unit
	let tempUnit = $derived(getTempUnit());
	let useCelsius = $derived(configState.config.temp_units === 'C');

	// Filter points by type (use toSorted to avoid mutating state)
	let sgPoints = $derived((calibrationData?.points || []).toSorted((a, b) => a[0] - b[0]));
	let tempPoints = $derived((calibrationData?.temp_points || []).toSorted((a, b) => a[0] - b[0]));

	// Selected device object
	let selectedDevice = $derived(devices.find((d) => d.id === selectedDeviceId));

	async function loadDevices() {
		try {
			const response = await fetch('/api/devices?device_type=tilt&paired_only=true');
			if (response.ok) {
				devices = await response.json();
				if (devices.length > 0 && !selectedDeviceId) {
					selectedDeviceId = devices[0].id;
					// Load calibration for initial device
					await loadCalibration();
				}
			}
		} catch (e) {
			console.error('Failed to load devices:', e);
		} finally {
			loading = false;
		}
	}

	function handleDeviceChange() {
		// Clear form state when switching devices
		sgRawValue = '';
		sgActualValue = '';
		tempRawValue = '';
		tempActualValue = '';
		// Load calibration for new device
		loadCalibration();
	}

	async function loadCalibration() {
		if (!selectedDeviceId) return;
		loadingPoints = true;
		try {
			const response = await fetch(`/api/devices/${selectedDeviceId}/calibration`);
			if (response.ok) {
				const data = await response.json();
				calibrationType = data.calibration_type;
				calibrationData = data.calibration_data;
			}
		} catch (e) {
			console.error('Failed to load calibration:', e);
		} finally {
			loadingPoints = false;
		}
	}

	async function saveCalibration(data: CalibrationData) {
		if (!selectedDeviceId) return;
		saving = true;
		try {
			// Determine calibration type based on whether any points exist
			const hasPoints = (data.points?.length ?? 0) > 0;
			const hasTempPoints = (data.temp_points?.length ?? 0) > 0;
			const calType = (hasPoints || hasTempPoints) ? 'linear' : 'none';

			const payload: CalibrationRequest = {
				calibration_type: calType,
				calibration_data: calType === 'none' ? null : data
			};
			const response = await fetch(`/api/devices/${selectedDeviceId}/calibration`, {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(payload)
			});
			if (response.ok) {
				// Use the response from PUT instead of making redundant GET call
				const updatedDevice = await response.json();
				calibrationType = updatedDevice.calibration_type;
				calibrationData = updatedDevice.calibration_data;
			} else {
				const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
				alert(`Failed to save calibration: ${errorData.detail || response.statusText}`);
			}
		} catch (e) {
			console.error('Failed to save calibration:', e);
			alert(`Failed to save calibration: ${e instanceof Error ? e.message : 'Unknown error'}`);
		} finally {
			saving = false;
		}
	}

	async function addSGPoint(rawValue: string, actualValue: string) {
		if (!selectedDeviceId) return;

		const raw = parseFloat(rawValue);
		const actual = parseFloat(actualValue);

		if (isNaN(raw) || isNaN(actual)) {
			alert('Please enter valid numbers for both raw and actual gravity values');
			return;
		}

		// Validation
		if (raw < 0.990 || raw > 1.200 || actual < 0.990 || actual > 1.200) {
			alert('Gravity values must be between 0.990 and 1.200');
			return;
		}

		// Check for duplicate raw values
		const existingPoints = calibrationData?.points || [];
		const isDuplicate = existingPoints.some(point => Math.abs(point[0] - raw) < 0.001);
		if (isDuplicate) {
			alert('A calibration point with this raw value already exists');
			return;
		}

		// Add new point to existing points
		const newPoints = [...existingPoints, [raw, actual] as [number, number]];

		// Save with updated points
		await saveCalibration({
			...calibrationData,
			points: newPoints
		});

		// Clear form
		sgRawValue = '';
		sgActualValue = '';
	}

	async function addTempPoint(rawValue: string, actualValue: string) {
		if (!selectedDeviceId) return;

		const raw = parseFloat(rawValue);
		const actual = parseFloat(actualValue);

		if (isNaN(raw) || isNaN(actual)) {
			alert('Please enter valid numbers for both raw and actual temperature values');
			return;
		}

		// Validation (in user's preferred unit)
		const minTemp = useCelsius ? -10 : 14;
		const maxTemp = useCelsius ? 50 : 122;

		if (raw < minTemp || raw > maxTemp || actual < minTemp || actual > maxTemp) {
			const unit = useCelsius ? '°C' : '°F';
			alert(`Temperature values must be between ${minTemp}${unit} and ${maxTemp}${unit}`);
			return;
		}

		// Check for duplicate raw values in user's preferred unit
		const existingTempPoints = calibrationData?.temp_points || [];
		const tolerance = useCelsius ? 0.1 : 0.18; // 0.1°C ≈ 0.18°F
		const isDuplicate = existingTempPoints.some(point => {
			// Convert stored Celsius point back to user's unit for comparison
			const [storedRaw, _] = convertTempPointFromCelsius(point[0], point[1], useCelsius);
			return Math.abs(storedRaw - raw) < tolerance;
		});
		if (isDuplicate) {
			const unit = useCelsius ? '°C' : '°F';
			alert(`A calibration point with this raw value already exists (within ${tolerance}${unit})`);
			return;
		}

		// Convert to Celsius for backend storage
		const [rawC, actualC] = convertTempPointToCelsius(raw, actual, useCelsius);

		// Add new point to existing points
		const newTempPoints = [...existingTempPoints, [rawC, actualC] as [number, number]];

		// Save with updated temp points
		await saveCalibration({
			...calibrationData,
			temp_points: newTempPoints
		});

		// Clear form
		tempRawValue = '';
		tempActualValue = '';
	}

	async function clearSGCalibration() {
		if (!selectedDeviceId) return;

		if (!confirm('Clear all gravity calibration points?')) {
			return;
		}

		// Save with empty points array
		await saveCalibration({
			...calibrationData,
			points: []
		});
	}

	async function clearTempCalibration() {
		if (!selectedDeviceId) return;

		if (!confirm('Clear all temperature calibration points?')) {
			return;
		}

		// Save with empty temp_points array
		await saveCalibration({
			...calibrationData,
			temp_points: []
		});
	}

	async function removeSGPoint(point: [number, number]) {
		if (!selectedDeviceId) return;
		if (!confirm('Remove this gravity calibration point?')) return;
		await saveCalibration({
			...calibrationData,
			points: (calibrationData?.points || []).filter((p) => !(p[0] === point[0] && p[1] === point[1]))
		});
	}

	async function removeTempPoint(point: [number, number]) {
		if (!selectedDeviceId) return;
		if (!confirm('Remove this temperature calibration point?')) return;
		await saveCalibration({
			...calibrationData,
			temp_points: (calibrationData?.temp_points || []).filter((p) => !(p[0] === point[0] && p[1] === point[1]))
		});
	}

	function delta(raw: number, actual: number, digits: number): string {
		const d = actual - raw;
		const t = Math.abs(d).toFixed(digits);
		if (Number(t) === 0) return t;
		return (d < 0 ? '\u2212' : '+') + t;
	}

	function formatSG(sg: number): string {
		return sg.toFixed(3);
	}

	onMount(() => {
		loadDevices();
	});
</script>

<svelte:head>
	<title>Calibration | BrewSignal</title>
</svelte:head>

<div class="page-container">
	<nav class="crumbs" aria-label="Breadcrumb">
		<a href="/system">System</a>
		<span aria-hidden="true">/</span>
		<span aria-current="page">Calibration</span>
	</nav>
	<div class="page-header">
		<h1 class="page-title">Tilt Calibration</h1>
		<p class="page-description">Calibrate your Tilt hydrometer's gravity and temperature readings</p>
	</div>

	{#if loading}
		<div class="loading-state" role="status">
			<div class="loading-spinner"></div>
			<span>Loading Devices...</span>
		</div>
	{:else if devices.length === 0}
		<div class="empty-state">
			<h3 class="empty-title">No Tilt Devices Found</h3>
			<p class="empty-description">
				Pair a Tilt hydrometer on the Devices page to calibrate it.
				Only Tilt devices appear here (iSpindel/GravityMon calibrate on-device).
			</p>
			<a href="/devices" class="btn-primary">Go to Devices</a>
		</div>
	{:else}
		<!-- Device Selector -->
		<section class="panel selector-panel">
			<h2 class="panel-title">Select Device</h2>
			<div class="tilt-selector">
				<label class="sr-only" for="tilt-select">Tilt device</label>
				<select
					id="tilt-select"
					bind:value={selectedDeviceId}
					onchange={handleDeviceChange}
					class="select-input"
				>
					{#each devices as device}
						<option value={device.id}>
							{device.color} — {device.beer_name}
						</option>
					{/each}
				</select>
				{#if selectedDevice}
					<div class="tilt-info">
						<span class="tilt-color-dot" style="background: var(--tilt-{selectedDevice.color.toLowerCase()});"></span>
						<span class="device-id">{selectedDevice.id}</span>
					</div>
				{/if}
			</div>
		</section>

		<div class="workbench">
			<!-- SG Calibration -->
			<section class="panel">
				<div class="panel-head">
					<h2 class="panel-title">Gravity (SG)</h2>
					{#if sgPoints.length > 0}
						<button
							type="button"
							class="btn-danger-small"
							onclick={() => clearSGCalibration()}
							disabled={saving}
							aria-label="Clear all gravity calibration points"
						>
							Clear All
						</button>
					{/if}
				</div>
				<p class="section-description">
					Add calibration points by measuring with a reference hydrometer.
					The system will interpolate between points.
				</p>

				{#if loadingPoints}
					<div class="loading-inline" role="status">
						<div class="loading-spinner-small"></div>
						<span>Loading...</span>
					</div>
				{:else}
					{#if sgPoints.length > 0}
						<div class="calibration-table" role="table" aria-label="Gravity calibration points">
							<div class="grid-row head" role="row">
								<span role="columnheader">Raw</span>
								<span role="columnheader">Actual</span>
								<span role="columnheader">Delta</span>
								<span role="columnheader"><span class="sr-only">Remove</span></span>
							</div>
							{#each sgPoints as point}
								<div class="grid-row" role="row">
									<span role="cell" class="num">{formatSG(point[0])}</span>
									<span role="cell" class="num">{formatSG(point[1])}</span>
									<span role="cell" class="num muted">{delta(point[0], point[1], 3)}</span>
									<span role="cell">
										<button type="button" class="remove-btn" onclick={() => removeSGPoint(point)} disabled={saving} aria-label="Remove point {formatSG(point[0])} to {formatSG(point[1])}">
											<svg class="icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
										</button>
									</span>
								</div>
							{/each}
						</div>
					{:else}
						<div class="no-points">
							<span>No calibration points yet</span>
						</div>
					{/if}

					<div class="add-point-form">
						<div class="form-row">
							<div class="form-group">
								<label for="sg-raw">Raw SG</label>
								<input
									id="sg-raw"
									type="number"
									step="0.001"
									placeholder="1.050"
									bind:value={sgRawValue}
									class="input-field"
								/>
							</div>
							<div class="form-group">
								<label for="sg-actual">Actual SG</label>
								<input
									id="sg-actual"
									type="number"
									step="0.001"
									placeholder="1.048"
									bind:value={sgActualValue}
									class="input-field"
								/>
							</div>
							<span class="delta-spacer" aria-hidden="true"></span>
							<button
								type="button"
								class="btn-add"
								onclick={() => addSGPoint(sgRawValue, sgActualValue)}
								disabled={saving || !sgRawValue || !sgActualValue}
								aria-label="Add SG calibration point"
							>
								<svg class="icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
									<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
								</svg>
							</button>
						</div>
					</div>
				{/if}
			</section>

			<!-- Temperature Calibration -->
			<section class="panel">
				<div class="panel-head">
					<h2 class="panel-title">Temperature ({tempUnit})</h2>
					{#if tempPoints.length > 0}
						<button
							type="button"
							class="btn-danger-small"
							onclick={() => clearTempCalibration()}
							disabled={saving}
							aria-label="Clear all temperature calibration points"
						>
							Clear All
						</button>
					{/if}
				</div>
				<p class="section-description">
					Calibrate temperature by comparing with a reference thermometer.
					Values are stored in &deg;C internally.
				</p>

				{#if loadingPoints}
					<div class="loading-inline" role="status">
						<div class="loading-spinner-small"></div>
						<span>Loading...</span>
					</div>
				{:else}
					{#if tempPoints.length > 0}
						<div class="calibration-table" role="table" aria-label="Temperature calibration points">
							<div class="grid-row head" role="row">
								<span role="columnheader">Raw ({tempUnit})</span>
								<span role="columnheader">Actual ({tempUnit})</span>
								<span role="columnheader">Delta</span>
								<span role="columnheader"><span class="sr-only">Remove</span></span>
							</div>
							{#each tempPoints as point}
								{@const [rawDisplay, actualDisplay] = convertTempPointFromCelsius(point[0], point[1], useCelsius)}
								<div class="grid-row" role="row">
									<span role="cell" class="num">{rawDisplay.toFixed(1)}&deg;</span>
									<span role="cell" class="num">{actualDisplay.toFixed(1)}&deg;</span>
									<span role="cell" class="num muted">{delta(rawDisplay, actualDisplay, 1)}&deg;</span>
									<span role="cell">
										<button type="button" class="remove-btn" onclick={() => removeTempPoint(point)} disabled={saving} aria-label="Remove point {rawDisplay.toFixed(1)} to {actualDisplay.toFixed(1)}">
											<svg class="icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
										</button>
									</span>
								</div>
							{/each}
						</div>
					{:else}
						<div class="no-points">
							<span>No calibration points yet</span>
						</div>
					{/if}

					<div class="add-point-form">
						<div class="form-row">
							<div class="form-group">
								<label for="temp-raw">Raw {tempUnit}</label>
								<input
									id="temp-raw"
									type="number"
									step="0.1"
									placeholder={useCelsius ? '20.0' : '68.0'}
									bind:value={tempRawValue}
									class="input-field"
								/>
							</div>
							<div class="form-group">
								<label for="temp-actual">Actual {tempUnit}</label>
								<input
									id="temp-actual"
									type="number"
									step="0.1"
									placeholder={useCelsius ? '19.5' : '67.5'}
									bind:value={tempActualValue}
									class="input-field"
								/>
							</div>
							<span class="delta-spacer" aria-hidden="true"></span>
							<button
								type="button"
								class="btn-add"
								onclick={() => addTempPoint(tempRawValue, tempActualValue)}
								disabled={saving || !tempRawValue || !tempActualValue}
								aria-label="Add temperature calibration point"
							>
								<svg class="icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
									<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
								</svg>
							</button>
						</div>
					</div>
				{/if}
			</section>
		</div>

		<!-- Calibration Info -->
		<section class="info-section">
			<h3 class="info-title">How Tilt Calibration Works</h3>
			<p class="info-text">
				Tilt calibration is applied in software to raw BLE readings. Add at least two calibration
				points for accurate linear interpolation. Calibration happens app-side, not on the device.
			</p>
			<dl class="info-tips">
				<div class="tip">
					<dt class="tip-label">Gravity</dt>
					<dd>Use distilled water (1.000 SG) and a known sugar solution (1.061 or 1.110 SG) for best results.</dd>
				</div>
				<div class="tip">
					<dt class="tip-label">Temperature</dt>
					<dd>Rarely needed for Tilts (accurate 38&thinsp;&deg;F to 98&thinsp;&deg;F range). Calibrate only if you notice consistent offsets.</dd>
				</div>
				<div class="tip">
					<dt class="tip-label">iSpindel/GravityMon</dt>
					<dd>These devices calibrate on-board via polynomial formulas. Configure calibration through the device's web interface.</dd>
				</div>
			</dl>
		</section>
	{/if}
</div>

<style>
	.crumbs {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
		padding-bottom: var(--space-xs);
		margin-bottom: var(--space-md);
		border-bottom: 1px solid var(--rule-hairline);
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--ink-muted);
	}
	.crumbs a {
		display: inline-flex;
		align-items: center;
		min-height: 44px;
		color: var(--ink-secondary);
	}
	.crumbs a:hover {
		color: var(--ink-primary);
		text-decoration: underline;
	}
	.page-header {
		margin-bottom: var(--space-lg);
	}
	.page-title {
		font-family: var(--font-display);
		font-size: var(--text-xl);
		font-weight: 700;
		letter-spacing: -0.02em;
		line-height: 1.15;
		color: var(--ink-primary);
	}
	.page-description {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		margin-top: var(--space-2xs);
	}
	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
		white-space: nowrap;
	}

	.panel {
		padding-top: var(--space-md);
		border-top: 1px solid var(--rule-strong);
		margin-bottom: var(--space-lg);
		min-width: 0;
	}
	.panel-head {
		min-height: 44px;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-md);
	}
	.panel-title {
		font-family: var(--font-display);
		font-size: var(--text-lg);
		font-weight: 600;
		color: var(--ink-primary);
	}
	.section-description {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		margin: var(--space-2xs) 0 var(--space-md);
	}
	.workbench {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0 var(--space-xl);
	}

	.tilt-selector {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-md);
		margin-top: var(--space-sm);
	}
	.select-input,
	.input-field {
		min-height: 44px;
		padding: 0 var(--space-sm);
		font-size: var(--text-base);
		color: var(--ink-primary);
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
	}
	.select-input {
		min-width: min(18rem, 100%);
		padding-right: 2rem;
		text-overflow: ellipsis;
	}
	.input-field {
		width: 100%;
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		text-align: left;
	}
	.input-field::placeholder {
		color: var(--ink-muted);
	}
	.select-input:focus-visible,
	.input-field:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
		border-color: var(--accent);
	}
	.tilt-info {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
	}
	.tilt-color-dot {
		width: 0.875rem;
		height: 1.5rem;
		border-radius: 2px;
	}
	.device-id {
		font-family: var(--font-num);
		font-size: var(--text-xs);
		color: var(--ink-muted);
		overflow-wrap: anywhere;
	}

	/* Points table and add form share one grid */
	.calibration-table {
		margin-bottom: var(--space-md);
		font-variant-numeric: tabular-nums;
	}
	.grid-row,
	.form-row {
		display: grid;
		grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) 4.5rem 44px;
		align-items: center;
		gap: var(--space-sm);
	}
	.grid-row {
		min-height: 48px;
		padding: 0;
		border-bottom: 1px solid var(--rule-hairline);
		font-family: var(--font-num);
		font-size: var(--text-base);
		color: var(--ink-primary);
	}
	.grid-row.head {
		min-height: 36px;
		border-bottom: 1px solid var(--rule-strong);
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--ink-muted);
	}
	.grid-row .muted {
		color: var(--ink-secondary);
		font-size: var(--text-sm);
	}
	.remove-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 44px;
		height: 44px;
		color: var(--ink-muted);
		border-radius: 4px;
		cursor: pointer;
	}
	.remove-btn:hover:not(:disabled) {
		color: var(--status-danger);
		background: var(--negative-muted);
	}
	.remove-btn:disabled {
		opacity: 0.5;
	}
	.no-points {
		padding: var(--space-sm) var(--space-xs);
		margin-bottom: var(--space-md);
		font-size: var(--text-sm);
		color: var(--ink-muted);
		border-top: 1px solid var(--rule-hairline);
		border-bottom: 1px solid var(--rule-hairline);
	}

	/* Add form */
	.form-row {
		align-items: end;
	}
	.form-group label {
		display: block;
		margin-bottom: var(--space-2xs);
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--ink-muted);
	}
	.btn-add {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 44px;
		height: 44px;
		color: var(--ink-primary);
		background: var(--bg-subtle);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		cursor: pointer;
	}
	.btn-add:hover:not(:disabled) {
		background: var(--accent-tint);
		border-color: var(--accent-rule);
	}
	.btn-add:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}
	.icon {
		width: 1rem;
		height: 1rem;
	}
	.btn-primary {
		display: inline-flex;
		align-items: center;
		min-height: 44px;
		padding: 0 var(--space-md);
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--accent-ink);
		background: var(--accent);
		border-radius: 4px;
	}
	.btn-primary:hover {
		background: var(--accent-hover);
	}
	.btn-danger-small {
		min-height: 44px;
		padding: 0 var(--space-sm);
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--status-danger);
		background: var(--bg-surface);
		border: 1px solid color-mix(in oklch, var(--status-danger) 55%, transparent);
		border-radius: 4px;
		cursor: pointer;
	}
	.btn-danger-small:hover:not(:disabled) {
		background: var(--negative-muted);
	}
	.btn-danger-small:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	/* States */
	.loading-state,
	.loading-inline {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		padding: var(--space-md) var(--space-xs);
		font-size: var(--text-sm);
		color: var(--ink-muted);
	}
	.loading-spinner,
	.loading-spinner-small {
		width: 1.25rem;
		height: 1.25rem;
		border: 2px solid var(--rule-strong);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.9s linear infinite;
	}
	.loading-spinner-small {
		width: 1rem;
		height: 1rem;
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
	.empty-state {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: var(--space-sm);
		padding: var(--space-md) 0;
		border-top: 1px solid var(--rule-hairline);
	}
	.empty-title {
		font-family: var(--font-display);
		font-size: var(--text-lg);
		font-weight: 600;
		color: var(--ink-primary);
	}
	.empty-description {
		max-width: 40rem;
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}

	/* Info */
	.info-section {
		padding-top: var(--space-md);
		border-top: 1px solid var(--rule-strong);
	}
	.info-title {
		font-family: var(--font-display);
		font-size: var(--text-base);
		font-weight: 600;
		color: var(--ink-primary);
	}
	.info-text {
		max-width: 48rem;
		margin-top: var(--space-2xs);
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}
	.info-tips {
		margin: var(--space-sm) 0 0;
		border-top: 1px solid var(--rule-hairline);
	}
	.tip {
		display: grid;
		grid-template-columns: 12rem minmax(0, 1fr);
		gap: var(--space-md);
		padding: var(--space-xs) 0;
		border-bottom: 1px solid var(--rule-hairline);
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}
	.tip dd {
		margin: 0;
	}
	.tip-label {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--ink-muted);
	}

	@media (max-width: 1040px) {
		.workbench {
			grid-template-columns: minmax(0, 1fr);
		}
	}
	@media (max-width: 760px) {
		.tip {
			grid-template-columns: minmax(0, 1fr);
			gap: 0;
		}
		.select-input {
			width: 100%;
		}
	}
</style>
