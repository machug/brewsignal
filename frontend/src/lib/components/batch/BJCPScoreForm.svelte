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
					<span class="unit">&thinsp;&deg;C</span>
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
				<span class="section-subtotal num">{sub.subtotal}/{sub.max}</span>
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
								<span class="slider-value">{scores[subcat.key]}<span class="slider-max">/{subcat.maxScore}</span></span>
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
						<span class="slider-value">{scores.overall_score}<span class="slider-max">/{category.maxScore}</span></span>
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
			<span class="total-max">/{BJCP_MAX_TOTAL}</span>
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
	.num {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums lining-nums;
	}

	/* Form sits inside its parent section: hairlines only, no own card */
	.bjcp-form {
		border-top: 1px solid var(--rule-strong);
		display: flex;
		flex-direction: column;
		margin-bottom: var(--space-md);
	}

	.form-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: var(--space-sm);
		padding: var(--space-sm) 0;
		border-bottom: 1px solid var(--rule-hairline);
	}

	.form-title {
		font-family: var(--font-display);
		font-size: var(--text-base);
		font-weight: 600;
		color: var(--ink-primary);
		margin: 0;
	}

	.form-subtitle {
		font-family: var(--font-display);
		font-size: 0.6875rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		padding: 1px 7px;
		border: 1px solid var(--rule-strong);
		color: var(--ink-secondary);
		border-radius: 2px;
	}

	.section {
		padding: var(--space-md) 0;
		border-bottom: 1px solid var(--rule-hairline);
		display: flex;
		flex-direction: column;
		gap: var(--space-sm);
	}

	.section-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.section-title {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-muted);
		text-transform: uppercase;
		letter-spacing: 0.08em;
		margin: 0;
	}

	.section-subtotal {
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--accent);
	}

	.context-fields {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: var(--space-md);
	}

	.field {
		display: flex;
		flex-direction: column;
		gap: var(--space-2xs);
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
	.category-notes {
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

	.category-notes {
		min-height: 0;
		font-family: var(--font-body);
		resize: none;
	}

	.field-input:focus,
	.category-notes:focus {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
		border-color: var(--accent);
	}

	.input-with-unit {
		display: flex;
		align-items: center;
	}

	.input-with-unit .field-input {
		flex: 1;
	}

	.unit {
		font-size: var(--text-xs);
		color: var(--ink-muted);
		font-family: var(--font-num);
	}

	/* Sliders */
	.subcategories {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
	}

	.slider-row {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
	}

	.slider-label {
		font-size: var(--text-sm);
		font-weight: 700;
		color: var(--ink-secondary);
		min-width: 7rem;
		flex-shrink: 0;
	}

	.slider-control {
		flex: 1;
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		min-width: 0;
	}

	.range-slider {
		flex: 1;
		min-width: 0;
		height: 44px;
		-webkit-appearance: none;
		appearance: none;
		background: transparent;
		outline: none;
		cursor: pointer;
	}

	.range-slider::-webkit-slider-runnable-track {
		height: 4px;
		background: var(--rule-strong);
		border-radius: 2px;
	}

	.range-slider::-moz-range-track {
		height: 4px;
		background: var(--rule-strong);
		border-radius: 2px;
	}

	.range-slider::-webkit-slider-thumb {
		-webkit-appearance: none;
		appearance: none;
		width: 1.25rem;
		height: 1.25rem;
		margin-top: calc((4px - 1.25rem) / 2);
		background: var(--accent);
		border: 2px solid var(--bg-canvas);
		border-radius: 50%;
		cursor: pointer;
	}

	.range-slider::-moz-range-thumb {
		width: 1.25rem;
		height: 1.25rem;
		background: var(--accent);
		border: 2px solid var(--bg-canvas);
		border-radius: 50%;
		cursor: pointer;
	}

	.range-slider:focus-visible::-webkit-slider-thumb {
		outline: 2px solid var(--accent);
		outline-offset: 3px;
	}

	.range-slider:focus-visible::-moz-range-thumb {
		outline: 2px solid var(--accent);
		outline-offset: 3px;
	}

	/* Value as instrument cell */
	.slider-value {
		display: inline-flex;
		align-items: baseline;
		justify-content: flex-end;
		gap: 1px;
		min-width: 3.5rem;
		padding: 3px var(--space-xs);
		border: 1px solid var(--rule-hairline);
		border-radius: 4px;
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--ink-primary);
	}

	.slider-max {
		font-size: 0.6875rem;
		font-weight: 400;
		color: var(--ink-muted);
	}

	.checkbox-row {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
		min-height: 44px;
		cursor: pointer;
	}

	.checkbox {
		width: 1.125rem;
		height: 1.125rem;
		accent-color: var(--accent);
		cursor: pointer;
	}

	.checkbox:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.checkbox-label {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}

	/* Total: readout */
	.total-section {
		padding: var(--space-md) 0;
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: var(--space-sm);
		border-bottom: 1px solid var(--rule-hairline);
	}

	.total-score-display {
		display: flex;
		align-items: baseline;
		gap: var(--space-2xs);
	}

	.total-label {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-muted);
		text-transform: uppercase;
		letter-spacing: 0.08em;
		margin-right: var(--space-xs);
	}

	.total-value {
		font-size: var(--text-inst);
		font-weight: 500;
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		line-height: 1;
	}

	.total-max {
		font-size: var(--text-sm);
		color: var(--ink-muted);
		font-family: var(--font-num);
	}

	.rating-badge {
		font-family: var(--font-display);
		font-size: 0.6875rem;
		font-weight: 600;
		padding: 2px 7px;
		border: 1px solid currentColor;
		border-radius: 2px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}

	.outstanding,
	.excellent {
		color: var(--positive);
	}

	.very-good {
		color: var(--temp-trace);
	}

	.good {
		color: var(--ink-primary);
	}

	.rating-badge.good {
		color: var(--ink-secondary);
	}

	.fair {
		color: var(--warning);
	}

	.problematic {
		color: var(--negative);
	}

	.error-msg {
		padding: var(--space-sm);
		margin-top: var(--space-sm);
		border: 1px solid var(--negative);
		border-radius: 4px;
		color: var(--negative);
		font-size: var(--text-sm);
	}

	.form-actions {
		display: flex;
		justify-content: flex-end;
		gap: var(--space-xs);
		padding: var(--space-md) 0 0;
	}

	.cancel-btn,
	.save-btn {
		min-height: 44px;
		padding: 0 var(--space-md);
		border-radius: 4px;
		font-size: var(--text-sm);
		font-weight: 600;
		cursor: pointer;
	}

	.cancel-btn:focus-visible,
	.save-btn:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.cancel-btn {
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		color: var(--ink-secondary);
	}

	.cancel-btn:hover:not(:disabled) {
		background: var(--bg-subtle);
		color: var(--ink-primary);
	}

	.save-btn {
		background: var(--accent);
		border: 1px solid var(--accent);
		color: var(--accent-ink);
	}

	.save-btn:hover:not(:disabled) {
		background: var(--accent-hover);
		border-color: var(--accent-hover);
	}

	.cancel-btn:disabled,
	.save-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	@media (max-width: 480px) {
		.context-fields {
			grid-template-columns: 1fr;
		}

		.slider-row {
			flex-direction: column;
			align-items: flex-start;
			gap: 0;
		}

		.slider-label {
			min-width: unset;
		}

		.slider-control {
			width: 100%;
		}
	}
</style>
