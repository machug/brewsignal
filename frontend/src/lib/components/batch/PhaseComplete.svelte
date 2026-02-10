<script lang="ts">
	import type { BatchResponse } from '$lib/api';
	import type { BatchReflection } from '$lib/types/reflection';
	import type { TastingNote } from '$lib/types/tasting';
	import { formatGravity, configState } from '$lib/stores/config.svelte';
	import PackagingInfo from './PackagingInfo.svelte';
	import TastingNotesList from './TastingNotesList.svelte';
	import BJCPScoreForm from './BJCPScoreForm.svelte';
	import TastingPanel from './TastingPanel.svelte';
	import ReflectionCard from './ReflectionCard.svelte';
	import BatchNotesCard from './BatchNotesCard.svelte';

	interface Props {
		batch: BatchResponse;
		reflections: BatchReflection[];
		tastingNotes: TastingNote[];
		reflectionsLoading: boolean;
		tastingLoading: boolean;
		onBatchUpdate: (updated: BatchResponse) => void;
		onTastingNotesReload: () => void;
	}

	let {
		batch,
		reflections,
		tastingNotes,
		reflectionsLoading,
		tastingLoading,
		onBatchUpdate,
		onTastingNotesReload,
	}: Props = $props();

	let reflectionsExpanded = $state(true);
	let tastingExpanded = $state(true);
	let showBJCPForm = $state(false);
	let showTastingPanel = $state(false);

	function formatSG(value?: number | null): string {
		if (value === undefined || value === null) return '--';
		return formatGravity(value);
	}

	function formatDate(dateStr?: string | null): string {
		if (!dateStr) return '--';
		return new Date(dateStr).toLocaleDateString('en-GB', {
			weekday: 'short',
			day: 'numeric',
			month: 'short',
			year: 'numeric'
		});
	}
</script>

