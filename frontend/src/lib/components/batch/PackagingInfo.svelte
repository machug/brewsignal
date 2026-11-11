<script lang="ts">
	import type { BatchResponse, BatchUpdate } from '$lib/api';
	import { updateBatch } from '$lib/api';

	interface Props {
		batch: BatchResponse;
		onUpdate?: (batch: BatchResponse) => void;
	}

	let { batch, onUpdate }: Props = $props();

	// Form state - initialize from batch
	let packagedAt = $state(batch.packaged_at ? batch.packaged_at.split('T')[0] : '');
	let packagingType = $state(batch.packaging_type ?? '');
	let packagingVolume = $state(batch.packaging_volume ?? null);
	let carbonationMethod = $state(batch.carbonation_method ?? '');
	let primingSugarType = $state(batch.priming_sugar_type ?? '');
	let primingSugarAmount = $state(batch.priming_sugar_amount ?? null);
	let packagingNotes = $state(batch.packaging_notes ?? '');

	let saving = $state(false);
	let lastSaved = $state<Date | null>(null);
	let expanded = $state(!batch.packaged_at); // Start expanded if not yet packaged

	// Show priming sugar fields only for bottle/keg conditioning
	let showPrimingSugar = $derived(
		carbonationMethod === 'bottle_conditioned' || carbonationMethod === 'keg_conditioned'
	);

	async function savePackaging() {
		if (saving) return;
		saving = true;

		try {
			const update: BatchUpdate = {
				packaged_at: packagedAt ? new Date(packagedAt).toISOString() : undefined,
				packaging_type: packagingType || undefined,
				packaging_volume: packagingVolume ?? undefined,
				carbonation_method: carbonationMethod || undefined,
				priming_sugar_type: showPrimingSugar ? (primingSugarType || undefined) : undefined,
				priming_sugar_amount: showPrimingSugar ? (primingSugarAmount ?? undefined) : undefined,
				packaging_notes: packagingNotes || undefined,
			};

			const updated = await updateBatch(batch.id, update);
			lastSaved = new Date();
			onUpdate?.(updated);
		} catch (e) {
			console.error('Failed to save packaging info:', e);
		} finally {
			saving = false;
		}
	}

	function toggleExpanded() {
		expanded = !expanded;
	}

	// Packaging type options
	const packagingTypes = [
		{ value: 'keg', label: 'Keg' },
		{ value: 'bottles', label: 'Bottles' },
		{ value: 'cans', label: 'Cans' },
	];

	// Carbonation method options
	const carbonationMethods = [
		{ value: 'forced', label: 'Force Carbonated' },
		{ value: 'bottle_conditioned', label: 'Bottle Conditioned' },
		{ value: 'keg_conditioned', label: 'Keg Conditioned' },
		{ value: 'natural', label: 'Naturally Carbonated' },
	];
</script>

