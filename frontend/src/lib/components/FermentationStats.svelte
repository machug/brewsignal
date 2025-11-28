<script lang="ts">
	import type { HistoricalReading } from '$lib/api';
	import { configState, formatTemp, getTempUnit, fahrenheitToCelsius } from '$lib/stores/config.svelte';

	interface Props {
		readings: HistoricalReading[];
		originalGravity: number | null;
		onOgChange: (og: number | null) => void;
	}

	let { readings, originalGravity, onOgChange }: Props = $props();

	// OG editing state
	let isEditingOg = $state(false);
	let ogEditValue = $state('');
	let ogInputRef = $state<HTMLInputElement | null>(null);

	// Reactive temp unit from config
	let useCelsius = $derived(configState.config.temp_units === 'C');
	let tempUnit = $derived(getTempUnit());

	// Compute stats from readings
	let stats = $derived.by(() => {
		if (readings.length === 0) {
			return null;
		}

		// Readings come newest first, so reverse for chronological order
		const sorted = [...readings].sort(
			(a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
		);

		const firstReading = sorted[0];
		const lastReading = sorted[sorted.length - 1];

		// SG values (prefer calibrated)
		const sgValues = sorted
			.map((r) => r.sg_calibrated ?? r.sg_raw)
			.filter((v): v is number => v !== null);

		// Temp values (prefer calibrated, in Fahrenheit from backend)
		const tempValues = sorted
			.map((r) => r.temp_calibrated ?? r.temp_raw)
			.filter((v): v is number => v !== null);

		if (sgValues.length === 0) {
			return null;
		}

		const currentSg = sgValues[sgValues.length - 1];
		const firstSg = sgValues[0];
		const highSg = Math.max(...sgValues);
		const lowSg = Math.min(...sgValues);

		// Duration in days
		const firstTime = new Date(firstReading.timestamp).getTime();
		const lastTime = new Date(lastReading.timestamp).getTime();
		const durationMs = lastTime - firstTime;
		const durationDays = durationMs / (1000 * 60 * 60 * 24);

		// Fermentation rate (SG drop per day)
		const fermRate = durationDays > 0 ? (currentSg - firstSg) / durationDays : 0;

		// Temp stats (convert if needed)
		let currentTemp: number | null = null;
		let avgTemp: number | null = null;
		let highTemp: number | null = null;
		let lowTemp: number | null = null;

		if (tempValues.length > 0) {
			const lastTempF = tempValues[tempValues.length - 1];
			const avgTempF = tempValues.reduce((a, b) => a + b, 0) / tempValues.length;
			const highTempF = Math.max(...tempValues);
			const lowTempF = Math.min(...tempValues);

			currentTemp = useCelsius ? fahrenheitToCelsius(lastTempF) : lastTempF;
			avgTemp = useCelsius ? fahrenheitToCelsius(avgTempF) : avgTempF;
			highTemp = useCelsius ? fahrenheitToCelsius(highTempF) : highTempF;
			lowTemp = useCelsius ? fahrenheitToCelsius(lowTempF) : lowTempF;
		}

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

		// Attenuation and ABV (require OG)
		let apparentAttenuation: number | null = null;
		let abv: number | null = null;
		const og = originalGravity;

		if (og !== null && og > 1.0) {
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
			abv
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
			onOgChange(null);
		} else {
			const parsed = parseFloat(trimmed);
			if (!isNaN(parsed) && parsed >= 0.99 && parsed <= 1.2) {
				onOgChange(parsed);
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
		return sg.toFixed(3);
	}

	function formatRate(rate: number): string {
		const sign = rate >= 0 ? '+' : '';
		return `${sign}${rate.toFixed(4)}`;
	}

	function formatDuration(days: number): string {
		if (days < 1) {
			const hours = days * 24;
			return `${hours.toFixed(1)}h`;
		}
		return `${days.toFixed(1)}d`;
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
				<h4 class="stats-header">Gravity</h4>
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
					<span class="stat-value">{formatTempStat(stats.currentTemp)}<span class="stat-unit">{tempUnit}</span></span>
				</div>
				<div class="stat-row">
					<span class="stat-label">Average</span>
					<span class="stat-value">{formatTempStat(stats.avgTemp)}<span class="stat-unit">{tempUnit}</span></span>
				</div>
				<div class="stat-row">
					<span class="stat-label">High</span>
					<span class="stat-value">{formatTempStat(stats.highTemp)}<span class="stat-unit">{tempUnit}</span></span>
				</div>
				<div class="stat-row">
					<span class="stat-label">Low</span>
					<span class="stat-value">{formatTempStat(stats.lowTemp)}<span class="stat-unit">{tempUnit}</span></span>
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
				{#if isEditingOg}
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
				{:else}
					<button type="button" class="og-btn" onclick={startEditingOg} title="Click to set Original Gravity">
						<span class="stat-value">{originalGravity ? formatSg(originalGravity) : '--'}</span>
						<svg class="edit-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
						</svg>
					</button>
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
		</div>
	</div>
{:else}
	<div class="stats-empty">
		<span>Not enough data for statistics</span>
	</div>
{/if}

<style>
	.stats-panel {
		margin-top: 1rem;
		padding: 0.75rem;
		background: var(--bg-surface);
		border-radius: 0.5rem;
		border: 1px solid var(--border-subtle);
	}

	.stats-grid {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 1rem;
		margin-bottom: 0.75rem;
	}

	.stats-column {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.stats-header {
		font-size: 0.6875rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-muted);
		margin-bottom: 0.25rem;
		font-family: 'JetBrains Mono', monospace;
	}

	.stat-row {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		padding: 0.125rem 0;
	}

	.stat-label {
		font-size: 0.6875rem;
		color: var(--text-muted);
		font-family: 'JetBrains Mono', monospace;
	}

	.stat-value {
		font-size: 0.8125rem;
		font-weight: 500;
		color: var(--text-primary);
		font-family: 'JetBrains Mono', monospace;
	}

	.stat-unit {
		font-size: 0.6875rem;
		color: var(--text-secondary);
		margin-left: 0.125rem;
	}

	.stats-bottom {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		padding-top: 0.75rem;
		border-top: 1px solid var(--border-subtle);
	}

	.stat-pill {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		padding: 0.25rem 0.5rem;
		background: var(--bg-elevated);
		border-radius: 0.375rem;
		border: 1px solid var(--border-subtle);
	}

	.stat-pill .stat-label {
		font-size: 0.625rem;
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}

	.stat-pill .stat-value {
		font-size: 0.75rem;
	}

	.stat-value.rate.fermenting {
		color: var(--positive);
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

	.og-btn:hover .edit-icon {
		opacity: 1;
	}

	.edit-icon {
		width: 0.75rem;
		height: 0.75rem;
		color: var(--text-muted);
		opacity: 0;
		transition: opacity 0.15s ease;
	}

	.og-input {
		width: 3.5rem;
		font-size: 0.75rem;
		font-family: 'JetBrains Mono', monospace;
		font-weight: 500;
		color: var(--text-primary);
		background: var(--bg-surface);
		border: 1px solid var(--accent);
		border-radius: 0.25rem;
		padding: 0.125rem 0.25rem;
		outline: none;
	}

	.stats-empty {
		padding: 1rem;
		text-align: center;
		color: var(--text-muted);
		font-size: 0.75rem;
	}
</style>
