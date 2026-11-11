<script lang="ts">
	import type { BatchResponse, BatchProgressResponse } from '$lib/api';
	import type { TiltReading } from '$lib/stores/tilts.svelte';
	import { formatGravity, getGravityUnit, formatTemp, getTempUnit } from '$lib/stores/config.svelte';
	import { statusConfig } from './status';

	interface Props {
		batch: BatchResponse;
		progress?: BatchProgressResponse;
		liveReading?: TiltReading | null;
		expanded?: boolean;
		onToggleExpand?: () => void;
		onStatusChange?: (status: string) => void;
		onViewDetails?: () => void;
	}

	let { batch, progress, liveReading = null, expanded = false, onToggleExpand, onStatusChange, onViewDetails }: Props = $props();

	// Temperature status indicators
	const tempStatusConfig: Record<string, { icon: string; color: string }> = {
		in_range: { icon: '', color: 'var(--ink-primary)' },
		too_cold: { icon: '\u2193', color: 'var(--status-warn)' },
		too_hot: { icon: '\u2191', color: 'var(--status-danger)' },
		unknown: { icon: '', color: 'var(--ink-muted)' }
	};

	let statusInfo = $derived(statusConfig[batch.status] || statusConfig.planning);
	let tempStatus = $derived(progress?.temperature?.status ? tempStatusConfig[progress.temperature.status] : tempStatusConfig.unknown);
	let gravityUnit = $derived(getGravityUnit());
	let tempUnit = $derived(getTempUnit());

	// Determine fermentation activity status based on sg_rate
	let activityStatus = $derived.by(() => {
		if (batch.status !== 'fermenting' && batch.status !== 'conditioning') return null;

		const sgRate = liveReading?.sg_rate;
		if (sgRate === null || sgRate === undefined) return null;

		// sg_rate is in points per hour (e.g., -0.001 means dropping 0.001 SG per hour)
		const absRate = Math.abs(sgRate);

		if (absRate > 0.002) return { label: 'Very Active', color: 'var(--activity-very-active)' };
		if (absRate > 0.0005) return { label: 'Active', color: 'var(--activity-active)' };
		if (absRate > 0.0001) return { label: 'Slowing', color: 'var(--activity-slowing)' };
		return { label: 'Complete', color: 'var(--activity-complete)' };
	});

	// Check for anomalies in live reading
	let hasAnomaly = $derived(liveReading?.is_anomaly ?? false);

	// Format gravity for display
	function formatSG(value?: number): string {
		if (value === undefined || value === null) return '--';
		return formatGravity(value);
	}

	// Format temperature for display
	function formatTempValue(value?: number): string {
		if (value === undefined || value === null) return '--';
		return formatTemp(value);
	}

	// Calculate days since brew date
	function daysSinceBrew(): string {
		if (!batch.brew_date) return '--';
		const brewDate = new Date(batch.brew_date);
		const now = new Date();
		const days = Math.floor((now.getTime() - brewDate.getTime()) / (1000 * 60 * 60 * 24));
		if (days === 0) return 'Today';
		if (days === 1) return '1 day';
		return `${days} days`;
	}

	// Format date for display
	function formatDate(dateStr?: string): string {
		if (!dateStr) return '--';
		return new Date(dateStr).toLocaleDateString('en-US', {
			month: 'short',
			day: 'numeric'
		});
	}

	let brewDays = $derived(daysSinceBrew());
	let displayName = $derived(batch.name || batch.recipe?.name || 'Unnamed Batch');
	let fg = $derived(progress?.measured?.current_sg ?? batch.measured_fg ?? null);
	let abvVal = $derived(progress?.measured?.abv ?? batch.measured_abv ?? null);
	let pct = $derived(progress?.progress?.percent_complete ?? null);
	let styleName = $derived(batch.recipe?.style?.name ?? (batch.recipe?.name && batch.name && batch.name !== batch.recipe.name ? batch.recipe.name : null));
</script>