<div class="packaging-card">
	<button type="button" class="card-header" onclick={toggleExpanded}>
		<div class="header-content">
			<h3 class="card-title">Packaging</h3>
			{#if batch.packaged_at}
				<span class="packaged-badge">Packaged</span>
			{/if}
		</div>
		<div class="header-right">
			{#if lastSaved}
				<span class="save-indicator">Saved</span>
			{/if}
			<svg class="chevron" class:expanded fill="none" viewBox="0 0 24 24" stroke="currentColor">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
			</svg>
		</div>
	</button>

	{#if expanded}
		<div class="card-content">
			<!-- Packaging Date & Type -->
			<div class="field-row">
				<div class="field">
					<label class="field-label">Packaged On</label>
					<input
						type="date"
						class="field-input"
						bind:value={packagedAt}
						onblur={savePackaging}
					/>
				</div>

				<div class="field">
					<label class="field-label">Package Type</label>
					<select
						class="field-input"
						bind:value={packagingType}
						onchange={savePackaging}
					>
						<option value="">Select...</option>
						{#each packagingTypes as type}
							<option value={type.value}>{type.label}</option>
						{/each}
					</select>
				</div>
			</div>

			<!-- Volume & Carbonation -->
			<div class="field-row">
				<div class="field">
					<label class="field-label">Volume Packaged</label>
					<div class="input-with-unit">
						<input
							type="number"
							step="0.1"
							class="field-input"
							placeholder="--"
							bind:value={packagingVolume}
							onblur={savePackaging}
						/>
						<span class="unit">L</span>
					</div>
				</div>

				<div class="field">
					<label class="field-label">Carbonation Method</label>
					<select
						class="field-input"
						bind:value={carbonationMethod}
						onchange={savePackaging}
					>
						<option value="">Select...</option>
						{#each carbonationMethods as method}
							<option value={method.value}>{method.label}</option>
						{/each}
					</select>
				</div>
			</div>

			<!-- Priming Sugar (conditional) -->
			{#if showPrimingSugar}
				<div class="field-row priming-row">
					<div class="field">
						<label class="field-label">Priming Sugar Type</label>
						<input
							type="text"
							class="field-input"
							placeholder="e.g., table sugar, corn sugar"
							bind:value={primingSugarType}
							onblur={savePackaging}
						/>
					</div>

					<div class="field">
						<label class="field-label">Amount</label>
						<div class="input-with-unit">
							<input
								type="number"
								step="1"
								class="field-input"
								placeholder="--"
								bind:value={primingSugarAmount}
								onblur={savePackaging}
							/>
							<span class="unit">g</span>
						</div>
					</div>
				</div>
			{/if}

			<!-- Notes -->
			<div class="field full-width">
				<label class="field-label">Packaging Notes</label>
				<textarea
					class="notes-input"
					placeholder="Any observations about packaging day..."
					rows="3"
					bind:value={packagingNotes}
					onblur={savePackaging}
				></textarea>
			</div>
		</div>
	{/if}

	{#if saving}
		<div class="saving-indicator">
			<span class="spinner"></span>
			Saving...
		</div>
	{/if}
</div>

<style>
	.packaging-card {
		border-top: 1px solid var(--rule-strong);
		border-bottom: 1px solid var(--rule-hairline);
		overflow: hidden;
	}

	.card-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		width: 100%;
		min-height: 48px;
		padding: var(--space-sm) var(--space-md);
		background: transparent;
		border: none;
		cursor: pointer;
		text-align: left;
	}

	.card-header:hover {
		background: var(--bg-elevated);
	}

	.card-header:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: -2px;
	}

	.header-content,
	.header-right {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
	}

	.card-title {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-muted);
		text-transform: uppercase;
		letter-spacing: 0.08em;
		margin: 0;
	}

	.packaged-badge {
		font-family: var(--font-display);
		font-size: 0.6875rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		padding: 2px 7px;
		border: 1px solid var(--status-steady);
		color: var(--status-steady);
		border-radius: 2px;
	}

	.save-indicator {
		font-size: 0.6875rem;
		color: var(--positive);
	}

	.chevron {
		width: 1rem;
		height: 1rem;
		color: var(--ink-muted);
		transition: transform 0.2s var(--ease-out-quart);
	}

	.chevron.expanded {
		transform: rotate(180deg);
	}

	.card-content {
		padding: var(--space-md);
		border-top: 1px solid var(--rule-hairline);
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
	}

	.field-row {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: var(--space-md);
	}

	.priming-row {
		padding-top: var(--space-md);
		border-top: 1px solid var(--rule-hairline);
	}

	.field {
		display: flex;
		flex-direction: column;
		gap: var(--space-2xs);
	}

	.field.full-width {
		grid-column: 1 / -1;
	}

	.field-label {
		font-family: var(--font-display);
		font-size: 0.6875rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--ink-muted);
	}

	.field-input,
	.notes-input {
		width: 100%;
		min-height: 44px;
		padding: var(--space-xs) var(--space-sm);
		background: var(--bg-canvas);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: var(--text-sm);
		color: var(--ink-primary);
	}

	.notes-input {
		font-family: var(--font-body);
		resize: vertical;
	}

	.field-input:focus,
	.notes-input:focus {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
		border-color: var(--accent);
	}

	.input-with-unit {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
	}

	.input-with-unit .field-input {
		flex: 1;
	}

	.unit {
		font-size: var(--text-xs);
		color: var(--ink-muted);
		font-family: var(--font-num);
	}

	.saving-indicator {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: var(--space-xs);
		padding: var(--space-xs);
		font-size: var(--text-xs);
		color: var(--ink-muted);
		border-top: 1px solid var(--rule-hairline);
	}

	.spinner {
		width: 0.875rem;
		height: 0.875rem;
		border: 2px solid var(--rule-hairline);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.6s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	@media (max-width: 480px) {
		.field-row {
			grid-template-columns: 1fr;
		}
	}
</style>
