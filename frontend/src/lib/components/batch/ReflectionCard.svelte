<script lang="ts">
	import type { BatchReflection, ReflectionPhase } from '$lib/types';
	import { PHASE_INFO, METRIC_LABELS } from '$lib/types';
	import BatchCard from './BatchCard.svelte';

	interface Props {
		reflection: BatchReflection;
		onEdit?: () => void;
		onRegenerateInsights?: () => void;
	}

	let { reflection, onEdit, onRegenerateInsights }: Props = $props();

	// Get phase display info
	let phaseInfo = $derived(PHASE_INFO[reflection.phase as ReflectionPhase]);

	// Format metrics for display
	let metricsEntries = $derived.by(() => {
		if (!reflection.metrics) return [];
		return Object.entries(reflection.metrics).map(([key, value]) => ({
			key,
			label: METRIC_LABELS[key] || formatMetricKey(key),
			value: formatMetricValue(key, value)
		}));
	});

	// Check if there's any content to display
	let hasNotes = $derived(
		reflection.what_went_well ||
		reflection.what_went_wrong ||
		reflection.lessons_learned ||
		reflection.next_time_changes
	);

	let hasAiSummary = $derived(!!reflection.ai_summary);

	function formatMetricKey(key: string): string {
		// Convert snake_case to Title Case
		return key
			.split('_')
			.map(word => word.charAt(0).toUpperCase() + word.slice(1))
			.join(' ');
	}

	function formatMetricValue(key: string, value: number): string {
		// Format based on key type
		if (key.includes('sg') || key.includes('gravity')) {
			return value.toFixed(3);
		}
		if (key.includes('temp')) {
			return `${value.toFixed(1)}`;
		}
		if (key.includes('percent') || key.includes('efficiency')) {
			return `${value.toFixed(1)}%`;
		}
		if (key.includes('volume')) {
			return `${value.toFixed(1)} L`;
		}
		if (Number.isInteger(value)) {
			return value.toString();
		}
		return value.toFixed(2);
	}

	function formatDate(dateStr: string): string {
		return new Date(dateStr).toLocaleDateString('en-AU', {
			day: 'numeric',
			month: 'short',
			year: 'numeric'
		});
	}

	function formatDateTime(dateStr: string): string {
		return new Date(dateStr).toLocaleString('en-AU', {
			day: 'numeric',
			month: 'short',
			year: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	}
</script>

<BatchCard title={phaseInfo?.name ?? reflection.phase}>
	<div class="reflection-content">
		<!-- Header with date and actions -->
		<div class="reflection-header">
			<span class="reflection-date">{formatDate(reflection.created_at)}</span>
			<div class="header-actions">
				{#if onEdit}
					<button type="button" class="action-btn edit-btn" onclick={onEdit} title="Edit reflection">
						<svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
						</svg>
					</button>
				{/if}
			</div>
		</div>

		<!-- Metrics Grid -->
		{#if metricsEntries.length > 0}
			<div class="metrics-section">
				<h4 class="section-title">Metrics</h4>
				<div class="metrics-grid">
					{#each metricsEntries as metric}
						<div class="metric-item">
							<span class="metric-label">{metric.label}</span>
							<span class="metric-value">{metric.value}</span>
						</div>
					{/each}
				</div>
			</div>
		{/if}

		<!-- AI Summary Section -->
		{#if hasAiSummary}
			<div class="ai-section">
				<div class="ai-header">
					<div class="ai-title-row">
						<span class="ai-badge">AI Insights</span>
						{#if reflection.ai_generated_at}
							<span class="ai-date">Generated {formatDateTime(reflection.ai_generated_at)}</span>
						{/if}
					</div>
					{#if onRegenerateInsights}
						<button
							type="button"
							class="regenerate-btn"
							onclick={onRegenerateInsights}
							title="Regenerate AI insights"
						>
							<svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
							</svg>
							Regenerate
						</button>
					{/if}
				</div>
				<p class="ai-summary">{reflection.ai_summary}</p>
			</div>
		{:else if onRegenerateInsights}
			<!-- Show generate button if no summary exists -->
			<div class="ai-section empty">
				<button
					type="button"
					class="generate-btn"
					onclick={onRegenerateInsights}
				>
					<svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
					</svg>
					Generate AI Insights
				</button>
			</div>
		{/if}

		<!-- User Notes Sections -->
		{#if hasNotes}
			<div class="notes-section">
				{#if reflection.what_went_well}
					<div class="note-block positive">
						<h4 class="note-title">
							<svg class="note-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 13l4 4L19 7"/></svg>
							What Went Well
						</h4>
						<p class="note-content">{reflection.what_went_well}</p>
					</div>
				{/if}

				{#if reflection.what_went_wrong}
					<div class="note-block negative">
						<h4 class="note-title">
							<svg class="note-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>
							What Went Wrong
						</h4>
						<p class="note-content">{reflection.what_went_wrong}</p>
					</div>
				{/if}

				{#if reflection.lessons_learned}
					<div class="note-block neutral">
						<h4 class="note-title">
							<svg class="note-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3"/></svg>
							Lessons Learned
						</h4>
						<p class="note-content">{reflection.lessons_learned}</p>
					</div>
				{/if}

				{#if reflection.next_time_changes}
					<div class="note-block neutral">
						<h4 class="note-title">
							<svg class="note-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
							Next Time
						</h4>
						<p class="note-content">{reflection.next_time_changes}</p>
					</div>
				{/if}
			</div>
		{/if}

		<!-- Empty state -->
		{#if !metricsEntries.length && !hasNotes && !hasAiSummary}
			<div class="empty-state">
				<p class="empty-text">No reflection data recorded yet.</p>
				{#if onEdit}
					<button type="button" class="add-reflection-btn" onclick={onEdit}>
						Add reflection notes
					</button>
				{/if}
			</div>
		{/if}
	</div>
</BatchCard>

<style>
	.reflection-content {
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
	}

	.reflection-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.reflection-date {
		font-family: var(--font-num);
		font-size: var(--text-xs);
		color: var(--ink-muted);
	}

	.header-actions {
		display: flex;
		gap: var(--space-2xs);
	}

	button:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.action-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		min-width: 44px;
		min-height: 44px;
		background: transparent;
		border: none;
		border-radius: 4px;
		color: var(--ink-muted);
		cursor: pointer;
	}

	.action-btn:hover {
		background: var(--bg-elevated);
		color: var(--ink-primary);
	}

	.action-btn svg {
		width: 1rem;
		height: 1rem;
	}

	.section-title {
		font-family: var(--font-display);
		font-size: 0.6875rem;
		font-weight: 600;
		color: var(--ink-muted);
		text-transform: uppercase;
		letter-spacing: 0.08em;
		margin: 0 0 var(--space-xs) 0;
	}

	/* Metrics: readout grid */
	.metrics-section {
		padding-bottom: var(--space-md);
		border-bottom: 1px solid var(--rule-hairline);
	}

	.metrics-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
		border-top: 1px solid var(--rule-hairline);
	}

	.metric-item {
		display: flex;
		flex-direction: column;
		gap: var(--space-2xs);
		padding: var(--space-xs) var(--space-sm);
		border-bottom: 1px solid var(--rule-hairline);
		min-width: 0;
	}

	.metric-label {
		font-family: var(--font-display);
		font-size: 0.625rem;
		font-weight: 600;
		color: var(--ink-muted);
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}

	.metric-value {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--ink-primary);
	}

	/* AI section: hairline-separated */
	.ai-section {
		padding-top: var(--space-sm);
		border-top: 1px solid var(--rule-hairline);
	}

	.ai-section.empty {
		text-align: center;
		border-top: none;
		padding-top: 0;
	}

	.ai-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: var(--space-sm);
		margin-bottom: var(--space-xs);
	}

	.ai-title-row {
		display: flex;
		flex-direction: column;
		gap: var(--space-2xs);
	}

	.ai-badge {
		font-family: var(--font-display);
		font-size: 0.6875rem;
		font-weight: 600;
		color: var(--ink-muted);
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}

	.ai-date {
		font-family: var(--font-num);
		font-size: 0.625rem;
		color: var(--ink-muted);
	}

	.regenerate-btn,
	.generate-btn,
	.add-reflection-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: var(--space-xs);
		min-height: 44px;
		padding: 0 var(--space-md);
		font-size: var(--text-xs);
		font-weight: 600;
		border-radius: 4px;
		cursor: pointer;
	}

	.regenerate-btn {
		color: var(--ink-secondary);
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
	}

	.regenerate-btn:hover {
		color: var(--ink-primary);
		background: var(--bg-subtle);
	}

	.generate-btn,
	.add-reflection-btn {
		color: var(--accent);
		background: var(--accent-tint);
		border: 1px solid var(--accent-rule);
	}

	.generate-btn:hover,
	.add-reflection-btn:hover {
		border-color: var(--accent);
	}

	.regenerate-btn svg,
	.generate-btn svg {
		width: 0.875rem;
		height: 0.875rem;
	}

	.ai-summary {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		line-height: 1.6;
		margin: 0;
		white-space: pre-wrap;
	}

	/* Notes: hairline-separated blocks, tone via icon and title colour */
	.notes-section {
		display: flex;
		flex-direction: column;
	}

	.note-block {
		padding: var(--space-sm) 0;
		border-top: 1px solid var(--rule-hairline);
	}

	.note-title {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--ink-secondary);
		margin: 0 0 var(--space-xs) 0;
	}

	.note-icon {
		flex-shrink: 0;
		color: var(--ink-muted);
	}

	.note-block.positive .note-icon {
		color: var(--positive);
	}

	.note-block.negative .note-icon {
		color: var(--negative);
	}

	.note-block.neutral .note-icon {
		color: var(--accent);
	}

	.note-content {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		line-height: 1.5;
		margin: 0;
		white-space: pre-wrap;
	}

	.empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: var(--space-lg);
		text-align: center;
	}

	.empty-text {
		font-size: var(--text-sm);
		color: var(--ink-muted);
		margin: 0 0 var(--space-md) 0;
	}

	@media (max-width: 480px) {
		.metrics-grid {
			grid-template-columns: repeat(2, 1fr);
		}

		.ai-header {
			flex-direction: column;
		}
	}
</style>
