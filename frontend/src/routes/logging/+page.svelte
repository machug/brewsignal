<script lang="ts">
	import { onMount } from 'svelte';
	import { configState, updateConfig } from '$lib/stores/config.svelte';

	interface Stats {
		total_readings: number;
		oldest_reading: string | null;
		newest_reading: string | null;
		estimated_size_bytes: number;
	}

	let stats = $state<Stats | null>(null);
	let loading = $state(true);
	let saving = $state(false);

	// Local form state
	let loggingEnabled = $state(true);
	let intervalMinutes = $state(15);

	async function loadStats() {
		try {
			const response = await fetch('/api/stats');
			if (response.ok) {
				stats = await response.json();
			}
		} catch (e) {
			console.error('Failed to load stats:', e);
		} finally {
			loading = false;
		}
	}

	function syncFromConfig() {
		loggingEnabled = configState.config.local_logging_enabled;
		intervalMinutes = configState.config.local_interval_minutes;
	}

	async function saveSettings() {
		saving = true;
		try {
			await updateConfig({
				local_logging_enabled: loggingEnabled,
				local_interval_minutes: intervalMinutes
			});
		} finally {
			saving = false;
		}
	}

	function formatBytes(bytes: number): string {
		if (!Number.isFinite(bytes) || bytes < 0) return `${0} B`;
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	}

	function formatDate(isoString: string | null): string {
		if (!isoString) return 'N/A';
		return new Date(isoString).toLocaleString();
	}

	function formatNumber(n: number): string {
		return n.toLocaleString();
	}

	onMount(() => {
		loadStats();
		syncFromConfig();
	});

	// Sync when config loads
	$effect(() => {
		if (configState.loaded) {
			syncFromConfig();
		}
	});
</script>

<svelte:head>
	<title>Logging | BrewSignal</title>
</svelte:head>

<div class="page-container">
	<nav class="crumbs" aria-label="Breadcrumb">
		<a href="/system">System</a>
		<span aria-hidden="true">/</span>
		<span aria-current="page">Logging</span>
	</nav>
	
