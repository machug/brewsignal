<script lang="ts">
	import { scaleRecipe, type RecipeResponse } from '$lib/api';

	interface BeforeFermentable {
		name: string;
		amount_kg?: number | null;
	}
	interface BeforeHop {
		name: string;
		amount_grams?: number | null;
		amount_ml?: number | null;
	}

	interface Props {
		open: boolean;
		recipeId: number;
		currentBatchLiters: number;
		/** Current amounts, used for the before→after preview table. */
		fermentables?: BeforeFermentable[];
		hops?: BeforeHop[];
		/** Pre-filled target (e.g. from "Scale to fit"). */
		initialTarget?: number | null;
		onClose: () => void;
		/** Awaited before onBigJumpScaled so the reviewer sees the refreshed recipe. */
		onScaled: () => void | Promise<void>;
		/** Called after a large-ratio scale (≥2× or ≤0.5×) so the page can hand
		 *  the result to the AI reviewer for an ingredient sanity check. */
		onBigJumpScaled?: () => void;
	}

	let {
		open,
		recipeId,
		currentBatchLiters,
		fermentables = [],
		hops = [],
		initialTarget,
		onClose,
		onScaled,
		onBigJumpScaled,
	}: Props = $props();

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

	let step = $state<'pick' | 'preview'>('pick');
	let targetLiters = $state(0);
	let preview = $state<RecipeResponse | null>(null);
	let busy = $state(false);
	let error = $state<string | null>(null);

	$effect(() => {
		if (open) {
			step = 'pick';
			preview = null;
			targetLiters = initialTarget ?? currentBatchLiters;
			error = null;
		}
	});

	let ratio = $derived(currentBatchLiters > 0 && targetLiters > 0 ? targetLiters / currentBatchLiters : 0);
	let bigJump = $derived(ratio >= 2 || (ratio > 0 && ratio <= 0.5));

	// Before→after rows for the preview table. Rows come from the dry-run
	// response (authoritative post-scale amounts); before values match by
	// name against the current recipe, falling back to index order.
	let previewRows = $derived.by(() => {
		if (!preview) return [];
		const rows: Array<{ label: string; before: string; after: string }> = [];
		const fmt = (n: number | null | undefined, unit: string) =>
			n == null ? '—' : `${Math.round(n * 100) / 100} ${unit}`;
		// "After" amounts follow the same format_extensions-first precedence as
		// the page display — legacy UI recipes can have empty relationship rows
		// while the (scaled) editor copy is the authoritative one.
		const ext = preview.format_extensions as
			| {
					fermentables?: Array<{ name?: string; amount_kg?: number | null }>;
					hops?: Array<{ name?: string; amount_grams?: number | null; amount_ml?: number | null }>;
			  }
			| undefined;
		const afterFerms = Array.isArray(ext?.fermentables)
			? ext!.fermentables!.map((f) => ({ name: String(f.name ?? ''), amount_kg: f.amount_kg }))
			: (preview.fermentables ?? []);
		const afterHops = Array.isArray(ext?.hops)
			? ext!.hops!.map((h) => ({
					name: String(h.name ?? ''),
					amount_grams: h.amount_grams,
					amount_ml: h.amount_ml,
				}))
			: (preview.hops ?? []);
		// Match by index first — collections are rebuilt in editor order, so
		// arrays are parallel; duplicate names (same hop at several timings)
		// would otherwise all show the first addition's amount.
		const beforeFerm = (name: string, i: number) =>
			fermentables[i]?.name === name
				? fermentables[i]
				: (fermentables.find((f) => f.name === name) ?? fermentables[i]);
		for (const [i, f] of afterFerms.entries()) {
			rows.push({
				label: f.name,
				before: fmt(beforeFerm(f.name, i)?.amount_kg, 'kg'),
				after: fmt(f.amount_kg, 'kg'),
			});
		}
		const beforeHop = (name: string, i: number) =>
			hops[i]?.name === name ? hops[i] : (hops.find((h) => h.name === name) ?? hops[i]);
		for (const [i, h] of afterHops.entries()) {
			const b = beforeHop(h.name, i);
			const liquid = h.amount_ml != null && h.amount_ml > 0;
			rows.push({
				label: h.name,
				before: liquid ? fmt(b?.amount_ml, 'ml') : fmt(b?.amount_grams, 'g'),
				after: liquid ? fmt(h.amount_ml, 'ml') : fmt(h.amount_grams, 'g'),
			});
		}
		return rows;
	});

	async function handlePreview() {
		if (!(targetLiters > 0)) {
			error = 'Enter a target batch size above 0 L';
			return;
		}
		busy = true;
		error = null;
		try {
			preview = await scaleRecipe(recipeId, targetLiters, { dryRun: true });
			step = 'preview';
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to preview scaling';
		} finally {
			busy = false;
		}
	}

	async function handleSave() {
		busy = true;
		error = null;
		try {
			const wasBigJump = bigJump;
			await scaleRecipe(recipeId, targetLiters);
			await onScaled();
			onClose();
			if (wasBigJump) onBigJumpScaled?.();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to scale recipe';
		} finally {
			busy = false;
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

			{#if step === 'pick'}
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
								Large jump — hop character and boil-off behave a little differently at this scale.
								{#if onBigJumpScaled}The AI reviewer will check the scaled ingredients after saving.{:else}Taste-check
									the numbers before brew day.{/if}
							</p>
						{/if}
					{/if}

					{#if error}
						<p class="error-note">{error}</p>
					{/if}
				</div>
				<div class="modal-footer">
					<button type="button" class="btn-cancel" onclick={onClose} disabled={busy}>Cancel</button>
					<button
						type="button"
						class="btn-scale"
						onclick={handlePreview}
						disabled={busy || !(targetLiters > 0) || Math.abs(ratio - 1) <= 0.001}
					>
						{busy ? 'Calculating…' : 'Preview scale'}
					</button>
				</div>
			{:else}
				<div class="modal-body">
					<p class="current-size">
						<strong>{currentBatchLiters} L → {targetLiters} L</strong> (×{ratio.toFixed(2)}) — nothing
						is saved until you confirm.
					</p>

					<table class="preview-table">
						<thead>
							<tr><th>Ingredient</th><th>Now</th><th>Scaled</th></tr>
						</thead>
						<tbody>
							{#each previewRows as row, i (row.label + i)}
								<tr>
									<td>{row.label}</td>
									<td class="num">{row.before}</td>
									<td class="num after">{row.after}</td>
								</tr>
							{/each}
						</tbody>
					</table>

					{#if preview?.boil_size_l != null}
						<p class="ratio-note">Pre-boil volume: {preview.boil_size_l} L</p>
					{/if}

					{#if bigJump}
						<p class="jump-warning">
							Large jump — hop character and boil-off behave a little differently at this scale.
							{#if onBigJumpScaled}The AI reviewer will check the scaled ingredients after saving.{/if}
						</p>
					{/if}

					{#if error}
						<p class="error-note">{error}</p>
					{/if}
				</div>
				<div class="modal-footer">
					<button type="button" class="btn-cancel" onclick={() => (step = 'pick')} disabled={busy}>
						Back
					</button>
					<button type="button" class="btn-cancel" onclick={onClose} disabled={busy}>Discard</button>
					<button type="button" class="btn-scale" onclick={handleSave} disabled={busy}>
						{busy ? 'Saving…' : 'Save changes'}
					</button>
				</div>
			{/if}
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

	.preview-table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.85rem;
	}

	.preview-table th {
		text-align: left;
		color: var(--text-muted);
		font-weight: 500;
		padding: var(--space-1) var(--space-2);
		border-bottom: 1px solid var(--border-subtle);
	}

	.preview-table td {
		padding: var(--space-1) var(--space-2);
		color: var(--text-secondary);
		border-bottom: 1px solid var(--border-subtle);
	}

	.preview-table .num {
		text-align: right;
		font-variant-numeric: tabular-nums;
		white-space: nowrap;
	}

	.preview-table .after {
		color: var(--text-primary);
		font-weight: 600;
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
