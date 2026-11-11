<script module lang="ts">
	import type { HistoricalReading } from '$lib/api';

	// Valid ranges for outlier filtering (matches backend)
	const SG_MIN = 0.5;
	const SG_MAX = 1.2;
	const TEMP_MIN_C = 0; // Celsius (API returns Celsius since PR #66)
	const TEMP_MAX_C = 100;

	// Percentile helper - filters out noise spikes from High/Low stats
	export function percentile(arr: number[], p: number): number {
		const sorted = [...arr].sort((a, b) => a - b);
		const idx = (p / 100) * (sorted.length - 1);
		const lower = Math.floor(idx);
		const upper = Math.ceil(idx);
		if (lower === upper) return sorted[lower];
		return sorted[lower] + (sorted[upper] - sorted[lower]) * (idx - lower);
	}

	export function formatRate(rate: number): string {
		const sign = rate >= 0 ? '+' : '';
		return `${sign}${rate.toFixed(4)}`;
	}

	export function formatDuration(days: number): string {
		if (days < 1) {
			const hours = days * 24;
			return `${hours.toFixed(1)}h`;
		}
		return `${days.toFixed(1)}d`;
	}

	/** Gravity-derived stats shared by the full stats panel and Home's trend strip. */
	export function analyseSg(readings: HistoricalReading[], originalGravity: number | null) {
		// Filter out invalid readings (flagged by backend) first
		const validReadings = readings.filter((r) => r.status !== 'invalid');
		if (validReadings.length === 0) return null;

		// Readings come newest first, so sort for chronological order
		const sorted = [...validReadings].sort(
			(a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
		);
		const firstReading = sorted[0];
		const lastReading = sorted[sorted.length - 1];

		// SG values (prefer calibrated, filter outliers for historical data)
		const sgValues = sorted
			.map((r) => r.sg_calibrated ?? r.sg_raw)
			.filter((v): v is number => v !== null && v >= SG_MIN && v <= SG_MAX);
		if (sgValues.length === 0) return null;

		const currentSg = sgValues[sgValues.length - 1];
		const firstSg = sgValues[0];
		// Use percentiles to filter noise spikes (Tilt can report bad values when bumped)
		const highSg = percentile(sgValues, 95);
		const lowSg = percentile(sgValues, 5);

		const firstTime = new Date(firstReading.timestamp).getTime();
		const lastTime = new Date(lastReading.timestamp).getTime();
		const durationDays = (lastTime - firstTime) / (1000 * 60 * 60 * 24);

		// Fermentation rate (SG drop per day)
		const fermRate = durationDays > 0 ? (currentSg - firstSg) / durationDays : 0;

		// Days at current SG (find when SG last changed by >0.001)
		let daysAtCurrentSg = 0;
		const SG_CHANGE_THRESHOLD = 0.001;
		for (let i = sgValues.length - 2; i >= 0; i--) {
			if (Math.abs(sgValues[i] - currentSg) > SG_CHANGE_THRESHOLD) {
				const changeTime = new Date(sorted[i + 1].timestamp).getTime();
				daysAtCurrentSg = (lastTime - changeTime) / (1000 * 60 * 60 * 24);
				break;
			}
		}

		// Use explicit OG if set, otherwise estimate from highSg (95th percentile)
		const og = originalGravity ?? highSg;
		const ogIsEstimated = originalGravity === null;

		return { sorted, currentSg, firstSg, highSg, lowSg, fermRate, durationDays, daysAtCurrentSg, og, ogIsEstimated };
	}
</script>

<script lang="ts">
	import { configState, formatTemp, getTempUnit, fahrenheitToCelsius, formatGravity, getGravityUnit } from '$lib/stores/config.svelte';

	// Trend prediction data from TiltChart
	interface TrendPrediction {
		predictedFg: number | null;
		daysToFg: number | null;
		r2: number;
	}

	interface Props {
		readings: HistoricalReading[];
		originalGravity: number | null;
		onOgChange?: (og: number | null) => void;
		trend?: TrendPrediction | null;
	}

	let { readings, originalGravity, onOgChange, trend = null }: Props = $props();

	// OG editing state
	let isEditingOg = $state(false);
	let ogEditValue = $state('');
	let ogInputRef = $state<HTMLInputElement | null>(null);

	// Reactive units from config
	let useCelsius = $derived(configState.config.temp_units === 'C');
	let tempUnit = $derived(getTempUnit());
	let gravityUnit = $derived(getGravityUnit());

	// Compute stats from readings
	let stats = $derived.by(() => {
		if (readings.length === 0) {
			return null;
		}

		const sg = analyseSg(readings, originalGravity);
		if (!sg) return null;
		const { sorted, currentSg, firstSg, highSg, lowSg, fermRate, durationDays, daysAtCurrentSg } = sg;

		// Temp values (prefer calibrated, in Celsius from API since PR #66, filter outliers)
		const tempValues = sorted
			.map((r) => r.temp_calibrated ?? r.temp_raw)
			.filter((v): v is number => v !== null && v >= TEMP_MIN_C && v <= TEMP_MAX_C);

		// Temp stats (convert if needed)
		let currentTemp: number | null = null;
		let avgTemp: number | null = null;
		let highTemp: number | null = null;
		let lowTemp: number | null = null;

		if (tempValues.length > 0) {
			// Temperature is already in Celsius from API (since PR #66)
			const lastTempC = tempValues[tempValues.length - 1];
			const avgTempC = tempValues.reduce((a, b) => a + b, 0) / tempValues.length;
			// Use percentiles for High/Low to filter noise
			const highTempC = percentile(tempValues, 95);
			const lowTempC = percentile(tempValues, 5);

			// Convert to F only if user preference is Fahrenheit
			currentTemp = useCelsius ? lastTempC : (lastTempC * 9 / 5) + 32;
			avgTemp = useCelsius ? avgTempC : (avgTempC * 9 / 5) + 32;
			highTemp = useCelsius ? highTempC : (highTempC * 9 / 5) + 32;
			lowTemp = useCelsius ? lowTempC : (lowTempC * 9 / 5) + 32;
		}

		// Attenuation and ABV
		let apparentAttenuation: number | null = null;
		let abv: number | null = null;
		const { og, ogIsEstimated } = sg;

		if (og > 1.0 && og > currentSg) {
			// Apparent attenuation = (OG - FG) / (OG - 1) * 100
			apparentAttenuation = ((og - currentSg) / (og - 1.0)) * 100;
			// Standard ABV formula
			abv = (og - currentSg) * 131.25;
		}

		return {
			currentSg,
			firstSg,
			highSg,
			lowSg,
			currentTemp,
			avgTemp,
			highTemp,
			lowTemp,
			fermRate,
			durationDays,
			daysAtCurrentSg,
			apparentAttenuation,
			abv,
			ogIsEstimated,
			effectiveOg: og
		};
	});

	function startEditingOg() {
		ogEditValue = originalGravity?.toFixed(3) ?? '';
		isEditingOg = true;
		setTimeout(() => ogInputRef?.focus(), 0);
	}

	function saveOg() {
		const trimmed = ogEditValue.trim();
		if (!trimmed) {
			onOgChange?.(null);
		} else {
			const parsed = parseFloat(trimmed);
			if (!isNaN(parsed) && parsed >= 0.99 && parsed <= 1.2) {
				onOgChange?.(parsed);
			}
		}
		isEditingOg = false;
	}

	function handleOgKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') {
			saveOg();
		} else if (e.key === 'Escape') {
			isEditingOg = false;
		}
	}

	function formatSg(sg: number): string {
		return formatGravity(sg);
	}

	function formatTempStat(temp: number | null): string {
		if (temp === null) return '--';
		return temp.toFixed(1);
	}

	function formatPercent(val: number | null): string {
		if (val === null) return '--';
		return `${val.toFixed(1)}%`;
	}