<div class="completed-phase">
	<div class="batch-summary-card">
		<h2 class="summary-title">Batch Complete</h2>
		<div class="summary-stats">
			<div class="summary-stat">
				<span class="stat-label">Original Gravity</span>
				<span class="stat-value">{formatSG(batch.measured_og)}</span>
			</div>
			<div class="summary-stat">
				<span class="stat-label">Final Gravity</span>
				<span class="stat-value">{formatSG(batch.measured_fg)}</span>
			</div>
			<div class="summary-stat">
				<span class="stat-label">ABV</span>
				<span class="stat-value">{batch.measured_abv?.toFixed(1) ?? '--'}%</span>
			</div>
			<div class="summary-stat">
				<span class="stat-label">Attenuation</span>
				<span class="stat-value">
					{#if batch.measured_og && batch.measured_fg}
						{(((batch.measured_og - batch.measured_fg) / (batch.measured_og - 1)) * 100).toFixed(0)}%
					{:else}
						--
					{/if}
				</span>
			</div>
		</div>
	</div>

	<!-- Batch Timeline -->
	<div class="timeline-card">
		<h3 class="timeline-title">Batch Timeline</h3>
		<div class="timeline">
			{#if batch.brew_date || batch.brewing_started_at}
				<div class="timeline-item">
					<div class="timeline-dot brewing"></div>
					<div class="timeline-content">
						<span class="timeline-label">Brew Day</span>
						<span class="timeline-date">{formatDate(batch.brewing_started_at || batch.brew_date)}</span>
					</div>
				</div>
			{/if}
			{#if batch.start_time || batch.fermenting_started_at}
				<div class="timeline-item">
					<div class="timeline-dot fermenting"></div>
					<div class="timeline-content">
						<span class="timeline-label">Fermentation Started</span>
						<span class="timeline-date">{formatDate(batch.fermenting_started_at || batch.start_time)}</span>
					</div>
				</div>
			{/if}
			{#if batch.conditioning_started_at}
				<div class="timeline-item">
					<div class="timeline-dot conditioning"></div>
					<div class="timeline-content">
						<span class="timeline-label">Conditioning Started</span>
						<span class="timeline-date">{formatDate(batch.conditioning_started_at)}</span>
					</div>
				</div>
			{/if}
			{#if batch.end_time || batch.completed_at}
				<div class="timeline-item">
					<div class="timeline-dot completed"></div>
					<div class="timeline-content">
						<span class="timeline-label">Completed</span>
						<span class="timeline-date">{formatDate(batch.completed_at || batch.end_time)}</span>
					</div>
				</div>
			{/if}
			{#if batch.packaged_at}
				<div class="timeline-item">
					<div class="timeline-dot packaged"></div>
					<div class="timeline-content">
						<span class="timeline-label">Packaged ({batch.packaging_type || 'kegged'})</span>
						<span class="timeline-date">{formatDate(batch.packaged_at)}</span>
					</div>
				</div>
			{/if}
		</div>
	</div>

	<!-- Packaging Info -->
	<PackagingInfo
		{batch}
		onUpdate={(updated) => onBatchUpdate(updated)}
	/>

	<!-- Reflections & Learnings Section -->
	<div class="postmortem-section">
		<button
			type="button"
			class="section-header"
			onclick={() => reflectionsExpanded = !reflectionsExpanded}
		>
			<div class="section-header-left">
				<span class="section-icon">💭</span>
				<h3 class="section-title">Reflections & Learnings</h3>
				{#if reflections.length > 0}
					<span class="section-count">{reflections.length}</span>
				{/if}
			</div>
			<svg class="section-chevron" class:expanded={reflectionsExpanded} fill="none" viewBox="0 0 24 24" stroke="currentColor">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
			</svg>
		</button>

		{#if reflectionsExpanded}
			<div class="section-content">
				{#if reflectionsLoading}
					<div class="section-loading">
						<div class="spinner-small"></div>
						<span>Loading reflections...</span>
					</div>
				{:else if reflections.length === 0}
					<div class="section-empty">
						<p class="empty-text">No reflections recorded yet.</p>
						<p class="empty-subtext">Reflections help you learn from each brew. Record what went well, what could improve, and lessons for next time.</p>
						<button type="button" class="add-first-btn">
							<svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
							</svg>
							Add First Reflection
						</button>
					</div>
				{:else}
					<div class="reflections-grid">
						{#each reflections as reflection}
							<ReflectionCard {reflection} />
						{/each}
					</div>
				{/if}
			</div>
		{/if}
	</div>

	<!-- Tasting Journal Section -->
	<div class="postmortem-section">
		<button
			type="button"
			class="section-header"
			onclick={() => tastingExpanded = !tastingExpanded}
		>
			<div class="section-header-left">
				<span class="section-icon">🍺</span>
				<h3 class="section-title">Tasting Journal</h3>
				{#if tastingNotes.length > 0}
					<span class="section-count">{tastingNotes.length}</span>
				{/if}
			</div>
			<svg class="section-chevron" class:expanded={tastingExpanded} fill="none" viewBox="0 0 24 24" stroke="currentColor">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
			</svg>
		</button>

		{#if tastingExpanded}
			<div class="section-content">
				{#if tastingLoading}
					<div class="section-loading">
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

					<TastingNotesList {tastingNotes} />
				{/if}
			</div>
		{/if}
	</div>

	{#if batch.notes}
		<BatchNotesCard notes={batch.notes} />
	{/if}
</div>

{#if showTastingPanel}
	<TastingPanel
		{batch}
		onClose={() => showTastingPanel = false}
		onSaved={() => { showTastingPanel = false; onTastingNotesReload(); }}
	/>
{/if}

<style>
	.completed-phase {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	/* Completed Phase */
	.batch-summary-card {
		background: linear-gradient(135deg, rgba(34, 197, 94, 0.08) 0%, rgba(74, 222, 128, 0.03) 100%);
		border: 1px solid rgba(34, 197, 94, 0.25);
		border-radius: 1rem;
		padding: 1.5rem;
	}

	.summary-title {
		font-size: 1.25rem;
		font-weight: 600;
		color: var(--positive);
		margin: 0 0 1.25rem 0;
		text-align: center;
	}

	.summary-stats {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
		gap: 1rem;
	}

	.summary-stat {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.25rem;
		padding: 0.75rem;
		background: var(--bg-surface);
		border-radius: 0.5rem;
	}

	.stat-label {
		font-size: 0.6875rem;
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-muted);
	}

	.stat-value {
		font-size: 1.25rem;
		font-weight: 600;
		font-family: var(--font-mono);
		color: var(--text-primary);
	}

	/* Timeline */
	.timeline-card {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.75rem;
		padding: 1.25rem;
	}

	.timeline-title {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin: 0 0 1rem 0;
	}

	.timeline {
		display: flex;
		flex-direction: column;
		gap: 0;
		position: relative;
		padding-left: 1.5rem;
	}

	.timeline::before {
		content: '';
		position: absolute;
		left: 0.4375rem;
		top: 0.5rem;
		bottom: 0.5rem;
		width: 2px;
		background: var(--border-subtle);
	}

	.timeline-item {
		display: flex;
		align-items: flex-start;
		gap: 1rem;
		padding: 0.75rem 0;
		position: relative;
	}

	.timeline-dot {
		position: absolute;
		left: -1.5rem;
		top: 1rem;
		width: 0.875rem;
		height: 0.875rem;
		border-radius: 50%;
		background: var(--bg-elevated);
		border: 2px solid var(--border-default);
		z-index: 1;
	}

	.timeline-dot.brewing {
		background: var(--status-brewing, #f97316);
		border-color: var(--status-brewing, #f97316);
	}

	.timeline-dot.fermenting {
		background: var(--status-fermenting);
		border-color: var(--status-fermenting);
	}

	.timeline-dot.conditioning {
		background: var(--status-conditioning);
		border-color: var(--status-conditioning);
	}

	.timeline-dot.completed {
		background: var(--status-completed);
		border-color: var(--status-completed);
	}

	.timeline-dot.packaged {
		background: var(--amber);
		border-color: var(--amber);
	}

	.timeline-content {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
	}

	.timeline-label {
		font-size: 0.875rem;
		font-weight: 500;
		color: var(--text-primary);
	}

	.timeline-date {
		font-size: 0.8125rem;
		color: var(--text-secondary);
	}

	/* Post-mortem Sections */
	.postmortem-section {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.75rem;
		overflow: hidden;
	}

	.section-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		width: 100%;
		padding: 1rem 1.25rem;
		background: transparent;
		border: none;
		cursor: pointer;
		text-align: left;
		transition: background 0.15s ease;
	}

	.section-header:hover {
		background: var(--bg-elevated);
	}

	.section-header-left {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}

	.section-icon {
		font-size: 1.25rem;
	}

	.section-title {
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
	}

	.section-count {
		font-size: 0.6875rem;
		font-weight: 600;
		padding: 0.125rem 0.5rem;
		background: var(--accent-bg, rgba(99, 102, 241, 0.1));
		color: var(--accent);
		border-radius: 1rem;
	}

	.section-chevron {
		width: 1.25rem;
		height: 1.25rem;
		color: var(--text-muted);
		transition: transform 0.2s ease;
	}

	.section-chevron.expanded {
		transform: rotate(180deg);
	}

	.section-content {
		padding: 0 1.25rem 1.25rem;
	}

	.section-loading {
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

	.section-empty {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 2rem 1rem;
		text-align: center;
	}

	.section-empty .empty-text {
		font-size: 0.9375rem;
		font-weight: 500;
		color: var(--text-secondary);
		margin: 0 0 0.25rem 0;
	}

	.section-empty .empty-subtext {
		font-size: 0.8125rem;
		color: var(--text-muted);
		margin: 0 0 1rem 0;
		max-width: 320px;
		line-height: 1.5;
	}

	.add-first-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.625rem 1rem;
		font-size: 0.8125rem;
		font-weight: 500;
		color: var(--accent);
		background: transparent;
		border: 1px dashed var(--accent);
		border-radius: 0.5rem;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.add-first-btn:hover {
		background: rgba(99, 102, 241, 0.1);
	}

	.add-first-btn svg {
		width: 1rem;
		height: 1rem;
	}

	.reflections-grid {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	@media (min-width: 768px) {
		.reflections-grid {
			display: grid;
			grid-template-columns: repeat(2, 1fr);
		}
	}

	.tasting-actions {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		margin-bottom: 1rem;
	}

	.guided-tasting-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		padding: 0.875rem 1rem;
		background: linear-gradient(135deg, var(--accent) 0%, color-mix(in srgb, var(--accent) 80%, purple) 100%);
		color: white;
		border: none;
		border-radius: 0.5rem;
		font-size: 0.875rem;
		font-weight: 600;
		cursor: pointer;
		transition: opacity 0.15s ease;
	}

	.guided-tasting-btn:hover { opacity: 0.9; }

	.manual-tasting-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		padding: 0.625rem 1rem;
		background: transparent;
		color: var(--text-secondary);
		border: 1px dashed var(--border-subtle);
		border-radius: 0.5rem;
		font-size: 0.8125rem;
		font-weight: 500;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.manual-tasting-btn:hover {
		border-color: var(--accent);
		color: var(--accent);
	}
</style>
