<script lang="ts">
	import type { BatchResponse } from '$lib/api';
	import { createTastingNote } from '$lib/api';
	import { BJCP_CATEGORIES, BJCP_MAX_TOTAL, getBJCPRating } from '$lib/types/tasting';

	interface Props {
		batch: BatchResponse;
		onSave: () => void;
		onCancel: () => void;
	}

	let { batch, onSave, onCancel }: Props = $props();

	// Subcategory scores keyed by field name (e.g. 'aroma_malt')
	let scores: Record<string, number> = $state({
		aroma_malt: 0,
		aroma_hops: 0,
		aroma_fermentation: 0,
		aroma_other: 0,
		appearance_color: 0,
		appearance_clarity: 0,
		appearance_head: 0,
		flavor_malt: 0,
		flavor_hops: 0,
		flavor_bitterness: 0,
		flavor_fermentation: 0,
		flavor_balance: 0,
		flavor_finish: 0,
		mouthfeel_body: 0,
		mouthfeel_carbonation: 0,
		mouthfeel_warmth: 0,
		overall_score: 0,
	});

	// Category notes keyed by category key
	let notes: Record<string, string> = $state({
		aroma: '',
		appearance: '',
		flavor: '',
		mouthfeel: '',
		overall: '',
	});

	// Context
	let servingTemp = $state<number | null>(null);
	let glassware = $state('');

	// Style conformance
	let toStyle = $state(true);
	let deviationNotes = $state('');

	// Save state
	let saving = $state(false);
	let error = $state('');

	const glasswareOptions = [
		{ value: 'pint', label: 'Pint' },
		{ value: 'tulip', label: 'Tulip' },
		{ value: 'snifter', label: 'Snifter' },
		{ value: 'weizen', label: 'Weizen' },
		{ value: 'stange', label: 'Stange' },
		{ value: 'goblet', label: 'Goblet' },
		{ value: 'teku', label: 'Teku' },
	];

	// Computed category subtotals
	let categorySubtotals = $derived(
		BJCP_CATEGORIES.map((cat) => {
			if (cat.subcategories.length === 0) {
				// Overall category — use overall_score directly
				return { key: cat.key, name: cat.name, subtotal: scores.overall_score, max: cat.maxScore };
			}
			const subtotal = cat.subcategories.reduce((sum, sub) => sum + (scores[sub.key] ?? 0), 0);
			return { key: cat.key, name: cat.name, subtotal, max: cat.maxScore };
		})
	);

	// Total score across all categories
	let totalScore = $derived(
		categorySubtotals.reduce((sum, cat) => sum + cat.subtotal, 0)
	);

	// BJCP rating string
	let rating = $derived(getBJCPRating(totalScore));

	// Rating color class
	let ratingClass = $derived(
		totalScore >= 45 ? 'outstanding' :
		totalScore >= 38 ? 'excellent' :
		totalScore >= 30 ? 'very-good' :
		totalScore >= 21 ? 'good' :
		totalScore >= 14 ? 'fair' :
		'problematic'
	);

	async function save() {
		saving = true;
		error = '';
		try {
			await createTastingNote(batch.id, {
				scoring_version: 2,
				// All subcategory scores
				aroma_malt: scores.aroma_malt,
				aroma_hops: scores.aroma_hops,
				aroma_fermentation: scores.aroma_fermentation,
				aroma_other: scores.aroma_other,
				appearance_color: scores.appearance_color,
				appearance_clarity: scores.appearance_clarity,
				appearance_head: scores.appearance_head,
				flavor_malt: scores.flavor_malt,
				flavor_hops: scores.flavor_hops,
				flavor_bitterness: scores.flavor_bitterness,
				flavor_fermentation: scores.flavor_fermentation,
				flavor_balance: scores.flavor_balance,
				flavor_finish: scores.flavor_finish,
				mouthfeel_body: scores.mouthfeel_body,
				mouthfeel_carbonation: scores.mouthfeel_carbonation,
				mouthfeel_warmth: scores.mouthfeel_warmth,
				// Category notes
				aroma_notes: notes.aroma || undefined,
				appearance_notes: notes.appearance || undefined,
				flavor_notes: notes.flavor || undefined,
				mouthfeel_notes: notes.mouthfeel || undefined,
				// Overall
				overall_score: scores.overall_score,
				overall_notes: notes.overall || undefined,
				// Context
				serving_temp_c: servingTemp || undefined,
				glassware: glassware || undefined,
				to_style: toStyle,
				style_deviation_notes: deviationNotes || undefined,
			});
			onSave();
		} catch (e) {
			error = (e as Error).message;
		} finally {
			saving = false;
		}
	}
</script>

