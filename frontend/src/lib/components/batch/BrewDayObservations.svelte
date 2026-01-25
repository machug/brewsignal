<script lang="ts">
	import type { BatchResponse, BatchUpdate, RecipeResponse } from '$lib/api';
	import { updateBatch } from '$lib/api';
	import { formatTemp, getTempUnit, formatGravity, getGravityUnit } from '$lib/stores/config.svelte';

	interface Props {
		batch: BatchResponse;
		recipe: RecipeResponse;
		onUpdate?: (batch: BatchResponse) => void;
	}

	let { batch, recipe, onUpdate }: Props = $props();

	// Form state - initialize from batch
	let actualMashTemp = $state(batch.actual_mash_temp ?? null);
	let actualMashPh = $state(batch.actual_mash_ph ?? null);
	let strikeWaterVolume = $state(batch.strike_water_volume ?? null);
	let preBoilGravity = $state(batch.pre_boil_gravity ?? null);
	let preBoilVolume = $state(batch.pre_boil_volume ?? null);
	let postBoilVolume = $state(batch.post_boil_volume ?? null);
	let measuredOg = $state(batch.measured_og ?? null);
	let actualEfficiency = $state(batch.actual_efficiency ?? null);
	let brewDayNotes = $state(batch.brew_day_notes ?? '');

	let saving = $state(false);
	let lastSaved = $state<Date | null>(null);
	let expandedSection = $state<string | null>('mash');

	// Derived values from recipe
	let tempUnit = $derived(getTempUnit());
	let gravityUnit = $derived(getGravityUnit());

	// Recipe targets for comparison
	let targetMashTemp = $derived(recipe.mash_temp);
	let targetOg = $derived(recipe.og);
	let targetPreBoilGravity = $derived(recipe.pre_boil_og);
	let targetBatchSize = $derived(recipe.batch_size_liters);
	let targetEfficiency = $derived(recipe.efficiency_percent);

	// Calculate efficiency from actual vs expected
	function calculateEfficiency(): number | null {
		if (!measuredOg || !targetOg || !targetEfficiency) return null;
		// Efficiency = (actual_points / expected_points) * target_efficiency
		const actualPoints = (measuredOg - 1) * 1000;
		const expectedPoints = (targetOg - 1) * 1000;
		if (expectedPoints === 0) return null;
		return (actualPoints / expectedPoints) * targetEfficiency;
	}

	// Auto-calculate efficiency when OG changes
	$effect(() => {
		if (measuredOg && !actualEfficiency) {
			const calc = calculateEfficiency();
			if (calc) actualEfficiency = Math.round(calc * 10) / 10;
		}
	});

	async function saveObservations() {
		if (saving) return;
		saving = true;

		try {
			const update: BatchUpdate = {
				actual_mash_temp: actualMashTemp ?? undefined,
				actual_mash_ph: actualMashPh ?? undefined,
				strike_water_volume: strikeWaterVolume ?? undefined,
				pre_boil_gravity: preBoilGravity ?? undefined,
				pre_boil_volume: preBoilVolume ?? undefined,
				post_boil_volume: postBoilVolume ?? undefined,
				measured_og: measuredOg ?? undefined,
				actual_efficiency: actualEfficiency ?? undefined,
				brew_day_notes: brewDayNotes || undefined,
			};

			const updated = await updateBatch(batch.id, update);
			lastSaved = new Date();
			onUpdate?.(updated);
		} catch (e) {
			console.error('Failed to save observations:', e);
		} finally {
			saving = false;
		}
	}

	function toggleSection(section: string) {
		expandedSection = expandedSection === section ? null : section;
	}

	// Format helpers
	function formatDiff(actual: number | null, target: number | undefined, unit: string, invert = false): string {
		if (actual === null || target === undefined) return '';
		const diff = actual - target;
		const sign = diff > 0 ? '+' : '';
		const color = invert ? (diff < 0 ? 'positive' : diff > 0 ? 'negative' : 'neutral') : (diff > 0 ? 'positive' : diff < 0 ? 'negative' : 'neutral');
		return `<span class="diff ${color}">${sign}${diff.toFixed(1)}${unit}</span>`;
	}
</script>