</script>

{#if stats}
	<div class="stats-panel">
		<div class="stats-grid">
			<!-- Gravity column -->
			<div class="stats-column">
				<h4 class="stats-header">{gravityUnit === 'SG' ? 'Gravity' : gravityUnit === '°P' ? 'Plato' : 'Brix'}</h4>
				<div class="stat-row">
					<span class="stat-label">Current</span>
					<span class="stat-value">{formatSg(stats.currentSg)}</span>
				</div>
				<div class="stat-row">
					<span class="stat-label">Start</span>
					<span class="stat-value">{formatSg(stats.firstSg)}</span>
				</div>
				<div class="stat-row">
					<span class="stat-label">High</span>
					<span class="stat-value">{formatSg(stats.highSg)}</span>
				</div>
				<div class="stat-row">
					<span class="stat-label">Low</span>
					<span class="stat-value">{formatSg(stats.lowSg)}</span>
				</div>
			</div>

			<!-- Temperature column -->
			<div class="stats-column">
				<h4 class="stats-header">Temperature</h4>
				<div class="stat-row">
					<span class="stat-label">Current</span>
					<span class="stat-value temp">{formatTempStat(stats.currentTemp)}<span class="stat-unit">&thinsp;{tempUnit}</span></span>
				</div>
				<div class="stat-row">
					<span class="stat-label">Average</span>
					<span class="stat-value temp">{formatTempStat(stats.avgTemp)}<span class="stat-unit">&thinsp;{tempUnit}</span></span>
				</div>
				<div class="stat-row">
					<span class="stat-label">High</span>
					<span class="stat-value temp">{formatTempStat(stats.highTemp)}<span class="stat-unit">&thinsp;{tempUnit}</span></span>
				</div>
				<div class="stat-row">
					<span class="stat-label">Low</span>
					<span class="stat-value temp">{formatTempStat(stats.lowTemp)}<span class="stat-unit">&thinsp;{tempUnit}</span></span>
				</div>
			</div>
		</div>

		<!-- Bottom row with rate, duration, OG, attenuation, ABV -->
		<div class="stats-bottom">
			<div class="stat-pill">
				<span class="stat-label">Rate</span>
				<span class="stat-value rate" class:fermenting={stats.fermRate < 0}>{formatRate(stats.fermRate)}/day</span>
			</div>
			<div class="stat-pill">
				<span class="stat-label">Duration</span>
				<span class="stat-value">{formatDuration(stats.durationDays)}</span>
			</div>
			<div class="stat-pill">
				<span class="stat-label">At SG</span>
				<span class="stat-value">{formatDuration(stats.daysAtCurrentSg)}</span>
			</div>
			<div class="stat-pill og-pill">
				<span class="stat-label">OG</span>
				{#if onOgChange && isEditingOg}
					<input
						type="text"
						bind:this={ogInputRef}
						bind:value={ogEditValue}
						onblur={saveOg}
						onkeydown={handleOgKeydown}
						class="og-input"
						placeholder="1.050"
						maxlength="5"
					/>
				{:else if onOgChange}
					<button type="button" class="og-btn" onclick={startEditingOg} title={stats.ogIsEstimated ? "Estimated from high reading - click to set actual OG" : "Click to edit Original Gravity"}>
						<span class="stat-value" class:estimated={stats.ogIsEstimated}>{formatSg(stats.effectiveOg)}</span>
						{#if stats.ogIsEstimated}
							<span class="estimated-badge">est</span>
						{/if}
						<svg class="edit-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
						</svg>
					</button>
				{:else}
					<span class="stat-value" class:estimated={stats.ogIsEstimated}>{formatSg(stats.effectiveOg)}</span>
					{#if stats.ogIsEstimated}
						<span class="estimated-badge">est</span>
					{/if}
				{/if}
			</div>
			<div class="stat-pill">
				<span class="stat-label">Atten.</span>
				<span class="stat-value">{formatPercent(stats.apparentAttenuation)}</span>
			</div>
			<div class="stat-pill">
				<span class="stat-label">ABV</span>
				<span class="stat-value">{formatPercent(stats.abv)}</span>
			</div>
			{#if trend?.daysToFg !== null && trend?.daysToFg !== undefined}
				<div class="stat-pill prediction-pill" title="Estimated time until target FG (R²={trend.r2.toFixed(2)})">
					<span class="stat-label">ETA</span>
					<span class="stat-value prediction">{formatDuration(trend.daysToFg)}</span>
					<span class="prediction-badge">pred</span>
				</div>
			{/if}
		</div>
	</div>
{:else}
	<div class="stats-empty">
		<span>Not enough data for statistics</span>
	</div>
{/if}

<style>
	.stats-panel {
		padding: var(--space-sm) var(--space-md);
		border-top: 1px solid var(--rule-hairline);
	}

	.stats-grid {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: var(--space-md);
		margin-bottom: var(--space-sm);
	}

	.stats-column {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.stats-header {
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--ink-muted);
		margin-bottom: 0.25rem;
		font-family: var(--font-display);
	}

	.stat-row {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		padding: 0.125rem 0;
	}

	.stat-label {
		font-size: var(--text-xs);
		color: var(--ink-muted);
		font-family: var(--font-display);
	}

	.stat-value {
		font-size: var(--text-sm);
		font-weight: 500;
		color: var(--ink-primary);
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums lining-nums;
	}

	.stat-unit {
		font-family: var(--font-body);
		font-size: 0.78em;
		color: var(--ink-muted);
		margin-left: 0.125rem;
	}

	/* Flat ledger cells: hairline separation, no nested pills */
	.stats-bottom {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-xs) var(--space-lg);
		padding-top: var(--space-sm);
		border-top: 1px solid var(--rule-hairline);
	}

	.stat-pill {
		display: flex;
		align-items: baseline;
		gap: 0.5rem;
	}

	.stat-pill .stat-label {
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}

	.stat-value.temp {
		color: var(--temp-trace);
	}

	.stat-value.rate.fermenting {
		color: var(--ink-primary);
	}

	.og-pill {
		position: relative;
	}

	.og-btn {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		background: none;
		border: none;
		padding: 0;
		cursor: pointer;
	}

	.og-btn:hover .edit-icon,
	.og-btn:focus-visible .edit-icon {
		opacity: 1;
	}

	.edit-icon {
		width: 0.75rem;
		height: 0.75rem;
		color: var(--ink-muted);
		opacity: 0.6;
		transition: opacity 0.15s ease;
	}

	.og-input {
		width: 3.5rem;
		font-size: var(--text-xs);
		font-family: var(--font-num);
		font-weight: 500;
		color: var(--ink-primary);
		background: var(--bg-surface);
		border: 1px solid var(--accent);
		border-radius: 3px;
		padding: 0.125rem 0.25rem;
		outline: none;
	}

	.stat-value.estimated {
		color: var(--ink-secondary);
		font-style: italic;
	}

	.estimated-badge,
	.prediction-badge {
		font-size: 0.625rem;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--ink-muted);
		margin-left: 0.125rem;
	}

	.stat-value.prediction {
		color: var(--ink-primary);
	}

	.stats-empty {
		padding: 1rem;
		text-align: center;
		color: var(--ink-muted);
		font-size: var(--text-xs);
	}
</style>
