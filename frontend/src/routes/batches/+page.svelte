<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import type { BatchResponse, BatchProgressResponse } from '$lib/api';
	import { fetchActiveBatches, fetchCompletedBatches, fetchDeletedBatches, fetchBatchProgress, deleteBatch, restoreBatch } from '$lib/api';
	import BatchCard from '$lib/components/BatchCard.svelte';
	import { tiltsState } from '$lib/stores/tilts.svelte';
	import { onConfigLoaded } from '$lib/config';

	type TabType = 'active' | 'completed' | 'deleted';

	// State
	let batches = $state<BatchResponse[]>([]);
	let progressMap = $state<Map<number, BatchProgressResponse>>(new Map());
	let loading = $state(true);
	let error = $state<string | null>(null);
	let activeTab = $state<TabType>('active');
	let searchQuery = $state('');
	let notification = $state<{ message: string; type: 'success' | 'error' } | null>(null);

	// Map device_id to batch_id for live updates
	let deviceToBatch = $derived(
		new Map(
			batches
				.filter((b) => b.device_id && (b.status === 'fermenting' || b.status === 'conditioning'))
				.map((b) => [b.device_id!, b.id])
		)
	);

	// Enhance progress with live WebSocket data
	let liveProgressMap = $derived.by(() => {
		const enhanced = new Map(progressMap);
		for (const [deviceId, batchId] of deviceToBatch) {
			const tiltReading = tiltsState.tilts.get(deviceId);
			if (tiltReading) {
				const existing = enhanced.get(batchId) || {
					batch_id: batchId,
					status: 'fermenting' as const,
					measured: {},
					temperature: { status: 'unknown' as const },
					progress: {},
					targets: {}
				};
				// Update with live data
				enhanced.set(batchId, {
					...existing,
					measured: {
						...existing.measured,
						current_sg: tiltReading.sg
					},
					temperature: {
						...existing.temperature,
						current: tiltReading.temp,
						// Determine temperature status based on yeast thresholds (if available)
						status: existing.temperature.yeast_min !== undefined && existing.temperature.yeast_max !== undefined
							? (tiltReading.temp < existing.temperature.yeast_min ? 'too_cold' :
							   tiltReading.temp > existing.temperature.yeast_max ? 'too_hot' : 'in_range')
							: existing.temperature.status
					}
				});
			}
		}
		return enhanced;
	});

	// Filtered batches
	let filteredBatches = $derived(
		batches.filter((b) => {
			const matchesSearch =
				!searchQuery ||
				(b.name?.toLowerCase().includes(searchQuery.toLowerCase()) ?? false) ||
				(b.recipe?.name?.toLowerCase().includes(searchQuery.toLowerCase()) ?? false);
			return matchesSearch;
		})
	);

	async function loadBatches() {
		loading = true;
		error = null;
		try {
			// Load batches based on active tab
			switch (activeTab) {
				case 'active':
					batches = await fetchActiveBatches();
					break;
				case 'completed':
					batches = await fetchCompletedBatches();
					break;
				case 'deleted':
					batches = await fetchDeletedBatches();
					break;
			}

			// Load progress for fermenting/conditioning batches
			const activeStatuses = ['fermenting', 'conditioning'];
			const activeBatches = batches.filter((b) => activeStatuses.includes(b.status));
			const progressPromises = activeBatches.map(async (b) => {
				try {
					const progress = await fetchBatchProgress(b.id);
					return [b.id, progress] as const;
				} catch {
					return null;
				}
			});
			const results = await Promise.all(progressPromises);
			const newMap = new Map<number, BatchProgressResponse>();
			for (const result of results) {
				if (result) {
					newMap.set(result[0], result[1]);
				}
			}
			progressMap = newMap;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load batches';
		} finally {
			loading = false;
		}
	}

	function handleViewDetails(batchId: number) {
		goto(`/batches/${batchId}`);
	}

	async function handleDelete(batchId: number, batchName: string) {
		const isHardDelete = activeTab === 'deleted';
		const confirmMessage = isHardDelete
			? 'This will permanently delete this batch. This cannot be undone. Are you sure?'
			: `Soft delete "${batchName}"? You can restore it later from the Deleted tab.`;

		if (!confirm(confirmMessage)) return;

		try {
			await deleteBatch(batchId, isHardDelete);
			showNotification('Batch deleted successfully', 'success');
			await loadBatches();
		} catch (e) {
			showNotification('Failed to delete batch', 'error');
		}
	}

	async function handleRestore(batchId: number, batchName: string) {
		try {
			await restoreBatch(batchId);
			showNotification(`"${batchName}" restored successfully`, 'success');
			await loadBatches();
		} catch (e) {
			showNotification('Failed to restore batch', 'error');
		}
	}

	function showNotification(message: string, type: 'success' | 'error') {
		notification = { message, type };
		setTimeout(() => {
			notification = null;
		}, 3000);
	}

	onMount(() => {
		// Wait for config to be initialized before loading batches
		// This ensures auth token is available for Cloud Sync users
		onConfigLoaded(() => {
			loadBatches();
		});
	});

	// Reload when tab changes
	$effect(() => {
		if (activeTab !== undefined) {
			loadBatches();
		}
	});