<div class="row" class:expanded class:has-anomaly={hasAnomaly}>
	<span class="n num">#{batch.batch_number || '?'}</span>
	<div class="name-cell">
		<button type="button" class="name" onclick={onViewDetails} disabled={!onViewDetails}>{displayName}</button>
		<span class="sub">
			{#if styleName}{styleName}{/if}
			{#if activityStatus}<span class="activity" style="color: {activityStatus.color};">{styleName ? ' \u00b7 ' : ''}{activityStatus.label}</span>{/if}
			{#if hasAnomaly}<span class="anomaly">{styleName || activityStatus ? ' \u00b7 ' : ''}Anomaly</span>{/if}
		</span>
	</div>
	<button type="button" class="pill s-{batch.status}" onclick={() => onStatusChange?.(batch.status)}>{statusInfo.label}</button>
	<div class="figs">
	<span class="fig num" data-label="OG">{formatSG(batch.measured_og)}</span>
	<span class="fig num" data-label={progress?.measured?.current_sg ? 'Now' : 'FG'}>{formatSG(fg ?? undefined)}</span>
	<span class="fig num" data-label="ABV">{abvVal != null ? abvVal.toFixed(1) : '--'}<span class="u">%</span></span>
	<span class="fig num temp" data-label="Temp" style="color: {tempStatus.color};">
		{#if progress?.temperature?.current != null}{formatTempValue(progress.temperature.current)}<span class="u">&thinsp;{tempUnit}</span>{#if tempStatus.icon}<span class="u">{tempStatus.icon}</span>{/if}{:else}--{/if}
	</span>
	<span class="fig num date" data-label="Brewed">{formatDate(batch.brew_date ?? batch.start_time)}{#if batch.brew_date && (batch.status === 'fermenting' || batch.status === 'conditioning')}<span class="u"> &middot; {brewDays}</span>{/if}</span>
	</div>
	<div class="actions">
		{#if onViewDetails}
			<button type="button" class="view" onclick={onViewDetails}>
				View
				<svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M6 4l4 4-4 4" /></svg>
			</button>
		{/if}
		{#if onToggleExpand}
			<button type="button" class="view" onclick={onToggleExpand} aria-label={expanded ? 'Collapse' : 'Expand'}>
				<svg class:flip={expanded} viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M4 6l4 4 4-4" /></svg>
			</button>
		{/if}
	</div>
	{#if batch.status === 'fermenting' || batch.status === 'conditioning'}
		<div class="track" role="progressbar" aria-valuenow={pct ?? 0} aria-valuemin="0" aria-valuemax="100" aria-label="Progress"><span style="width: {pct ?? 0}%;"></span></div>
	{/if}
</div>

<style>
	.row {
		position: relative;
		display: grid;
		grid-template-columns: 52px minmax(0, 2fr) 112px repeat(4, minmax(64px, 0.7fr)) minmax(120px, 1fr) 76px;
		align-items: center;
		gap: var(--space-sm);
		padding: var(--space-sm) var(--space-xs);
		min-height: 56px;
		border-bottom: 1px solid var(--rule-hairline);
		font-size: var(--text-sm);
		transition: background-color 140ms var(--ease-out-quart);
	}
	.row:hover {
		background-color: var(--bg-surface);
	}
	.row.has-anomaly {
		background-color: color-mix(in oklch, var(--status-warn) 6%, transparent);
	}
	.num {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums lining-nums;
		letter-spacing: -0.02em;
	}
	.n {
		font-size: var(--text-xs);
		color: var(--ink-muted);
	}
	.name-cell {
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.name {
		text-align: left;
		font-family: var(--font-display);
		font-weight: 600;
		font-size: var(--text-base);
		color: var(--ink-primary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		cursor: pointer;
		min-height: 24px;
	}
	.name:hover:not(:disabled) {
		text-decoration: underline;
		text-decoration-color: var(--accent);
		text-underline-offset: 3px;
	}
	.sub {
		font-size: var(--text-xs);
		color: var(--ink-secondary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.anomaly {
		color: var(--status-warn);
	}
	.pill {
		justify-self: start;
		font-family: var(--font-display);
		font-size: 0.6875rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		padding: 2px 7px;
		border-radius: 2px;
		border: 1px solid var(--rule-strong);
		color: var(--ink-secondary);
		white-space: nowrap;
		cursor: default;
	}
	.pill.s-planning {
		border-color: var(--accent-rule);
		color: var(--accent);
		background-color: var(--accent-tint);
	}
	.pill.s-brewing,
	.pill.s-fermenting {
		border-color: var(--accent-rule);
		color: var(--accent);
	}
	.pill.s-conditioning {
		border-color: color-mix(in oklch, var(--status-conditioning) 55%, transparent);
		color: var(--status-conditioning);
	}
	.pill.s-completed {
		border-color: color-mix(in oklch, var(--status-completed) 55%, transparent);
		color: var(--status-completed);
	}
	.figs {
		display: contents;
	}
	.fig {
		font-size: var(--text-sm);
		color: var(--ink-primary);
		text-align: right;
	}
	.fig.date {
		font-size: var(--text-xs);
		color: var(--ink-secondary);
	}
	.u {
		font-family: var(--font-body);
		font-size: 0.78em;
		color: var(--ink-muted);
		letter-spacing: 0;
	}
	.actions {
		display: flex;
		justify-content: flex-end;
		gap: var(--space-2xs);
	}
	.view {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		min-height: 32px;
		padding: 0 var(--space-xs);
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-secondary);
		border-radius: 3px;
		cursor: pointer;
	}
	.view:hover {
		color: var(--ink-primary);
	}
	.flip {
		transform: rotate(180deg);
	}
	.track {
		position: absolute;
		left: var(--space-xs);
		right: var(--space-xs);
		bottom: -1px;
		height: 2px;
		background-color: var(--rule-hairline);
	}
	.track span {
		display: block;
		height: 100%;
		background-color: var(--accent);
	}

	@media (max-width: 900px) {
		.row {
			grid-template-columns: 42px minmax(0, 1fr) auto;
			row-gap: var(--space-2xs);
		}
		.name {
			min-height: 44px;
			display: flex;
			align-items: center;
		}
		.pill {
			min-height: 28px;
			display: inline-flex;
			align-items: center;
		}
		.figs {
			grid-column: 2 / -1;
			display: flex;
			flex-wrap: wrap;
			gap: 2px var(--space-md);
		}
		.fig {
			text-align: left;
			font-size: var(--text-xs);
		}
		.fig::before {
			content: attr(data-label) ' ';
			font-family: var(--font-display);
			text-transform: uppercase;
			letter-spacing: 0.06em;
			color: var(--ink-muted);
			margin-right: 4px;
		}
		.actions {
			display: none;
		}
	}
</style>
