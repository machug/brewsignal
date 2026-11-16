<script lang="ts">
	import { srmToHex, srmToDescription, describeBUGU } from '$lib/brewing';
	import { statDiffers, type EffectiveStats, type StatValues } from '$lib/recipeStats';

	interface Props {
		// Numbers worked out by the server (see effectiveStats in $lib/recipeStats)
		stats: EffectiveStats;
		// Brewer-declared targets. Shown beside a calculated value when they differ.
		targets?: StatValues;
		// The last calculation failed; the numbers shown are the previous ones.
		stale?: boolean;
		// BJCP style metadata for the linked Style row. Rendered as a
		// dedicated cell at the left of the stats grid so brewers see the
		// target style alongside the core stats without scrolling back up
		// to the title card (tilt_ui-6b9).
		styleName?: string;
		styleCategory?: string; // e.g. "21A"
	}

	let { stats, targets, stale = false, styleName, styleCategory }: Props = $props();

	const DASH = '\u2014';
	const fmt = (v: number | undefined, d: number) => (v == null ? DASH : v.toFixed(d));

	// Hint under a calculated stat when the declared target differs.
	function hint(stat: keyof StatValues, d: number, suffix = ''): string | null {
		const t = targets?.[stat];
		return stats.source === 'calculated' && t != null && statDiffers(stat, stats[stat], t)
			? `src ${t.toFixed(d)}${suffix}`
			: null;
	}

	let colorHex = $derived(stats.colorHex ?? (stats.srm != null ? srmToHex(stats.srm) : null));
	let colorDesc = $derived(stats.srm != null ? srmToDescription(stats.srm) : null);
	let balanceDesc = $derived(stats.buGu != null ? describeBUGU(stats.buGu) : null);
	let assumptionsTip = $derived(stats.assumptions.join('\n'));
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
		<span class="value">{fmt(stats.og, 3)}</span>
		{#if hint('og', 3)}<span class="sub">{hint('og', 3)}</span>{/if}
	</div>
	<div class="cell">
		<span class="label">FG</span>
		<span class="value">{fmt(stats.fg, 3)}</span>
		{#if hint('fg', 3)}<span class="sub">{hint('fg', 3)}</span>{/if}
	</div>
	<div class="cell">
		<span class="label">ABV</span>
		<span class="value">{fmt(stats.abv, 1)}{#if stats.abv != null}<span class="unit pct">%</span>{/if}</span>
		{#if hint('abv', 1, '%')}<span class="sub">{hint('abv', 1, '%')}</span>{/if}
	</div>
	<div class="cell">
		<span class="label">IBU</span>
		<span class="value">{fmt(stats.ibu, 0)}</span>
		{#if hint('ibu', 0)}<span class="sub">{hint('ibu', 0)}</span>{/if}
	</div>
	<div class="cell">
		<span class="label">BU:GU</span>
		<span class="value">{fmt(stats.buGu, 2)}</span>
		{#if balanceDesc}<span class="sub">{balanceDesc}</span>{/if}
	</div>
	<div class="cell cell-color">
		<!-- Flat SRM indicator; fill is beer colour (data), not theme -->
		<svg class="glass" viewBox="0 0 24 36" aria-hidden="true">
			<path d="M3 2h18l-2.5 31a2 2 0 0 1-2 1.8H7.5a2 2 0 0 1-2-1.8z" fill="none" stroke="var(--rule-strong)" stroke-width="1.5" />
			{#if colorHex}<path d="M4.1 10h15.8l-2.1 23a1 1 0 0 1-1 .9H7.2a1 1 0 0 1-1-.9z" style="fill: {colorHex}" />{/if}
		</svg>
		<div class="color-text">
			<span class="label">Color</span>
			<span class="value">{fmt(stats.srm, 0)}{#if stats.srm != null}<span class="unit">SRM</span>{/if}</span>
			{#if colorDesc}<span class="sub">{colorDesc}</span>{/if}
			{#if hint('srm', 0)}<span class="sub">{hint('srm', 0)}</span>{/if}
		</div>
	</div>
	<div class="cell">
		<span class="label">Calories</span>
		<span class="value">{stats.caloriesPer330ml ?? DASH}</span>
		<span class="sub">per 330&thinsp;mL</span>
	</div>
	{#if stats.source !== 'empty'}
		<div class="cell cell-note">
			{#if stats.source === 'declared'}
				<span class="sub" title="No ingredients to work these out from">Declared</span>
			{:else if assumptionsTip}
				<span class="sub tip" title={assumptionsTip}>Estimated</span>
			{/if}
			{#if stale}<span class="sub">Not updated</span>{/if}
		</div>
	{:else if stale}
		<div class="cell cell-note"><span class="sub">Not updated</span></div>
	{/if}
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

	.cell-note {
		flex: 0 1 auto;
		justify-content: center;
	}

	.tip {
		cursor: help;
		text-decoration: underline dotted;
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
