<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import type { BatchResponse, BatchProgressResponse, BatchUpdate, BatchStatus, BatchControlStatus, ControlEvent } from '$lib/api';
	import { fetchBatch, fetchBatchProgress, updateBatch, deleteBatch, fetchBatchControlStatus, setBatchHeaterOverride, fetchBatchReflections, fetchTastingNotes } from '$lib/api';
	import { configState } from '$lib/stores/config.svelte';
	import { tiltsState } from '$lib/stores/tilts.svelte';
	import { onConfigLoaded } from '$lib/config';
	import BatchForm from '$lib/components/BatchForm.svelte';
	import LifecycleStepper from '$lib/components/batch/LifecycleStepper.svelte';
	import PhaseRecipe from '$lib/components/batch/PhaseRecipe.svelte';
	import PhaseBrewDay from '$lib/components/batch/PhaseBrewDay.svelte';
	import PhaseFermentation from '$lib/components/batch/PhaseFermentation.svelte';
	import PhaseConditioning from '$lib/components/batch/PhaseConditioning.svelte';
	import PhaseComplete from '$lib/components/batch/PhaseComplete.svelte';
	import { statusConfig } from '$lib/components/status';
	import type { BatchReflection } from '$lib/types/reflection';
	import type { TastingNote } from '$lib/types/tasting';

	// WebSocket for live heater state updates
	let controlWs: WebSocket | null = null;
	let wsReconnectTimer: ReturnType<typeof setTimeout> | null = null;

	// State
	let batch = $state<BatchResponse | null>(null);
	let progress = $state<BatchProgressResponse | null>(null);
	let controlStatus = $state<BatchControlStatus | null>(null);
	let controlEvents = $state<ControlEvent[]>([]);
	let reflections = $state<BatchReflection[]>([]);
	let tastingNotes = $state<TastingNote[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let isEditing = $state(false);
	let statusUpdating = $state(false);
	let heaterLoading = $state(false);
	let showDeleteConfirm = $state(false);
	let deleting = $state(false);
	let tempControlCollapsed = $state(false);
	let pauseUpdating = $state(false);
	let reflectionsLoading = $state(false);
	let tastingLoading = $state(false);

	// Tab navigation state
	type PhaseTab = 'planning' | 'brewing' | 'fermenting' | 'conditioning' | 'completed';
	let activeTab = $state<PhaseTab>('planning');

	let batchId = $derived(parseInt($page.params.id ?? '0'));

	const statusOptions: BatchStatus[] = ['planning', 'brewing', 'fermenting', 'conditioning', 'completed', 'archived'];

	let statusInfo = $derived(batch ? statusConfig[batch.status] : statusConfig.planning);

	// Check if temperature control is available for this batch
	let hasTempControl = $derived(
		!!(configState.config.ha_enabled &&
		configState.config.temp_control_enabled &&
		(batch?.heater_entity_id || batch?.cooler_entity_id))
	);

	// Default active tab to current batch status
	$effect(() => {
		if (batch) {
			const status = batch.status;
			// Map archived to completed tab
			activeTab = status === 'archived' ? 'completed' : status as PhaseTab;
		}
	});

	const tabs: { id: PhaseTab; label: string }[] = [
		{ id: 'planning', label: 'Recipe' },
		{ id: 'brewing', label: 'Brew Day' },
		{ id: 'fermenting', label: 'Fermentation' },
		{ id: 'conditioning', label: 'Conditioning' },
		{ id: 'completed', label: 'Complete' },
	];

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
			// Load progress for active batches AND completed batches (for historical stats)
			if (batch.status === 'fermenting' || batch.status === 'conditioning' || batch.status === 'completed') {
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
			// Load reflections and tasting notes for completed/conditioning batches
			if (batch.status === 'completed' || batch.status === 'conditioning') {
				loadReflections();
				loadTastingNotes();
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load batch';
		} finally {
			loading = false;
		}
	}

	async function loadReflections() {
		reflectionsLoading = true;
		try {
			const response = await fetchBatchReflections(batchId);
			// Map API response to BatchReflection type
			reflections = response.map(r => ({
				...r,
				phase: r.phase as BatchReflection['phase']
			}));
		} catch (e) {
			console.error('Failed to load reflections:', e);
			reflections = [];
		} finally {
			reflectionsLoading = false;
		}
	}

	async function loadTastingNotes() {
		tastingLoading = true;
		try {
			const response = await fetchTastingNotes(batchId);
			// Map API response to TastingNote type, calculating days_since_packaging if we have package date
			const packageDate = batch?.packaged_at ? new Date(batch.packaged_at) : null;
			tastingNotes = response.map(n => {
				let daysSincePackaging: number | undefined = undefined;
				if (packageDate && n.tasted_at) {
					const tastedDate = new Date(n.tasted_at);
					daysSincePackaging = Math.floor((tastedDate.getTime() - packageDate.getTime()) / (1000 * 60 * 60 * 24));
					if (daysSincePackaging < 0) daysSincePackaging = undefined;
				}
				return {
					...n,
					days_since_packaging: daysSincePackaging,
				};
			});
		} catch (e) {
			console.error('Failed to load tasting notes:', e);
			tastingNotes = [];
		} finally {
			tastingLoading = false;
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

	async function handleStartBrewDay() {
		if (!batch || statusUpdating) return;
		statusUpdating = true;
		try {
			batch = await updateBatch(batch.id, { status: 'brewing' });
		} catch (e) {
			console.error('Failed to start brew day:', e);
		} finally {
			statusUpdating = false;
		}
	}

	async function handleStartFermentation() {
		if (!batch || statusUpdating) return;
		statusUpdating = true;
		try {
			batch = await updateBatch(batch.id, { status: 'fermenting' });
			progress = await fetchBatchProgress(batch.id);
		} catch (e) {
			console.error('Failed to start fermentation:', e);
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

	async function handleTogglePause() {
		if (!batch || pauseUpdating) return;

		pauseUpdating = true;
		try {
			batch = await updateBatch(batch.id, { readings_paused: !batch.readings_paused });
		} catch (e) {
			console.error('Failed to toggle pause:', e);
		} finally {
			pauseUpdating = false;
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

	onMount(() => {
		// Wait for config to be initialized before loading batch
		// This ensures auth token is available for Cloud Sync users
		onConfigLoaded(() => {
			loadBatch();
			// Connect WebSocket for live heater state updates
			connectControlWebSocket();
		});
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
				<!-- Pause readings button (only for fermenting/conditioning) -->
				{#if batch.status === 'fermenting' || batch.status === 'conditioning'}
					<button
						type="button"
						class="pause-btn"
						class:paused={batch.readings_paused}
						onclick={handleTogglePause}
						disabled={pauseUpdating}
						title={batch.readings_paused ? 'Resume storing readings' : 'Pause storing readings'}
					>
						{#if batch.readings_paused}
							<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
								<path stroke-linecap="round" stroke-linejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
							</svg>
							Resume
						{:else}
							<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z" />
							</svg>
							Pause
						{/if}
					</button>
				{/if}
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

		<!-- Readings Paused Banner -->
		{#if batch.readings_paused && (batch.status === 'fermenting' || batch.status === 'conditioning')}
			<div class="paused-banner">
				<div class="paused-header">
					<svg class="paused-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z" />
					</svg>
					<h3 class="paused-title">Readings Paused</h3>
				</div>
				<p class="paused-text">
					Hydrometer readings are not being stored. Live readings still display but won't be saved to the fermentation history.
				</p>
				<button type="button" class="resume-btn" onclick={handleTogglePause} disabled={pauseUpdating}>
					{pauseUpdating ? 'Resuming...' : 'Resume Readings'}
				</button>
			</div>
		{/if}

		<!-- Lifecycle Stepper -->
		<LifecycleStepper currentStatus={batch.status} />

		<!-- Phase Tab Bar -->
		<div class="phase-tabs" role="tablist" aria-label="Batch phase tabs">
			{#each tabs as tab}
				<button
					type="button"
					role="tab"
					class="phase-tab"
					class:active={activeTab === tab.id}
					aria-selected={activeTab === tab.id}
					onclick={() => activeTab = tab.id}
				>
					{tab.label}
				</button>
			{/each}
		</div>

		<!-- Phase Content -->
		<div class="phase-content" role="tabpanel">
			{#if activeTab === 'planning'}
				<PhaseRecipe
					{batch}
					{statusUpdating}
					onStartBrewDay={handleStartBrewDay}
				/>
			{:else if activeTab === 'brewing'}
				<PhaseBrewDay
					{batch}
					{liveReading}
					{statusUpdating}
					onStartFermentation={handleStartFermentation}
					onEdit={() => (isEditing = true)}
					onBatchUpdate={(updated) => batch = updated}
				/>
			{:else if activeTab === 'fermenting'}
				<PhaseFermentation
					{batch}
					{progress}
					{liveReading}
					{controlStatus}
					{controlEvents}
					{hasTempControl}
					{heaterLoading}
					{tempControlCollapsed}
					onOverride={handleOverride}
					onClearOverrides={handleClearAllOverrides}
					onTempControlToggle={() => tempControlCollapsed = !tempControlCollapsed}
				/>
			{:else if activeTab === 'conditioning'}
				<PhaseConditioning
					{batch}
					{progress}
					{liveReading}
					{controlStatus}
					{controlEvents}
					{hasTempControl}
					{heaterLoading}
					{tempControlCollapsed}
					{tastingNotes}
					{tastingLoading}
					onOverride={handleOverride}
					onClearOverrides={handleClearAllOverrides}
					onTempControlToggle={() => tempControlCollapsed = !tempControlCollapsed}
				/>
			{:else if activeTab === 'completed'}
				<PhaseComplete
					{batch}
					{reflections}
					{tastingNotes}
					{reflectionsLoading}
					{tastingLoading}
					onBatchUpdate={(updated) => batch = updated}
					onTastingNotesReload={loadTastingNotes}
				/>
			{/if}
		</div>
	{/if}
</div>

{#if showDeleteConfirm}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="modal-overlay"
		onclick={() => (showDeleteConfirm = false)}
		onkeydown={(e) => e.key === 'Escape' && (showDeleteConfirm = false)}
		role="presentation"
	>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="modal" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="delete-modal-title" tabindex="-1">
			<h2 id="delete-modal-title" class="modal-title">Delete Batch?</h2>
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

	/* Readings Paused Banner */
	.paused-banner {
		margin-bottom: 1.5rem;
		padding: 1.25rem;
		background: linear-gradient(135deg, rgba(245, 158, 11, 0.12) 0%, rgba(251, 191, 36, 0.05) 100%);
		border: 1px solid rgba(245, 158, 11, 0.4);
		border-radius: 0.75rem;
		text-align: center;
	}

	.paused-header {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.75rem;
		margin-bottom: 0.75rem;
	}

	.paused-icon {
		width: 1.5rem;
		height: 1.5rem;
		color: var(--recipe-accent);
	}

	.paused-title {
		font-size: 1.125rem;
		font-weight: 600;
		color: var(--recipe-accent);
		margin: 0;
	}

	.paused-text {
		font-size: 0.875rem;
		color: var(--text-secondary);
		margin: 0 0 1rem 0;
	}

	.resume-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.5rem 1rem;
		font-size: 0.875rem;
		font-weight: 500;
		color: var(--recipe-accent);
		background: var(--recipe-accent-muted);
		border: 1px solid var(--recipe-accent-border);
		border-radius: 0.375rem;
		cursor: pointer;
		transition: all var(--transition);
	}

	.resume-btn:hover:not(:disabled) {
		background: rgba(245, 158, 11, 0.25);
		border-color: rgba(245, 158, 11, 0.6);
	}

	.resume-btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
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

	.pause-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		padding: 0.5rem 0.75rem;
		font-size: 0.8125rem;
		font-weight: 500;
		border-radius: 0.375rem;
		cursor: pointer;
		transition: all var(--transition);
		color: var(--text-secondary);
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
	}

	.pause-btn:hover:not(:disabled) {
		color: var(--recipe-accent);
		border-color: var(--recipe-accent-border);
		background: var(--recipe-accent-muted);
	}

	.pause-btn.paused {
		color: var(--recipe-accent);
		border-color: var(--recipe-accent-border);
		background: var(--recipe-accent-muted);
	}

	.pause-btn.paused:hover:not(:disabled) {
		color: var(--positive);
		border-color: rgba(34, 197, 94, 0.4);
		background: var(--positive-muted);
	}

	.pause-btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.btn-icon {
		width: 1rem;
		height: 1rem;
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
		background: var(--negative);
	}

	.modal-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	/* Phase Tab Bar */
	.phase-tabs {
		display: flex;
		gap: 0.25rem;
		padding: 0.25rem;
		background: var(--bg-elevated);
		border-radius: 0.5rem;
		margin-bottom: 1.5rem;
		overflow-x: auto;
	}

	.phase-tab {
		flex: 1;
		min-width: 0;
		padding: 0.625rem 0.75rem;
		font-size: 0.8125rem;
		font-weight: 500;
		color: var(--text-muted);
		background: transparent;
		border: none;
		border-radius: 0.375rem;
		cursor: pointer;
		transition: all 0.15s ease;
		white-space: nowrap;
		text-align: center;
	}

	.phase-tab:hover:not(.active) {
		color: var(--text-secondary);
		background: var(--bg-hover);
	}

	.phase-tab.active {
		color: var(--text-primary);
		background: var(--bg-surface);
		font-weight: 600;
		box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
	}

	.phase-content {
		min-height: 200px;
	}
</style>
