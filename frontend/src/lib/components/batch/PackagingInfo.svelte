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
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.75rem;
		overflow: hidden;
	}

	.card-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		width: 100%;
		padding: 1rem 1.25rem;
		background: transparent;
		border: none;
		cursor: pointer;
		text-align: left;
		transition: background 0.15s ease;
	}

	.card-header:hover {
		background: var(--bg-elevated);
	}

	.header-content {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}

	.header-right {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}

	.card-title {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin: 0;
	}

	.packaged-badge {
		font-size: 0.6875rem;
		font-weight: 500;
		padding: 0.25rem 0.5rem;
		background: var(--positive-bg);
		color: var(--positive);
		border-radius: 0.25rem;
	}

	.save-indicator {
		font-size: 0.6875rem;
		color: var(--positive);
	}

	.chevron {
		width: 1rem;
		height: 1rem;
		color: var(--text-muted);
		transition: transform 0.2s ease;
	}

	.chevron.expanded {
		transform: rotate(180deg);
	}

	.card-content {
		padding: 1rem 1.25rem;
		border-top: 1px solid var(--border-subtle);
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.field-row {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 1rem;
	}

	.priming-row {
		padding: 0.75rem;
		background: var(--bg-elevated);
		border-radius: 0.5rem;
		margin-top: -0.25rem;
	}

	.field {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
	}

	.field.full-width {
		grid-column: 1 / -1;
	}

	.field-label {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-muted);
	}

	.field-input {
		width: 100%;
		padding: 0.5rem 0.75rem;
		background: var(--bg-base);
		border: 1px solid var(--border-subtle);
		border-radius: 0.375rem;
		font-size: 0.875rem;
		color: var(--text-primary);
		transition: border-color 0.15s ease;
	}

	.field-input:focus {
		outline: none;
		border-color: var(--primary);
	}

	.input-with-unit {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.input-with-unit .field-input {
		flex: 1;
	}

	.unit {
		font-size: 0.75rem;
		color: var(--text-muted);
		font-family: var(--font-mono);
	}

	.notes-input {
		width: 100%;
		padding: 0.75rem;
		background: var(--bg-base);
		border: 1px solid var(--border-subtle);
		border-radius: 0.375rem;
		font-size: 0.875rem;
		color: var(--text-primary);
		resize: vertical;
		font-family: inherit;
	}

	.notes-input:focus {
		outline: none;
		border-color: var(--primary);
	}

	.saving-indicator {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		padding: 0.5rem;
		font-size: 0.75rem;
		color: var(--text-muted);
		background: var(--bg-elevated);
		border-top: 1px solid var(--border-subtle);
	}

	.spinner {
		width: 0.875rem;
		height: 0.875rem;
		border: 2px solid var(--border-subtle);
		border-top-color: var(--primary);
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
