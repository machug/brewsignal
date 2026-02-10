<script lang="ts">
	import type { BatchResponse, BatchProgressResponse, BatchControlStatus, ControlEvent } from '$lib/api';
	import type { TiltReading } from '$lib/stores/tilts.svelte';
	import type { TastingNote } from '$lib/types/tasting';
	import { formatTemp, getTempUnit, configState } from '$lib/stores/config.svelte';
	import BatchFermentationCard from './BatchFermentationCard.svelte';
	import BatchRecipeTargetsCard from './BatchRecipeTargetsCard.svelte';
	import BatchAlertsCard from './BatchAlertsCard.svelte';
	import BatchNotesCard from './BatchNotesCard.svelte';
	import TastingNotesList from './TastingNotesList.svelte';
	import TastingNotes from './TastingNotes.svelte';
	import FermentationChart from '../FermentationChart.svelte';

	interface Props {
		batch: BatchResponse;
		progress: BatchProgressResponse | null;
		liveReading: TiltReading | null;
		controlStatus: BatchControlStatus | null;
		controlEvents: ControlEvent[];
		hasTempControl: boolean;
		heaterLoading: boolean;
		tempControlCollapsed: boolean;
		tastingNotes: TastingNote[];
		tastingLoading: boolean;
		onOverride: (deviceType: 'heater' | 'cooler', state: 'on' | 'off' | null) => void;
		onClearOverrides: () => void;
		onTempControlToggle: () => void;
		onBatchUpdate: (updated: BatchResponse) => void;
		onTastingNotesReload: () => void;
	}

	let {
		batch,
		progress,
		liveReading,
		controlStatus,
		controlEvents,
		hasTempControl,
		heaterLoading,
		tempControlCollapsed,
		tastingNotes,
		tastingLoading,
		onOverride,
		onClearOverrides,
		onTempControlToggle,
		onBatchUpdate,
		onTastingNotesReload,
	}: Props = $props();

	let tempUnit = $derived(getTempUnit());

	function formatTempValue(value?: number | null): string {
		if (value === undefined || value === null) return '--';
		return formatTemp(value);
	}
</script>

