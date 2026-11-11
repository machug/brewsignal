<script lang="ts">
	import type { BatchResponse } from '$lib/api';
	import BatchCard from './BatchCard.svelte';

	interface Props {
		batch: BatchResponse;
	}

	let { batch }: Props = $props();

	function formatDate(dateStr?: string | null): string {
		if (!dateStr) return '--';
		return new Date(dateStr).toLocaleDateString('en-GB', {
			weekday: 'short',
			day: 'numeric',
			month: 'short',
			year: 'numeric'
		});
	}

	function formatDateTime(dateStr?: string | null): string {
		if (!dateStr) return '--';
		return new Date(dateStr).toLocaleString('en-GB', {
			day: 'numeric',
			month: 'short',
			hour: 'numeric',
			minute: '2-digit'
		});
	}
</script>

<BatchCard title="Timeline">
	<div class="timeline">
		<div class="timeline-item">
			<span class="timeline-label">Brew Date</span>
			<span class="timeline-value">{formatDate(batch.brew_date)}</span>
		</div>
		<div class="timeline-item">
			<span class="timeline-label">Started</span>
			<span class="timeline-value">{formatDateTime(batch.start_time)}</span>
		</div>
		<div class="timeline-item">
			<span class="timeline-label">Ended</span>
			<span class="timeline-value">{formatDateTime(batch.end_time)}</span>
		</div>
		<div class="timeline-item">
			<span class="timeline-label">Created</span>
			<span class="timeline-value">{formatDateTime(batch.created_at)}</span>
		</div>
	</div>
</BatchCard>

<style>
	.timeline {
		display: flex;
		flex-direction: column;
	}
	.timeline-item {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: var(--space-md);
		padding: var(--space-xs) 0;
		border-bottom: 1px solid var(--rule-hairline);
	}
	.timeline-label {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}
	.timeline-value {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: var(--text-xs);
		color: var(--ink-primary);
		text-align: right;
	}
</style>
