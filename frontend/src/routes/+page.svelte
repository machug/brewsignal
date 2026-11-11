<script lang="ts">
	import { onMount } from 'svelte';
	import { tiltsState } from '$lib/stores/tilts.svelte';
	import { configState } from '$lib/stores/config.svelte';
	import StatusStrip, { type ChamberIdleStatus } from '$lib/components/home/StatusStrip.svelte';
	import BatchInstrument from '$lib/components/home/BatchInstrument.svelte';
	import BatchLog from '$lib/components/home/BatchLog.svelte';
	import InventoryGlance from '$lib/components/home/InventoryGlance.svelte';
	import AssistantEntry from '$lib/components/home/AssistantEntry.svelte';
	import type { BatchResponse, BatchProgressResponse } from '$lib/api';
	import { fetchBatches, fetchBatchProgress } from '$lib/api';
	import { onConfigLoaded } from '$lib/config';

	// Batch state
	let allBatches = $state<BatchResponse[]>([]);
	let batches = $state<BatchResponse[]>([]); // active: fermenting or conditioning
	let progressMap = $state<Map<number, BatchProgressResponse>>(new Map());
	let loading = $state(true);
	let error = $state<string | null>(null);

	// Chamber idle state
	let chamberIdle = $state<ChamberIdleStatus | null>(null);

	onMount(() => {
		let idleTimer: ReturnType<typeof setInterval> | undefined;
		// Wait for config to be initialized before loading batches
		// This ensures auth token is available for Cloud Sync users
		onConfigLoaded(() => {
			loadBatches();
			loadChamberIdleStatus();
			idleTimer = setInterval(loadChamberIdleStatus, 30000);
		});
		return () => clearInterval(idleTimer);
	});

	async function loadBatches() {
		loading = true;
		error = null;
		try {
			allBatches = await fetchBatches(undefined, undefined, 200);
			batches = allBatches.filter((b) => b.status === 'fermenting' || b.status === 'conditioning');

			// Load progress for each active batch
			const progressPromises = batches.map(async (b) => {
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

	async function loadChamberIdleStatus() {
		try {
			const response = await fetch('/api/control/chamber-idle/status');
			if (response.ok) {
				chamberIdle = await response.json();
			}
		} catch {
			// Silently ignore - not critical
		}
	}

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
				// Use calibrated values (consistent with batch detail view)
				const displaySg = tiltReading.sg;
				const displayTemp = tiltReading.temp;
				// Update with live data
				enhanced.set(batchId, {
					...existing,
					measured: {
						...existing.measured,
						current_sg: displaySg
					},
					temperature: {
						...existing.temperature,
						current: displayTemp,
						// Determine temperature status based on yeast thresholds (if available)
						status: existing.temperature.yeast_min !== undefined && existing.temperature.yeast_max !== undefined
							? (displayTemp < existing.temperature.yeast_min ? 'too_cold' :
							   displayTemp > existing.temperature.yeast_max ? 'too_hot' : 'in_range')
							: existing.temperature.status
					}
				});
			}
		}
		return enhanced;
	});

	// Only one batch instrument open at a time; the first opens by default
	let expandedBatchId = $state<number | null>(null);
	let expandTouched = false;

	$effect(() => {
		if (!expandTouched && expandedBatchId === null && batches.length > 0) {
			expandedBatchId = batches[0].id;
		}
	});

	function toggleExpand(batchId: number) {
		expandTouched = true;
		expandedBatchId = expandedBatchId === batchId ? null : batchId;
	}

	// Active batches with wort temperature outside the yeast range (for the status strip)
	let outOfRange = $derived(
		batches.flatMap((b) => {
			const st = liveProgressMap.get(b.id)?.temperature.status;
			return st === 'too_hot' || st === 'too_cold'
				? [`Batch #${b.batch_number ?? b.id} ${st === 'too_hot' ? 'above' : 'below'} yeast range`]
				: [];
		})
	);
</script>

<svelte:head>
	<title>Home | BrewSignal</title>
</svelte:head>

