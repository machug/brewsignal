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
			case 'warning': return '#f59e0b';
			case 'info': return 'var(--accent)';
			default: return 'var(--text-muted)';
		}
	}

	function getAlertIcon(type: string): string {
		switch (type) {
			case 'stall': return '⏸';
			case 'temperature_high': return '🔥';
			case 'temperature_low': return '❄';
			case 'anomaly': return '⚠';
			default: return '⚠';
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
	<BatchCard title="Alerts" icon="🔔">
		<div class="loading">Loading alerts...</div>
	</BatchCard>
{:else if alerts.length === 0}
	<!-- Don't show card if no alerts -->
{:else}
	<BatchCard title="Active Alerts" icon="🔔" highlight>
		{#if error}
			<div class="error-banner">
				<span>{error}</span>
				<button type="button" class="dismiss-error" onclick={() => error = null}>×</button>
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
					<div class="alert-icon">{getAlertIcon(alert.alert_type)}</div>
					<div class="alert-content">
						<div class="alert-header">
							<span class="alert-type">{alert.alert_type.replace('_', ' ')}</span>
							<span class="severity-badge" style="background: {getSeverityColor(alert.severity)}">
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
						title="Dismiss alert"
					>
						{#if dismissing === alert.id}
							<span class="spinner"></span>
						{:else}
							<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
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
		font-size: 0.8125rem;
		color: var(--text-muted);
		text-align: center;
		padding: 0.5rem 0;
	}

	.error-banner {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.5rem 0.75rem;
		background: rgba(239, 68, 68, 0.1);
		border-radius: 0.375rem;
		margin-bottom: 0.75rem;
		font-size: 0.8125rem;
		color: var(--negative);
	}

	.dismiss-error {
		background: none;
		border: none;
		color: var(--negative);
		cursor: pointer;
		font-size: 1.25rem;
		line-height: 1;
		padding: 0;
	}

	.alerts-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 0.75rem;
	}

	.alert-count {
		font-size: 0.75rem;
		color: var(--text-muted);
		font-weight: 500;
	}

	.dismiss-all-btn {
		font-size: 0.6875rem;
		font-weight: 500;
		color: var(--text-muted);
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
		border-radius: 0.25rem;
		padding: 0.25rem 0.5rem;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.dismiss-all-btn:hover:not(:disabled) {
		color: var(--text-primary);
		border-color: var(--border-default);
	}

	.dismiss-all-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.alerts-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.alert-item {
		display: flex;
		align-items: flex-start;
		gap: 0.625rem;
		padding: 0.625rem;
		background: var(--bg-elevated);
		border-radius: 0.375rem;
		border-left: 3px solid var(--severity-color);
	}

	.alert-icon {
		font-size: 1rem;
		line-height: 1;
		flex-shrink: 0;
		margin-top: 0.125rem;
	}

	.alert-content {
		flex: 1;
		min-width: 0;
	}

	.alert-header {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-bottom: 0.25rem;
	}

	.alert-type {
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--text-primary);
		text-transform: capitalize;
	}

	.severity-badge {
		font-size: 0.5625rem;
		font-weight: 600;
		color: white;
		padding: 0.125rem 0.375rem;
		border-radius: 9999px;
		text-transform: uppercase;
		letter-spacing: 0.025em;
	}

	.alert-message {
		font-size: 0.75rem;
		color: var(--text-secondary);
		margin: 0 0 0.375rem 0;
		line-height: 1.4;
	}

	.alert-meta {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		font-size: 0.625rem;
		color: var(--text-muted);
	}

	.alert-time {
		cursor: help;
	}

	.alert-separator {
		opacity: 0.5;
	}

	.dismiss-btn {
		flex-shrink: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		width: 1.5rem;
		height: 1.5rem;
		border-radius: 0.25rem;
		background: transparent;
		border: none;
		color: var(--text-muted);
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.dismiss-btn:hover:not(:disabled) {
		color: var(--negative);
		background: rgba(239, 68, 68, 0.1);
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
		border: 2px solid var(--border-subtle);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.6s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
</style>
