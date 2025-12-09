<script lang="ts">
	import type { RecipeCreate, RecipeUpdateData } from '$lib/api';

	interface Props {
		recipe?: RecipeUpdateData;
		onSubmit: (data: RecipeCreate | RecipeUpdateData) => Promise<void>;
		onCancel: () => void;
		submitting?: boolean;
	}

	let { recipe, onSubmit, onCancel, submitting = false }: Props = $props();

	// Form state
	let name = $state(recipe?.name ?? '');
	let author = $state(recipe?.author ?? '');
	let type = $state(recipe?.type ?? '');
	let batch_size_liters = $state(recipe?.batch_size_liters ?? 19);
	let og = $state(recipe?.og ?? 1.050);
	let fg = $state(recipe?.fg ?? 1.010);
	let abv = $state(recipe?.abv ?? 5.0);
	let ibu = $state(recipe?.ibu ?? 30);
	let color_srm = $state(recipe?.color_srm ?? 10);
	let notes = $state(recipe?.notes ?? '');

	// Form error state
	let formError = $state<string | null>(null);

	async function handleSubmit(e: Event) {
		e.preventDefault();
		formError = null;

		// Validate batch size
		if (batch_size_liters <= 0) {
			formError = 'Batch size must be greater than zero';
			return;
		}

		// Validate ABV range
		if (abv < 0 || abv > 20) {
			formError = 'ABV must be between 0% and 20%';
			return;
		}

		// Validate color (if provided)
		if (color_srm !== null && color_srm < 0) {
			formError = 'Color (SRM) cannot be negative';
			return;
		}

		// Validate OG > FG
		if (og <= fg) {
			formError = 'Original gravity must be greater than final gravity';
			return;
		}

		const data: RecipeCreate | RecipeUpdateData = {
			name,
			author: author || undefined,
			type: type || undefined,
			batch_size_liters,
			og,
			fg,
			abv,
			ibu: ibu ?? undefined,
			color_srm: color_srm ?? undefined,
			notes: notes || undefined
		};

		await onSubmit(data);
	}
</script>

<form onsubmit={handleSubmit} class="recipe-form">
	{#if formError}
		<div class="error-banner">
			<svg class="error-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
			</svg>
			<span>{formError}</span>
		</div>
	{/if}

	<div class="form-section">
		<h2 class="section-title">Basic Information</h2>

		<div class="form-row">
			<label class="form-label">
				Recipe Name *
				<input
					type="text"
					bind:value={name}
					required
					class="form-input"
					placeholder="e.g., Philter XPA Clone"
				/>
			</label>
		</div>

		<div class="form-row">
			<label class="form-label">
				Brewer
				<input
					type="text"
					bind:value={author}
					class="form-input"
					placeholder="Your name"
				/>
			</label>

			<label class="form-label">
				Style
				<input
					type="text"
					bind:value={type}
					class="form-input"
					placeholder="e.g., American Pale Ale"
				/>
			</label>
		</div>
	</div>

	<div class="form-section">
		<h2 class="section-title">Batch Details</h2>

		<div class="form-row">
			<label class="form-label">
				Batch Size (L) *
				<input
					type="number"
					bind:value={batch_size_liters}
					required
					step="0.1"
					min="0"
					class="form-input"
				/>
			</label>

			<label class="form-label">
				Color (SRM)
				<input
					type="number"
					bind:value={color_srm}
					step="0.1"
					min="0"
					class="form-input"
				/>
			</label>

			<label class="form-label">
				Bitterness (IBU)
				<input
					type="number"
					bind:value={ibu}
					step="0.1"
					min="0"
					class="form-input"
				/>
			</label>
		</div>
	</div>

	<div class="form-section">
		<h2 class="section-title">Fermentation Targets</h2>

		<div class="form-row">
			<label class="form-label">
				Original Gravity *
				<input
					type="number"
					bind:value={og}
					required
					step="0.001"
					min="1.000"
					max="1.200"
					class="form-input"
				/>
			</label>

			<label class="form-label">
				Final Gravity *
				<input
					type="number"
					bind:value={fg}
					required
					step="0.001"
					min="1.000"
					max="1.200"
					class="form-input"
				/>
			</label>

			<label class="form-label">
				ABV (%) *
				<input
					type="number"
					bind:value={abv}
					required
					step="0.1"
					min="0"
					max="20"
					class="form-input"
				/>
			</label>
		</div>
	</div>

	<div class="form-section">
		<h2 class="section-title">Notes</h2>

		<label class="form-label">
			Brewing Notes
			<textarea
				bind:value={notes}
				rows="4"
				class="form-textarea"
				placeholder="Optional brewing notes, tips, or variations..."
			></textarea>
		</label>
	</div>

	<div class="form-actions">
		<button
			type="button"
			onclick={onCancel}
			class="btn-secondary"
			disabled={submitting}
		>
			Cancel
		</button>
		<button
			type="submit"
			class="btn-primary"
			disabled={submitting}
		>
			{submitting ? 'Saving...' : recipe ? 'Update Recipe' : 'Create Recipe'}
		</button>
	</div>
</form>

<style>
	.recipe-form {
		display: flex;
		flex-direction: column;
		gap: var(--space-8);
		max-width: 800px;
	}

	.form-section {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}

	.section-title {
		font-size: 16px;
		font-weight: 600;
		color: var(--recipe-accent);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin: 0;
	}

	.form-row {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
		gap: var(--space-4);
	}

	.form-label {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		font-size: 13px;
		font-weight: 500;
		color: var(--text-secondary);
	}

	.form-input,
	.form-textarea {
		width: 100%;
		padding: var(--space-3);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 6px;
		color: var(--text-primary);
		font-size: 14px;
		font-family: var(--font-sans);
		transition: border-color var(--transition);
	}

	.form-input:focus,
	.form-textarea:focus {
		outline: none;
		border-color: var(--recipe-accent);
	}

	.form-textarea {
		resize: vertical;
		min-height: 80px;
	}

	.form-actions {
		display: flex;
		gap: var(--space-3);
		justify-content: flex-end;
		padding-top: var(--space-4);
		border-top: 1px solid var(--border-subtle);
	}

	.btn-secondary,
	.btn-primary {
		padding: var(--space-3) var(--space-6);
		border-radius: 6px;
		font-size: 14px;
		font-weight: 500;
		cursor: pointer;
		transition: all var(--transition);
		border: none;
	}

	.btn-secondary {
		background: transparent;
		border: 1px solid var(--border-default);
		color: var(--text-primary);
	}

	.btn-secondary:hover:not(:disabled) {
		background: var(--bg-hover);
	}

	.btn-primary {
		background: var(--recipe-accent);
		color: white;
	}

	.btn-primary:hover:not(:disabled) {
		background: var(--recipe-accent-hover);
	}

	.btn-secondary:disabled,
	.btn-primary:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.error-banner {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		padding: var(--space-4);
		background: var(--error-bg);
		border: 1px solid var(--negative);
		border-radius: 6px;
		color: var(--negative);
		font-size: 14px;
	}

	.error-icon {
		width: 20px;
		height: 20px;
		flex-shrink: 0;
	}
</style>
