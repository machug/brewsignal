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
	import BJCPScoreForm from './BJCPScoreForm.svelte';
	import TastingPanel from './TastingPanel.svelte';
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
	let showBJCPForm = $state(false);
	let showTastingPanel = $state(false);

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
				Tasting Journal
				{#if tastingNotes.length > 0}
					<span class="note-count num">{tastingNotes.length}</span>
				{/if}
			</h3>
			{#if tastingLoading}
				<div class="loading-state">
					<div class="spinner-small"></div>
					<span>Loading tasting notes...</span>
				</div>
			{:else}
				{#if !showBJCPForm && !showTastingPanel}
					<div class="tasting-actions">
						{#if configState.config.ai_enabled}
							<button type="button" class="guided-tasting-btn" onclick={() => showTastingPanel = true}>
								<svg fill="none" viewBox="0 0 24 24" stroke="currentColor" width="18" height="18">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
								</svg>
								Start Guided Tasting
							</button>
						{/if}
						<button type="button" class="manual-tasting-btn" onclick={() => showBJCPForm = true}>
							<svg fill="none" viewBox="0 0 24 24" stroke="currentColor" width="16" height="16">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
							</svg>
							{configState.config.ai_enabled ? 'Manual Scoresheet' : 'Add Tasting Note'}
						</button>
					</div>
				{/if}

				{#if showBJCPForm}
					<BJCPScoreForm
						{batch}
						onSave={() => { showBJCPForm = false; onTastingNotesReload(); }}
						onCancel={() => showBJCPForm = false}
					/>
				{/if}

				{#if tastingNotes.length === 0}
					<div class="empty-state">
						<p class="empty-text">No tasting notes yet.</p>
						<p class="empty-subtext">Track how your beer develops during conditioning. Regular tasting notes help you learn and decide when it's ready.</p>
					</div>
				{:else}
					<TastingNotesList {tastingNotes} />
				{/if}
			{/if}
		</div>
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
							<span class="status-badge heater">Heating</span>
						{:else if controlStatus?.cooler_state === 'on'}
							<span class="status-badge cooler">Cooling</span>
						{:else if tempControlCollapsed && controlStatus}
							<span class="status-badge idle"><span class="num">Target {formatTempValue(controlStatus.target_temp)}&thinsp;{tempUnit}</span></span>
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
								<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3c1 3.5 5 5.5 5 10a5 5 0 0 1-10 0c0-2 1-3 2-4 0 2 1 3 2 3 0-3-1-6 1-9z"/></svg>
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
								<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" aria-hidden="true"><path d="M12 3v18M4.2 7.5l15.6 9M19.8 7.5l-15.6 9"/></svg>
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
							<span class="detail-value">{formatTempValue(controlStatus.target_temp)}&thinsp;{tempUnit}</span>
						</div>
						<div class="control-detail">
							<span class="detail-label">Hysteresis</span>
							<span class="detail-value">±{controlStatus.hysteresis?.toFixed(1) || '--'}&thinsp;{tempUnit}</span>
						</div>
					</div>

					{#if controlStatus.override_active}
						<div class="override-banner">
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

{#if showTastingPanel}
	<TastingPanel
		{batch}
		onClose={() => showTastingPanel = false}
		onSaved={() => { showTastingPanel = false; onTastingNotesReload(); }}
	/>
{/if}

<style>
	.content-grid {
		display: grid;
		grid-template-columns: 2fr 1fr;
		gap: var(--space-md);
		align-items: start;
	}

	@media (max-width: 900px) {
		.content-grid {
			grid-template-columns: 1fr;
		}
	}

	.chart-section {
		margin-top: var(--space-lg);
	}

	.stats-section,
	.info-section {
		display: flex;
		flex-direction: column;
		gap: var(--space-sm);
	}

	.num {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums lining-nums;
	}

	.info-card,
	.tasting-card {
		border-top: 1px solid var(--rule-strong);
		padding: var(--space-md) 0;
	}

	.info-title,
	.card-title {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-muted);
		text-transform: uppercase;
		letter-spacing: 0.08em;
		margin: 0 0 var(--space-md) 0;
	}

	.card-title {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
	}

	.no-device {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}

	.hint {
		font-size: var(--text-xs);
		color: var(--ink-muted);
	}

	.note-count {
		font-size: 0.6875rem;
		font-weight: 600;
		padding: 1px 7px;
		border: 1px solid var(--rule-strong);
		border-radius: 2px;
		color: var(--ink-secondary);
	}

	.loading-state {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: var(--space-sm);
		padding: var(--space-xl);
		color: var(--ink-muted);
		font-size: var(--text-sm);
	}

	.spinner-small {
		width: 1.25rem;
		height: 1.25rem;
		border: 2px solid var(--rule-hairline);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	.empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: var(--space-xl) var(--space-md);
		text-align: center;
	}

	.empty-text {
		font-size: var(--text-base);
		font-weight: 700;
		color: var(--ink-secondary);
		margin: 0 0 var(--space-2xs) 0;
	}

	.empty-subtext {
		font-size: var(--text-sm);
		color: var(--ink-muted);
		margin: 0;
		max-width: 320px;
		line-height: 1.5;
	}

	/* Temperature control */
	.temp-control-card.collapsed {
		padding-bottom: var(--space-sm);
	}

	.collapsible-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		width: 100%;
		min-height: 44px;
		background: none;
		border: none;
		cursor: pointer;
		padding: 0;
		margin-bottom: var(--space-sm);
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
		gap: var(--space-xs);
	}

	.status-badge {
		font-family: var(--font-display);
		font-size: 0.6875rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		padding: 2px 7px;
		border-radius: 2px;
		border: 1px solid var(--rule-strong);
		color: var(--ink-secondary);
	}

	.status-badge.heater {
		border-color: var(--status-warn);
		color: var(--status-warn);
	}

	.status-badge.cooler {
		border-color: var(--temp-trace);
		color: var(--temp-trace);
	}

	.chevron {
		width: 1rem;
		height: 1rem;
		color: var(--ink-muted);
		transition: transform 0.2s var(--ease-out-quart);
	}

	.chevron.rotated {
		transform: rotate(180deg);
	}

	.temp-control-card.heater-on {
		border-color: var(--status-warn);
	}

	.temp-control-card.cooler-on {
		border-color: var(--temp-trace);
	}

	.device-status-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
		gap: var(--space-sm);
		margin-bottom: var(--space-md);
	}

	.device-status {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
	}

	.device-icon-wrap {
		width: 2.5rem;
		height: 2.5rem;
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: 4px;
		border: 1px solid var(--rule-hairline);
		background: var(--bg-elevated);
		color: var(--ink-muted);
	}

	.device-status.heater .device-icon-wrap.active {
		border-color: var(--status-warn);
		color: var(--status-warn);
	}

	.device-status.cooler .device-icon-wrap.active {
		border-color: var(--temp-trace);
		color: var(--temp-trace);
	}

	.device-info {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.device-label,
	.detail-label,
	.override-label {
		font-family: var(--font-display);
		font-size: 0.6875rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--ink-muted);
	}

	.device-state {
		font-size: var(--text-base);
		font-weight: 600;
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		color: var(--ink-secondary);
	}

	.device-status.heater .device-state.on {
		color: var(--status-warn);
	}

	.device-status.cooler .device-state.on {
		color: var(--temp-trace);
	}

	.device-entity {
		font-size: 0.6875rem;
		color: var(--ink-muted);
		font-family: var(--font-num);
	}

	.control-details {
		display: grid;
		grid-template-columns: 1fr 1fr;
		margin-bottom: var(--space-sm);
		border-top: 1px solid var(--rule-hairline);
		border-bottom: 1px solid var(--rule-hairline);
	}

	.control-detail {
		display: flex;
		flex-direction: column;
		gap: 2px;
		padding: var(--space-xs) var(--space-sm);
	}

	.control-detail + .control-detail {
		border-left: 1px solid var(--rule-hairline);
	}

	.detail-value {
		font-size: var(--text-sm);
		font-weight: 600;
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		color: var(--ink-primary);
	}

	.override-banner {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
		margin-bottom: var(--space-sm);
		padding: var(--space-xs) var(--space-sm);
		border: 1px solid var(--temp-trace);
		border-radius: 4px;
		font-size: var(--text-xs);
		color: var(--temp-trace);
	}

	.override-cancel-inline {
		margin-left: auto;
		min-height: 44px;
		padding: 0 var(--space-sm);
		font-size: var(--text-xs);
		font-weight: 600;
		border-radius: 4px;
		background: transparent;
		border: 1px solid var(--temp-trace);
		color: var(--temp-trace);
		cursor: pointer;
	}

	.override-cancel-inline:hover:not(:disabled) {
		background: var(--bg-subtle);
	}

	.override-cancel-inline:disabled,
	.override-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.override-controls {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
	}

	.override-btns-grid {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: var(--space-xs);
	}

	.override-btn {
		min-height: 44px;
		padding: 0 var(--space-sm);
		font-size: var(--text-xs);
		font-weight: 600;
		border-radius: 4px;
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		color: var(--ink-secondary);
		cursor: pointer;
		transition: background-color 140ms var(--ease-out-quart);
	}

	.override-btn:hover:not(:disabled) {
		background: var(--bg-subtle);
		color: var(--ink-primary);
	}

	.override-btn.heat-on:hover:not(:disabled),
	.override-btn.heat-off:hover:not(:disabled) {
		border-color: var(--status-warn);
	}

	.override-btn.cool-on:hover:not(:disabled),
	.override-btn.cool-off:hover:not(:disabled) {
		border-color: var(--temp-trace);
	}

	.override-btn.auto-mode {
		grid-column: 1 / -1;
		background: var(--accent-tint);
		border-color: var(--accent-rule);
		color: var(--accent);
	}

	.override-btn.auto-mode:hover:not(:disabled) {
		background: var(--accent-tint);
		border-color: var(--accent);
		color: var(--accent-hover);
	}

	button:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	.tasting-actions {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: flex-start;
		gap: var(--space-xs);
		margin-bottom: var(--space-md);
	}

	.guided-tasting-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: var(--space-xs);
		width: auto;
		min-height: 44px;
		padding: 0 var(--space-md);
		background: var(--accent-tint);
		color: var(--accent);
		border: 1px solid var(--accent-rule);
		border-radius: 4px;
		font-size: var(--text-sm);
		font-weight: 700;
		cursor: pointer;
	}

	.guided-tasting-btn:hover { border-color: var(--accent); }

	.manual-tasting-btn {
		display: inline-flex;
		width: auto;
		align-items: center;
		justify-content: center;
		gap: var(--space-xs);
		min-height: 44px;
		padding: 0 var(--space-md);
		background: var(--bg-surface);
		color: var(--ink-primary);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		font-size: var(--text-sm);
		font-weight: 600;
		cursor: pointer;
	}

	.manual-tasting-btn:hover {
		background: var(--bg-subtle);
		color: var(--ink-primary);
	}
</style>
