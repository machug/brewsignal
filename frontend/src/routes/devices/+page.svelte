<script lang="ts">
	import { onMount } from 'svelte';
	import { pairDevice, unpairDevice, type DeviceResponse } from '$lib/api/devices';
	import { deviceCache } from '$lib/stores/deviceCache.svelte';
	import { config, API_URL } from '$lib/config';
	import { authFetch } from '$lib/api';

	let devices = $state<DeviceResponse[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	// HTTP device setup state
	let systemIp = $state<string | null>(null);
	let ingestToken = $state<string | null>(null);
	let tokenLoading = $state(false);
	let copied = $state<string | null>(null);

	const ingestItems = [
		{ key: 'gravitymon', name: 'GravityMon', hint: "Enter this URL in your GravityMon's HTTP Post settings", href: 'https://github.com/mp-se/gravitymon/wiki' },
		{ key: 'ispindel', name: 'iSpindel', hint: "Enter this URL in your iSpindel's HTTP configuration", href: 'https://www.ispindel.de/docs/README_en.html' }
	] as const;

	onMount(async () => {
		// Try to load from cache first for instant display
		const cached = deviceCache.getCachedDevices();
		if (cached) {
			devices = cached;
			loading = false;
		}
		await loadDevices();
		await loadSetupInfo();
	});

	async function loadSetupInfo() {
		if (config.isLocalMode) {
			// Get system IP for local endpoint URL
			try {
				const res = await fetch(`${API_URL}/api/system/info`);
				if (res.ok) {
					const info = await res.json();
					// Use first non-localhost IP
					systemIp = info.ip_addresses?.find((ip: string) => !ip.startsWith('127.')) || null;
				}
			} catch (e) {
				console.error('Failed to get system info:', e);
			}
		} else {
			// Cloud mode - get or generate ingest token
			await loadIngestToken();
		}
	}

	async function loadIngestToken() {
		tokenLoading = true;
		try {
			const res = await authFetch(`${API_URL}/api/user/ingest-token`);
			if (res.ok) {
				const data = await res.json();
				ingestToken = data.token;
			}
		} catch (e) {
			console.error('Failed to get ingest token:', e);
		} finally {
			tokenLoading = false;
		}
	}

	async function regenerateToken() {
		tokenLoading = true;
		try {
			const res = await authFetch(`${API_URL}/api/user/ingest-token`, {
				method: 'POST'
			});
			if (res.ok) {
				const data = await res.json();
				ingestToken = data.token;
			}
		} catch (e) {
			console.error('Failed to regenerate token:', e);
		} finally {
			tokenLoading = false;
		}
	}

	function getIngestUrl(deviceType: 'gravitymon' | 'ispindel'): string {
		if (config.isLocalMode && systemIp) {
			return `http://${systemIp}:8080/api/ingest/${deviceType}`;
		} else if (config.isCloudMode && ingestToken) {
			return `https://api.brewsignal.io/api/ingest/${ingestToken}/${deviceType}`;
		}
		return '';
	}

	async function copyToClipboard(text: string, label: string) {
		try {
			await navigator.clipboard.writeText(text);
			copied = label;
			setTimeout(() => copied = null, 2000);
		} catch (e) {
			console.error('Failed to copy:', e);
		}
	}

	async function loadDevices(forceRefresh = false) {
		loading = true;
		error = null;
		try {
			devices = await deviceCache.getDevices(forceRefresh);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load devices';
		} finally {
			loading = false;
		}
	}

	async function handlePair(deviceId: string) {
		error = null;
		try {
			await pairDevice(deviceId);
			deviceCache.invalidate();
			await loadDevices(true);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to pair device';
		}
	}

	async function handleUnpair(deviceId: string) {
		error = null;
		try {
			await unpairDevice(deviceId);
			deviceCache.invalidate();
			await loadDevices(true);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to unpair device';
		}
	}

	function timeSince(isoString: string | null): string {
		if (!isoString) return 'Never seen';
		const seconds = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000);
		if (seconds < 10) return 'just now';
		if (seconds < 60) return `${seconds}s ago`;
		const minutes = Math.floor(seconds / 60);
		if (minutes < 60) return `${minutes}m ago`;
		const hours = Math.floor(minutes / 60);
		if (hours < 24) return `${hours}h ago`;
		const days = Math.floor(hours / 24);
		return `${days}d ago`;
	}

	function getDeviceDisplayName(device: DeviceResponse): string {
		if (device.display_name) return device.display_name;
		if (device.device_type === 'tilt' && device.color) {
			return `${device.color} Tilt`;
		}
		if (device.device_type === 'ispindel') {
			return `iSpindel ${device.name}`;
		}
		if (device.device_type === 'gravitymon') {
			return `GravityMon ${device.name}`;
		}
		return device.name;
	}

	function getDeviceTypeLabel(deviceType: string): string {
		const labels: Record<string, string> = {
			tilt: 'Tilt',
			ispindel: 'iSpindel',
			gravitymon: 'GravityMon',
			floaty: 'Floaty'
		};
		return labels[deviceType] || deviceType;
	}

	let pairedDevices = $derived(devices.filter(d => d.paired));
	let unpairedDevices = $derived(devices.filter(d => !d.paired));
