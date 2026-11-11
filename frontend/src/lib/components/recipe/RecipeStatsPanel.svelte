<script lang="ts">
	import { srmToHex, srmToDescription, calculateBUGU, calculateCalories, describeBUGU } from '$lib/brewing';

	interface Props {
		og?: number;
		fg?: number;
		abv?: number;
		ibu?: number;
		colorSrm?: number;
		batchSizeLiters?: number;
		// BJCP style metadata for the linked Style row. Rendered as a
		// dedicated cell at the left of the stats grid so brewers see the
		// target style alongside the core stats without scrolling back up
		// to the title card (tilt_ui-6b9).
		styleName?: string;
		styleCategory?: string; // e.g. "21A"
		// Imported brewer-declared targets. When present and meaningfully
		// different from the calculated value, displayed as a small "src N"
		// hint under the stat (tilt_ui-ak6).
		targetOg?: number;
		targetFg?: number;
		targetAbv?: number;
		targetIbu?: number;
		targetSrm?: number;
	}

	let {
		og = 1.050, fg = 1.010, abv = 5.0, ibu = 30, colorSrm = 8, batchSizeLiters = 20,
		styleName, styleCategory,
		targetOg, targetFg, targetAbv, targetIbu, targetSrm,
	}: Props = $props();

	function showDelta(target: number | undefined, actual: number, threshold: number): boolean {
		if (target == null) return false;
		return Math.abs(target - actual) >= threshold;
	}

	// Derived calculations
	let colorHex = $derived(srmToHex(colorSrm));
	let colorDesc = $derived(srmToDescription(colorSrm));
	let buguRatio = $derived(ibu && og ? calculateBUGU(ibu, og) : 0);
	let calories = $derived(og && fg ? calculateCalories(og, fg) : 0);

	// Balance description based on BU:GU ratio
	let balanceDesc = $derived(describeBUGU(buguRatio));
</script>

<div class="stats-panel">
	{#if styleName}
		<div class="cell cell-style" title={styleName}>
			<span class="label">Style</span>
			<span class="value style-value">{styleName}</span>
			{#if styleCategory}
				<span class="sub">BJCP {styleCategory}</span>
			{/if}
		</div>
	{/if}

	<div class="cell">
		<span class="label">OG</span>
		<span class="value">{og.toFixed(3)}</span>
		{#if showDelta(targetOg, og, 0.002)}
			<span class="sub">src {targetOg!.toFixed(3)}</span>
		{/if}
	</div>
	<div class="cell">
		<span class="label">FG</span>
		<span class="value">{fg.toFixed(3)}</span>
		{#if showDelta(targetFg, fg, 0.002)}
			<span class="sub">src {targetFg!.toFixed(3)}</span>
		{/if}
	</div>
	<div class="cell">
		<span class="label">ABV</span>
		<span class="value">{abv.toFixed(1)}<span class="unit pct">%</span></span>
		{#if showDelta(targetAbv, abv, 0.2)}
			<span class="sub">src {targetAbv!.toFixed(1)}%</span>
		{/if}
	</div>
	<div class="cell">
		<span class="label">IBU</span>
		<span class="value">{ibu.toFixed(0)}</span>
		{#if showDelta(targetIbu, ibu, 3)}
			<span class="sub">src {targetIbu!.toFixed(0)}</span>
		{/if}
	</div>
	<div class="cell">
		<span class="label">BU:GU</span>
		<span class="value">{buguRatio.toFixed(2)}</span>
		<span class="sub">{balanceDesc}</span>
	</div>
	<div class="cell cell-color">
		<!-- Flat SRM indicator; fill is beer colour (data), not theme -->
		<svg class="glass" viewBox="0 0 24 36" aria-hidden="true">
			<path d="M3 2h18l-2.5 31a2 2 0 0 1-2 1.8H7.5a2 2 0 0 1-2-1.8z" fill="none" stroke="var(--rule-strong)" stroke-width="1.5" />
			<path d="M4.1 10h15.8l-2.1 23a1 1 0 0 1-1 .9H7.2a1 1 0 0 1-1-.9z" style="fill: {colorHex}" />
		</svg>
		<div class="color-text">
			<span class="label">Color</span>
			<span class="value">{colorSrm.toFixed(0)}<span class="unit">SRM</span></span>
			<span class="sub">{colorDesc}</span>
			{#if showDelta(targetSrm, colorSrm, 1)}
				<span class="sub">src {targetSrm!.toFixed(0)}</span>
			{/if}
		</div>
	</div>
	<div class="cell">
		<span class="label">Calories</span>
		<span class="value">{calories}</span>
		<span class="sub">per 330&thinsp;mL</span>
	</div>
</div>

<style>
	.stats-panel {
		display: flex;
		flex-wrap: wrap;
		border-top: 1px solid var(--rule-hairline);
		border-left: 1px solid var(--rule-hairline);
		background: var(--bg-surface);
		overflow: hidden;
		margin-bottom: var(--space-lg);
	}

	/* Hairline grid: every cell draws its right/bottom rule */
	.cell {
		flex: 1 1 100px;
		display: flex;
		flex-direction: column;
		gap: 2px;
		padding: var(--space-sm) var(--space-md);
		border-right: 1px solid var(--rule-hairline);
		border-bottom: 1px solid var(--rule-hairline);
		margin: 0 -1px -1px 0;
		min-width: 0;
	}

	.cell-style {
		flex: 2 1 180px;
	}

	.cell-color {
		flex: 1.5 1 150px;
		flex-direction: row;
		align-items: center;
		gap: var(--space-sm);
	}

	.glass {
		width: 24px;
		height: 36px;
		flex-shrink: 0;
	}

	.color-text {
		display: flex;
		flex-direction: column;
		gap: 2px;
		min-width: 0;
	}

	.label {
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-muted);
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}

	.value {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: var(--text-xl);
		font-weight: 500;
		line-height: 1.2;
		color: var(--ink-primary);
		white-space: nowrap;
	}

	.unit {
		margin-left: 0.25em;
		font-size: 0.875rem;
		font-weight: 400;
		color: var(--ink-muted);
	}

	.unit.pct {
		margin-left: 0;
	}

	/* Style name is text, not a reading */
	.style-value {
		font-family: var(--font-display);
		font-size: var(--text-base);
		font-weight: 600;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.sub {
		font-size: var(--text-xs);
		color: var(--ink-secondary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	/* Phone: clean 2-column grid, equal 1px hairlines via grid gap */
	@media (max-width: 760px) {
		.stats-panel {
			display: grid;
			grid-template-columns: 1fr 1fr;
			gap: 1px;
			border: 1px solid var(--rule-hairline);
			background: var(--rule-hairline);
		}

		.cell {
			flex: none;
			margin: 0;
			border: none;
			background: var(--bg-surface);
			padding: var(--space-sm);
		}

		/* An odd final cell spans the row so no empty hole shows */
		.cell:last-child:nth-child(odd) {
			grid-column: 1 / -1;
		}
	}
</style>
