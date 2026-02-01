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

<BatchCard title={phaseInfo?.name ?? reflection.phase} icon={phaseInfo?.icon}>
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
							<span class="note-icon">✓</span>
							What Went Well
						</h4>
						<p class="note-content">{reflection.what_went_well}</p>
					</div>
				{/if}

				{#if reflection.what_went_wrong}
					<div class="note-block negative">
						<h4 class="note-title">
							<span class="note-icon">✗</span>
							What Went Wrong
						</h4>
						<p class="note-content">{reflection.what_went_wrong}</p>
					</div>
				{/if}

				{#if reflection.lessons_learned}
					<div class="note-block neutral">
						<h4 class="note-title">
							<span class="note-icon">💡</span>
							Lessons Learned
						</h4>
						<p class="note-content">{reflection.lessons_learned}</p>
					</div>
				{/if}

				{#if reflection.next_time_changes}
					<div class="note-block neutral">
						<h4 class="note-title">
							<span class="note-icon">→</span>
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
		gap: 1rem;
	}

	/* Header */
	.reflection-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.reflection-date {
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	.header-actions {
		display: flex;
		gap: 0.25rem;
	}

	.action-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 0.375rem;
		background: transparent;
		border: none;
		border-radius: 0.25rem;
		color: var(--text-muted);
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.action-btn:hover {
		background: var(--bg-elevated);
		color: var(--text-primary);
	}

	.action-btn svg {
		width: 1rem;
		height: 1rem;
	}

	/* Section titles */
	.section-title {
		font-size: 0.6875rem;
		font-weight: 600;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin: 0 0 0.5rem 0;
	}

	/* Metrics */
	.metrics-section {
		padding-bottom: 1rem;
		border-bottom: 1px solid var(--border-subtle);
	}

	.metrics-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
		gap: 0.5rem;
	}

	.metric-item {
		display: flex;
		flex-direction: column;
		padding: 0.5rem 0.75rem;
		background: var(--bg-elevated);
		border-radius: 0.375rem;
	}

	.metric-label {
		font-size: 0.625rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.025em;
		margin-bottom: 0.25rem;
	}

	.metric-value {
		font-family: var(--font-mono);
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--text-primary);
	}

	/* AI Section */
	.ai-section {
		padding: 0.875rem;
		background: linear-gradient(135deg, rgba(99, 102, 241, 0.08) 0%, rgba(139, 92, 246, 0.05) 100%);
		border: 1px solid rgba(99, 102, 241, 0.2);
		border-radius: 0.5rem;
	}

	.ai-section.empty {
		padding: 1rem;
		text-align: center;
	}

	.ai-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		margin-bottom: 0.75rem;
	}

	.ai-title-row {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.ai-badge {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		font-size: 0.6875rem;
		font-weight: 600;
		color: var(--accent);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.ai-date {
		font-size: 0.625rem;
		color: var(--text-muted);
	}

	.regenerate-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		padding: 0.375rem 0.625rem;
		font-size: 0.6875rem;
		font-weight: 500;
		color: var(--text-secondary);
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.375rem;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.regenerate-btn:hover {
		color: var(--accent);
		border-color: var(--accent);
	}

	.regenerate-btn svg {
		width: 0.875rem;
		height: 0.875rem;
	}

	.generate-btn {
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

	.generate-btn:hover {
		background: rgba(99, 102, 241, 0.1);
	}

	.generate-btn svg {
		width: 1rem;
		height: 1rem;
	}

	.ai-summary {
		font-size: 0.8125rem;
		color: var(--text-secondary);
		line-height: 1.6;
		margin: 0;
		white-space: pre-wrap;
	}

	/* Notes Section */
	.notes-section {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.note-block {
		padding: 0.75rem;
		border-radius: 0.5rem;
		border-left: 3px solid var(--border-subtle);
		background: var(--bg-elevated);
	}

	.note-block.positive {
		border-left-color: var(--positive);
		background: rgba(34, 197, 94, 0.05);
	}

	.note-block.negative {
		border-left-color: var(--negative);
		background: rgba(239, 68, 68, 0.05);
	}

	.note-block.neutral {
		border-left-color: var(--recipe-accent);
		background: rgba(245, 158, 11, 0.05);
	}

	.note-title {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--text-secondary);
		margin: 0 0 0.5rem 0;
	}

	.note-icon {
		font-size: 0.75rem;
	}

	.note-block.positive .note-icon {
		color: var(--positive);
	}

	.note-block.negative .note-icon {
		color: var(--negative);
	}

	.note-block.neutral .note-icon {
		color: var(--recipe-accent);
	}

	.note-content {
		font-size: 0.8125rem;
		color: var(--text-secondary);
		line-height: 1.5;
		margin: 0;
		white-space: pre-wrap;
	}

	/* Empty State */
	.empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 1.5rem;
		text-align: center;
	}

	.empty-text {
		font-size: 0.875rem;
		color: var(--text-muted);
		margin: 0 0 1rem 0;
	}

	.add-reflection-btn {
		padding: 0.5rem 1rem;
		font-size: 0.8125rem;
		font-weight: 500;
		color: var(--primary);
		background: transparent;
		border: 1px solid var(--primary);
		border-radius: 0.375rem;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.add-reflection-btn:hover {
		background: var(--primary);
		color: white;
	}

	/* Responsive */
	@media (max-width: 480px) {
		.metrics-grid {
			grid-template-columns: repeat(2, 1fr);
		}

		.ai-header {
			flex-direction: column;
			gap: 0.5rem;
		}
	}
</style>
