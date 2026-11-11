<script lang="ts">
	import type { BatchResponse } from '$lib/api';
	import type { TiltReading } from '$lib/stores/tilts.svelte';
	import { formatTemp, getTempUnit, configState } from '$lib/stores/config.svelte';
	import BrewDayTimer from './BrewDayTimer.svelte';
	import BrewDayChecklist from './BrewDayChecklist.svelte';
	import BrewDayObservations from './BrewDayObservations.svelte';
	import BatchDeviceCard from './BatchDeviceCard.svelte';
	import BatchRecipeTargetsCard from './BatchRecipeTargetsCard.svelte';
	import BrewDayWaterCard from './BrewDayWaterCard.svelte';

	interface Props {
		batch: BatchResponse;
		liveReading: TiltReading | null;
		statusUpdating: boolean;
		onStartFermentation: () => void;
		onEdit: () => void;
		onBatchUpdate: (updated: BatchResponse) => void;
	}

	let { batch, liveReading, statusUpdating, onStartFermentation, onEdit, onBatchUpdate }: Props = $props();

	let tempUnit = $derived(getTempUnit());

	let isPrePitchChilling = $derived(
		(batch.status === 'planning' || batch.status === 'brewing') && batch.temp_target != null
	);

	let pitchTempReached = $derived.by(() => {
		if (!isPrePitchChilling || !liveReading?.temp || !batch.temp_target) return false;
		return liveReading.temp <= batch.temp_target;
	});

	let chillingProgress = $derived.by(() => {
		if (!isPrePitchChilling || !liveReading?.temp || !batch.temp_target) return null;
		const estimatedStartTemp = batch.temp_target + 30;
		const currentTemp = liveReading.temp;
		const targetTemp = batch.temp_target;

		if (currentTemp <= targetTemp) return 100;
		if (currentTemp >= estimatedStartTemp) return 0;

		const progress = ((estimatedStartTemp - currentTemp) / (estimatedStartTemp - targetTemp)) * 100;
		return Math.min(100, Math.max(0, progress));
	});

	function formatTempValue(value?: number | null): string {
		if (value === undefined || value === null) return '--';
		return formatTemp(value);
	}
</script>