<div class="page-header">
		<h1 class="page-title">Logging</h1>
		<p class="page-description">Configure local data logging and export readings</p>
	</div>

	<div class="workbench">
		<!-- Logging Settings -->
		<section class="panel">
			<h2 class="panel-title">Settings</h2>

			<div class="setting-row">
				<div class="setting-info">
					<span class="setting-label">Local Logging</span>
					<span class="setting-description">Store readings to database</span>
				</div>
				<button
					type="button"
					class="toggle"
					class:active={loggingEnabled}
					onclick={() => (loggingEnabled = !loggingEnabled)}
					aria-pressed={loggingEnabled}
					aria-label="Toggle local logging"
				>
					<span class="toggle-text">{loggingEnabled ? 'On' : 'Off'}</span>
					<span class="toggle-slider"></span>
				</button>
			</div>

			<div class="setting-row">
				<div class="setting-info">
					<label class="setting-label" for="log-interval">Logging Interval</label>
					<span class="setting-description">How often to save readings</span>
				</div>
				<select
					id="log-interval"
					bind:value={intervalMinutes}
					class="select-input"
					disabled={!loggingEnabled}
				>
					<option value={1}>1 min</option>
					<option value={5}>5 min</option>
					<option value={10}>10 min</option>
					<option value={15}>15 min</option>
					<option value={30}>30 min</option>
					<option value={60}>60 min</option>
				</select>
			</div>

			<div class="actions">
				<button
					type="button"
					class="btn-primary"
					onclick={saveSettings}
					disabled={saving}
				>
					{#if saving}
						<span class="loading-dot"></span>
						Saving...
					{:else}
						Save Settings
					{/if}
				</button>
			</div>
		</section>

		<!-- Database Stats -->
		<section class="panel">
			<h2 class="panel-title">Database</h2>
			{#if loading}
				<div class="loading-state" role="status">
					<div class="loading-spinner"></div>
					<span>Loading statistics...</span>
				</div>
			{:else if stats}
				<dl class="stats-grid">
					<div class="stat-item">
						<dt class="stat-label">Total Readings</dt>
						<dd class="stat-value">{formatNumber(stats.total_readings)}</dd>
					</div>
					<div class="stat-item">
						<dt class="stat-label">Estimated Size</dt>
						<dd class="stat-value">{formatBytes(stats.estimated_size_bytes)}</dd>
					</div>
					<div class="stat-item full-width">
						<dt class="stat-label">Data Range</dt>
						<dd class="stat-range">
							{formatDate(stats.oldest_reading)} — {formatDate(stats.newest_reading)}
						</dd>
					</div>
				</dl>
			{:else}
				<p class="text-muted">No statistics available</p>
			{/if}
		</section>

		<!-- Export Section -->
		<section class="panel wide">
			<h2 class="panel-title">Export Data</h2>
			<div class="export-section">
				<p class="export-description">
					Download all recorded readings as a CSV file. The export includes timestamp,
					tilt ID, color, beer name, raw and calibrated values for SG and temperature,
					and signal strength.
				</p>
				<a
					href="/log.csv"
					download="tilt_readings.csv"
					class="btn-secondary"
				>
					<svg class="icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
						<path stroke-linecap="round" stroke-linejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
					</svg>
					Download CSV
				</a>
			</div>
		</section>
	</div>
</div>

<style>
	.crumbs {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
		padding-bottom: var(--space-xs);
		margin-bottom: var(--space-md);
		border-bottom: 1px solid var(--rule-hairline);
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--ink-muted);
	}
	.crumbs a {
		display: inline-flex;
		align-items: center;
		min-height: 44px;
		color: var(--ink-secondary);
	}
	.crumbs a:hover {
		color: var(--ink-primary);
		text-decoration: underline;
	}
	.page-header {
		margin-bottom: var(--space-lg);
	}
	.page-title {
		font-family: var(--font-display);
		font-size: var(--text-xl);
		font-weight: 700;
		letter-spacing: -0.02em;
		line-height: 1.15;
		color: var(--ink-primary);
	}
	.page-description {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		margin-top: var(--space-2xs);
	}
	.workbench {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0 var(--space-xl);
	}
	.panel {
		padding-top: var(--space-md);
		border-top: 1px solid var(--rule-strong);
		margin-bottom: var(--space-lg);
		min-width: 0;
	}
	.panel.wide {
		grid-column: 1 / -1;
	}
	.panel-title {
		font-family: var(--font-display);
		font-size: var(--text-lg);
		font-weight: 600;
		color: var(--ink-primary);
		margin-bottom: var(--space-sm);
	}

	/* Setting rows */
	.setting-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-md);
		min-height: 56px;
		padding: var(--space-sm) 0;
		border-top: 1px solid var(--rule-hairline);
	}
	.setting-info {
		display: flex;
		flex-direction: column;
		min-width: 0;
	}
	.setting-label {
		font-weight: 700;
		color: var(--ink-primary);
	}
	.setting-description {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}
	.toggle {
		display: inline-flex;
		align-items: center;
		gap: var(--space-xs);
		min-height: 44px;
		padding: 0 var(--space-xs);
		cursor: pointer;
	}
	.toggle-text {
		min-width: 1.75rem;
		text-align: right;
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--ink-muted);
	}
	.toggle.active .toggle-text {
		color: var(--status-steady);
	}
	.toggle-slider {
		position: relative;
		width: 2.5rem;
		height: 1.5rem;
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		background: var(--bg-subtle);
	}
	.toggle-slider::after {
		content: '';
		position: absolute;
		top: 2px;
		left: 2px;
		width: calc(1.5rem - 6px);
		height: calc(1.5rem - 6px);
		border-radius: 2px;
		background: var(--ink-muted);
		transition: transform 140ms var(--ease-out-quart);
	}
	.toggle.active .toggle-slider {
		border-color: var(--status-steady);
	}
	.toggle.active .toggle-slider::after {
		transform: translateX(1rem);
		background: var(--status-steady);
	}
	.toggle:focus-visible,
	.select-input:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}
	.select-input {
		min-height: 44px;
		min-width: 7rem;
		padding: 0 2rem 0 var(--space-sm);
		text-overflow: ellipsis;
		font-family: var(--font-num);
		font-size: var(--text-base);
		color: var(--ink-primary);
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
	}
	.select-input:disabled {
		opacity: 0.5;
	}
	.actions {
		padding-top: var(--space-md);
		border-top: 1px solid var(--rule-hairline);
	}

	/* Buttons */
	.btn-primary,
	.btn-secondary {
		display: inline-flex;
		align-items: center;
		gap: var(--space-xs);
		min-height: 44px;
		padding: 0 var(--space-md);
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		border-radius: 4px;
		cursor: pointer;
	}
	.btn-primary {
		color: var(--accent-ink);
		background: var(--accent);
	}
	.btn-primary:hover:not(:disabled) {
		background: var(--accent-hover);
	}
	.btn-primary:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}
	.btn-secondary {
		color: var(--ink-primary);
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
	}
	.btn-secondary:hover {
		background: var(--accent-tint);
		border-color: var(--accent-rule);
	}
	.icon {
		width: 1rem;
		height: 1rem;
	}
	.loading-dot {
		width: 0.5rem;
		height: 0.5rem;
		border-radius: 50%;
		background: currentColor;
		animation: pulse 1s ease-in-out infinite;
	}
	@keyframes pulse {
		50% {
			opacity: 0.3;
		}
	}

	/* Stats */
	.stats-grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		margin: 0;
		border: 1px solid var(--rule-hairline);
		background: var(--bg-surface);
	}
	.stat-item {
		display: flex;
		flex-direction: column;
		gap: var(--space-2xs);
		padding: var(--space-sm);
		border-right: 1px solid var(--rule-hairline);
	}
	.stat-item:nth-child(2) {
		border-right: 0;
	}
	.stat-item.full-width {
		grid-column: 1 / -1;
		border-right: 0;
		border-top: 1px solid var(--rule-hairline);
	}
	.stat-label {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--ink-muted);
		order: -1;
	}
	.stat-value {
		margin: 0;
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: var(--text-lg);
		font-weight: 500;
		color: var(--ink-primary);
	}
	.stat-range {
		margin: 0;
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: var(--text-sm);
		color: var(--ink-primary);
	}
	.text-muted {
		font-size: var(--text-sm);
		color: var(--ink-muted);
	}
	.loading-state {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		font-size: var(--text-sm);
		color: var(--ink-muted);
	}
	.loading-spinner {
		width: 1.25rem;
		height: 1.25rem;
		border: 2px solid var(--rule-strong);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.9s linear infinite;
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	/* Export */
	.export-section {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-md);
		padding-top: var(--space-sm);
		border-top: 1px solid var(--rule-hairline);
	}
	.export-description {
		flex: 1 1 24rem;
		max-width: 48rem;
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}

	@media (max-width: 1040px) {
		.workbench {
			grid-template-columns: minmax(0, 1fr);
		}
	}
	@media (max-width: 760px) {
		.export-section .btn-secondary {
			width: 100%;
			justify-content: center;
		}
	}
</style>
