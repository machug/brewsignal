<script lang="ts">
	import { scaleRecipe } from '$lib/api';

	interface Props {
		open: boolean;
		recipeId: number;
		currentBatchLiters: number;
		/** Pre-filled target (e.g. from "Scale to fit"). */
		initialTarget?: number | null;
		onClose: () => void;
		onScaled: () => void;
	}

	let { open, recipeId, currentBatchLiters, initialTarget, onClose, onScaled }: Props = $props();

	// Typical batch sizes for popular vessels — presets set the target batch,
	// not the vessel volume (a G30 brews ~23 L batches, not 30 L).
	const PRESETS: Array<{ label: string; liters: number }> = [
		{ label: 'Grainfather G30', liters: 23 },
		{ label: 'Grainfather G40', liters: 30 },
		{ label: 'Grainfather G70', liters: 52 },
		{ label: 'BrewZilla 35', liters: 23 },
		{ label: 'BrewZilla 65', liters: 45 },
		{ label: 'Braumeister 20', liters: 20 },
		{ label: 'Braumeister 50', liters: 50 },
		{ label: 'Corny keg (5 gal)', liters: 19 },
	];

	let targetLiters = $state(0);
	let scaling = $state(false);
	let error = $state<string | null>(null);

	$effect(() => {
		if (open) {
			targetLiters = initialTarget ?? currentBatchLiters;
			error = null;
		}
	});

	let ratio = $derived(currentBatchLiters > 0 && targetLiters > 0 ? targetLiters / currentBatchLiters : 0);
	let bigJump = $derived(ratio >= 2 || (ratio > 0 && ratio <= 0.5));

	async function handleScale() {
		if (!(targetLiters > 0)) {
			error = 'Enter a target batch size above 0 L';
			return;
		}
		scaling = true;
		error = null;
		try {
			await scaleRecipe(recipeId, targetLiters);
			onScaled();
			onClose();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to scale recipe';
		} finally {
			scaling = false;
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') onClose();
	}
</script>

{#if open}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="modal-overlay"
		onclick={(e) => {
			if (e.target === e.currentTarget) onClose();
		}}
		onkeydown={handleKeydown}
		role="presentation"
	>
		<div
			class="modal-content"
			role="dialog"
			aria-modal="true"
			aria-labelledby="scale-dialog-title"
			tabindex="-1"
			onkeydown={(e) => e.stopPropagation()}
		>
			<div class="modal-header">
				<h2 id="scale-dialog-title">Scale Recipe</h2>
				<button class="modal-close" onclick={onClose} aria-label="Close">&times;</button>
			</div>
			<div class="modal-body">
				<p class="current-size">
					Current batch: <strong>{currentBatchLiters} L</strong>
				</p>

				<div class="preset-grid">
					{#each PRESETS as preset (preset.label)}
						<button
							type="button"
							class="preset-chip"
							class:selected={targetLiters === preset.liters}
							onclick={() => (targetLiters = preset.liters)}
						>
							<span class="preset-name">{preset.label}</span>
							<span class="preset-liters">{preset.liters} L</span>
						</button>
					{/each}
				</div>

				<label class="target-row">
					<span>Target batch size</span>
					<span class="target-input-wrap">
						<input type="number" min="0.5" step="0.5" bind:value={targetLiters} />
						<span class="unit">L</span>
					</span>
				</label>

				{#if ratio > 0 && Math.abs(ratio - 1) > 0.001}
					<p class="ratio-note">
						All ingredient amounts and water volumes will be multiplied by
						<strong>×{ratio.toFixed(2)}</strong>. Stats (OG, IBU, colour) are recomputed and should
						stay the same.
					</p>
					{#if bigJump}
						<p class="jump-warning">
							Large jump — hop character and boil-off behave a little differently at this scale, so
							taste-check the numbers before brew day.
						</p>
					{/if}
				{/if}

				{#if error}
					<p class="error-note">{error}</p>
				{/if}
			</div>
			<div class="modal-footer">
				<button type="button" class="btn-cancel" onclick={onClose} disabled={scaling}>Cancel</button>
				<button
					type="button"
					class="btn-scale"
					onclick={handleScale}
					disabled={scaling || !(targetLiters > 0) || Math.abs(ratio - 1) <= 0.001}
				>
					{scaling ? 'Scaling…' : `Scale to ${targetLiters || '—'} L`}
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.modal-overlay {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.7);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
		padding: var(--space-4);
	}

	.modal-content {
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 12px;
		max-width: 480px;
		width: 100%;
		max-height: 85vh;
		overflow-y: auto;
		display: flex;
		flex-direction: column;
		box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
	}

	.modal-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: var(--space-4) var(--space-5);
		border-bottom: 1px solid var(--border-subtle);
	}

	.modal-header h2 {
		margin: 0;
		font-size: 18px;
		font-weight: 600;
		color: var(--text-primary);
	}

	.modal-close {
		background: none;
		border: none;
		font-size: 24px;
		line-height: 1;
		color: var(--text-muted);
		cursor: pointer;
		padding: 0 var(--space-1);
	}

	.modal-close:hover {
		color: var(--text-primary);
	}

	.modal-body {
		padding: var(--space-4) var(--space-5);
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}

	.current-size {
		margin: 0;
		color: var(--text-secondary);
		font-size: 0.9rem;
	}

	.preset-grid {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: var(--space-2);
	}

	.preset-chip {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: var(--space-2);
		padding: var(--space-2) var(--space-3);
		background: var(--bg-elevated, transparent);
		border: 1px solid var(--border-subtle);
		border-radius: 8px;
		color: var(--text-secondary);
		font-size: 0.85rem;
		cursor: pointer;
		text-align: left;
	}

	.preset-chip:hover {
		border-color: var(--border-default);
		color: var(--text-primary);
	}

	.preset-chip.selected {
		border-color: var(--recipe-accent, #f59e0b);
		color: var(--text-primary);
	}

	.preset-liters {
		font-variant-numeric: tabular-nums;
		color: var(--text-muted);
		flex-shrink: 0;
	}

	.target-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-3);
		color: var(--text-primary);
		font-size: 0.9rem;
	}

	.target-input-wrap {
		display: flex;
		align-items: center;
		gap: var(--space-2);
	}

	.target-input-wrap input {
		width: 90px;
		padding: var(--space-2) var(--space-3);
		background: var(--bg-elevated, transparent);
		border: 1px solid var(--border-default);
		border-radius: 8px;
		color: var(--text-primary);
		font-variant-numeric: tabular-nums;
	}

	.unit {
		color: var(--text-muted);
	}

	.ratio-note {
		margin: 0;
		font-size: 0.85rem;
		color: var(--text-secondary);
	}

	.jump-warning {
		margin: 0;
		font-size: 0.85rem;
		color: var(--warning);
	}

	.error-note {
		margin: 0;
		font-size: 0.85rem;
		color: var(--negative);
	}

	.modal-footer {
		display: flex;
		justify-content: flex-end;
		gap: var(--space-3);
		padding: var(--space-4) var(--space-5);
		border-top: 1px solid var(--border-subtle);
	}

	.btn-cancel {
		padding: var(--space-2) var(--space-4);
		background: none;
		border: 1px solid var(--border-default);
		border-radius: 8px;
		color: var(--text-secondary);
		cursor: pointer;
	}

	.btn-scale {
		padding: var(--space-2) var(--space-4);
		background: var(--recipe-accent, #f59e0b);
		border: none;
		border-radius: 8px;
		color: #1a1208;
		font-weight: 600;
		cursor: pointer;
	}

	.btn-scale:disabled,
	.btn-cancel:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
</style>
