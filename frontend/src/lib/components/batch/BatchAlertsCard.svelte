<script lang="ts">
	import { fetchBatchAlerts, dismissAlert, dismissAllAlerts, markDryHopDone, crashReadyNotYet, updateBatch, type BatchResponse, type FermentationAlert, type AlertType } from '$lib/api';
	import { configState, fahrenheitToCelsius, celsiusToFahrenheit } from '$lib/stores/config.svelte';
	import BatchCard from './BatchCard.svelte';

	// Cleared only by marking the dry hop done (tilt_ui-n1w7, tilt_ui-8ih3)
	const DRY_HOP_TYPES: AlertType[] = ['dry_hop_due', 'crash_wait_dry_hop'];

	interface Props {
		batchId: number;
		/** The batch, when known: decides whether "Start cold crash" can set the target. */
		batch?: BatchResponse;
		onBatchUpdate?: (batch: BatchResponse) => void;
	}

	let { batchId, batch, onBatchUpdate }: Props = $props();

	// --- Start cold crash (tilt_ui-ifmj) ---
	// The server ends the ready notice once the target drops below 5 °C.
	const CRASH_DEFAULT_C = 2;
	const CRASH_MIN_C = 0; // the API rejects targets below 0 °C
	const CRASH_MAX_C = 4;
	let useF = $derived(configState.config.temp_units === 'F');
	let crashOpen = $state(false);
	// bind:value on a number input gives a number, or null when cleared.
	let crashTemp = $state<number | null>(null);
	let crashBusy = $state(false);
	// Only a cooler can pull wort down, and only while the controller runs
	// (same switches and HA settings the control loop checks). Otherwise a new
	// target would end the notice while nothing cools.
	let controllerRunning = $derived(
		!!configState.config.temp_control_enabled &&
			!!configState.config.ha_enabled &&
			!!configState.config.ha_url &&
			!!configState.config.ha_token
	);
	// A heater counts too: in a fridge it would keep heating toward the old target.
	let canSetTarget = $derived(!!(batch?.cooler_entity_id || batch?.heater_entity_id) && controllerRunning);
	// Bounds shown in the user's unit, rounded inward so the shown limits always pass.
	let crashMinShown = $derived(useF ? Math.ceil(celsiusToFahrenheit(CRASH_MIN_C)) : CRASH_MIN_C);
	let crashMaxShown = $derived(useF ? Math.floor(celsiusToFahrenheit(CRASH_MAX_C)) : CRASH_MAX_C);
	let unit = $derived(useF ? '°F' : '°C');
	let crashTempC = $derived.by(() => {
		if (crashTemp === null || !Number.isFinite(crashTemp)) return null;
		return useF ? fahrenheitToCelsius(crashTemp) : crashTemp;
	});
	let crashTempValid = $derived(
		crashTemp !== null && crashTempC !== null && crashTemp >= crashMinShown && crashTemp <= crashMaxShown
	);

	function openCrash() {
		crashTemp = useF ? Math.round(celsiusToFahrenheit(CRASH_DEFAULT_C)) : CRASH_DEFAULT_C;
		crashOpen = true;
	}

	async function startCrash(alertId: number) {
		try {
			crashBusy = true;
			error = null;
			if (canSetTarget) {
				if (!crashTempValid || crashTempC === null) return;
				const updated = await updateBatch(batchId, { temp_target: Math.round(crashTempC * 10) / 10 });
				onBatchUpdate?.(updated);
			} else {
				// No cooler on this batch: the brewer moved it somewhere cold.
				await dismissAlert(batchId, alertId);
			}
			// The server also takes down any "not ready" warning: reload the list.
			crashOpen = false;
			await loadAlerts(true);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to start the cold crash';
		} finally {
			crashBusy = false;
		}
	}

	async function handleNotYet(alertId: number) {
		try {
			dismissing = alertId;
			error = null;
			const updated = await crashReadyNotYet(batchId);
			alerts = alerts.filter((a) => a.id !== alertId);
			crashOpen = false;
			onBatchUpdate?.(updated);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to snooze the notice';
		} finally {
			dismissing = null;
		}
	}

	let alerts = $state<FermentationAlert[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let dismissing = $state<number | null>(null);
	let dismissingAll = $state(false);

	// Load alerts on mount and when batchId changes
	$effect(() => {
		loadAlerts();
	});

	async function loadAlerts(quiet = false) {
		try {
			loading = !quiet; // a refresh after an action keeps the list on screen
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

	async function handleDryHopDone(alertId: number) {
		try {
			dismissing = alertId;
			const updated = await markDryHopDone(batchId);
			onBatchUpdate?.(updated);
			// The server also takes down a ready-to-crash notice: reload the list.
			await loadAlerts(true);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to mark dry hop done';
		} finally {
			dismissing = null;
		}
	}

	async function handleDismissAll() {
		try {
			dismissingAll = true;
			await dismissAllAlerts(batchId);
			// The server keeps the dry hop reminder until it is marked done
			alerts = alerts.filter((a) => DRY_HOP_TYPES.includes(a.alert_type));
			crashOpen = false;
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
							<span class="alert-type">{alert.alert_type.replaceAll('_', ' ')}</span>
							<span class="severity-badge">
								{alert.severity}
							</span>
						</div>
						<p class="alert-message">{alert.message}</p>
						{#if alert.alert_type === 'crash_ready'}
							{#if !crashOpen}
								<div class="crash-actions">
									<button type="button" class="dismiss-all-btn primary-btn" onclick={openCrash} disabled={dismissing === alert.id}>
										Start cold crash
									</button>
									<button type="button" class="dismiss-all-btn" onclick={() => handleNotYet(alert.id)} disabled={dismissing === alert.id}>
										Not yet
									</button>
								</div>
								<p class="crash-hint">Not yet: keep it warm. The notice comes back after 48 more steady hours.</p>
							{:else}
								<div class="crash-panel">
									<p class="crash-heading">Before you crash</p>
									<ul class="crash-list">
										<li>
											Stop suck-back: swap the blow-off tube for a CO<sub>2</sub> balloon, a check valve or a
											spunding valve, or put the fermenter under a little CO<sub>2</sub> pressure.
											<small>Cooling beer shrinks and pulls air or liquid back in. A plain airlock sucks its sanitiser into the beer.</small>
										</li>
										<li>
											Run a forced diacetyl test.
											<small>
												Warm a sealed sample to about {useF ? '140 °F' : '60 °C'} for 15 minutes, cool it, then smell
												for butter. Butter? Press "Not yet" and keep it warm.
											</small>
										</li>
									</ul>
									{#if canSetTarget}
										<label class="crash-temp">
											<span>Crash to</span>
											<input
												type="number"
												inputmode="decimal"
												step="0.5"
												min={crashMinShown}
												max={crashMaxShown}
												bind:value={crashTemp}
												aria-invalid={!crashTempValid}
												aria-describedby={crashTempValid ? undefined : `crash-error-${alert.id}`}
											/>
											<span class="unit">{unit}</span>
										</label>
										{#if !crashTempValid}
											<p class="crash-error" id="crash-error-{alert.id}">Pick {crashMinShown} to {crashMaxShown} {unit}.</p>
										{/if}
										{#if !batch?.cooler_entity_id}
											<p class="crash-note">This batch has no cooler: move the fermenter somewhere cold. The new target keeps the heater off.</p>
										{/if}
									{:else}
										<p class="crash-note">
											{batch?.cooler_entity_id || batch?.heater_entity_id
												? 'Temperature control is off or Home Assistant is not set up, so the app cannot crash it.'
												: 'This batch has no cooler, so the app cannot crash it.'}
											Move the fermenter somewhere cold (about {useF ? '36 °F' : '2 °C'}), then press below.
										</p>
									{/if}
									<div class="crash-actions">
										<button
											type="button"
											class="dismiss-all-btn primary-btn"
											onclick={() => startCrash(alert.id)}
											disabled={crashBusy || dismissing === alert.id || (canSetTarget && !crashTempValid)}
										>
											{crashBusy ? 'Starting…' : canSetTarget ? 'Set target and start' : 'I started the crash'}
										</button>
										<button type="button" class="dismiss-all-btn" onclick={() => handleNotYet(alert.id)} disabled={crashBusy || dismissing === alert.id}>
											Not yet
										</button>
										<button type="button" class="dismiss-all-btn" onclick={() => (crashOpen = false)} disabled={crashBusy || dismissing === alert.id}>
											Cancel
										</button>
									</div>
								</div>
							{/if}
						{/if}
						{#if DRY_HOP_TYPES.includes(alert.alert_type)}
							<button type="button" class="dismiss-all-btn dry-hop-btn" onclick={() => handleDryHopDone(alert.id)} disabled={dismissing === alert.id}>
								Mark dry hopped
							</button>
						{/if}
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
					{#if !DRY_HOP_TYPES.includes(alert.alert_type) && !(alert.alert_type === 'crash_ready' && crashOpen)}
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
					{/if}
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
		display: inline-flex;
		align-items: center;
		justify-content: center;
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
	.dry-hop-btn {
		margin-bottom: var(--space-2xs);
	}
	.primary-btn {
		color: var(--bg-surface);
		background: var(--ink-primary);
		border-color: var(--ink-primary);
	}
	.primary-btn:hover:not(:disabled) {
		background: var(--ink-secondary);
	}
	.crash-actions {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-xs);
		margin-bottom: var(--space-2xs);
	}
	.crash-hint,
	.crash-note {
		font-size: var(--text-xs);
		color: var(--ink-muted);
		line-height: 1.4;
		margin-bottom: var(--space-2xs);
	}
	.crash-panel {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
		padding: var(--space-sm) 0 var(--space-2xs);
		border-top: 1px solid var(--rule-hairline);
	}
	.crash-heading {
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--ink-primary);
	}
	.crash-list {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
		margin: 0;
		padding-left: 1.1rem;
		list-style: disc;
		font-size: var(--text-sm);
		color: var(--ink-primary);
		line-height: 1.4;
	}
	.crash-list small {
		display: block;
		font-size: var(--text-xs);
		color: var(--ink-muted);
	}
	.crash-temp {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
		font-size: var(--text-sm);
		color: var(--ink-primary);
	}
	.crash-temp input {
		width: 5rem;
		font-size: 1rem; /* 16px: iOS Safari zooms into smaller inputs */
		min-height: 44px;
		padding: 0 var(--space-xs);
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		color: var(--ink-primary);
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
	}
	.crash-temp input[aria-invalid='true'] {
		border-color: var(--status-danger);
	}
	.crash-temp .unit {
		font-family: var(--font-num);
		color: var(--ink-secondary);
	}
	.crash-error {
		font-size: var(--text-xs);
		color: var(--status-danger);
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