</script>

<svelte:head>
	<title>Devices | BrewSignal</title>
</svelte:head>

{#snippet ingestRows()}
	<ul class="ledger setup-ledger">
		{#each ingestItems as item}
			<li class="setup-row">
				<div class="setup-meta">
					<h3 class="setup-name">{item.name}</h3>
					<p class="setup-description">{item.hint}</p>
					<a href={item.href} target="_blank" rel="noopener" class="docs-link">
						{item.name} setup guide
					</a>
				</div>
				<div class="url-display">
					<code>{getIngestUrl(item.key)}</code>
					<button class="btn-secondary btn-sm" onclick={() => copyToClipboard(getIngestUrl(item.key), item.key)}>
						{copied === item.key ? 'Copied' : 'Copy'}
					</button>
				</div>
			</li>
		{/each}
	</ul>
{/snippet}

{#snippet deviceRow(device: DeviceResponse, paired: boolean)}
	<li class="device-row">
		<div class="device-info">
			{#if device.device_type === 'tilt' && device.color}
				<span class="swatch" style="background: var(--tilt-{device.color.toLowerCase()})" aria-hidden="true"></span>
			{:else}
				<span class="type-badge">{getDeviceTypeLabel(device.device_type)}</span>
			{/if}
			<div class="device-id-block">
				<h3 class="device-name">{getDeviceDisplayName(device)}</h3>
				<p class="device-id">
					{device.id}{#if device.device_type === 'tilt' && device.mac}&nbsp;/&nbsp;{device.mac}{/if}
				</p>
				{#if device.beer_name}<p class="device-beer">{device.beer_name}</p>{/if}
			</div>
		</div>

		<div class="cell">
			<span class="pill" class:pill-on={paired}>{paired ? 'Paired' : 'Unpaired'}</span>
		</div>

		<div class="cell num">
			<span class="cell-label">Last seen</span>
			{timeSince(device.last_seen)}
		</div>
		<div class="cell num">
			<span class="cell-label">Battery</span>
			{#if (device.device_type === 'ispindel' || device.device_type === 'gravitymon') && device.battery_voltage !== null && Number.isFinite(device.battery_voltage)}
				{device.battery_voltage.toFixed(2)}&thinsp;V
			{:else}
				&ndash;
			{/if}
		</div>
		<div class="cell num">
			<span class="cell-label">Firmware</span>
			{device.firmware_version ?? '–'}
		</div>

		<div class="device-action">
			{#if paired}
				<button onclick={() => handleUnpair(device.id)} class="btn-secondary btn-sm">Unpair Device</button>
			{:else}
				<button onclick={() => handlePair(device.id)} class="btn-secondary btn-sm">Pair Device</button>
			{/if}
		</div>
	</li>
{/snippet}

{#snippet ledgerHead()}
	<div class="ledger-head" aria-hidden="true">
		<span>Device</span>
		<span>Status</span>
		<span>Last seen</span>
		<span>Battery</span>
		<span>Firmware</span>
		<span></span>
	</div>
{/snippet}

<nav class="crumbs" aria-label="Breadcrumb">
	<a href="/system">System</a>
	<span aria-hidden="true">/</span>
	<span aria-current="page">Devices</span>
</nav>

<div class="page-header">
	<h1 class="page-title">Devices</h1>
	<p class="page-description">Manage your hydrometer devices (Tilt, iSpindel, GravityMon)</p>
</div>

<!-- HTTP Device Setup Section -->
<section class="section">
	<h2 class="section-title">HTTP Device Setup</h2>
	<p class="section-description">
		Configure your GravityMon or iSpindel to send data to BrewSignal
	</p>

	{#if config.isLocalMode}
		{#if systemIp}
			{@render ingestRows()}

			<div class="setup-note">
				<strong>Tilt Hydrometers</strong> are automatically detected via Bluetooth - no configuration needed.
			</div>
		{:else}
			<div class="setup-loading">Loading network information...</div>
		{/if}
	{:else}
		<!-- Cloud mode -->
		{#if tokenLoading}
			<div class="setup-loading">Loading your ingest token...</div>
		{:else if ingestToken}
			{@render ingestRows()}

			<div class="token-section">
				<p class="token-note">
					Ingest token <code class="token-display">{ingestToken.slice(0, 8)}...{ingestToken.slice(-4)}</code>
				</p>
				<button class="btn-secondary btn-sm" onclick={regenerateToken} disabled={tokenLoading}>
					Regenerate Token
				</button>
				<p class="token-warning">
					<span class="pill pill-warn">Warning</span>
					Regenerating will invalidate URLs configured in your devices
				</p>
			</div>

			<div class="setup-note">
				<strong>Tilt Hydrometers</strong> require a BrewSignal Gateway device for cloud connectivity.
				<a href="/system">Configure your gateway</a> in System Settings.
			</div>
		{:else}
			<div class="setup-error" role="alert">Unable to load ingest token. Please try refreshing the page.</div>
		{/if}
	{/if}
</section>

{#if loading}
	<div class="loading-state">Loading devices...</div>
{:else if error}
	<div class="error-state" role="alert">
		<p>{error}</p>
		<button onclick={() => loadDevices(true)} class="btn-secondary">Retry</button>
	</div>
{:else}
	<section class="section">
		<h2 class="section-title">Paired Devices <span class="count">{pairedDevices.length}</span></h2>
		<p class="section-description">These devices are actively logging readings</p>

		{#if pairedDevices.length === 0}
			<div class="empty-state">
				<p>No paired devices. Pair a device below to start logging readings.</p>
			</div>
		{:else}
			{@render ledgerHead()}
			<ul class="ledger">
				{#each pairedDevices as device}
					{@render deviceRow(device, true)}
				{/each}
			</ul>
		{/if}
	</section>

	<section class="section">
		<h2 class="section-title">Detected Devices <span class="count">{unpairedDevices.length}</span></h2>
		<p class="section-description">These devices are detected but not logging readings</p>

		{#if unpairedDevices.length === 0}
			<div class="empty-state">
				<p>No unpaired devices detected. Make sure your devices are broadcasting and within range.</p>
			</div>
		{:else}
			{@render ledgerHead()}
			<ul class="ledger">
				{#each unpairedDevices as device}
					{@render deviceRow(device, false)}
				{/each}
			</ul>
		{/if}
	</section>
{/if}

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
	.section {
		margin-bottom: var(--space-xl);
	}
	.section-title {
		font-family: var(--font-display);
		font-size: var(--text-lg);
		font-weight: 600;
		color: var(--ink-primary);
		padding-top: var(--space-md);
		border-top: 1px solid var(--rule-strong);
	}
	.count {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: var(--text-sm);
		font-weight: 500;
		color: var(--ink-muted);
		margin-left: var(--space-2xs);
	}
	.section-description {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		margin: var(--space-2xs) 0 var(--space-md);
	}

	/* Buttons */
	.btn-secondary {
		min-height: 44px;
		padding: 0 var(--space-md);
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		border-radius: 4px;
		cursor: pointer;
		white-space: nowrap;
	}
	.btn-secondary {
		color: var(--ink-primary);
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
	}
	.btn-secondary:hover:not(:disabled) {
		background: var(--accent-tint);
		border-color: var(--accent-rule);
	}
	.btn-secondary:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
	.btn-sm {
		font-size: var(--text-xs);
	}
	/* Pills */
	.pill {
		display: inline-flex;
		align-items: center;
		padding: 2px var(--space-xs);
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--ink-muted);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
	}
	.pill-on {
		color: var(--status-steady);
		border-color: color-mix(in oklch, var(--status-steady) 60%, transparent);
	}
	.pill-warn {
		color: var(--status-warn);
		border-color: color-mix(in oklch, var(--status-warn) 60%, transparent);
	}

	/* Ledgers */
	.ledger {
		list-style: none;
		margin: 0;
		padding: 0;
		border-top: 1px solid var(--rule-hairline);
	}
	.device-row,
	.ledger-head {
		display: grid;
		grid-template-columns: minmax(10rem, 1.6fr) 6rem repeat(3, minmax(7rem, 1fr)) 8.5rem;
		align-items: center;
		gap: var(--space-md);
	}
	.device-row {
		padding: var(--space-sm) var(--space-xs);
		border-bottom: 1px solid var(--rule-hairline);
	}
	.ledger-head {
		padding: var(--space-xs);
		border-bottom: 1px solid var(--rule-strong);
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--ink-muted);
	}
	.ledger-head + .ledger {
		border-top: 0;
	}
	.cell {
		min-width: 0;
		font-size: var(--text-sm);
		color: var(--ink-primary);
	}
	.cell.num {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		overflow-wrap: anywhere;
	}
	.cell-label {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
		white-space: nowrap;
	}
	.device-beer {
		font-size: var(--text-xs);
		color: var(--ink-secondary);
	}
	.device-info {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		min-width: 0;
	}
	.swatch {
		flex: none;
		width: 0.875rem;
		height: 2rem;
		border-radius: 2px;
	}
	.type-badge {
		flex: none;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-width: 3.5rem;
		padding: 2px var(--space-xs);
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--ink-secondary);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
	}
	.device-id-block {
		min-width: 0;
	}
	.device-name {
		font-family: var(--font-display);
		font-size: var(--text-base);
		font-weight: 600;
		color: var(--ink-primary);
	}
	.device-id {
		font-family: var(--font-num);
		font-size: var(--text-xs);
		color: var(--ink-muted);
		overflow-wrap: anywhere;
	}
	.device-action {
		display: flex;
		justify-content: flex-end;
	}

	/* Setup ledger */
	.setup-row {
		display: grid;
		grid-template-columns: minmax(0, 1fr) minmax(0, 1.4fr);
		gap: var(--space-md);
		align-items: center;
		padding: var(--space-sm) var(--space-xs);
		border-bottom: 1px solid var(--rule-hairline);
	}
	.setup-name {
		font-family: var(--font-display);
		font-size: var(--text-base);
		font-weight: 600;
		color: var(--ink-primary);
	}
	.setup-description {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}
	.docs-link,
	.setup-note a {
		color: var(--accent);
		font-size: var(--text-sm);
		display: inline-flex;
		align-items: center;
		min-height: 44px;
	}
	.docs-link:hover,
	.setup-note a:hover {
		color: var(--accent-hover);
	}
	.url-display {
		display: flex;
		gap: var(--space-xs);
		align-items: center;
		min-width: 0;
	}
	.url-display code,
	.token-display {
		font-family: var(--font-num);
		font-size: var(--text-xs);
		color: var(--ink-primary);
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		padding: var(--space-xs) var(--space-sm);
	}
	.url-display code {
		flex: 1;
		min-width: 0;
		overflow-wrap: anywhere;
	}
	.setup-note {
		margin-top: var(--space-md);
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}
	.setup-note strong {
		color: var(--ink-primary);
	}
	.token-section {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-sm) var(--space-md);
		margin-top: var(--space-md);
		padding-top: var(--space-sm);
		border-top: 1px solid var(--rule-hairline);
	}
	.token-note {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}
	.token-warning {
		flex-basis: 100%;
		display: flex;
		align-items: center;
		gap: var(--space-xs);
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}

	/* States */
	.setup-loading,
	.loading-state,
	.empty-state {
		padding: var(--space-md) var(--space-xs);
		font-size: var(--text-sm);
		color: var(--ink-muted);
		border-top: 1px solid var(--rule-hairline);
	}
	.setup-error,
	.error-state {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-md);
		padding: var(--space-sm) var(--space-md);
		font-size: var(--text-sm);
		color: var(--status-danger);
		border: 1px solid color-mix(in oklch, var(--status-danger) 60%, transparent);
		border-radius: 4px;
	}

	@media (max-width: 1040px) {
		.ledger-head {
			display: none;
		}
		.device-row {
			grid-template-columns: repeat(3, minmax(0, 1fr));
		}
		.device-info {
			grid-column: 1 / 3;
		}
		.device-row > .cell:nth-child(2) {
			justify-self: end;
		}
		.device-action {
			grid-column: 1 / -1;
			justify-content: flex-start;
		}
		.cell-label {
			position: static;
			display: block;
			width: auto;
			height: auto;
			clip: auto;
			font-family: var(--font-display);
			font-size: var(--text-xs);
			font-weight: 600;
			text-transform: uppercase;
			letter-spacing: 0.07em;
			color: var(--ink-muted);
		}
	}
	@media (max-width: 760px) {
		.setup-row {
			grid-template-columns: minmax(0, 1fr);
		}
		.device-action .btn-secondary {
			width: 100%;
		}
	}
</style>
