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
	import ReflectionFormModal from './ReflectionFormModal.svelte';
	import BatchNotesCard from './BatchNotesCard.svelte';
	import type { ReflectionPhase } from '$lib/types/reflection';

	interface Props {
		batch: BatchResponse;
		reflections: BatchReflection[];
		tastingNotes: TastingNote[];
		reflectionsLoading: boolean;
		tastingLoading: boolean;
		onBatchUpdate: (updated: BatchResponse) => void;
		onTastingNotesReload: () => void;
		onReflectionsReload?: () => void;
	}

	let {
		batch,
		reflections,
		tastingNotes,
		reflectionsLoading,
		tastingLoading,
		onBatchUpdate,
		onTastingNotesReload,
		onReflectionsReload,
	}: Props = $props();

	let reflectionsExpanded = $state(true);
	let tastingExpanded = $state(true);
	let showBJCPForm = $state(false);
	let showTastingPanel = $state(false);
	let showReflectionForm = $state(false);

	let existingPhases = $derived(reflections.map((r) => r.phase as ReflectionPhase));

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
				<h3 class="section-title">Reflections & Learnings</h3>
				{#if reflections.length > 0}
					<span class="section-count num">{reflections.length}</span>
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
						<button
							type="button"
							class="add-first-btn"
							onclick={() => (showReflectionForm = true)}
						>
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
					{#if existingPhases.length < 4}
						<button
							type="button"
							class="add-more-btn"
							onclick={() => (showReflectionForm = true)}
						>
							<svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
							</svg>
							Add Another Reflection
						</button>
					{/if}
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
				<h3 class="section-title">Tasting Journal</h3>
				{#if tastingNotes.length > 0}
					<span class="section-count num">{tastingNotes.length}</span>
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

<ReflectionFormModal
	open={showReflectionForm}
	batchId={batch.id}
	{existingPhases}
	onClose={() => (showReflectionForm = false)}
	onSaved={() => onReflectionsReload?.()}
/>

<style>
	.completed-phase {
		display: flex;
		flex-direction: column;
		gap: var(--space-lg);
	}

	.num {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums lining-nums;
	}

	/* Summary: instrument readout grid */
	.batch-summary-card {
		border-top: 1px solid var(--rule-strong);
		border-bottom: 1px solid var(--rule-hairline);
	}

	.summary-title {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--status-steady);
		margin: 0;
		padding: var(--space-sm) 0 var(--space-xs);
	}

	.summary-stats {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
	}

	.summary-stat {
		display: flex;
		flex-direction: column;
		gap: var(--space-2xs);
		padding: var(--space-sm) var(--space-md) var(--space-md);
		min-width: 0;
	}

	.summary-stat + .summary-stat {
		border-left: 1px solid var(--rule-hairline);
	}

	@media (max-width: 600px) {
		.summary-stats {
			grid-template-columns: 1fr 1fr;
		}
		.summary-stat:nth-child(3) {
			border-left: none;
		}
		.summary-stat:nth-child(n + 3) {
			border-top: 1px solid var(--rule-hairline);
		}
	}

	.stat-label {
		font-family: var(--font-display);
		font-size: 0.6875rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--ink-muted);
	}

	.stat-value {
		font-size: var(--text-xl);
		font-weight: 500;
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums lining-nums;
		color: var(--ink-primary);
	}

	/* Timeline: hairline ledger */
	.timeline-card {
		border-top: 1px solid var(--rule-hairline);
		padding-top: var(--space-md);
	}

	.timeline-title,
	.section-title {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-muted);
		text-transform: uppercase;
		letter-spacing: 0.08em;
		margin: 0;
	}

	.timeline-title {
		margin-bottom: var(--space-sm);
	}

	.timeline {
		display: flex;
		flex-direction: column;
		position: relative;
		padding-left: var(--space-lg);
	}

	.timeline::before {
		content: '';
		position: absolute;
		left: 5px;
		top: var(--space-sm);
		bottom: var(--space-sm);
		width: 1px;
		background: var(--rule-strong);
	}

	.timeline-item {
		display: flex;
		align-items: flex-start;
		gap: var(--space-md);
		padding: var(--space-sm) 0;
		position: relative;
		border-bottom: 1px solid var(--rule-hairline);
	}

	.timeline-item:last-child {
		border-bottom: none;
	}

	.timeline-dot {
		position: absolute;
		left: calc(-1 * var(--space-lg));
		top: 1.0625rem;
		width: 11px;
		height: 11px;
		border-radius: 50%;
		background: var(--bg-canvas);
		border: 1px solid var(--rule-strong);
		z-index: 1;
	}

	.timeline-dot.brewing {
		border-color: var(--status-planning);
		background: var(--status-planning);
	}

	.timeline-dot.fermenting {
		border-color: var(--status-fermenting);
		background: var(--status-fermenting);
	}

	.timeline-dot.conditioning {
		border-color: var(--status-conditioning);
		background: var(--status-conditioning);
	}

	.timeline-dot.completed {
		border-color: var(--status-completed);
		background: var(--status-completed);
	}

	.timeline-dot.packaged {
		border-color: var(--accent);
		background: var(--accent);
	}

	.timeline-content {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.timeline-label {
		font-size: var(--text-sm);
		font-weight: 700;
		color: var(--ink-primary);
	}

	.timeline-date {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: var(--text-xs);
		color: var(--ink-secondary);
	}

	/* Post-mortem sections: hairline-separated, no container */
	.postmortem-section {
		border-top: 1px solid var(--rule-hairline);
	}

	.section-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		width: 100%;
		min-height: 48px;
		padding: var(--space-sm) 0;
		background: transparent;
		border: none;
		cursor: pointer;
		text-align: left;
	}

	.section-header:hover .section-title {
		color: var(--ink-primary);
	}

	.section-header:focus-visible,
	.add-first-btn:focus-visible,
	.add-more-btn:focus-visible,
	.guided-tasting-btn:focus-visible,
	.manual-tasting-btn:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.section-header-left {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
	}

	.section-count {
		font-size: 0.6875rem;
		font-weight: 600;
		padding: 1px 7px;
		border: 1px solid var(--rule-strong);
		border-radius: 2px;
		color: var(--ink-secondary);
	}

	.section-chevron {
		width: 1.25rem;
		height: 1.25rem;
		color: var(--ink-muted);
		transition: transform 0.2s var(--ease-out-quart);
	}

	.section-chevron.expanded {
		transform: rotate(180deg);
	}

	.section-content {
		padding: 0 0 var(--space-md);
	}

	.section-loading {
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

	.section-empty {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: var(--space-xl) var(--space-md);
		text-align: center;
	}

	.section-empty .empty-text {
		font-size: var(--text-base);
		font-weight: 700;
		color: var(--ink-secondary);
		margin: 0 0 var(--space-2xs) 0;
	}

	.section-empty .empty-subtext {
		font-size: var(--text-sm);
		color: var(--ink-muted);
		margin: 0 0 var(--space-md) 0;
		max-width: 320px;
		line-height: 1.5;
	}

	.add-first-btn,
	.add-more-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: var(--space-xs);
		min-height: 44px;
		padding: 0 var(--space-md);
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--accent);
		background: var(--accent-tint);
		border: 1px solid var(--accent-rule);
		border-radius: 4px;
		cursor: pointer;
	}

	.add-more-btn {
		align-self: flex-start;
		margin-top: var(--space-sm);
	}

	.add-first-btn:hover,
	.add-more-btn:hover {
		border-color: var(--accent);
	}

	.add-first-btn svg,
	.add-more-btn svg {
		width: 1rem;
		height: 1rem;
	}

	.reflections-grid {
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
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
		gap: var(--space-xs);
		margin-bottom: var(--space-md);
	}

	.guided-tasting-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: var(--space-xs);
		min-height: 44px;
		padding: 0 var(--space-md);
		background: var(--accent);
		color: var(--accent-ink);
		border: 1px solid var(--accent);
		border-radius: 4px;
		font-size: var(--text-sm);
		font-weight: 700;
		cursor: pointer;
	}

	.guided-tasting-btn:hover { background: var(--accent-hover); border-color: var(--accent-hover); }

	.manual-tasting-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: var(--space-xs);
		min-height: 44px;
		padding: 0 var(--space-md);
		background: var(--bg-surface);
		color: var(--ink-secondary);
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