<div class="bjcp-form">
	<div class="form-header">
		<h3 class="form-title">BJCP Scoresheet</h3>
		<span class="form-subtitle">Manual Entry</span>
	</div>

	<!-- Context Section -->
	<div class="section context-section">
		<h4 class="section-title">Serving Context</h4>
		<div class="context-fields">
			<div class="field">
				<label class="field-label" for="serving-temp">Serving Temp</label>
				<div class="input-with-unit">
					<input
						id="serving-temp"
						type="number"
						step="0.5"
						min="0"
						max="30"
						class="field-input"
						placeholder="--"
						bind:value={servingTemp}
					/>
					<span class="unit">&deg;C</span>
				</div>
			</div>
			<div class="field">
				<label class="field-label" for="glassware">Glassware</label>
				<select id="glassware" class="field-input" bind:value={glassware}>
					<option value="">Select...</option>
					{#each glasswareOptions as opt}
						<option value={opt.value}>{opt.label}</option>
					{/each}
				</select>
			</div>
		</div>
	</div>

	<!-- Score Sections -->
	{#each BJCP_CATEGORIES as category, catIdx}
		{@const sub = categorySubtotals[catIdx]}
		<div class="section score-section">
			<div class="section-header">
				<h4 class="section-title">{category.name}</h4>
				<span class="section-subtotal">{sub.subtotal}/{sub.max}</span>
			</div>

			{#if category.subcategories.length > 0}
				<!-- Subcategory sliders -->
				<div class="subcategories">
					{#each category.subcategories as subcat}
						<div class="slider-row">
							<label class="slider-label" for="score-{subcat.key}">{subcat.name}</label>
							<div class="slider-control">
								<input
									id="score-{subcat.key}"
									type="range"
									min="0"
									max={subcat.maxScore}
									step="1"
									class="range-slider"
									bind:value={scores[subcat.key]}
								/>
								<span class="slider-value">{scores[subcat.key]}</span>
							</div>
						</div>
					{/each}
				</div>
			{:else}
				<!-- Overall: single slider (0-10) -->
				<div class="slider-row overall-slider">
					<label class="slider-label" for="score-overall">Overall Impression</label>
					<div class="slider-control">
						<input
							id="score-overall"
							type="range"
							min="0"
							max={category.maxScore}
							step="1"
							class="range-slider"
							bind:value={scores.overall_score}
						/>
						<span class="slider-value">{scores.overall_score}</span>
					</div>
				</div>
			{/if}

			<!-- Category notes -->
			<textarea
				class="category-notes"
				placeholder="{category.name} notes..."
				rows="2"
				bind:value={notes[category.key]}
			></textarea>
		</div>
	{/each}

	<!-- Style Conformance -->
	<div class="section style-section">
		<h4 class="section-title">Style Conformance</h4>
		<label class="checkbox-row">
			<input type="checkbox" class="checkbox" bind:checked={toStyle} />
			<span class="checkbox-label">True to style?</span>
		</label>
		{#if !toStyle}
			<textarea
				class="category-notes"
				placeholder="Describe style deviations..."
				rows="2"
				bind:value={deviationNotes}
			></textarea>
		{/if}
	</div>

	<!-- Total Score Display -->
	<div class="total-section">
		<div class="total-score-display">
			<span class="total-label">Total Score</span>
			<span class="total-value {ratingClass}">{totalScore}</span>
			<span class="total-max">/ {BJCP_MAX_TOTAL}</span>
		</div>
		<div class="rating-badge {ratingClass}">{rating}</div>
	</div>

	<!-- Error -->
	{#if error}
		<div class="error-msg">{error}</div>
	{/if}

	<!-- Actions -->
	<div class="form-actions">
		<button type="button" class="cancel-btn" onclick={onCancel} disabled={saving}>Cancel</button>
		<button type="button" class="save-btn" onclick={save} disabled={saving}>
			{saving ? 'Saving...' : 'Save Scoresheet'}
		</button>
	</div>
</div>

<style>
	.bjcp-form {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.75rem;
		overflow: hidden;
		display: flex;
		flex-direction: column;
	}

	.form-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 1rem 1.25rem;
		border-bottom: 1px solid var(--border-subtle);
	}

	.form-title {
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
	}

	.form-subtitle {
		font-size: 0.6875rem;
		font-weight: 500;
		padding: 0.25rem 0.5rem;
		background: var(--bg-elevated);
		color: var(--text-muted);
		border-radius: 0.25rem;
	}

	/* Sections */
	.section {
		padding: 1rem 1.25rem;
		border-bottom: 1px solid var(--border-subtle);
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.section-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.section-title {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin: 0;
	}

	.section-subtotal {
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--accent);
		font-family: var(--font-mono);
	}

	/* Context fields */
	.context-fields {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 1rem;
	}

	.field {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
	}

	.field-label {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-muted);
	}

	.field-input {
		width: 100%;
		padding: 0.5rem 0.75rem;
		background: var(--bg-base, var(--bg-elevated));
		border: 1px solid var(--border-subtle);
		border-radius: 0.375rem;
		font-size: 0.875rem;
		color: var(--text-primary);
		transition: border-color 0.15s ease;
	}

	.field-input:focus {
		outline: none;
		border-color: var(--accent);
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

	/* Slider rows */
	.subcategories {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.slider-row {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}

	.slider-label {
		font-size: 0.8125rem;
		font-weight: 500;
		color: var(--text-secondary);
		min-width: 7rem;
		flex-shrink: 0;
	}

	.slider-control {
		flex: 1;
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}

	.range-slider {
		flex: 1;
		height: 0.375rem;
		-webkit-appearance: none;
		appearance: none;
		background: var(--border-subtle);
		border-radius: 0.25rem;
		outline: none;
		cursor: pointer;
	}

	.range-slider::-webkit-slider-thumb {
		-webkit-appearance: none;
		appearance: none;
		width: 1.125rem;
		height: 1.125rem;
		background: var(--accent);
		border: 2px solid var(--bg-surface);
		border-radius: 50%;
		box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
		cursor: pointer;
		transition: transform 0.1s ease;
	}

	.range-slider::-webkit-slider-thumb:hover {
		transform: scale(1.15);
	}

	.range-slider::-moz-range-thumb {
		width: 1.125rem;
		height: 1.125rem;
		background: var(--accent);
		border: 2px solid var(--bg-surface);
		border-radius: 50%;
		box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
		cursor: pointer;
	}

	.slider-value {
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--text-primary);
		font-family: var(--font-mono);
		min-width: 1.5rem;
		text-align: right;
	}

	/* Category notes */
	.category-notes {
		width: 100%;
		padding: 0.5rem 0.75rem;
		background: var(--bg-base, var(--bg-elevated));
		border: 1px solid var(--border-subtle);
		border-radius: 0.375rem;
		font-size: 0.8125rem;
		color: var(--text-primary);
		resize: none;
		font-family: inherit;
	}

	.category-notes:focus {
		outline: none;
		border-color: var(--accent);
	}

	/* Style conformance */
	.checkbox-row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		cursor: pointer;
	}

	.checkbox {
		width: 1rem;
		height: 1rem;
		accent-color: var(--accent);
		cursor: pointer;
	}

	.checkbox-label {
		font-size: 0.875rem;
		color: var(--text-secondary);
	}

	/* Total score */
	.total-section {
		padding: 1.25rem;
		display: flex;
		justify-content: space-between;
		align-items: center;
		border-bottom: 1px solid var(--border-subtle);
		background: var(--bg-elevated);
	}

	.total-score-display {
		display: flex;
		align-items: baseline;
		gap: 0.375rem;
	}

	.total-label {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin-right: 0.5rem;
	}

	.total-value {
		font-size: 1.75rem;
		font-weight: 700;
		font-family: var(--font-mono);
		line-height: 1;
	}

	.total-max {
		font-size: 0.875rem;
		font-weight: 500;
		color: var(--text-muted);
		font-family: var(--font-mono);
	}

	.rating-badge {
		font-size: 0.75rem;
		font-weight: 600;
		padding: 0.375rem 0.75rem;
		border-radius: 1rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	/* Rating color classes */
	.outstanding {
		color: var(--positive);
	}
	.rating-badge.outstanding {
		background: var(--positive-bg, rgba(34, 197, 94, 0.1));
		color: var(--positive);
	}

	.excellent {
		color: var(--positive);
	}
	.rating-badge.excellent {
		background: var(--positive-bg, rgba(34, 197, 94, 0.1));
		color: var(--positive);
	}

	.very-good {
		color: var(--accent);
	}
	.rating-badge.very-good {
		background: rgba(var(--accent-rgb, 59, 130, 246), 0.1);
		color: var(--accent);
	}

	.good {
		color: var(--text-primary);
	}
	.rating-badge.good {
		background: var(--bg-surface);
		color: var(--text-secondary);
	}

	.fair {
		color: var(--amber, #f59e0b);
	}
	.rating-badge.fair {
		background: rgba(245, 158, 11, 0.1);
		color: var(--amber, #f59e0b);
	}

	.problematic {
		color: var(--negative, #ef4444);
	}
	.rating-badge.problematic {
		background: rgba(239, 68, 68, 0.1);
		color: var(--negative, #ef4444);
	}

	/* Error */
	.error-msg {
		padding: 0.75rem 1.25rem;
		background: rgba(239, 68, 68, 0.1);
		color: var(--negative, #ef4444);
		font-size: 0.8125rem;
		border-bottom: 1px solid var(--border-subtle);
	}

	/* Actions */
	.form-actions {
		display: flex;
		justify-content: flex-end;
		gap: 0.5rem;
		padding: 1rem 1.25rem;
	}

	.cancel-btn,
	.save-btn {
		padding: 0.5rem 1rem;
		border-radius: 0.375rem;
		font-size: 0.8125rem;
		font-weight: 500;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.cancel-btn {
		background: transparent;
		border: 1px solid var(--border-subtle);
		color: var(--text-secondary);
	}

	.cancel-btn:hover {
		border-color: var(--text-muted);
	}

	.cancel-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.save-btn {
		background: var(--accent);
		border: none;
		color: white;
	}

	.save-btn:hover {
		opacity: 0.9;
	}

	.save-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	/* Responsive */
	@media (max-width: 480px) {
		.context-fields {
			grid-template-columns: 1fr;
		}

		.slider-row {
			flex-direction: column;
			align-items: flex-start;
			gap: 0.25rem;
		}

		.slider-label {
			min-width: unset;
		}

		.slider-control {
			width: 100%;
		}
	}
</style>
