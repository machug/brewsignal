<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import type { BatchResponse, BatchProgressResponse, BatchUpdate, BatchStatus, BatchControlStatus, ControlEvent } from '$lib/api';
	import { fetchBatch, fetchBatchProgress, updateBatch, deleteBatch, fetchBatchControlStatus, setBatchHeaterOverride, fetchBatchControlEvents } from '$lib/api';
	import { formatGravity, getGravityUnit, formatTemp, getTempUnit, configState } from '$lib/stores/config.svelte';
	import { tiltsState } from '$lib/stores/tilts.svelte';
	import BatchForm from '$lib/components/BatchForm.svelte';
	import BatchFermentationCard from '$lib/components/batch/BatchFermentationCard.svelte';
	import BatchDeviceCard from '$lib/components/batch/BatchDeviceCard.svelte';
	import BatchRecipeTargetsCard from '$lib/components/batch/BatchRecipeTargetsCard.svelte';
	import BatchNotesCard from '$lib/components/batch/BatchNotesCard.svelte';
	import MLPredictions from '$lib/components/batch/MLPredictions.svelte';
	import FermentationChart from '$lib/components/FermentationChart.svelte';

	// WebSocket for live heater state updates
	let controlWs: WebSocket | null = null;
	let wsReconnectTimer: ReturnType<typeof setTimeout> | null = null;

	// State
	let batch = $state<BatchResponse | null>(null);
	let progress = $state<BatchProgressResponse | null>(null);
	let controlStatus = $state<BatchControlStatus | null>(null);
	let controlEvents = $state<ControlEvent[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let isEditing = $state(false);
	let statusUpdating = $state(false);
	let heaterLoading = $state(false);
	let showDeleteConfirm = $state(false);
	let deleting = $state(false);
	let tempControlCollapsed = $state(false);

	let batchId = $derived(parseInt($page.params.id ?? '0'));

	// Status configuration
	const statusConfig: Record<string, { label: string; color: string; bg: string }> = {
		planning: { label: 'Planning', color: 'var(--text-secondary)', bg: 'var(--bg-elevated)' },
		fermenting: { label: 'Fermenting', color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.12)' },
		conditioning: { label: 'Conditioning', color: '#8b5cf6', bg: 'rgba(139, 92, 246, 0.12)' },
		completed: { label: 'Completed', color: 'var(--positive)', bg: 'rgba(34, 197, 94, 0.12)' },
		archived: { label: 'Archived', color: 'var(--text-muted)', bg: 'var(--bg-elevated)' }
	};

	const statusOptions: BatchStatus[] = ['planning', 'fermenting', 'conditioning', 'completed', 'archived'];

	let statusInfo = $derived(batch ? statusConfig[batch.status] : statusConfig.planning);
	let gravityUnit = $derived(getGravityUnit());
	let tempUnit = $derived(getTempUnit());

	// Check if temperature control is available for this batch
	let hasTempControl = $derived(
		configState.config.ha_enabled &&
		configState.config.temp_control_enabled &&
		(batch?.heater_entity_id || batch?.cooler_entity_id)
	);

	// Pre-pitch chilling mode: planning status with target temp set
	let isPrePitchChilling = $derived(
		batch?.status === 'planning' && batch?.temp_target != null
	);

	// Check if wort has reached pitch temperature
	let pitchTempReached = $derived.by(() => {
		if (!isPrePitchChilling || !liveReading?.temp || !batch?.temp_target) return false;
		return liveReading.temp <= batch.temp_target;
	});

	// Calculate chilling progress (100% when at or below target)
	let chillingProgress = $derived.by(() => {
		if (!isPrePitchChilling || !liveReading?.temp || !batch?.temp_target) return null;
		// Assume starting temp is roughly 30°C higher than target (typical post-boil)
		const estimatedStartTemp = batch.temp_target + 30;
		const currentTemp = liveReading.temp;
		const targetTemp = batch.temp_target;

		if (currentTemp <= targetTemp) return 100;
		if (currentTemp >= estimatedStartTemp) return 0;

		const progress = ((estimatedStartTemp - currentTemp) / (estimatedStartTemp - targetTemp)) * 100;
		return Math.min(100, Math.max(0, progress));
	});

	// Get live readings from WebSocket if device is linked
	// Supports all device types: Tilt, GravityMon, iSpindel
	// - GravityMon/iSpindel: device_id is the device's ID (e.g., "fce4b6")
	// - Tilt: device_id is the color (e.g., "RED" or "BLUE")
	let liveReading = $derived.by(() => {
		if (!batch?.device_id) return null;

		// First try direct ID match (works for all device types)
		const directMatch = tiltsState.tilts.get(batch.device_id);
		if (directMatch) return directMatch;

		// Fall back to color match for Tilt devices (device_id might be "tilt-red" format)
		const colorMatch = batch.device_id.match(/^(?:tilt-)?(\w+)$/i);
		if (!colorMatch?.[1]) return null;
		const targetColor = colorMatch[1].toUpperCase();
		for (const tilt of tiltsState.tilts.values()) {
			if (tilt.color && tilt.color.toUpperCase() === targetColor) {
				return tilt;
			}
		}
		return null;
	});

	async function loadBatch() {
		loading = true;
		error = null;
		try {
			batch = await fetchBatch(batchId);
			if (batch.status === 'fermenting' || batch.status === 'conditioning') {
				try {
					progress = await fetchBatchProgress(batchId);
				} catch {
					// Progress may not be available
				}
			}
			// Load control status if heater or cooler is configured
			if (batch.heater_entity_id || batch.cooler_entity_id) {
				try {
					controlStatus = await fetchBatchControlStatus(batchId);
				} catch {
					// Control status may not be available
				}
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load batch';
		} finally {
			loading = false;
		}
	}

	async function handleStatusChange(newStatus: BatchStatus) {
		if (!batch || statusUpdating) return;

		// Show reminder when entering conditioning from fermenting
		if (newStatus === 'conditioning' && batch.status === 'fermenting') {
			const message =
				'💡 Entering Conditioning Phase\n\n' +
				'Reminder: Adjust target temperature if cold crashing.\n' +
				'Temperature control will continue during conditioning.\n\n' +
				'Continue?';

			if (!confirm(message)) {
				return;
			}
		}

		statusUpdating = true;
		try {
			batch = await updateBatch(batch.id, { status: newStatus });
			// Reload progress if needed
			if (newStatus === 'fermenting' || newStatus === 'conditioning') {
				progress = await fetchBatchProgress(batch.id);
			}
		} catch (e) {
			console.error('Failed to update status:', e);
		} finally {
			statusUpdating = false;
		}
	}

	async function handleFormSubmit(data: BatchUpdate) {
		if (!batch) return;
		batch = await updateBatch(batch.id, data);
		isEditing = false;
		// Reload control status if heater or cooler was changed
		if (batch.heater_entity_id || batch.cooler_entity_id) {
			try {
				controlStatus = await fetchBatchControlStatus(batch.id);
			} catch {
				// Control status may not be available
			}
		}
	}

	async function handleDelete() {
		if (!batch) return;

		deleting = true;
		try {
			await deleteBatch(batch.id);
			goto('/batches');
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to delete batch';
			deleting = false;
			showDeleteConfirm = false;
		}
	}

	async function handleOverride(deviceType: 'heater' | 'cooler', state: 'on' | 'off' | null) {
		if (!batch || heaterLoading) return;
		heaterLoading = true;
		try {
			await setBatchHeaterOverride(batch.id, state, 60, deviceType);
			// Reload control status
			controlStatus = await fetchBatchControlStatus(batch.id);
		} catch (e) {
			console.error('Failed to set override:', e);
		} finally {
			heaterLoading = false;
		}
	}

	async function handleClearAllOverrides() {
		if (!batch || heaterLoading) return;
		heaterLoading = true;
		try {
			// Clear heater override if configured
			if (batch.heater_entity_id) {
				await setBatchHeaterOverride(batch.id, null, 60, 'heater');
			}
			// Clear cooler override if configured
			if (batch.cooler_entity_id) {
				await setBatchHeaterOverride(batch.id, null, 60, 'cooler');
			}
			// Reload control status
			controlStatus = await fetchBatchControlStatus(batch.id);
		} catch (e) {
			console.error('Failed to clear overrides:', e);
		} finally {
			heaterLoading = false;
		}
	}

	// WebSocket connection for live heater state updates
	function connectControlWebSocket() {
		if (controlWs?.readyState === WebSocket.OPEN) return;

		const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
		const wsUrl = `${protocol}//${window.location.host}/ws`;

		controlWs = new WebSocket(wsUrl);

		controlWs.onmessage = async (event) => {
			try {
				const data = JSON.parse(event.data);

				// Handle control events for this batch
				if (data.type === 'control_event' && data.batch_id === batchId) {
					// Update device state based on action
					if (controlStatus) {
						if (data.action === 'heat_on') {
							controlStatus = { ...controlStatus, heater_state: 'on' };
						} else if (data.action === 'heat_off') {
							controlStatus = { ...controlStatus, heater_state: 'off' };
						} else if (data.action === 'cool_on') {
							controlStatus = { ...controlStatus, cooler_state: 'on' };
						} else if (data.action === 'cool_off') {
							controlStatus = { ...controlStatus, cooler_state: 'off' };
						}
					}
				}
			} catch (e) {
				// Not a JSON message or parse error - ignore
			}
		};

		controlWs.onclose = () => {
			controlWs = null;
			// Reconnect after 3 seconds
			wsReconnectTimer = setTimeout(connectControlWebSocket, 3000);
		};

		controlWs.onerror = () => {
			controlWs?.close();
		};
	}

	function disconnectControlWebSocket() {
		if (wsReconnectTimer) {
			clearTimeout(wsReconnectTimer);
			wsReconnectTimer = null;
		}
		controlWs?.close();
		controlWs = null;
	}

	function formatSG(value?: number | null): string {
		if (value === undefined || value === null) return '--';
		return formatGravity(value);
	}

	function formatTempValue(value?: number | null): string {
		if (value === undefined || value === null) return '--';
		return formatTemp(value);
	}

	function formatShortDate(isoString?: string | null): string {
		if (!isoString) return '--';
		const date = new Date(isoString);
		return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
	}

	function formatDuration(startIso?: string | null): string {
		if (!startIso) return '--';
		const start = new Date(startIso);
		const now = new Date();
		const hours = (now.getTime() - start.getTime()) / (1000 * 60 * 60);
		if (hours < 1) return `${Math.round(hours * 60)}m`;
		if (hours < 24) return `${hours.toFixed(1)}h`;
		const days = hours / 24;
		if (days < 7) return `${days.toFixed(1)}d`;
		return `${Math.round(days)}d`;
	}

	function formatDate(dateStr?: string | null): string {
		if (!dateStr) return '--';
		return new Date(dateStr).toLocaleDateString('en-GB', {
			weekday: 'short',
			day: 'numeric',
			month: 'short',
			year: 'numeric'
		});
	}

	function formatDateTime(dateStr?: string | null): string {
		if (!dateStr) return '--';
		return new Date(dateStr).toLocaleString('en-GB', {
			day: 'numeric',
			month: 'short',
			hour: 'numeric',
			minute: '2-digit'
		});
	}

	onMount(() => {
		loadBatch();
		// Connect WebSocket for live heater state updates
		connectControlWebSocket();
	});

	onDestroy(() => {
		disconnectControlWebSocket();
	});
</script>

<svelte:head>
	<title>{batch?.name || 'Batch'} | BrewSignal</title>
</svelte:head>

<div class="page-container">
	<!-- Back link -->
	<div class="back-link">
		<a href="/batches" class="back-btn">
			<svg class="back-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
			</svg>
			Back to Batches
		</a>
	</div>

	{#if loading}
		<div class="loading-state">
			<div class="spinner"></div>
			<span>Loading batch...</span>
		</div>
	{:else if error}
		<div class="error-state">
			<span class="error-icon">!</span>
			<p>{error}</p>
			<button type="button" class="retry-btn" onclick={loadBatch}>Retry</button>
		</div>
	{:else if !batch}
		<div class="error-state">
			<p>Batch not found</p>
		</div>
	{:else if isEditing}
		<BatchForm
			{batch}
			onSubmit={handleFormSubmit}
			onCancel={() => (isEditing = false)}
		/>
	{:else}
		<!-- Batch Header -->
		<div class="batch-header">
			<div class="header-main">
				<div class="batch-number">#{batch.batch_number || '?'}</div>
				<div class="header-info">
					<h1 class="batch-name">{batch.name || batch.recipe?.name || 'Unnamed Batch'}</h1>
					{#if batch.recipe}
						<a href="/recipes/{batch.recipe.id}" class="recipe-link">
							{batch.recipe.name}
							{#if batch.recipe.type}
								<span class="recipe-type">({batch.recipe.type})</span>
							{/if}
						</a>
					{/if}
					{#if batch.start_time}
						<div class="batch-timing">
							Started {formatShortDate(batch.start_time)} · {formatDuration(batch.start_time)} ago
						</div>
					{:else if batch.brew_date}
						<div class="batch-timing">
							Brewed {formatShortDate(batch.brew_date)}
						</div>
					{/if}
				</div>
			</div>
			<div class="header-actions">
				<!-- Status selector -->
				<div class="status-selector">
					<select
						class="status-select"
						value={batch.status}
						onchange={(e) => handleStatusChange(e.currentTarget.value as BatchStatus)}
						disabled={statusUpdating}
						style="color: {statusInfo.color}; background: {statusInfo.bg};"
					>
						{#each statusOptions as status}
							<option value={status}>{statusConfig[status].label}</option>
						{/each}
					</select>
				</div>
				<button type="button" class="edit-btn" onclick={() => (isEditing = true)}>
					<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
					</svg>
					Edit
				</button>
				<button type="button" class="delete-btn" onclick={() => (showDeleteConfirm = true)} aria-label="Delete batch">
					<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
					</svg>
				</button>
			</div>
		</div>

		<!-- Pre-Pitch Chilling Banner -->
		{#if isPrePitchChilling}
			<div class="chilling-banner" class:ready={pitchTempReached}>
				<div class="chilling-header">
					{#if pitchTempReached}
						<span class="chilling-icon">🍺</span>
						<h3 class="chilling-title">Ready to Pitch!</h3>
					{:else}
						<span class="chilling-icon">❄️</span>
						<h3 class="chilling-title">Chilling to Pitch Temperature</h3>
					{/if}
				</div>

				<div class="chilling-content">
					<div class="temp-display">
						<div class="temp-current">
							<span class="temp-label">Current</span>
							<span class="temp-value">{liveReading?.temp != null ? formatTempValue(liveReading.temp) : '--'}</span>
						</div>
						<div class="temp-arrow">→</div>
						<div class="temp-target">
							<span class="temp-label">Target</span>
							<span class="temp-value">{batch.temp_target != null ? formatTempValue(batch.temp_target) : '--'}</span>
						</div>
					</div>

					{#if chillingProgress != null && !pitchTempReached}
						<div class="progress-section">
							<div class="progress-bar">
								<div class="progress-fill" style="width: {chillingProgress}%"></div>
							</div>
							<span class="progress-text">{Math.round(chillingProgress)}% to target</span>
						</div>
					{/if}

					<div class="chilling-status">
						{#if !batch.cooler_entity_id}
							<span class="status-warning">⚠️ No cooler configured - set a cooler entity to enable automated chilling</span>
						{:else if !configState.config.ha_enabled || !configState.config.temp_control_enabled}
							<span class="status-warning">⚠️ Temperature control disabled in settings</span>
						{:else if pitchTempReached}
							<span class="status-ready">Wort has reached pitch temperature - ready to add yeast!</span>
						{:else}
							<span class="status-active">Cooler will run automatically when temp exceeds target + hysteresis</span>
						{/if}
					</div>
				</div>
			</div>
		{/if}

		<!-- Main content grid -->
		<div class="content-grid">
			<!-- Left column -->
			<div class="stats-section">
				<!-- Fermentation Card (includes live readings) -->
				<BatchFermentationCard
					{batch}
					currentSg={liveReading?.sg ?? progress?.measured?.current_sg}
					{progress}
					{liveReading}
				/>

				<!-- Recipe Targets Card (only if recipe exists) -->
				{#if batch.recipe}
					<BatchRecipeTargetsCard recipe={batch.recipe} yeastStrain={batch.yeast_strain} />
				{/if}
			</div>

			<!-- Right column -->
			<div class="info-section">
				<!-- Device Card -->
				<BatchDeviceCard
					{batch}
					{liveReading}
					onEdit={() => (isEditing = true)}
				/>

				<!-- ML Predictions Panel -->
				<MLPredictions
					batchId={batch.id}
					measuredOg={batch.measured_og}
					currentSg={liveReading?.sg}
					{liveReading}
				/>

				<!-- Temperature Control Card -->
				{#if hasTempControl && (batch.status === 'fermenting' || batch.status === 'conditioning')}
					<div class="info-card temp-control-card"
						class:heater-on={controlStatus?.heater_state === 'on'}
						class:cooler-on={controlStatus?.cooler_state === 'on'}
						class:collapsed={tempControlCollapsed}>
						<button
							type="button"
							class="collapsible-header"
							onclick={() => tempControlCollapsed = !tempControlCollapsed}
						>
							<h3 class="info-title">Temperature Control</h3>
							<div class="collapse-indicator">
								{#if controlStatus?.heater_state === 'on'}
									<span class="status-badge heater">🔥 Heating</span>
								{:else if controlStatus?.cooler_state === 'on'}
									<span class="status-badge cooler">❄️ Cooling</span>
								{:else if tempControlCollapsed && controlStatus}
									<span class="status-badge idle">🎯 {formatTempValue(controlStatus.target_temp)}{tempUnit}</span>
								{/if}
								<svg class="chevron" class:rotated={!tempControlCollapsed} fill="none" viewBox="0 0 24 24" stroke="currentColor">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
								</svg>
							</div>
						</button>

						{#if !tempControlCollapsed}
						<!-- Device status indicators -->
						<div class="device-status-grid">
							{#if batch.heater_entity_id}
								<div class="device-status heater">
									<div class="device-icon-wrap" class:active={controlStatus?.heater_state === 'on'}>
										🔥
									</div>
									<div class="device-info">
										<span class="device-label">Heater</span>
										<span class="device-state" class:on={controlStatus?.heater_state === 'on'}>
											{controlStatus?.heater_state === 'on' ? 'ON' : 'OFF'}
										</span>
										<span class="device-entity">{batch.heater_entity_id}</span>
									</div>
								</div>
							{/if}

							{#if batch.cooler_entity_id}
								<div class="device-status cooler">
									<div class="device-icon-wrap" class:active={controlStatus?.cooler_state === 'on'}>
										❄️
									</div>
									<div class="device-info">
										<span class="device-label">Cooler</span>
										<span class="device-state" class:on={controlStatus?.cooler_state === 'on'}>
											{controlStatus?.cooler_state === 'on' ? 'ON' : 'OFF'}
										</span>
										<span class="device-entity">{batch.cooler_entity_id}</span>
									</div>
								</div>
							{/if}
						</div>

						{#if controlStatus}
							<div class="control-details">
								<div class="control-detail">
									<span class="detail-label">Target</span>
									<span class="detail-value">{formatTempValue(controlStatus.target_temp)}{tempUnit}</span>
								</div>
								<div class="control-detail">
									<span class="detail-label">Hysteresis</span>
									<span class="detail-value">±{controlStatus.hysteresis?.toFixed(1) || '--'}{tempUnit}</span>
								</div>
							</div>

							{#if controlStatus.override_active}
								<div class="override-banner">
									<span class="override-icon">⚡</span>
									<span>Override active: {controlStatus.override_state?.toUpperCase()}</span>
									<button
										type="button"
										class="override-cancel-inline"
										onclick={() => handleClearAllOverrides()}
										disabled={heaterLoading}
									>
										Cancel
									</button>
								</div>
							{/if}

							<div class="override-controls">
								<span class="override-label">Manual Override (1hr)</span>
								<div class="override-btns-grid">
									{#if batch.heater_entity_id}
										<button
											type="button"
											class="override-btn heat-on"
											onclick={() => handleOverride('heater', 'on')}
											disabled={heaterLoading}
										>
											Force Heat ON
										</button>
										<button
											type="button"
											class="override-btn heat-off"
											onclick={() => handleOverride('heater', 'off')}
											disabled={heaterLoading}
										>
											Force Heat OFF
										</button>
									{/if}

									{#if batch.cooler_entity_id}
										<button
											type="button"
											class="override-btn cool-on"
											onclick={() => handleOverride('cooler', 'on')}
											disabled={heaterLoading}
										>
											Force Cool ON
										</button>
										<button
											type="button"
											class="override-btn cool-off"
											onclick={() => handleOverride('cooler', 'off')}
											disabled={heaterLoading}
										>
											Force Cool OFF
										</button>
									{/if}

									<button
										type="button"
										class="override-btn auto-mode"
										onclick={() => handleClearAllOverrides()}
										disabled={heaterLoading}
									>
										Auto Mode
									</button>
								</div>
							</div>
						{/if}
						{/if}
					</div>
				{:else if (batch.heater_entity_id || batch.cooler_entity_id) && batch.status !== 'fermenting'}
					<div class="info-card">
						<h3 class="info-title">Temperature Control</h3>
						<div class="no-device">
							{#if batch.heater_entity_id}
								<span>Heater: {batch.heater_entity_id}</span>
							{/if}
							{#if batch.cooler_entity_id}
								<span>Cooler: {batch.cooler_entity_id}</span>
							{/if}
							<span class="hint">Active only during fermentation</span>
						</div>
					</div>
				{/if}

				<!-- Notes Card (only if notes exist) -->
				{#if batch.notes}
					<BatchNotesCard notes={batch.notes} />
				{/if}
			</div>
		</div>

		<!-- Fermentation Chart (shows historical data for all batches with a device) -->
		{#if batch.device_id}
			<div class="chart-section">
				<FermentationChart
					batchId={batch.id}
					deviceColor={batch.device_id}
					originalGravity={batch.measured_og}
					{controlEvents}
				/>
			</div>
		{/if}
	{/if}
</div>

{#if showDeleteConfirm}
	<div class="modal-overlay" onclick={() => (showDeleteConfirm = false)}>
		<div class="modal" onclick={(e) => e.stopPropagation()}>
			<h2 class="modal-title">Delete Batch?</h2>
			<p class="modal-text">
				Are you sure you want to delete "{batch?.name || 'this batch'}"? This cannot be undone.
			</p>
			<div class="modal-actions">
				<button
					type="button"
					class="modal-btn cancel"
					onclick={() => (showDeleteConfirm = false)}
					disabled={deleting}
				>
					Cancel
				</button>
				<button type="button" class="modal-btn delete" onclick={handleDelete} disabled={deleting}>
					{deleting ? 'Deleting...' : 'Delete Batch'}
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.page-container {
		max-width: 1200px;
	}

	/* Pre-Pitch Chilling Banner */
	.chilling-banner {
		margin-bottom: 1.5rem;
		padding: 1.25rem;
		background: linear-gradient(135deg, rgba(59, 130, 246, 0.1) 0%, rgba(147, 197, 253, 0.05) 100%);
		border: 1px solid rgba(59, 130, 246, 0.3);
		border-radius: 0.75rem;
	}

	.chilling-banner.ready {
		background: linear-gradient(135deg, rgba(34, 197, 94, 0.15) 0%, rgba(134, 239, 172, 0.05) 100%);
		border-color: rgba(34, 197, 94, 0.4);
	}

	.chilling-header {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-bottom: 1rem;
	}

	.chilling-icon {
		font-size: 1.5rem;
	}

	.chilling-title {
		font-size: 1.125rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
	}

	.chilling-content {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.temp-display {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 1.5rem;
	}

	.temp-current,
	.temp-target {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.25rem;
	}

	.temp-label {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.temp-value {
		font-size: 1.75rem;
		font-weight: 600;
		color: var(--text-primary);
		font-variant-numeric: tabular-nums;
	}

	.temp-arrow {
		font-size: 1.5rem;
		color: var(--text-muted);
	}

	.progress-section {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.5rem;
	}

	.progress-bar {
		width: 100%;
		max-width: 300px;
		height: 8px;
		background: var(--bg-elevated);
		border-radius: 4px;
		overflow: hidden;
	}

	.progress-fill {
		height: 100%;
		background: linear-gradient(90deg, #3b82f6, #60a5fa);
		border-radius: 4px;
		transition: width 0.5s ease;
	}

	.progress-text {
		font-size: 0.8125rem;
		color: var(--text-secondary);
	}

	.chilling-status {
		text-align: center;
		font-size: 0.875rem;
	}

	.status-warning {
		color: #f59e0b;
	}

	.status-active {
		color: var(--text-secondary);
	}

	.status-ready {
		color: var(--positive);
		font-weight: 500;
	}

	.back-link {
		margin-bottom: 1.5rem;
	}

	.back-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.875rem;
		font-weight: 500;
		color: var(--text-secondary);
		text-decoration: none;
		transition: color var(--transition);
	}

	.back-btn:hover {
		color: var(--text-primary);
	}

	.back-icon {
		width: 1rem;
		height: 1rem;
	}

	/* Loading/Error states */
	.loading-state,
	.error-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 4rem 2rem;
		text-align: center;
		color: var(--text-secondary);
	}

	.spinner {
		width: 2rem;
		height: 2rem;
		border: 2px solid var(--bg-hover);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
		margin-bottom: 1rem;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	.error-icon {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 3rem;
		height: 3rem;
		font-size: 1.5rem;
		font-weight: 700;
		color: var(--negative);
		background: rgba(239, 68, 68, 0.1);
		border-radius: 50%;
		margin-bottom: 1rem;
	}

	.retry-btn {
		margin-top: 1rem;
		padding: 0.5rem 1rem;
		font-size: 0.875rem;
		font-weight: 500;
		color: var(--text-primary);
		background: var(--bg-elevated);
		border: 1px solid var(--border-default);
		border-radius: 0.375rem;
		cursor: pointer;
	}

	/* Header */
	.batch-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 1.5rem;
		margin-bottom: 2rem;
		padding-bottom: 1.5rem;
		border-bottom: 1px solid var(--border-subtle);
	}

	.header-main {
		display: flex;
		align-items: flex-start;
		gap: 1rem;
	}

	.batch-number {
		flex-shrink: 0;
		font-family: var(--font-mono);
		font-size: 0.875rem;
		font-weight: 500;
		color: var(--text-muted);
		background: var(--bg-elevated);
		padding: 0.375rem 0.75rem;
		border-radius: 0.375rem;
		margin-top: 0.25rem;
	}

	.header-info {
		min-width: 0;
	}

	.batch-name {
		font-size: 1.5rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0 0 0.25rem 0;
		line-height: 1.3;
	}

	.recipe-link {
		font-size: 0.875rem;
		color: var(--accent);
		text-decoration: none;
	}

	.recipe-link:hover {
		text-decoration: underline;
	}

	.recipe-type {
		color: var(--text-muted);
	}

	.batch-timing {
		font-size: 0.8125rem;
		color: var(--text-muted);
		margin-top: 0.25rem;
	}

	.header-actions {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		flex-shrink: 0;
	}

	.status-selector {
		position: relative;
	}

	.status-select {
		padding: 0.5rem 2rem 0.5rem 0.75rem;
		font-size: 0.8125rem;
		font-weight: 500;
		border: none;
		border-radius: 9999px;
		cursor: pointer;
		appearance: none;
		background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%239ca3af'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'/%3E%3C/svg%3E");
		background-repeat: no-repeat;
		background-position: right 0.5rem center;
		background-size: 1rem;
	}

	.edit-btn,
	.delete-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		padding: 0.5rem 0.75rem;
		font-size: 0.8125rem;
		font-weight: 500;
		border-radius: 0.375rem;
		cursor: pointer;
		transition: all var(--transition);
	}

	.edit-btn {
		color: var(--text-secondary);
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
	}

	.edit-btn:hover {
		color: var(--text-primary);
		border-color: var(--border-default);
	}

	.delete-btn {
		color: var(--text-muted);
		background: transparent;
		border: none;
		padding: 0.5rem;
	}

	.delete-btn:hover {
		color: var(--negative);
	}

	.btn-icon {
		width: 1rem;
		height: 1rem;
	}

	/* Content grid */
	.content-grid {
		display: grid;
		grid-template-columns: 2fr 1fr;
		gap: 1rem;
		align-items: start;
	}

	@media (max-width: 900px) {
		.content-grid {
			grid-template-columns: 1fr;
		}
	}

	/* Chart section */
	.chart-section {
		margin-top: 1.5rem;
	}

	/* Stats section */
	.stats-section {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	/* Info section */
	.info-section {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.info-card {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.75rem;
		padding: 1.25rem;
	}

	.info-title {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin: 0 0 1rem 0;
	}

	/* Keep .no-device for heater card compatibility */
	.no-device {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		font-size: 0.875rem;
		color: var(--text-muted);
	}

	.hint {
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	/* Temperature Control Card */
	.temp-control-card {
		transition: all 0.3s ease;
	}

	.temp-control-card.collapsed {
		padding-bottom: 0.75rem;
	}

	.collapsible-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		width: 100%;
		background: none;
		border: none;
		cursor: pointer;
		padding: 0;
		margin-bottom: 1rem;
	}

	.temp-control-card.collapsed .collapsible-header {
		margin-bottom: 0;
	}

	.collapsible-header .info-title {
		margin: 0;
	}

	.collapse-indicator {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.status-badge {
		font-size: 0.6875rem;
		font-weight: 600;
		padding: 0.125rem 0.375rem;
		border-radius: 0.25rem;
	}

	.status-badge.heater {
		background: rgba(239, 68, 68, 0.15);
		color: var(--tilt-red);
	}

	.status-badge.cooler {
		background: rgba(59, 130, 246, 0.15);
		color: var(--tilt-blue);
	}

	.status-badge.idle {
		background: var(--bg-elevated);
		color: var(--text-secondary);
	}

	.chevron {
		width: 1rem;
		height: 1rem;
		color: var(--text-muted);
		transition: transform 0.2s ease;
	}

	.chevron.rotated {
		transform: rotate(180deg);
	}

	.temp-control-card.heater-on {
		background: rgba(239, 68, 68, 0.08);
		border-color: rgba(239, 68, 68, 0.3);
	}

	.temp-control-card.cooler-on {
		background: rgba(59, 130, 246, 0.08);
		border-color: rgba(59, 130, 246, 0.3);
	}

	.device-status-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
		gap: 0.75rem;
		margin-bottom: 1rem;
	}

	.device-status {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}

	.device-icon-wrap {
		width: 2.5rem;
		height: 2.5rem;
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: 0.5rem;
		background: var(--bg-elevated);
		font-size: 1.25rem;
		transition: all 0.3s ease;
		filter: grayscale(100%) opacity(0.5);
	}

	.device-status.heater .device-icon-wrap.active {
		background: rgba(239, 68, 68, 0.2);
		animation: pulse-glow-red 2s ease-in-out infinite;
		filter: none;
	}

	.device-status.cooler .device-icon-wrap.active {
		background: rgba(59, 130, 246, 0.2);
		animation: pulse-glow-blue 2s ease-in-out infinite;
		filter: none;
	}

	@keyframes pulse-glow-red {
		0%, 100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4); }
		50% { box-shadow: 0 0 15px 3px rgba(239, 68, 68, 0.3); }
	}

	@keyframes pulse-glow-blue {
		0%, 100% { box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.4); }
		50% { box-shadow: 0 0 15px 3px rgba(59, 130, 246, 0.3); }
	}

	.device-info {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
	}

	.device-label {
		font-size: 0.625rem;
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-muted);
	}

	.device-state {
		font-size: 1rem;
		font-weight: 700;
		font-family: 'JetBrains Mono', monospace;
		color: var(--text-secondary);
	}

	.device-status.heater .device-state.on {
		color: var(--tilt-red);
	}

	.device-status.cooler .device-state.on {
		color: var(--tilt-blue);
	}

	.device-entity {
		font-size: 0.6875rem;
		color: var(--text-muted);
		font-family: 'JetBrains Mono', monospace;
	}

	.control-details {
		display: flex;
		gap: 1.5rem;
		margin-bottom: 0.75rem;
		padding: 0.5rem 0.75rem;
		background: var(--bg-elevated);
		border-radius: 0.375rem;
	}

	.control-detail {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
	}

	.detail-label {
		font-size: 0.625rem;
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-muted);
	}

	.detail-value {
		font-size: 0.875rem;
		font-weight: 500;
		font-family: 'JetBrains Mono', monospace;
		color: var(--text-primary);
	}

	.override-banner {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-bottom: 0.75rem;
		padding: 0.5rem 0.75rem;
		background: rgba(59, 130, 246, 0.1);
		border-radius: 0.375rem;
		font-size: 0.75rem;
		color: var(--tilt-blue);
	}

	.override-icon {
		font-size: 0.875rem;
	}

	.override-cancel-inline {
		margin-left: auto;
		padding: 0.25rem 0.5rem;
		font-size: 0.6875rem;
		font-weight: 500;
		border-radius: 0.25rem;
		background: transparent;
		border: 1px solid var(--tilt-blue);
		color: var(--tilt-blue);
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.override-cancel-inline:hover:not(:disabled) {
		background: rgba(59, 130, 246, 0.15);
	}

	.override-cancel-inline:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.override-controls {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
	}

	.override-label {
		font-size: 0.625rem;
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-muted);
	}

	.override-btns-grid {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 0.375rem;
	}

	.override-btn {
		padding: 0.5rem 0.75rem;
		font-size: 0.6875rem;
		font-weight: 500;
		border-radius: 0.25rem;
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
		color: var(--text-secondary);
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.override-btn:hover:not(:disabled) {
		background: var(--bg-hover);
		color: var(--text-primary);
	}

	.override-btn.heat-on:hover:not(:disabled) {
		background: rgba(239, 68, 68, 0.1);
		border-color: var(--tilt-red);
		color: var(--tilt-red);
	}

	.override-btn.heat-off:hover:not(:disabled) {
		background: rgba(239, 68, 68, 0.05);
		border-color: rgba(239, 68, 68, 0.3);
		color: var(--text-primary);
	}

	.override-btn.cool-on:hover:not(:disabled) {
		background: rgba(59, 130, 246, 0.1);
		border-color: var(--tilt-blue);
		color: var(--tilt-blue);
	}

	.override-btn.cool-off:hover:not(:disabled) {
		background: rgba(59, 130, 246, 0.05);
		border-color: rgba(59, 130, 246, 0.3);
		color: var(--text-primary);
	}

	.override-btn.auto-mode {
		grid-column: 1 / -1;
		background: var(--accent);
		border-color: var(--accent);
		color: white;
	}

	.override-btn.auto-mode:hover:not(:disabled) {
		background: var(--accent-hover);
		border-color: var(--accent-hover);
	}

	.override-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	@media (max-width: 640px) {
		.batch-header {
			flex-direction: column;
			gap: 1rem;
		}

		.header-actions {
			width: 100%;
			justify-content: flex-start;
		}
	}

	/* Modal styles */
	.modal-overlay {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.6);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
	}

	.modal {
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 8px;
		padding: var(--space-6);
		max-width: 400px;
		width: 90%;
	}

	.modal-title {
		font-size: 20px;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0 0 var(--space-3) 0;
	}

	.modal-text {
		font-size: 14px;
		color: var(--text-secondary);
		line-height: 1.5;
		margin: 0 0 var(--space-6) 0;
	}

	.modal-actions {
		display: flex;
		gap: var(--space-3);
		justify-content: flex-end;
	}

	.modal-btn {
		padding: var(--space-2) var(--space-4);
		border-radius: 6px;
		font-size: 14px;
		font-weight: 500;
		cursor: pointer;
		transition: all var(--transition);
	}

	.modal-btn.cancel {
		background: transparent;
		border: 1px solid var(--border-default);
		color: var(--text-primary);
	}

	.modal-btn.cancel:hover {
		background: var(--bg-hover);
	}

	.modal-btn.delete {
		background: var(--negative);
		border: none;
		color: white;
	}

	.modal-btn.delete:hover {
		background: #dc2626;
	}

	.modal-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
</style>
