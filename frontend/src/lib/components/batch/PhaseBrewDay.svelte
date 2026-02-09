<script lang="ts">
	import type { BatchResponse } from '$lib/api';
	import type { TiltReading } from '$lib/stores/tilts.svelte';
	import { formatTemp, getTempUnit, configState } from '$lib/stores/config.svelte';
	import BrewDayTimer from './BrewDayTimer.svelte';
	import BrewDayChecklist from './BrewDayChecklist.svelte';
	import BrewDayObservations from './BrewDayObservations.svelte';
	import BatchDeviceCard from './BatchDeviceCard.svelte';
	import BatchRecipeTargetsCard from './BatchRecipeTargetsCard.svelte';

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
			<div class="phase-icon">✅</div>
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
			<div class="phase-icon">❄️</div>
			<h2 class="phase-title">Chilling to Pitch Temperature</h2>
			<p class="phase-description">
				Wort is being cooled to pitch temperature. The cooler will run automatically.
				Once target is reached, you can pitch the yeast.
			</p>
			<div class="chilling-temp-display">
				<div class="temp-current">
					<span class="temp-label">Current</span>
					<span class="temp-value">{liveReading?.temp != null ? formatTempValue(liveReading.temp) : '--'}</span>
				</div>
				<div class="temp-arrow">→</div>
				<div class="temp-target">
					<span class="temp-label">Target</span>
					<span class="temp-value">{batch.temp_target != null ? formatTempValue(batch.temp_target) : '--'}</span>
				</div>
			</div>
			{#if chillingProgress != null}
				<div class="chilling-progress">
					<div class="progress-bar">
						<div class="progress-fill" style="width: {chillingProgress}%"></div>
					</div>
					<span class="progress-text">{Math.round(chillingProgress)}% to pitch temp</span>
				</div>
			{/if}
			<div class="chilling-status">
				{#if !batch.cooler_entity_id}
					<span class="status-warning">⚠️ No cooler configured - set in Edit to enable automated chilling</span>
				{:else if !configState.config.ha_enabled || !configState.config.temp_control_enabled}
					<span class="status-warning">⚠️ Temperature control disabled in settings</span>
				{:else}
					<span class="status-active">Cooler running automatically</span>
				{/if}
			</div>
		</div>
	{:else if isPrePitchChilling && pitchTempReached}
		<!-- Ready to pitch -->
		<div class="phase-action-card ready-to-pitch">
			<div class="phase-icon">🍺</div>
			<h2 class="phase-title">Ready to Pitch!</h2>
			<p class="phase-description">
				Wort has reached pitch temperature ({formatTempValue(batch.temp_target)}{tempUnit}).
				Pitch the yeast and start fermentation.
			</p>
			<button
				type="button"
				class="start-fermentation-btn"
				onclick={onStartFermentation}
				disabled={statusUpdating}
			>
				{#if statusUpdating}
					<span class="btn-spinner"></span>
					Starting...
				{:else}
					<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
					</svg>
					Yeast Pitched - Start Fermentation
				{/if}
			</button>
		</div>
	{:else}
		<!-- Normal brewing mode (no device/target set) -->
		<div class="phase-action-card brewing">
			<div class="phase-icon">🍺</div>
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
					<span class="btn-spinner"></span>
					Starting...
				{:else}
					<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
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
		<BatchRecipeTargetsCard recipe={batch.recipe} yeastStrain={batch.yeast_strain} />
	{/if}
</div>

<style>
	.brewing-phase {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	/* Phase Action Card */
	.phase-action-card {
		background: linear-gradient(135deg, var(--bg-surface) 0%, var(--bg-elevated) 100%);
		border: 1px solid var(--border-subtle);
		border-radius: 1rem;
		padding: 2rem;
		text-align: center;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 1rem;
	}

	.phase-action-card.completed-brewday {
		background: linear-gradient(135deg, rgba(34, 197, 94, 0.08) 0%, rgba(74, 222, 128, 0.03) 100%);
		border-color: rgba(34, 197, 94, 0.25);
	}

	.phase-action-card.brewing {
		background: linear-gradient(135deg, rgba(249, 115, 22, 0.08) 0%, rgba(251, 146, 60, 0.03) 100%);
		border-color: rgba(249, 115, 22, 0.25);
	}

	.phase-action-card.chilling {
		background: linear-gradient(135deg, rgba(59, 130, 246, 0.1) 0%, rgba(147, 197, 253, 0.05) 100%);
		border-color: rgba(59, 130, 246, 0.3);
	}

	.phase-action-card.ready-to-pitch {
		background: linear-gradient(135deg, rgba(34, 197, 94, 0.12) 0%, rgba(134, 239, 172, 0.05) 100%);
		border-color: rgba(34, 197, 94, 0.35);
	}

	.chilling-temp-display {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 1.5rem;
		margin: 0.5rem 0;
	}

	.chilling-temp-display .temp-current,
	.chilling-temp-display .temp-target {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.25rem;
	}

	.chilling-temp-display .temp-label {
		font-size: 0.6875rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.chilling-temp-display .temp-value {
		font-size: 1.75rem;
		font-weight: 600;
		color: var(--text-primary);
		font-variant-numeric: tabular-nums;
	}

	.chilling-temp-display .temp-arrow {
		font-size: 1.5rem;
		color: var(--text-muted);
	}

	.chilling-progress {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.5rem;
		width: 100%;
		max-width: 300px;
	}

	.chilling-progress .progress-bar {
		width: 100%;
		height: 8px;
		background: var(--bg-elevated);
		border-radius: 4px;
		overflow: hidden;
	}

	.chilling-progress .progress-fill {
		height: 100%;
		background: linear-gradient(90deg, var(--tilt-blue), var(--accent));
		border-radius: 4px;
		transition: width 0.5s ease;
	}

	.chilling-progress .progress-text {
		font-size: 0.8125rem;
		color: var(--text-secondary);
	}

	.phase-action-card .chilling-status {
		margin-top: 0.5rem;
		font-size: 0.8125rem;
	}

	.phase-action-card .status-warning {
		color: var(--recipe-accent);
	}

	.phase-action-card .status-active {
		color: var(--tilt-blue);
	}

	/* Brew Day Tools Grid */
	.brewday-tools-grid {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 1rem;
	}

	@media (max-width: 900px) {
		.brewday-tools-grid {
			grid-template-columns: 1fr;
		}
	}

	.phase-icon {
		font-size: 3rem;
		line-height: 1;
	}

	.phase-title {
		font-size: 1.5rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
	}

	.phase-description {
		font-size: 0.9375rem;
		color: var(--text-secondary);
		max-width: 400px;
		line-height: 1.5;
		margin: 0;
	}

	.start-fermentation-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		padding: 0.875rem 1.5rem;
		font-size: 1rem;
		font-weight: 600;
		border-radius: 0.5rem;
		cursor: pointer;
		transition: all var(--transition);
		margin-top: 0.5rem;
		color: white;
		background: linear-gradient(135deg, var(--status-fermenting) 0%, var(--recipe-accent) 100%);
		border: none;
	}

	.start-fermentation-btn:hover:not(:disabled) {
		filter: brightness(1.1);
		transform: translateY(-1px);
	}

	.start-fermentation-btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
		transform: none;
	}

	.btn-spinner {
		width: 1rem;
		height: 1rem;
		border: 2px solid rgba(255, 255, 255, 0.3);
		border-top-color: white;
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
</style>