<div class="workbench">
	<div class="col-primary">
		<div class="rise" style="--i: 0">
			<StatusStrip {chamberIdle} {outOfRange} activeCount={batches.length} />
		</div>

		{#if loading}
			<section class="empty rise" style="--i: 1" aria-live="polite">
				<p class="empty-line"><span class="connecting-dots">Loading batches</span></p>
			</section>
		{:else if error}
			<section class="empty rise" style="--i: 1" role="alert">
				<p class="empty-title">Could not load batches</p>
				<p class="empty-line">{error}</p>
			</section>
		{:else if batches.length === 0}
			<section class="empty rise" style="--i: 1" aria-labelledby="empty-h">
				<h2 id="empty-h" class="empty-title">No batch fermenting</h2>
				<p class="empty-line">
					Start one from a recipe, then set its status to Fermenting or Conditioning to track it here.
				</p>
				<div class="empty-links">
					<a class="action" href="/recipes">Choose a recipe</a>
					<a class="link" href="/batches">Go to batches &rarr;</a>
				</div>
			</section>
		{:else}
			{#each batches as batch, i (batch.id)}
				<div class="rise" style="--i: {i + 1}">
					<BatchInstrument
						{batch}
						progress={liveProgressMap.get(batch.id)}
						expanded={expandedBatchId === batch.id}
						onToggleExpand={() => toggleExpand(batch.id)}
						onBatchUpdated={loadBatches}
					/>
				</div>
			{/each}
		{/if}

		<div class="rise" style="--i: {batches.length + 1}">
			<BatchLog batches={allBatches} />
		</div>
	</div>

	<div class="col-secondary">
		{#if configState.config.ai_enabled}
			<div class="rise" style="--i: 2"><AssistantEntry /></div>
		{/if}
		<div class="rise" style="--i: 3"><InventoryGlance /></div>
	</div>
</div>

<style>
	.workbench {
		display: grid;
		grid-template-columns: minmax(0, 1.68fr) minmax(300px, 1fr);
		align-items: stretch;
		border-top: 1px solid var(--rule-hairline);
	}
	.col-primary {
		display: flex;
		flex-direction: column;
		min-width: 0;
		border-right: 1px solid var(--rule-hairline);
	}
	.col-secondary {
		display: flex;
		flex-direction: column;
		min-width: 0;
	}

	/* One subtle staggered fade on load; content is visible at rest */
	.rise {
		animation: rise 420ms var(--ease-out-quart) both;
		animation-delay: calc(var(--i, 0) * 60ms);
	}
	@keyframes rise {
		from {
			opacity: 0;
			transform: translateY(6px);
		}
		to {
			opacity: 1;
			transform: none;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.rise {
			animation: none;
		}
		.connecting-dots::after {
			animation: none;
		}
	}

	/* Empty instrument: compact, teaches the next action */
	.empty {
		padding: var(--space-xl);
		border-bottom: 1px solid var(--rule-hairline);
		display: flex;
		flex-direction: column;
		gap: var(--space-sm);
	}
	.empty-title {
		font-family: var(--font-display);
		font-size: var(--text-xl);
		font-weight: 700;
		letter-spacing: -0.02em;
		color: var(--ink-primary);
	}
	.empty-line {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		max-width: 60ch;
	}
	.empty-links {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-md);
		margin-top: var(--space-xs);
	}
	.action {
		display: inline-flex;
		align-items: center;
		min-height: 40px;
		padding: 0 var(--space-md);
		background-color: var(--accent);
		color: var(--accent-ink);
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		border-radius: 2px;
	}
	.action:hover {
		background-color: var(--accent-hover);
	}
	.link {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-secondary);
		border-bottom: 1px solid transparent;
		padding-bottom: 1px;
	}
	.link:hover {
		color: var(--ink-primary);
		border-bottom-color: var(--accent);
	}
	.connecting-dots::after {
		content: '';
		animation: dots 1.5s steps(4, end) infinite;
	}
	@keyframes dots {
		0%,
		20% {
			content: '';
		}
		40% {
			content: '.';
		}
		60% {
			content: '..';
		}
		80%,
		100% {
			content: '...';
		}
	}

	@media (max-width: 1040px) {
		.workbench {
			grid-template-columns: minmax(0, 1fr);
		}
		.col-primary {
			border-right: none;
		}
		.col-secondary {
			display: grid;
			grid-template-columns: 1.15fr 1fr;
			border-top: 1px solid var(--rule-strong);
		}
		.col-secondary > .rise:first-child :global(section) {
			border-right: 1px solid var(--rule-hairline);
			border-bottom: none;
		}
	}
	@media (max-width: 760px) {
		.empty {
			padding: var(--space-lg) var(--space-md);
		}
		.col-secondary {
			grid-template-columns: minmax(0, 1fr);
		}
		.col-secondary > .rise:first-child :global(section) {
			border-right: none;
			border-bottom: 1px solid var(--rule-hairline);
		}
	}
</style>