<div class="brewing-phase">
	{#if batch.status !== 'brewing' && batch.status !== 'planning'}
		<!-- Historical: Brew day already completed -->
		<div class="phase-action-card completed-brewday">
			<h2 class="phase-title">Brew Day Complete</h2>
			{#if batch.brewing_started_at || batch.brew_date}
				<p class="phase-description">
					Brewed on {new Date(batch.brewing_started_at || batch.brew_date || '').toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })}
				</p>
			{/if}
		</div>
	{:else if isPrePitchChilling && !pitchTempReached}
		<!-- Chilling in progress -->
		<div class="phase-action-card chilling">
			<h2 class="phase-title">Chilling to Pitch Temperature</h2>
			<p class="phase-description">
				Wort is being cooled to pitch temperature. The cooler will run automatically.
				Once target is reached, you can pitch the yeast.
			</p>
			<div class="chilling-temp-display">
				<div class="temp-current">
					<span class="temp-label">Current</span>
					<span class="temp-value">{liveReading?.temp != null ? formatTempValue(liveReading.temp) : '--'}<span class="unit">&thinsp;{tempUnit}</span></span>
				</div>
				<div class="temp-arrow" aria-hidden="true">&rarr;</div>
				<div class="temp-target">
					<span class="temp-label">Target</span>
					<span class="temp-value">{batch.temp_target != null ? formatTempValue(batch.temp_target) : '--'}<span class="unit">&thinsp;{tempUnit}</span></span>
				</div>
			</div>
			{#if chillingProgress != null}
				<div class="chilling-progress">
					<div class="progress-bar" role="progressbar" aria-valuenow={Math.round(chillingProgress)} aria-valuemin="0" aria-valuemax="100" aria-label="Progress to pitch temperature">
						<div class="progress-fill" style="width: {chillingProgress}%"></div>
					</div>
					<span class="progress-text">{Math.round(chillingProgress)}% to pitch temp</span>
				</div>
			{/if}
			<div class="chilling-status">
				{#if !batch.cooler_entity_id}
					<span class="status-warning">No cooler configured - set in Edit to enable automated chilling</span>
				{:else if !configState.config.ha_enabled || !configState.config.temp_control_enabled}
					<span class="status-warning">Temperature control disabled in settings</span>
				{:else}
					<span class="status-active">Cooler running automatically</span>
				{/if}
			</div>
		</div>
	{:else if isPrePitchChilling && pitchTempReached}
		<!-- Ready to pitch -->
		<div class="phase-action-card ready-to-pitch">
			<h2 class="phase-title">Ready to Pitch!</h2>
			<p class="phase-description">
				Wort has reached pitch temperature ({formatTempValue(batch.temp_target)}&thinsp;{tempUnit}).
				Pitch the yeast and start fermentation.
			</p>
			<button
				type="button"
				class="start-fermentation-btn"
				onclick={onStartFermentation}
				disabled={statusUpdating}
			>
				{#if statusUpdating}
					<span class="btn-spinner" aria-hidden="true"></span>
					Starting...
				{:else}
					<svg class="btn-icon" aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
					</svg>
					Yeast Pitched - Start Fermentation
				{/if}
			</button>
		</div>
	{:else}
		<!-- Normal brewing mode (no device/target set) -->
		<div class="phase-action-card brewing">
			<h2 class="phase-title">Brew Day in Progress</h2>
			<p class="phase-description">
				Track your brew day activities. When you've pitched the yeast and fermentation begins, transition to the fermentation phase.
			</p>
			<button
				type="button"
				class="start-fermentation-btn"
				onclick={onStartFermentation}
				disabled={statusUpdating}
			>
				{#if statusUpdating}
					<span class="btn-spinner" aria-hidden="true"></span>
					Starting...
				{:else}
					<svg class="btn-icon" aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
					</svg>
					Yeast Pitched - Start Fermentation
				{/if}
			</button>
		</div>
	{/if}

	<!-- Brew Day Tools Grid -->
	<div class="brewday-tools-grid">
		<!-- Timer -->
		{#if batch.recipe}
			<BrewDayTimer {batch} recipe={batch.recipe} />
		{/if}

		<!-- Checklist -->
		{#if batch.recipe}
			<BrewDayChecklist recipe={batch.recipe} batchId={batch.id} />
		{/if}
	</div>

	<!-- Observations Log -->
	{#if batch.recipe}
		<BrewDayObservations
			{batch}
			recipe={batch.recipe}
			onUpdate={(updated) => onBatchUpdate(updated)}
		/>
	{/if}

	<!-- Device Card for chilling monitoring -->
	{#if batch.device_id}
		<BatchDeviceCard
			{batch}
			{liveReading}
			onEdit={() => onEdit()}
		/>
	{/if}

	{#if batch.recipe}
		<div class="brewday-ref-grid">
			<BatchRecipeTargetsCard recipe={batch.recipe} yeastStrain={batch.yeast_strain} />
			<BrewDayWaterCard recipe={batch.recipe} />
		</div>
	{/if}
</div>

<style>
	.brewing-phase {
		display: flex;
		flex-direction: column;
		gap: var(--space-lg);
	}

	/* Phase header: hairline section, status carried by a pill-like top rule */
	.phase-action-card {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: var(--space-xs);
		padding: var(--space-lg) 0;
		border-top: 1px solid var(--rule-strong);
		border-bottom: 1px solid var(--rule-hairline);
	}
	.phase-action-card.ready-to-pitch {
		border-top-color: var(--accent-rule);
	}
	.phase-action-card.chilling {
		border-top-color: color-mix(in oklch, var(--temp-trace) 55%, transparent);
	}
	.phase-title {
		font-family: var(--font-display);
		font-size: var(--text-lg);
		font-weight: 700;
		letter-spacing: -0.01em;
		color: var(--ink-primary);
	}
	.phase-description {
		font-size: var(--text-base);
		color: var(--ink-secondary);
		max-width: 56ch;
		line-height: 1.5;
	}

	.chilling-temp-display {
		display: flex;
		align-items: center;
		gap: var(--space-lg);
		margin: var(--space-xs) 0;
	}
	.chilling-temp-display .temp-current,
	.chilling-temp-display .temp-target {
		display: flex;
		flex-direction: column;
		gap: var(--space-2xs);
	}
	.chilling-temp-display .temp-label {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-muted);
		text-transform: uppercase;
		letter-spacing: 0.07em;
	}
	.chilling-temp-display .temp-value {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums lining-nums;
		font-size: var(--text-inst);
		font-weight: 600;
		line-height: 1.05;
		color: var(--ink-primary);
	}
	.chilling-temp-display .temp-target .temp-value {
		color: var(--temp-trace);
	}
	.unit {
		font-family: var(--font-body);
		font-size: 0.78em;
		font-weight: 400;
		color: var(--ink-muted);
	}
	.chilling-temp-display .temp-arrow {
		font-size: var(--text-lg);
		color: var(--ink-muted);
	}
	.chilling-progress {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
		width: 100%;
		max-width: 20rem;
	}
	.chilling-progress .progress-bar {
		width: 100%;
		height: 4px;
		background: var(--rule-hairline);
	}
	.chilling-progress .progress-fill {
		height: 100%;
		background: var(--temp-trace);
		transition: width 500ms var(--ease-out-quart);
	}
	.chilling-progress .progress-text {
		font-family: var(--font-num);
		font-size: var(--text-xs);
		color: var(--ink-secondary);
	}
	.phase-action-card .chilling-status {
		font-size: var(--text-sm);
	}
	.phase-action-card .status-warning {
		color: var(--status-warn);
	}
	.phase-action-card .status-active {
		color: var(--temp-trace);
	}

	.brewday-tools-grid,
	.brewday-ref-grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: var(--space-lg);
	}
	@media (max-width: 900px) {
		.brewday-tools-grid,
		.brewday-ref-grid {
			grid-template-columns: minmax(0, 1fr);
		}
	}

	.start-fermentation-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: var(--space-xs);
		min-height: 48px;
		padding: 0 var(--space-lg);
		margin-top: var(--space-xs);
		font-family: var(--font-display);
		font-size: var(--text-base);
		font-weight: 600;
		border-radius: 4px;
		cursor: pointer;
		color: var(--accent-ink);
		background: var(--accent);
		transition: background-color 140ms var(--ease-out-quart);
	}
	.start-fermentation-btn:hover:not(:disabled) {
		background: var(--accent-hover);
	}
	.start-fermentation-btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}
	.btn-spinner {
		width: 1rem;
		height: 1rem;
		border: 2px solid color-mix(in oklch, var(--accent-ink) 30%, transparent);
		border-top-color: var(--accent-ink);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}
	.btn-icon {
		width: 1rem;
		height: 1rem;
	}
	@keyframes spin {
		to { transform: rotate(360deg); }
	}
	@media (prefers-reduced-motion: reduce) {
		.btn-spinner {
			animation: none;
		}
	}
</style>