<div class="content-grid">
	<!-- Left column -->
	<div class="stats-section">
		<!-- Fermentation Card (includes live readings) -->
		<BatchFermentationCard
			{batch}
			currentSg={liveReading?.sg ?? progress?.measured?.current_sg}
			{progress}
			{liveReading}
		/>

		<!-- Recipe Targets Card (only if recipe exists) -->
		{#if batch.recipe}
			<BatchRecipeTargetsCard recipe={batch.recipe} yeastStrain={batch.yeast_strain} />
		{/if}

		<!-- Tasting Journal - Primary activity during conditioning -->
		<div class="tasting-card">
			<h3 class="card-title">
				<span class="card-icon">🍺</span>
				Tasting Journal
				{#if tastingNotes.length > 0}
					<span class="note-count">{tastingNotes.length}</span>
				{/if}
			</h3>
			{#if tastingLoading}
				<div class="loading-state">
					<div class="spinner-small"></div>
					<span>Loading tasting notes...</span>
				</div>
			{:else if tastingNotes.length === 0}
				<div class="empty-state">
					<p class="empty-text">No tasting notes yet.</p>
					<p class="empty-subtext">Track how your beer develops during conditioning. Regular tasting notes help you learn and decide when it's ready.</p>
				</div>
			{:else}
				<TastingNotesList {tastingNotes} />
			{/if}
		</div>

		<!-- Tasting Notes CRUD Form -->
		<TastingNotes
			{batch}
			onUpdate={(updated) => {
				onBatchUpdate(updated);
				onTastingNotesReload();
			}}
		/>
	</div>

	<!-- Right column -->
	<div class="info-section">
		<!-- Active Alerts Card -->
		<BatchAlertsCard batchId={batch.id} />

		<!-- Temperature Control Card -->
		{#if hasTempControl}
			<div class="info-card temp-control-card"
				class:heater-on={controlStatus?.heater_state === 'on'}
				class:cooler-on={controlStatus?.cooler_state === 'on'}
				class:collapsed={tempControlCollapsed}>
				<button
					type="button"
					class="collapsible-header"
					onclick={onTempControlToggle}
				>
					<h3 class="info-title">Temperature Control</h3>
					<div class="collapse-indicator">
						{#if controlStatus?.heater_state === 'on'}
							<span class="status-badge heater">🔥 Heating</span>
						{:else if controlStatus?.cooler_state === 'on'}
							<span class="status-badge cooler">❄️ Cooling</span>
						{:else if tempControlCollapsed && controlStatus}
							<span class="status-badge idle">🎯 {formatTempValue(controlStatus.target_temp)}{tempUnit}</span>
						{/if}
						<svg class="chevron" class:rotated={!tempControlCollapsed} fill="none" viewBox="0 0 24 24" stroke="currentColor">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
						</svg>
					</div>
				</button>

				{#if !tempControlCollapsed}
				<!-- Device status indicators -->
				<div class="device-status-grid">
					{#if batch.heater_entity_id}
						<div class="device-status heater">
							<div class="device-icon-wrap" class:active={controlStatus?.heater_state === 'on'}>
								🔥
							</div>
							<div class="device-info">
								<span class="device-label">Heater</span>
								<span class="device-state" class:on={controlStatus?.heater_state === 'on'}>
									{controlStatus?.heater_state === 'on' ? 'ON' : 'OFF'}
								</span>
								<span class="device-entity">{batch.heater_entity_id}</span>
							</div>
						</div>
					{/if}

					{#if batch.cooler_entity_id}
						<div class="device-status cooler">
							<div class="device-icon-wrap" class:active={controlStatus?.cooler_state === 'on'}>
								❄️
							</div>
							<div class="device-info">
								<span class="device-label">Cooler</span>
								<span class="device-state" class:on={controlStatus?.cooler_state === 'on'}>
									{controlStatus?.cooler_state === 'on' ? 'ON' : 'OFF'}
								</span>
								<span class="device-entity">{batch.cooler_entity_id}</span>
							</div>
						</div>
					{/if}
				</div>

				{#if controlStatus}
					<div class="control-details">
						<div class="control-detail">
							<span class="detail-label">Target</span>
							<span class="detail-value">{formatTempValue(controlStatus.target_temp)}{tempUnit}</span>
						</div>
						<div class="control-detail">
							<span class="detail-label">Hysteresis</span>
							<span class="detail-value">±{controlStatus.hysteresis?.toFixed(1) || '--'}{tempUnit}</span>
						</div>
					</div>

					{#if controlStatus.override_active}
						<div class="override-banner">
							<span class="override-icon">⚡</span>
							<span>Override active: {controlStatus.override_state?.toUpperCase()}</span>
							<button
								type="button"
								class="override-cancel-inline"
								onclick={() => onClearOverrides()}
								disabled={heaterLoading}
							>
								Cancel
							</button>
						</div>
					{/if}

					<div class="override-controls">
						<span class="override-label">Manual Override (1hr)</span>
						<div class="override-btns-grid">
							{#if batch.heater_entity_id}
								<button
									type="button"
									class="override-btn heat-on"
									onclick={() => onOverride('heater', 'on')}
									disabled={heaterLoading}
								>
									Force Heat ON
								</button>
								<button
									type="button"
									class="override-btn heat-off"
									onclick={() => onOverride('heater', 'off')}
									disabled={heaterLoading}
								>
									Force Heat OFF
								</button>
							{/if}

							{#if batch.cooler_entity_id}
								<button
									type="button"
									class="override-btn cool-on"
									onclick={() => onOverride('cooler', 'on')}
									disabled={heaterLoading}
								>
									Force Cool ON
								</button>
								<button
									type="button"
									class="override-btn cool-off"
									onclick={() => onOverride('cooler', 'off')}
									disabled={heaterLoading}
								>
									Force Cool OFF
								</button>
							{/if}

							<button
								type="button"
								class="override-btn auto-mode"
								onclick={() => onClearOverrides()}
								disabled={heaterLoading}
							>
								Auto Mode
							</button>
						</div>
					</div>
				{/if}
				{/if}
			</div>
		{:else if batch.heater_entity_id || batch.cooler_entity_id}
			<div class="info-card">
				<h3 class="info-title">Temperature Control</h3>
				<div class="no-device">
					{#if batch.heater_entity_id}
						<span>Heater: {batch.heater_entity_id}</span>
					{/if}
					{#if batch.cooler_entity_id}
						<span>Cooler: {batch.cooler_entity_id}</span>
					{/if}
					<span class="hint">Active only during fermentation</span>
				</div>
			</div>
		{/if}

		<!-- Notes Card (only if notes exist) -->
		{#if batch.notes}
			<BatchNotesCard notes={batch.notes} />
		{/if}
	</div>
</div>

<!-- Fermentation Chart (shows historical data for all batches with a device) -->
{#if batch.device_id}
	<div class="chart-section">
		<FermentationChart
			batchId={batch.id}
			deviceColor={batch.device_id}
			originalGravity={batch.measured_og}
			{controlEvents}
		/>
	</div>
{/if}

<style>
	/* Content grid - two column layout */
	.content-grid {
		display: grid;
		grid-template-columns: 2fr 1fr;
		gap: 1rem;
		align-items: start;
	}

	@media (max-width: 900px) {
		.content-grid {
			grid-template-columns: 1fr;
		}
	}

	/* Chart section */
	.chart-section {
		margin-top: 1.5rem;
	}

	/* Stats section (left column) */
	.stats-section {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	/* Info section (right column) */
	.info-section {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.info-card {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.75rem;
		padding: 1.25rem;
	}

	.info-title {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin: 0 0 1rem 0;
	}

	.no-device {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		font-size: 0.875rem;
		color: var(--text-muted);
	}

	.hint {
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	/* Tasting Journal Card */
	.tasting-card {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.75rem;
		padding: 1.25rem;
	}

	.card-title {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin: 0 0 1rem 0;
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.card-icon { font-size: 1rem; }

	.note-count {
		font-size: 0.6875rem;
		font-weight: 600;
		padding: 0.125rem 0.5rem;
		background: var(--accent-bg, rgba(99, 102, 241, 0.1));
		color: var(--accent);
		border-radius: 1rem;
	}

	.loading-state {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.75rem;
		padding: 2rem;
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	.spinner-small {
		width: 1.25rem;
		height: 1.25rem;
		border: 2px solid var(--bg-hover);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	.empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 2rem 1rem;
		text-align: center;
	}

	.empty-text {
		font-size: 0.9375rem;
		font-weight: 500;
		color: var(--text-secondary);
		margin: 0 0 0.25rem 0;
	}

	.empty-subtext {
		font-size: 0.8125rem;
		color: var(--text-muted);
		margin: 0;
		max-width: 320px;
		line-height: 1.5;
	}

	/* Temperature Control Card */
	.temp-control-card {
		transition: all 0.3s ease;
	}

	.temp-control-card.collapsed {
		padding-bottom: 0.75rem;
	}

	.collapsible-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		width: 100%;
		background: none;
		border: none;
		cursor: pointer;
		padding: 0;
		margin-bottom: 1rem;
	}

	.temp-control-card.collapsed .collapsible-header {
		margin-bottom: 0;
	}

	.collapsible-header .info-title {
		margin: 0;
	}

	.collapse-indicator {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.status-badge {
		font-size: 0.6875rem;
		font-weight: 600;
		padding: 0.125rem 0.375rem;
		border-radius: 0.25rem;
	}

	.status-badge.heater {
		background: rgba(239, 68, 68, 0.15);
		color: var(--tilt-red);
	}

	.status-badge.cooler {
		background: rgba(59, 130, 246, 0.15);
		color: var(--tilt-blue);
	}

	.status-badge.idle {
		background: var(--bg-elevated);
		color: var(--text-secondary);
	}

	.chevron {
		width: 1rem;
		height: 1rem;
		color: var(--text-muted);
		transition: transform 0.2s ease;
	}

	.chevron.rotated {
		transform: rotate(180deg);
	}

	.temp-control-card.heater-on {
		background: rgba(239, 68, 68, 0.08);
		border-color: rgba(239, 68, 68, 0.3);
	}

	.temp-control-card.cooler-on {
		background: rgba(59, 130, 246, 0.08);
		border-color: rgba(59, 130, 246, 0.3);
	}

	.device-status-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
		gap: 0.75rem;
		margin-bottom: 1rem;
	}

	.device-status {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}

	.device-icon-wrap {
		width: 2.5rem;
		height: 2.5rem;
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: 0.5rem;
		background: var(--bg-elevated);
		font-size: 1.25rem;
		transition: all 0.3s ease;
		filter: grayscale(100%) opacity(0.5);
	}

	.device-status.heater .device-icon-wrap.active {
		background: rgba(239, 68, 68, 0.2);
		animation: pulse-glow-red 2s ease-in-out infinite;
		filter: none;
	}

	.device-status.cooler .device-icon-wrap.active {
		background: rgba(59, 130, 246, 0.2);
		animation: pulse-glow-blue 2s ease-in-out infinite;
		filter: none;
	}

	@keyframes pulse-glow-red {
		0%, 100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4); }
		50% { box-shadow: 0 0 15px 3px rgba(239, 68, 68, 0.3); }
	}

	@keyframes pulse-glow-blue {
		0%, 100% { box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.4); }
		50% { box-shadow: 0 0 15px 3px rgba(59, 130, 246, 0.3); }
	}

	.device-info {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
	}

	.device-label {
		font-size: 0.625rem;
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-muted);
	}

	.device-state {
		font-size: 1rem;
		font-weight: 700;
		font-family: 'JetBrains Mono', monospace;
		color: var(--text-secondary);
	}

	.device-status.heater .device-state.on {
		color: var(--tilt-red);
	}

	.device-status.cooler .device-state.on {
		color: var(--tilt-blue);
	}

	.device-entity {
		font-size: 0.6875rem;
		color: var(--text-muted);
		font-family: 'JetBrains Mono', monospace;
	}

	.control-details {
		display: flex;
		gap: 1.5rem;
		margin-bottom: 0.75rem;
		padding: 0.5rem 0.75rem;
		background: var(--bg-elevated);
		border-radius: 0.375rem;
	}

	.control-detail {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
	}

	.detail-label {
		font-size: 0.625rem;
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-muted);
	}

	.detail-value {
		font-size: 0.875rem;
		font-weight: 500;
		font-family: 'JetBrains Mono', monospace;
		color: var(--text-primary);
	}

	.override-banner {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-bottom: 0.75rem;
		padding: 0.5rem 0.75rem;
		background: rgba(59, 130, 246, 0.1);
		border-radius: 0.375rem;
		font-size: 0.75rem;
		color: var(--tilt-blue);
	}

	.override-icon {
		font-size: 0.875rem;
	}

	.override-cancel-inline {
		margin-left: auto;
		padding: 0.25rem 0.5rem;
		font-size: 0.6875rem;
		font-weight: 500;
		border-radius: 0.25rem;
		background: transparent;
		border: 1px solid var(--tilt-blue);
		color: var(--tilt-blue);
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.override-cancel-inline:hover:not(:disabled) {
		background: rgba(59, 130, 246, 0.15);
	}

	.override-cancel-inline:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.override-controls {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
	}

	.override-label {
		font-size: 0.625rem;
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-muted);
	}

	.override-btns-grid {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 0.375rem;
	}

	.override-btn {
		padding: 0.5rem 0.75rem;
		font-size: 0.6875rem;
		font-weight: 500;
		border-radius: 0.25rem;
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
		color: var(--text-secondary);
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.override-btn:hover:not(:disabled) {
		background: var(--bg-hover);
		color: var(--text-primary);
	}

	.override-btn.heat-on:hover:not(:disabled) {
		background: rgba(239, 68, 68, 0.1);
		border-color: var(--tilt-red);
		color: var(--tilt-red);
	}

	.override-btn.heat-off:hover:not(:disabled) {
		background: rgba(239, 68, 68, 0.05);
		border-color: rgba(239, 68, 68, 0.3);
		color: var(--text-primary);
	}

	.override-btn.cool-on:hover:not(:disabled) {
		background: rgba(59, 130, 246, 0.1);
		border-color: var(--tilt-blue);
		color: var(--tilt-blue);
	}

	.override-btn.cool-off:hover:not(:disabled) {
		background: rgba(59, 130, 246, 0.05);
		border-color: rgba(59, 130, 246, 0.3);
		color: var(--text-primary);
	}

	.override-btn.auto-mode {
		grid-column: 1 / -1;
		background: var(--accent);
		border-color: var(--accent);
		color: white;
	}

	.override-btn.auto-mode:hover:not(:disabled) {
		background: var(--accent-hover);
		border-color: var(--accent-hover);
	}

	.override-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}
</style>
