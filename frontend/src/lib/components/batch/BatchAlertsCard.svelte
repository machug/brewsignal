<script lang="ts">
	import { fetchBatchAlerts, dismissAlert, dismissAllAlerts, type FermentationAlert } from '$lib/api';
	import BatchCard from './BatchCard.svelte';

	interface Props {
		batchId: number;
	}

	let { batchId }: Props = $props();

	let alerts = $state<FermentationAlert[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let dismissing = $state<number | null>(null);
	let dismissingAll = $state(false);

	// Load alerts on mount and when batchId changes
	$effect(() => {
		loadAlerts();
	});

	async function loadAlerts() {
		try {
			loading = true;
			error = null;
			alerts = await fetchBatchAlerts(batchId, false);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load alerts';
		} finally {
			loading = false;
		}
	}

	async function handleDismiss(alertId: number) {
		try {
			dismissing = alertId;
			await dismissAlert(batchId, alertId);
			alerts = alerts.filter(a => a.id !== alertId);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to dismiss alert';
		} finally {
			dismissing = null;
		}
	}

	async function handleDismissAll() {
		try {
			dismissingAll = true;
			await dismissAllAlerts(batchId);
			alerts = [];
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to dismiss alerts';
		} finally {
			dismissingAll = false;
		}
	}

	function getSeverityColor(severity: string): string {
		switch (severity) {
			case 'critical': return 'var(--negative)';
			case 'warning': return 'var(--warning)';
			case 'info': return 'var(--temp-trace)';
			default: return 'var(--text-muted)';
		}
	}

	function formatTimeAgo(dateStr: string): string {
		const date = new Date(dateStr);
		const now = new Date();
		const diffMs = now.getTime() - date.getTime();
		const diffMins = Math.floor(diffMs / 60000);
		const diffHours = Math.floor(diffMins / 60);
		const diffDays = Math.floor(diffHours / 24);

		if (diffDays > 0) return `${diffDays}d ago`;
		if (diffHours > 0) return `${diffHours}h ago`;
		if (diffMins > 0) return `${diffMins}m ago`;
		return 'just now';
	}
</script>

{#if loading}
	<BatchCard title="Alerts">
		<div class="loading">Loading alerts...</div>
	</BatchCard>
{:else if alerts.length === 0}
	<!-- Don't show card if no alerts -->
{:else}
	<BatchCard title="Active Alerts" highlight>
		{#if error}
			<div class="error-banner">
				<span>{error}</span>
				<button type="button" class="dismiss-error" onclick={() => error = null} aria-label="Dismiss error">&times;</button>
			</div>
		{/if}

		<div class="alerts-header">
			<span class="alert-count">{alerts.length} active</span>
			{#if alerts.length > 1}
				<button
					type="button"
					class="dismiss-all-btn"
					onclick={handleDismissAll}
					disabled={dismissingAll}
				>
					{dismissingAll ? 'Dismissing...' : 'Dismiss All'}
				</button>
			{/if}
		</div>

		<div class="alerts-list">
			{#each alerts as alert (alert.id)}
				<div class="alert-item" style="--severity-color: {getSeverityColor(alert.severity)}">
					<div class="alert-content">
						<div class="alert-header">
							<span class="alert-type">{alert.alert_type.replace('_', ' ')}</span>
							<span class="severity-badge">
								{alert.severity}
							</span>
						</div>
						<p class="alert-message">{alert.message}</p>
						<div class="alert-meta">
							<span class="alert-time" title="First detected: {new Date(alert.first_detected_at).toLocaleString()}">
								First: {formatTimeAgo(alert.first_detected_at)}
							</span>
							<span class="alert-separator">·</span>
							<span class="alert-time" title="Last seen: {new Date(alert.last_seen_at).toLocaleString()}">
								Last: {formatTimeAgo(alert.last_seen_at)}
							</span>
						</div>
					</div>
					<button
						type="button"
						class="dismiss-btn"
						onclick={() => handleDismiss(alert.id)}
						disabled={dismissing === alert.id}
						title="Dismiss alert" aria-label="Dismiss alert"
					>
						{#if dismissing === alert.id}
							<span class="spinner" aria-hidden="true"></span>
						{:else}
							<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
								<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
							</svg>
						{/if}
					</button>
				</div>
			{/each}
		</div>
	</BatchCard>
{/if}

<style>
	.loading {
		font-size: var(--text-sm);
		color: var(--ink-muted);
		padding: var(--space-xs) 0;
	}
	.error-banner {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: var(--space-xs) var(--space-sm);
		border: 1px solid color-mix(in oklch, var(--status-danger) 50%, transparent);
		margin-bottom: var(--space-sm);
		font-size: var(--text-sm);
		color: var(--status-danger);
	}
	.dismiss-error {
		color: inherit;
		cursor: pointer;
		font-size: 1.25rem;
		line-height: 1;
		min-width: 44px;
		min-height: 44px;
	}
	.alerts-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: var(--space-xs);
	}
	.alert-count {
		font-family: var(--font-num);
		font-size: var(--text-xs);
		color: var(--ink-secondary);
	}
	.dismiss-all-btn {
		min-height: 44px;
		padding: 0 var(--space-sm);
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-primary);
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		cursor: pointer;
	}
	.dismiss-all-btn:hover:not(:disabled) {
		background: var(--bg-subtle);
	}
	.dismiss-all-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
	.alerts-list {
		display: flex;
		flex-direction: column;
		border-top: 1px solid var(--rule-hairline);
	}
	.alert-item {
		display: flex;
		align-items: flex-start;
		gap: var(--space-sm);
		padding: var(--space-sm) 0;
		border-bottom: 1px solid var(--rule-hairline);
	}
	.alert-content {
		flex: 1;
		min-width: 0;
	}
	.alert-header {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
		margin-bottom: var(--space-2xs);
	}
	.alert-type {
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--ink-primary);
		text-transform: capitalize;
	}
	.severity-badge {
		font-family: var(--font-display);
		font-size: 0.6875rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		padding: 1px 6px;
		border-radius: 2px;
		border: 1px solid var(--severity-color);
		color: var(--severity-color);
	}
	.alert-message {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		line-height: 1.4;
		margin-bottom: var(--space-2xs);
	}
	.alert-meta {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
		font-family: var(--font-num);
		font-size: var(--text-xs);
		color: var(--ink-muted);
	}
	.alert-time {
		cursor: help;
	}
	.dismiss-btn {
		flex-shrink: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		width: 2.75rem;
		height: 2.75rem;
		margin: -0.5rem 0;
		border-radius: 4px;
		color: var(--ink-muted);
		cursor: pointer;
	}
	.dismiss-btn:hover:not(:disabled) {
		color: var(--status-danger);
		background: var(--negative-muted);
	}
	.dismiss-btn:disabled {
		cursor: not-allowed;
	}
	.dismiss-btn svg {
		width: 0.875rem;
		height: 0.875rem;
	}
	.spinner {
		width: 0.75rem;
		height: 0.75rem;
		border: 2px solid var(--rule-hairline);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.6s linear infinite;
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.spinner {
			animation: none;
		}
	}
</style>