<div class="observations-card">
	<div class="card-header">
		<h3 class="card-title">Brew Day Log</h3>
		{#if lastSaved}
			<span class="save-indicator">Saved {lastSaved.toLocaleTimeString()}</span>
		{/if}
	</div>

	<!-- Mash Section -->
	<div class="section" class:expanded={expandedSection === 'mash'}>
		<button type="button" class="section-header" onclick={() => toggleSection('mash')}>
			<span class="section-title">Mash</span>
			<div class="section-summary">
				{#if actualMashTemp}
					<span class="summary-value">{formatTemp(actualMashTemp)}{tempUnit}</span>
				{/if}
				{#if actualMashPh}
					<span class="summary-value">pH {actualMashPh.toFixed(2)}</span>
				{/if}
			</div>
			<svg class="chevron" fill="none" viewBox="0 0 24 24" stroke="currentColor">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
			</svg>
		</button>

		{#if expandedSection === 'mash'}
			<div class="section-content">
				<div class="field-row">
					<div class="field">
						<label class="field-label">Mash Temperature</label>
						<div class="input-with-target">
							<input
								type="number"
								step="0.1"
								class="field-input"
								placeholder="--"
								bind:value={actualMashTemp}
								onblur={saveObservations}
							/>
							<span class="unit">{tempUnit}</span>
						</div>
						{#if targetMashTemp}
							<span class="target">Target: {formatTemp(targetMashTemp)}{tempUnit}</span>
						{/if}
					</div>

					<div class="field">
						<label class="field-label">Mash pH</label>
						<div class="input-with-target">
							<input
								type="number"
								step="0.01"
								min="4"
								max="7"
								class="field-input"
								placeholder="--"
								bind:value={actualMashPh}
								onblur={saveObservations}
							/>
						</div>
						<span class="target">Target: 5.2-5.6</span>
					</div>
				</div>

				<div class="field-row">
					<div class="field">
						<label class="field-label">Strike Water Volume</label>
						<div class="input-with-target">
							<input
								type="number"
								step="0.1"
								class="field-input"
								placeholder="--"
								bind:value={strikeWaterVolume}
								onblur={saveObservations}
							/>
							<span class="unit">L</span>
						</div>
					</div>
				</div>
			</div>
		{/if}
	</div>

	<!-- Pre-Boil Section -->
	<div class="section" class:expanded={expandedSection === 'preboil'}>
		<button type="button" class="section-header" onclick={() => toggleSection('preboil')}>
			<span class="section-title">Pre-Boil</span>
			<div class="section-summary">
				{#if preBoilGravity}
					<span class="summary-value">{formatGravity(preBoilGravity)}</span>
				{/if}
				{#if preBoilVolume}
					<span class="summary-value">{preBoilVolume.toFixed(1)}L</span>
				{/if}
			</div>
			<svg class="chevron" fill="none" viewBox="0 0 24 24" stroke="currentColor">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
			</svg>
		</button>

		{#if expandedSection === 'preboil'}
			<div class="section-content">
				<div class="field-row">
					<div class="field">
						<label class="field-label">Pre-Boil Gravity</label>
						<div class="input-with-target">
							<input
								type="number"
								step="0.001"
								min="1.000"
								max="1.200"
								class="field-input"
								placeholder="1.0XX"
								bind:value={preBoilGravity}
								onblur={saveObservations}
							/>
						</div>
						{#if targetPreBoilGravity}
							<span class="target">Target: {formatGravity(targetPreBoilGravity)}</span>
						{/if}
					</div>

					<div class="field">
						<label class="field-label">Pre-Boil Volume</label>
						<div class="input-with-target">
							<input
								type="number"
								step="0.1"
								class="field-input"
								placeholder="--"
								bind:value={preBoilVolume}
								onblur={saveObservations}
							/>
							<span class="unit">L</span>
						</div>
					</div>
				</div>
			</div>
		{/if}
	</div>

	<!-- Post-Boil / OG Section -->
	<div class="section" class:expanded={expandedSection === 'postboil'}>
		<button type="button" class="section-header" onclick={() => toggleSection('postboil')}>
			<span class="section-title">Post-Boil / OG</span>
			<div class="section-summary">
				{#if measuredOg}
					<span class="summary-value og">{formatGravity(measuredOg)}</span>
				{/if}
				{#if actualEfficiency}
					<span class="summary-value">{actualEfficiency.toFixed(0)}% eff</span>
				{/if}
			</div>
			<svg class="chevron" fill="none" viewBox="0 0 24 24" stroke="currentColor">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
			</svg>
		</button>

		{#if expandedSection === 'postboil'}
			<div class="section-content">
				<div class="field-row">
					<div class="field">
						<label class="field-label">Original Gravity (OG)</label>
						<div class="input-with-target">
							<input
								type="number"
								step="0.001"
								min="1.000"
								max="1.200"
								class="field-input og-input"
								placeholder="1.0XX"
								bind:value={measuredOg}
								onblur={saveObservations}
							/>
						</div>
						{#if targetOg}
							<span class="target">Target: {formatGravity(targetOg)}</span>
						{/if}
					</div>

					<div class="field">
						<label class="field-label">Post-Boil Volume</label>
						<div class="input-with-target">
							<input
								type="number"
								step="0.1"
								class="field-input"
								placeholder="--"
								bind:value={postBoilVolume}
								onblur={saveObservations}
							/>
							<span class="unit">L</span>
						</div>
						{#if targetBatchSize}
							<span class="target">Target: {targetBatchSize.toFixed(1)}L</span>
						{/if}
					</div>
				</div>

				<div class="field-row">
					<div class="field">
						<label class="field-label">Brewhouse Efficiency</label>
						<div class="input-with-target">
							<input
								type="number"
								step="0.1"
								min="0"
								max="100"
								class="field-input"
								placeholder="--"
								bind:value={actualEfficiency}
								onblur={saveObservations}
							/>
							<span class="unit">%</span>
						</div>
						{#if targetEfficiency}
							<span class="target">Target: {targetEfficiency.toFixed(0)}%</span>
						{/if}
					</div>
				</div>
			</div>
		{/if}
	</div>

	<!-- Notes Section -->
	<div class="section" class:expanded={expandedSection === 'notes'}>
		<button type="button" class="section-header" onclick={() => toggleSection('notes')}>
			<span class="section-title">Brew Day Notes</span>
			{#if brewDayNotes}
				<span class="has-notes">Has notes</span>
			{/if}
			<svg class="chevron" fill="none" viewBox="0 0 24 24" stroke="currentColor">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
			</svg>
		</button>

		{#if expandedSection === 'notes'}
			<div class="section-content">
				<textarea
					class="notes-input"
					placeholder="Record any deviations, substitutions, or observations..."
					rows="4"
					bind:value={brewDayNotes}
					onblur={saveObservations}
				></textarea>
			</div>
		{/if}
	</div>

	{#if saving}
		<div class="saving-indicator">
			<span class="spinner"></span>
			Saving...
		</div>
	{/if}
</div>

<style>
	.observations-card {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.75rem;
		overflow: hidden;
	}

	.card-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 1rem 1.25rem;
		border-bottom: 1px solid var(--border-subtle);
	}

	.card-title {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin: 0;
	}

	.save-indicator {
		font-size: 0.6875rem;
		color: var(--positive);
	}

	/* Sections */
	.section {
		border-bottom: 1px solid var(--border-subtle);
	}

	.section:last-of-type {
		border-bottom: none;
	}

	.section-header {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		width: 100%;
		padding: 0.875rem 1.25rem;
		background: transparent;
		border: none;
		cursor: pointer;
		text-align: left;
		transition: background 0.15s ease;
	}

	.section-header:hover {
		background: var(--bg-elevated);
	}

	.section-title {
		font-size: 0.875rem;
		font-weight: 500;
		color: var(--text-primary);
	}

	.section-summary {
		display: flex;
		gap: 0.75rem;
		margin-left: auto;
	}

	.summary-value {
		font-size: 0.8125rem;
		font-weight: 500;
		font-family: var(--font-mono);
		color: var(--text-secondary);
	}

	.summary-value.og {
		color: var(--accent);
	}

	.has-notes {
		font-size: 0.6875rem;
		color: var(--text-muted);
		margin-left: auto;
	}

	.chevron {
		width: 1rem;
		height: 1rem;
		color: var(--text-muted);
		transition: transform 0.2s ease;
	}

	.section.expanded .chevron {
		transform: rotate(180deg);
	}

	.section-content {
		padding: 0 1.25rem 1.25rem;
	}

	/* Fields */
	.field-row {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 1rem;
		margin-bottom: 0.75rem;
	}

	.field-row:last-child {
		margin-bottom: 0;
	}

	@media (max-width: 500px) {
		.field-row {
			grid-template-columns: 1fr;
		}
	}

	.field {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
	}

	.field-label {
		font-size: 0.6875rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.input-with-target {
		display: flex;
		align-items: center;
		gap: 0.375rem;
	}

	.field-input {
		flex: 1;
		padding: 0.5rem 0.75rem;
		font-size: 0.9375rem;
		font-family: var(--font-mono);
		background: var(--bg-elevated);
		border: 1px solid var(--border-default);
		border-radius: 0.375rem;
		color: var(--text-primary);
		transition: border-color 0.15s ease;
	}

	.field-input:focus {
		outline: none;
		border-color: var(--accent);
	}

	.field-input.og-input {
		font-size: 1rem;
		font-weight: 600;
	}

	.unit {
		font-size: 0.8125rem;
		color: var(--text-muted);
		min-width: 1.5rem;
	}

	.target {
		font-size: 0.6875rem;
		color: var(--text-muted);
	}

	/* Notes */
	.notes-input {
		width: 100%;
		padding: 0.75rem;
		font-size: 0.875rem;
		font-family: inherit;
		background: var(--bg-elevated);
		border: 1px solid var(--border-default);
		border-radius: 0.375rem;
		color: var(--text-primary);
		resize: vertical;
		min-height: 80px;
	}

	.notes-input:focus {
		outline: none;
		border-color: var(--accent);
	}

	.notes-input::placeholder {
		color: var(--text-muted);
	}

	/* Saving indicator */
	.saving-indicator {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		padding: 0.5rem;
		font-size: 0.75rem;
		color: var(--text-muted);
		background: var(--bg-elevated);
	}

	.spinner {
		width: 0.875rem;
		height: 0.875rem;
		border: 2px solid var(--border-default);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	/* Diff styling */
	:global(.diff) {
		font-size: 0.6875rem;
		font-weight: 500;
		margin-left: 0.25rem;
	}

	:global(.diff.positive) {
		color: var(--positive);
	}

	:global(.diff.negative) {
		color: var(--negative);
	}

	:global(.diff.neutral) {
		color: var(--text-muted);
	}
</style>
