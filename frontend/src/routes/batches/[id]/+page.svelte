<script lang="ts">
	import { batchUrl, recipeUrl } from '$lib/urls';
	import { onMount, onDestroy } from 'svelte';
	import { page } from '$app/stores';
	import { goto, replaceState } from '$app/navigation';
	import type { BatchResponse, BatchProgressResponse, BatchUpdate, BatchStatus, BatchControlStatus, ControlEvent } from '$lib/api';
	import { fetchBatch, fetchBatchProgress, updateBatch, deleteBatch, fetchBatchControlStatus, setBatchHeaterOverride, fetchBatchReflections, fetchTastingNotes } from '$lib/api';
	import { configState } from '$lib/stores/config.svelte';
	import { tiltsState } from '$lib/stores/tilts.svelte';
	import { onConfigLoaded } from '$lib/config';
	import BatchForm from '$lib/components/BatchForm.svelte';

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
	let statusError = $state<string | null>(null);
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

	const phaseOrder: Record<PhaseTab, number> = {
		planning: 0,
		brewing: 1,
		fermenting: 2,
		conditioning: 3,
		completed: 4,
	};

	let currentPhaseIndex = $derived(
		batch ? phaseOrder[batch.status === 'archived' ? 'completed' : batch.status as PhaseTab] ?? 0 : 0
	);

	function isTabFuture(tabId: PhaseTab): boolean {
		return phaseOrder[tabId] > currentPhaseIndex;
	}

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

	// Show the readable URL (/batches/16-american-pale-ale) without a reload,
	// also after a rename; the leading id is what the page reads (tilt_ui-9hg).
	$effect(() => {
		if (!batch) return;
		const path = batchUrl(batch);
		// Compare with the real address: shallow replaceState does not update
		// $page.url, and reading $page here would re-run this effect in a loop.
		if (location.pathname !== path) replaceState(path + location.search + location.hash, {});
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
		statusError = null;
		try {
			batch = await updateBatch(batch.id, { status: newStatus });
			// Reload progress if needed
			if (newStatus === 'fermenting' || newStatus === 'conditioning') {
				progress = await fetchBatchProgress(batch.id);
			}
		} catch (e) {
			console.error('Failed to update status:', e);
			statusError = e instanceof Error ? e.message : 'Failed to update batch status';
		} finally {
			statusUpdating = false;
		}
	}

	async function handleStartBrewDay() {
		if (!batch || statusUpdating) return;
		statusUpdating = true;
		statusError = null;
		try {
			batch = await updateBatch(batch.id, { status: 'brewing' });
		} catch (e) {
			console.error('Failed to start brew day:', e);
			statusError = e instanceof Error ? e.message : 'Failed to update batch status';
		} finally {
			statusUpdating = false;
		}
	}

	async function handleStartFermentation() {
		if (!batch || statusUpdating) return;
		statusUpdating = true;
		statusError = null;
		try {
			batch = await updateBatch(batch.id, { status: 'fermenting' });
			progress = await fetchBatchProgress(batch.id);
		} catch (e) {
			console.error('Failed to start fermentation:', e);
			statusError = e instanceof Error ? e.message : 'Failed to update batch status';
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
		{#if statusError}
			<div class="status-error" role="alert">{statusError}</div>
		{/if}

		<!-- Batch Header -->
		<div class="batch-header">
			<div class="header-main">
				<div class="header-info">
					<div class="batch-number"><span>Batch #{batch.batch_number || '?'}</span><span class="status-selector">
						<select
							class="status-select s-{batch.status}"
							aria-label="Batch status"
							value={batch.status}
							onchange={(e) => handleStatusChange(e.currentTarget.value as BatchStatus)}
							disabled={statusUpdating}
						>
							{#each statusOptions as status}
								<option value={status}>{statusConfig[status].label}</option>
							{/each}
						</select>
						<svg class="status-chevron" viewBox="0 0 16 16" width="10" height="10" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M4 6l4 4 4-4" /></svg>
					</span>{#if batch.recipe?.style?.name}<span class="style-part"><span class="sep" aria-hidden="true">&middot;</span> <span class="style-name">{batch.recipe.style.name}</span></span>{/if}</div>
					<h1 class="batch-name">{batch.name || batch.recipe?.name || 'Unnamed Batch'}</h1>
					{#if batch.recipe}
						<a href={recipeUrl(batch.recipe)} class="recipe-link">
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
				<!-- Pause readings button (only for fermenting/conditioning) -->
				{#if batch.status === 'fermenting' || batch.status === 'conditioning'}
					<button
						type="button"
						class="pause-btn"
						class:paused={batch.readings_paused}
						onclick={handleTogglePause}
						disabled={pauseUpdating}
						title={batch.readings_paused ? 'Resume storing readings' : 'Pause storing readings'}
						aria-label={batch.readings_paused ? 'Resume readings' : 'Pause readings'}
					>
						{#if batch.readings_paused}
							<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
								<path stroke-linecap="round" stroke-linejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
							</svg>
							<span class="lbl">Resume</span>
						{:else}
							<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z" />
							</svg>
							<span class="lbl">Pause</span>
						{/if}
					</button>
				{/if}
				<button type="button" class="edit-btn" onclick={() => (isEditing = true)} aria-label="Edit batch">
					<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
					</svg>
					<span class="lbl">Edit</span>
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
			<div class="paused-banner" role="status">
				<div class="paused-header">
					<svg class="paused-icon" aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
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

		<!-- Phase Tab Bar -->
		<div class="phase-tabs" role="tablist" aria-label="Batch phase tabs">
			{#each tabs as tab}
				{@const future = isTabFuture(tab.id)}
				{@const completed = phaseOrder[tab.id] < currentPhaseIndex}
				{@const current = phaseOrder[tab.id] === currentPhaseIndex}
				<button
					type="button"
					role="tab"
					class="phase-tab"
					class:active={activeTab === tab.id}
					class:future
					class:phase-completed={completed}
					class:phase-current={current}
					aria-selected={activeTab === tab.id}
					onclick={() => activeTab = tab.id}
				>
					{#if completed}
						<svg class="tab-check" viewBox="0 0 16 16" fill="none" aria-hidden="true">
							<path d="M3.5 8.5L6.5 11.5L12.5 5.5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
						</svg>
					{:else if current}
						<span class="tab-dot"></span>
					{/if}
					{tab.label}
				</button>
			{/each}
		</div>

		<!-- Phase Content -->
		<div class="phase-content" role="tabpanel">
			{#if isTabFuture(activeTab)}
				<div class="future-phase-placeholder">
					<p class="future-text">Not started yet</p>
					<p class="future-subtext">This phase will become active as the batch progresses.</p>
				</div>
			{:else if activeTab === 'planning'}
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
					onBatchUpdate={(updated) => batch = updated}
					onTastingNotesReload={loadTastingNotes}
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
					onReflectionsReload={loadReflections}
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
		padding: var(--space-lg) var(--space-xl) var(--space-xl);
	}
	.back-btn {
		display: inline-flex;
		align-items: center;
		gap: var(--space-xs);
		min-height: 44px;
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--ink-secondary);
		transition: color 140ms var(--ease-out-quart);
	}
	.back-btn:hover {
		color: var(--ink-primary);
	}
	.back-icon {
		width: 1rem;
		height: 1rem;
	}

	/* States */
	.loading-state,
	.status-error {
		margin-bottom: 0.75rem;
		padding: 0.625rem 0.875rem;
		border: 1px solid var(--color-red-500, #ef4444);
		border-radius: 0.5rem;
		color: var(--color-red-500, #ef4444);
		font-size: 0.875rem;
	}

	.error-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-sm);
		padding: var(--space-2xl) var(--space-lg);
		text-align: center;
		color: var(--ink-secondary);
		border-top: 1px solid var(--rule-hairline);
	}
	.error-state {
		color: var(--status-danger);
	}
	.spinner {
		width: 1.5rem;
		height: 1.5rem;
		border: 2px solid var(--rule-hairline);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
	.retry-btn {
		min-height: 44px;
		padding: 0 var(--space-md);
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--ink-primary);
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		cursor: pointer;
	}

	/* Header */
	.batch-header {
		display: flex;
		flex-wrap: wrap;
		justify-content: space-between;
		align-items: flex-start;
		gap: var(--space-md);
		padding-bottom: var(--space-md);
		margin-bottom: var(--space-md);
		border-bottom: 1px solid var(--rule-strong);
	}
	.header-main {
		min-width: 0;
		flex: 1 1 20rem;
	}
	.batch-number {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: var(--space-xs);
		font-family: var(--font-num);
		font-size: var(--text-xs);
		font-weight: 600;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		color: var(--accent);
		margin-bottom: var(--space-xs);
	}
	.style-part {
		white-space: nowrap;
	}
	.batch-number .sep {
		color: var(--rule-strong);
	}
	.batch-number .style-name {
		font-family: var(--font-body);
		text-transform: none;
		font-weight: 400;
		letter-spacing: 0.02em;
		color: var(--ink-secondary);
	}
	.batch-name {
		font-family: var(--font-display);
		font-size: clamp(1.5rem, 2.4vw, 2rem);
		font-weight: 700;
		line-height: 1.15;
		letter-spacing: -0.02em;
		color: var(--ink-primary);
		overflow-wrap: anywhere;
	}
	.recipe-link {
		display: inline-block;
		margin-top: var(--space-2xs);
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		border-bottom: 1px solid transparent;
	}
	.recipe-link:hover {
		color: var(--ink-primary);
		border-bottom-color: var(--accent);
	}
	.recipe-type {
		color: var(--ink-muted);
	}
	.batch-timing {
		margin-top: var(--space-2xs);
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: var(--text-xs);
		color: var(--ink-secondary);
	}
	.header-actions {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-xs);
	}
	.status-selector {
		position: relative;
		display: inline-flex;
		align-items: center;
	}
	.status-select {
		appearance: none;
		height: 22px;
		padding: 0 22px 0 8px;
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		line-height: 1;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--ink-secondary);
		background: transparent;
		border: 1px solid var(--rule-strong);
		border-radius: 2px;
		cursor: pointer;
	}
	/* Compact badge on desk; full touch target on phone/tablet */
	@media (pointer: coarse), (max-width: 760px) {
		.status-select {
			height: 44px;
			padding: 0 28px 0 12px;
		}
	}
	.status-chevron {
		position: absolute;
		right: 6px;
		top: 50%;
		transform: translateY(-50%);
		color: var(--ink-secondary);
		pointer-events: none;
	}
	.status-select:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}
	.status-select option {
		background: var(--bg-elevated);
		color: var(--ink-primary);
	}
	.status-select.s-planning,
	.status-select.s-brewing,
	.status-select.s-fermenting {
		color: var(--accent);
		border-color: var(--accent-rule);
	}
	.status-select.s-planning {
		background: var(--accent-tint);
	}
	.status-select.s-conditioning {
		color: var(--status-conditioning);
		border-color: color-mix(in oklch, var(--status-conditioning) 55%, transparent);
	}
	.status-select.s-completed {
		color: var(--status-completed);
		border-color: color-mix(in oklch, var(--status-completed) 55%, transparent);
	}
	.pause-btn,
	.edit-btn,
	.delete-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: var(--space-xs);
		min-height: 44px;
		min-width: 44px;
		padding: 0 var(--space-sm);
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--ink-primary);
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		cursor: pointer;
		transition: background-color 140ms var(--ease-out-quart);
	}
	.pause-btn:hover:not(:disabled),
	.edit-btn:hover {
		background: var(--accent-tint);
		border-color: var(--accent-rule);
	}
	.pause-btn.paused {
		color: var(--accent);
		background: var(--accent-tint);
		border-color: var(--accent-rule);
	}
	.pause-btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}
	.delete-btn {
		color: var(--status-danger);
		border-color: color-mix(in oklch, var(--status-danger) 50%, transparent);
	}
	.delete-btn:hover {
		background: var(--negative-muted);
	}
	.btn-icon {
		width: 1rem;
		height: 1rem;
	}

	/* Readings paused banner */
	.paused-banner {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-sm) var(--space-md);
		margin-bottom: var(--space-md);
		padding: var(--space-sm) var(--space-md);
		border: 1px solid color-mix(in oklch, var(--status-warn) 50%, transparent);
		background: var(--warning-muted);
	}
	.paused-header {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
		color: var(--status-warn);
	}
	.paused-icon {
		width: 1.125rem;
		height: 1.125rem;
	}
	.paused-title {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}
	.paused-text {
		flex: 1 1 18rem;
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}
	.resume-btn {
		min-height: 44px;
		padding: 0 var(--space-md);
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--ink-primary);
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		cursor: pointer;
	}
	.resume-btn:hover:not(:disabled) {
		background: var(--accent-tint);
		border-color: var(--accent-rule);
	}
	.resume-btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	/* Phase step track: done ink, current accent, future muted */
	.phase-tabs {
		display: flex;
		gap: 0;
		overflow-x: auto;
		border-bottom: 1px solid var(--rule-hairline);
		margin-bottom: var(--space-lg);
		scrollbar-width: none;
	}
	.phase-tabs::-webkit-scrollbar {
		display: none;
	}
	.phase-tab {
		position: relative;
		display: inline-flex;
		align-items: center;
		gap: var(--space-xs);
		flex: 1 0 auto;
		justify-content: center;
		min-height: 44px;
		padding: 0 var(--space-md);
		margin-bottom: -1px;
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		white-space: nowrap;
		color: var(--ink-primary);
		border-bottom: 2px solid transparent;
		cursor: pointer;
		transition: color 140ms var(--ease-out-quart);
	}
	.phase-tab:hover:not(.active) {
		background: var(--bg-surface);
	}
	.phase-tab.future {
		color: var(--ink-muted);
	}
	.phase-tab.active {
		color: var(--accent);
		border-bottom-color: var(--accent);
	}
	.tab-check {
		width: 0.875rem;
		height: 0.875rem;
	}
	.tab-dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: var(--accent);
	}
	.phase-content {
		min-width: 0;
	}
	.future-phase-placeholder {
		padding: var(--space-2xl) var(--space-lg);
		text-align: center;
		border-top: 1px solid var(--rule-hairline);
	}
	.future-text {
		font-family: var(--font-display);
		font-size: var(--text-lg);
		font-weight: 600;
		color: var(--ink-primary);
	}
	.future-subtext {
		margin-top: var(--space-2xs);
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}

	/* Delete modal */
	.modal-overlay {
		position: fixed;
		inset: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: var(--space-md);
		background: color-mix(in oklch, var(--bg-canvas) 80%, transparent);
		z-index: 100;
	}
	.modal {
		width: 100%;
		max-width: 26rem;
		padding: var(--space-lg);
		background: var(--bg-elevated);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
	}
	.modal-title {
		font-family: var(--font-display);
		font-size: var(--text-lg);
		font-weight: 700;
		color: var(--ink-primary);
		margin-bottom: var(--space-xs);
	}
	.modal-text {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		margin-bottom: var(--space-lg);
	}
	.modal-actions {
		display: flex;
		justify-content: flex-end;
		gap: var(--space-xs);
	}
	.modal-btn {
		min-height: 44px;
		padding: 0 var(--space-md);
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		border-radius: 4px;
		cursor: pointer;
	}
	.modal-btn.cancel {
		color: var(--ink-primary);
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
	}
	.modal-btn.cancel:hover {
		background: var(--bg-subtle);
	}
	.modal-btn.delete {
		color: var(--status-danger);
		background: transparent;
		border: 1px solid color-mix(in oklch, var(--status-danger) 60%, transparent);
	}
	.modal-btn.delete:hover:not(:disabled) {
		background: var(--negative-muted);
	}
	.modal-btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	@media (max-width: 760px) {
		.page-container {
			padding: var(--space-md);
		}
		.header-actions {
			width: 100%;
			flex-wrap: nowrap;
		}
		.header-actions .lbl {
			display: none;
		}
		.header-actions button {
			padding: 0;
			width: 44px;
		}
		.phase-tabs {
			mask-image: linear-gradient(to right, var(--ink-primary) calc(100% - 40px), transparent);
			-webkit-mask-image: linear-gradient(to right, var(--ink-primary) calc(100% - 40px), transparent);
		}
		.phase-tab {
			flex: 0 0 auto;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.spinner {
			animation: none;
		}
	}
</style>
