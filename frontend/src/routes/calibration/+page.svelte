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
	<div class="page-header">
		<h1 class="page-title">Tilt Calibration</h1>
		<p class="page-description">Calibrate your Tilt hydrometer's gravity and temperature readings</p>
	</div>

	{#if loading}
		<div class="loading-state">
			<div class="loading-spinner"></div>
			<span>Loading Devices...</span>
		</div>
	{:else if devices.length === 0}
		<div class="empty-state">
			<div class="empty-icon">📊</div>
			<h3 class="empty-title">No Tilt Devices Found</h3>
			<p class="empty-description">
				Pair a Tilt hydrometer on the Devices page to calibrate it.
				Only Tilt devices appear here (iSpindel/GravityMon calibrate on-device).
			</p>
			<a href="/devices" class="btn-primary mt-4">Go to Devices</a>
		</div>
	{:else}
		<!-- Device Selector -->
		<div class="card mb-6">
			<div class="card-header">
				<h2 class="card-title">Select Device</h2>
			</div>
			<div class="card-body">
				<div class="tilt-selector">
					<select
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
							<span class="font-mono text-xs text-[var(--text-muted)]">{selectedDevice.id}</span>
						</div>
					{/if}
				</div>
			</div>
		</div>

		<div class="grid gap-6 md:grid-cols-2">
			<!-- SG Calibration -->
			<div class="card">
				<div class="card-header flex items-center justify-between">
					<h2 class="card-title">Gravity (SG)</h2>
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
				<div class="card-body">
					<p class="section-description">
						Add calibration points by measuring with a reference hydrometer.
						The system will interpolate between points.
					</p>

					{#if loadingPoints}
						<div class="loading-inline">
							<div class="loading-spinner-small"></div>
							<span>Loading...</span>
						</div>
					{:else}
						<!-- Existing Points -->
						{#if sgPoints.length > 0}
							<div class="calibration-table">
								<div class="table-header">
									<span>Raw</span>
									<span>→</span>
									<span>Actual</span>
								</div>
								{#each sgPoints as point}
									<div class="table-row">
										<span class="font-mono">{formatSG(point[0])}</span>
										<span class="text-[var(--text-muted)]">→</span>
										<span class="font-mono text-[var(--accent)]">{formatSG(point[1])}</span>
									</div>
								{/each}
							</div>
						{:else}
							<div class="no-points">
								<span>No calibration points yet</span>
							</div>
						{/if}

						<!-- Add New Point Form -->
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
								<div class="form-arrow">→</div>
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
								<button
									type="button"
									class="btn-add"
									onclick={() => addSGPoint(sgRawValue, sgActualValue)}
									disabled={saving || !sgRawValue || !sgActualValue}
									aria-label="Add SG calibration point"
								>
									<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
										<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
									</svg>
								</button>
							</div>
						</div>
					{/if}
				</div>
			</div>

			<!-- Temperature Calibration -->
			<div class="card">
				<div class="card-header flex items-center justify-between">
					<h2 class="card-title">Temperature ({tempUnit})</h2>
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
				<div class="card-body">
					<p class="section-description">
						Calibrate temperature by comparing with a reference thermometer.
						Values are stored in °C internally.
					</p>

					{#if loadingPoints}
						<div class="loading-inline">
							<div class="loading-spinner-small"></div>
							<span>Loading...</span>
						</div>
					{:else}
						<!-- Existing Points -->
						{#if tempPoints.length > 0}
							<div class="calibration-table">
								<div class="table-header">
									<span>Raw ({tempUnit})</span>
									<span>→</span>
									<span>Actual ({tempUnit})</span>
								</div>
								{#each tempPoints as point}
									{@const [rawDisplay, actualDisplay] = convertTempPointFromCelsius(point[0], point[1], useCelsius)}
									<div class="table-row">
										<span class="font-mono">{rawDisplay.toFixed(1)}°</span>
										<span class="text-[var(--text-muted)]">→</span>
										<span class="font-mono text-[var(--accent)]">{actualDisplay.toFixed(1)}°</span>
									</div>
								{/each}
							</div>
						{:else}
							<div class="no-points">
								<span>No calibration points yet</span>
							</div>
						{/if}

						<!-- Add New Point Form -->
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
								<div class="form-arrow">→</div>
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
								<button
									type="button"
									class="btn-add"
									onclick={() => addTempPoint(tempRawValue, tempActualValue)}
									disabled={saving || !tempRawValue || !tempActualValue}
									aria-label="Add temperature calibration point"
								>
									<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
										<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
									</svg>
								</button>
							</div>
						</div>
					{/if}
				</div>
			</div>
		</div>

		<!-- Calibration Info -->
		<div class="info-section mt-6">
			<h3 class="info-title">How Tilt Calibration Works</h3>
			<p class="info-text">
				Tilt calibration is applied in software to raw BLE readings. Add at least two calibration
				points for accurate linear interpolation. Calibration happens app-side, not on the device.
			</p>
			<div class="info-tips">
				<div class="tip">
					<span class="tip-label">Gravity:</span>
					<span>Use distilled water (1.000 SG) and a known sugar solution (1.061 or 1.110 SG) for best results.</span>
				</div>
				<div class="tip">
					<span class="tip-label">Temperature:</span>
					<span>Rarely needed for Tilts (accurate 38°F-98°F range). Calibrate only if you notice consistent offsets.</span>
				</div>
				<div class="tip">
					<span class="tip-label">iSpindel/GravityMon:</span>
					<span>These devices calibrate on-board via polynomial formulas. Configure calibration through the device's web interface.</span>
				</div>
			</div>
		</div>
	{/if}
</div>

<style>
	.page-container {
		max-width: 56rem;
	}

	.page-header {
		margin-bottom: 1.5rem;
	}

	.page-title {
		font-size: 1.5rem;
		font-weight: 700;
		color: var(--text-primary);
		margin-bottom: 0.25rem;
	}

	.page-description {
		color: var(--text-secondary);
		font-size: 0.875rem;
	}

	.card {
		background: var(--bg-card);
		border: 1px solid var(--bg-hover);
		border-radius: 0.75rem;
		overflow: hidden;
	}

	.card-header {
		padding: 1rem 1.25rem;
		border-bottom: 1px solid var(--bg-hover);
	}

	.card-title {
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--text-primary);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.card-body {
		padding: 1.25rem;
	}

	.section-description {
		font-size: 0.75rem;
		color: var(--text-muted);
		margin-bottom: 1rem;
		line-height: 1.5;
	}

	/* Tilt Selector */
	.tilt-selector {
		display: flex;
		align-items: center;
		gap: 1rem;
	}

	.select-input {
		flex: 1;
		max-width: 20rem;
		padding: 0.625rem 2.5rem 0.625rem 1rem;
		font-size: 0.875rem;
		color: var(--text-primary);
		background: var(--bg-elevated);
		border: 1px solid var(--bg-hover);
		border-radius: 0.5rem;
		cursor: pointer;
		appearance: none;
		background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%2371717a'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'/%3E%3C/svg%3E");
		background-repeat: no-repeat;
		background-position: right 0.75rem center;
		background-size: 1.25rem;
	}

	.select-input:focus {
		outline: none;
		border-color: var(--accent);
	}

	.tilt-info {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.tilt-color-dot {
		width: 0.625rem;
		height: 0.625rem;
		border-radius: 50%;
	}

	/* Calibration Table */
	.calibration-table {
		margin-bottom: 1rem;
		border: 1px solid var(--bg-hover);
		border-radius: 0.5rem;
		overflow: hidden;
	}

	.table-header {
		display: grid;
		grid-template-columns: 1fr auto 1fr;
		gap: 0.5rem;
		padding: 0.625rem 1rem;
		background: var(--bg-elevated);
		font-size: 0.6875rem;
		font-weight: 600;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.table-row {
		display: grid;
		grid-template-columns: 1fr auto 1fr;
		gap: 0.5rem;
		padding: 0.625rem 1rem;
		font-size: 0.8125rem;
		border-top: 1px solid var(--bg-hover);
	}

	.no-points {
		padding: 1.5rem;
		text-align: center;
		color: var(--text-muted);
		font-size: 0.8125rem;
		background: var(--bg-elevated);
		border-radius: 0.5rem;
		margin-bottom: 1rem;
	}

	/* Add Point Form */
	.add-point-form {
		padding-top: 1rem;
		border-top: 1px solid var(--bg-hover);
	}

	.form-row {
		display: flex;
		align-items: flex-end;
		gap: 0.75rem;
	}

	.form-group {
		flex: 1;
	}

	.form-group label {
		display: block;
		font-size: 0.6875rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin-bottom: 0.375rem;
	}

	.input-field {
		width: 100%;
		padding: 0.5rem 0.75rem;
		font-size: 0.8125rem;
		font-family: var(--font-mono);
		color: var(--text-primary);
		background: var(--bg-elevated);
		border: 1px solid var(--bg-hover);
		border-radius: 0.375rem;
	}

	.input-field:focus {
		outline: none;
		border-color: var(--accent);
	}

	.input-field::placeholder {
		color: var(--text-muted);
		opacity: 0.5;
	}

	.form-arrow {
		padding-bottom: 0.625rem;
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	.btn-add {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 2.25rem;
		height: 2.25rem;
		color: white;
		background: var(--accent);
		border: 1px solid var(--accent);
		border-radius: 0.5rem;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.btn-add:hover:not(:disabled) {
		background: var(--accent-hover);
		border-color: var(--accent-hover);
	}

	.btn-add:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}

	.btn-danger-small {
		padding: 0.25rem 0.625rem;
		font-size: 0.6875rem;
		font-weight: 500;
		color: var(--tilt-red);
		background: rgba(244, 63, 94, 0.1);
		border: 1px solid rgba(244, 63, 94, 0.2);
		border-radius: 0.375rem;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.btn-danger-small:hover:not(:disabled) {
		background: rgba(244, 63, 94, 0.15);
		border-color: rgba(244, 63, 94, 0.3);
	}

	.btn-danger-small:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	/* Info Section */
	.info-section {
		background: var(--bg-card);
		border: 1px solid var(--bg-hover);
		border-radius: 0.75rem;
		padding: 1.25rem;
	}

	.info-title {
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-primary);
		margin-bottom: 0.5rem;
	}

	.info-text {
		font-size: 0.8125rem;
		color: var(--text-secondary);
		line-height: 1.6;
		margin-bottom: 1rem;
	}

	.info-tips {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.tip {
		font-size: 0.75rem;
		color: var(--text-muted);
		line-height: 1.5;
	}

	.tip-label {
		font-weight: 600;
		color: var(--accent);
		margin-right: 0.25rem;
	}

	/* Loading States */
	.loading-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 1rem;
		padding: 4rem 2rem;
		color: var(--text-muted);
	}

	.loading-spinner {
		width: 2rem;
		height: 2rem;
		border: 2px solid var(--bg-hover);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	.loading-inline {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 1rem;
		color: var(--text-muted);
		font-size: 0.8125rem;
	}

	.loading-spinner-small {
		width: 1rem;
		height: 1rem;
		border: 2px solid var(--bg-hover);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	/* Empty State */
	.empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 4rem 2rem;
		text-align: center;
		background: var(--bg-card);
		border: 1px solid var(--bg-hover);
		border-radius: 0.75rem;
	}

	.empty-icon {
		font-size: 3rem;
		margin-bottom: 1rem;
		opacity: 0.6;
	}

	.empty-title {
		font-size: 1.125rem;
		font-weight: 600;
		color: var(--text-primary);
		margin-bottom: 0.5rem;
	}

	.empty-description {
		font-size: 0.875rem;
		color: var(--text-muted);
		max-width: 20rem;
		line-height: 1.6;
	}

	.btn-primary {
		display: inline-block;
		padding: 0.625rem 1.25rem;
		font-size: 0.875rem;
		font-weight: 500;
		color: white;
		background: var(--accent);
		border: 1px solid var(--accent);
		border-radius: 0.5rem;
		text-decoration: none;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.btn-primary:hover {
		background: var(--accent-hover);
		border-color: var(--accent-hover);
	}

	/* Grid utilities */
	.mb-6 {
		margin-bottom: 1.5rem;
	}

	.mt-4 {
		margin-top: 1rem;
	}

	.mt-6 {
		margin-top: 1.5rem;
	}

	@media (max-width: 768px) {
		.form-row {
			flex-wrap: wrap;
		}

		.form-group {
			flex: 1 1 40%;
		}

		.form-arrow {
			display: none;
		}

		.btn-add {
			flex: 0 0 100%;
			width: 100%;
			margin-top: 0.5rem;
		}
	}
</style>