</script>

<svelte:head>
	<title>Batches | BrewSignal</title>
</svelte:head>

<div class="page-container">
	<!-- Notification -->
	{#if notification}
		<div class="notification" class:success={notification.type === 'success'} class:error={notification.type === 'error'} role="status">
			<span>{notification.message}</span>
			<button type="button" class="notification-close" onclick={() => (notification = null)} aria-label="Dismiss">&times;</button>
		</div>
	{/if}

	<!-- Header -->
	<div class="page-header">
		<div class="header-content">
			<h1 class="page-title">Batches</h1>
			<p class="page-description">Track your fermentation batches</p>
		</div>
		<button type="button" class="create-btn" onclick={() => goto('/batches/new')}>
			<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
				<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
			</svg>
			New Batch
		</button>
	</div>

	<!-- Tabs -->
	<div class="tabs-container">
		<div class="tabs" role="tablist">
			<button type="button" role="tab" aria-selected={activeTab === 'active'} class="tab" class:active={activeTab === 'active'} onclick={() => (activeTab = 'active')}>Active</button>
			<button type="button" role="tab" aria-selected={activeTab === 'completed'} class="tab" class:active={activeTab === 'completed'} onclick={() => (activeTab = 'completed')}>Completed</button>
			<button type="button" role="tab" aria-selected={activeTab === 'deleted'} class="tab" class:active={activeTab === 'deleted'} onclick={() => (activeTab = 'deleted')}>Deleted</button>
		</div>
		<div class="search-box">
			<svg class="search-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
				<path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
			</svg>
			<input type="text" placeholder="Search batches..." aria-label="Search batches" bind:value={searchQuery} class="search-input" />
		</div>
	</div>

	<!-- Content -->
	{#if loading}
		<div class="state" role="status">
			<div class="spinner"></div>
			<span>Loading batches...</span>
		</div>
	{:else if error}
		<div class="state error-state">
			<p>{error}</p>
			<button type="button" class="secondary-btn" onclick={loadBatches}>Retry</button>
		</div>
	{:else if filteredBatches.length === 0}
		<div class="state">
			{#if batches.length === 0}
				<h3>No {activeTab} batches yet</h3>
				<p>
					{#if activeTab === 'active'}
						Create your first batch to start tracking fermentation
					{:else if activeTab === 'completed'}
						Complete a batch to see it here
					{:else}
						Deleted batches will appear here
					{/if}
				</p>
				{#if activeTab === 'active'}
					<button type="button" class="tint-btn" onclick={() => goto('/batches/new')}>Create Batch</button>
				{/if}
			{:else}
				<h3>No matches</h3>
				<p>Try adjusting your search query</p>
			{/if}
		</div>
	{:else}
		<div class="ledger-scroll">
			<div class="ledger-head" aria-hidden="true">
				<span>#</span>
				<span>Batch</span>
				<span>Status</span>
				<span class="r">OG</span>
				<span class="r">FG / Now</span>
				<span class="r">ABV</span>
				<span class="r">Temp</span>
				<span class="r">Brewed</span>
				<span></span>
			</div>
			<div class="ledger">
				{#each filteredBatches as batch (batch.id)}
					<div class="entry">
						<BatchCard
							{batch}
							progress={liveProgressMap.get(batch.id)}
							liveReading={batch.device_id ? tiltsState.tilts.get(batch.device_id) : null}
							onViewDetails={() => handleViewDetails(batch.id)}
						/>
						{#if batch.deleted_at}
							<div class="deleted-row">
								<span class="deleted-badge">Deleted {new Date(batch.deleted_at).toLocaleDateString()}</span>
								<div class="batch-actions">
									<button type="button" class="secondary-btn" onclick={() => handleRestore(batch.id, batch.name || batch.recipe?.name || 'Unnamed Batch')}>Restore</button>
									<button type="button" class="danger-btn" onclick={() => handleDelete(batch.id, batch.name || batch.recipe?.name || 'Unnamed Batch')}>Permanent Delete</button>
								</div>
							</div>
						{/if}
					</div>
				{/each}
			</div>
		</div>
	{/if}
</div>

<style>
	.page-container {
		max-width: 100%;
		padding: var(--space-lg) var(--space-xl) var(--space-xl);
	}
	.page-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-end;
		gap: var(--space-md);
		margin-bottom: var(--space-lg);
	}
	.header-content {
		flex: 1;
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
	.create-btn {
		display: inline-flex;
		align-items: center;
		gap: var(--space-xs);
		min-height: 44px;
		padding: 0 var(--space-md);
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--accent-ink);
		background: var(--accent);
		border-radius: 4px;
		cursor: pointer;
		transition: background-color 140ms var(--ease-out-quart);
	}
	.create-btn:hover {
		background: var(--accent-hover);
	}
	.tint-btn {
		display: inline-flex;
		align-items: center;
		min-height: 44px;
		padding: 0 var(--space-md);
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--accent);
		background: var(--accent-tint);
		border: 1px solid var(--accent-rule);
		border-radius: 4px;
		cursor: pointer;
	}
	.tint-btn:hover {
		border-color: var(--accent);
	}
	.btn-icon {
		width: 1rem;
		height: 1rem;
	}
	.secondary-btn,
	.danger-btn {
		min-height: 44px;
		padding: 0 var(--space-md);
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		border-radius: 4px;
		cursor: pointer;
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		color: var(--ink-primary);
	}
	.secondary-btn:hover {
		background: var(--accent-tint);
		border-color: var(--accent-rule);
	}
	.danger-btn {
		color: var(--status-danger);
		border-color: color-mix(in oklch, var(--status-danger) 55%, transparent);
	}
	.danger-btn:hover {
		background: var(--negative-muted);
	}

	/* Notification */
	.notification {
		position: fixed;
		top: var(--space-md);
		right: var(--space-md);
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		padding: var(--space-sm) var(--space-md);
		border-radius: 4px;
		border: 1px solid var(--rule-strong);
		background: var(--bg-elevated);
		color: var(--ink-primary);
		font-size: var(--text-sm);
		font-weight: 700;
		z-index: 1000;
		animation: slideIn 200ms var(--ease-out-quart);
	}
	@keyframes slideIn {
		from {
			transform: translateY(-8px);
			opacity: 0;
		}
		to {
			transform: translateY(0);
			opacity: 1;
		}
	}
	.notification.success {
		border-color: color-mix(in oklch, var(--status-steady) 60%, transparent);
		color: var(--status-steady);
	}
	.notification.error {
		border-color: color-mix(in oklch, var(--status-danger) 60%, transparent);
		color: var(--status-danger);
	}
	.notification-close {
		color: inherit;
		font-size: 1.5rem;
		line-height: 1;
		min-width: 32px;
		min-height: 32px;
		cursor: pointer;
	}

	/* Tabs */
	.tabs-container {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-md);
		align-items: center;
		border-bottom: 1px solid var(--rule-hairline);
		margin-bottom: var(--space-md);
	}
	.tabs {
		display: flex;
	}
	.tab {
		padding: 0 var(--space-md);
		min-height: 44px;
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--ink-secondary);
		border-bottom: 2px solid transparent;
		margin-bottom: -1px;
		cursor: pointer;
		transition: color 140ms var(--ease-out-quart);
	}
	.tab:hover {
		color: var(--ink-primary);
	}
	.tab.active {
		color: var(--accent);
		border-bottom-color: var(--accent);
	}
	.search-box {
		position: relative;
		flex: 1;
		max-width: 20rem;
		margin-left: auto;
	}
	.search-icon {
		position: absolute;
		left: var(--space-sm);
		top: 50%;
		transform: translateY(-50%);
		width: 1rem;
		height: 1rem;
		color: var(--ink-muted);
		pointer-events: none;
	}
	.search-input {
		width: 100%;
		min-height: 40px;
		padding: 0 var(--space-sm) 0 2.25rem;
		font-size: var(--text-sm);
		color: var(--ink-primary);
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		outline: none;
	}
	.search-input::placeholder {
		color: var(--ink-muted);
	}
	.search-input:focus {
		border-color: var(--accent);
	}

	/* Ledger */
	.ledger-scroll {
		overflow-x: auto;
	}
	.ledger-head {
		display: grid;
		grid-template-columns: 52px minmax(0, 2fr) 112px repeat(4, minmax(64px, 0.7fr)) minmax(120px, 1fr) 76px;
		gap: var(--space-sm);
		padding: var(--space-xs);
		border-bottom: 1px solid var(--rule-strong);
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--ink-muted);
	}
	.ledger-head .r {
		text-align: right;
	}
	.deleted-row {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-sm);
		padding: var(--space-xs) var(--space-xs) var(--space-sm);
		border-bottom: 1px solid var(--rule-hairline);
	}
	.deleted-badge {
		font-family: var(--font-display);
		font-size: 0.6875rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		padding: 2px 7px;
		border-radius: 2px;
		border: 1px solid color-mix(in oklch, var(--status-danger) 55%, transparent);
		color: var(--status-danger);
	}
	.batch-actions {
		display: flex;
		gap: var(--space-xs);
	}
	.entry :global(.row) {
		border-bottom: 1px solid var(--rule-hairline);
	}
	.entry:has(.deleted-row) :global(.row) {
		border-bottom: none;
	}

	/* States */
	.state {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-sm);
		padding: var(--space-2xl) var(--space-lg);
		text-align: center;
		color: var(--ink-secondary);
		border-top: 1px solid var(--rule-hairline);
	}
	.state h3 {
		font-family: var(--font-display);
		font-size: var(--text-lg);
		font-weight: 600;
		color: var(--ink-primary);
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
	.error-state {
		color: var(--status-danger);
	}

	@media (max-width: 900px) {
		.ledger-head {
			display: none;
		}
	}
	@media (max-width: 760px) {
		.page-container {
			padding: var(--space-lg) var(--space-md);
		}
		.page-header {
			flex-direction: column;
			align-items: flex-start;
		}
		.tabs-container {
			flex-direction: column;
			align-items: stretch;
			gap: var(--space-sm);
			border-bottom: none;
		}
		.tabs {
			width: 100%;
			border-bottom: 1px solid var(--rule-hairline);
		}
		.tab {
			flex: 1;
			text-align: center;
		}
		.search-box {
			max-width: 100%;
			margin-left: 0;
		}
		.notification {
			left: var(--space-md);
			right: var(--space-md);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.notification,
		.spinner {
			animation: none;
		}
	}
</style>
