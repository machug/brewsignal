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

<div class="page-header">
	<h1 class="page-title">Devices</h1>
	<p class="page-description">Manage your hydrometer devices (Tilt, iSpindel, GravityMon)</p>
</div>

<!-- HTTP Device Setup Section -->
<section class="setup-section">
	<h2 class="section-title">HTTP Device Setup</h2>
	<p class="section-description">
		Configure your GravityMon or iSpindel to send data to BrewSignal
	</p>

	{#if config.isLocalMode}
		{#if systemIp}
			<div class="setup-cards">
				<div class="setup-card">
					<div class="setup-card-header">
						<span class="setup-icon">📡</span>
						<h3>GravityMon</h3>
					</div>
					<p class="setup-description">Enter this URL in your GravityMon's HTTP Post settings</p>
					<div class="url-display">
						<code>{getIngestUrl('gravitymon')}</code>
						<button
							class="copy-btn"
							onclick={() => copyToClipboard(getIngestUrl('gravitymon'), 'gravitymon')}
						>
							{copied === 'gravitymon' ? '✓ Copied' : 'Copy'}
						</button>
					</div>
					<a href="https://github.com/mp-se/gravitymon/wiki" target="_blank" rel="noopener" class="docs-link">
						GravityMon Setup Guide →
					</a>
				</div>

				<div class="setup-card">
					<div class="setup-card-header">
						<span class="setup-icon">🧪</span>
						<h3>iSpindel</h3>
					</div>
					<p class="setup-description">Enter this URL in your iSpindel's HTTP configuration</p>
					<div class="url-display">
						<code>{getIngestUrl('ispindel')}</code>
						<button
							class="copy-btn"
							onclick={() => copyToClipboard(getIngestUrl('ispindel'), 'ispindel')}
						>
							{copied === 'ispindel' ? '✓ Copied' : 'Copy'}
						</button>
					</div>
					<a href="https://www.ispindel.de/docs/README_en.html" target="_blank" rel="noopener" class="docs-link">
						iSpindel Setup Guide →
					</a>
				</div>
			</div>

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
			<div class="setup-cards">
				<div class="setup-card">
					<div class="setup-card-header">
						<span class="setup-icon">📡</span>
						<h3>GravityMon</h3>
					</div>
					<p class="setup-description">Enter this URL in your GravityMon's HTTP Post settings</p>
					<div class="url-display">
						<code>{getIngestUrl('gravitymon')}</code>
						<button
							class="copy-btn"
							onclick={() => copyToClipboard(getIngestUrl('gravitymon'), 'gravitymon')}
						>
							{copied === 'gravitymon' ? '✓ Copied' : 'Copy'}
						</button>
					</div>
					<a href="https://github.com/mp-se/gravitymon/wiki" target="_blank" rel="noopener" class="docs-link">
						GravityMon Setup Guide →
					</a>
				</div>

				<div class="setup-card">
					<div class="setup-card-header">
						<span class="setup-icon">🧪</span>
						<h3>iSpindel</h3>
					</div>
					<p class="setup-description">Enter this URL in your iSpindel's HTTP configuration</p>
					<div class="url-display">
						<code>{getIngestUrl('ispindel')}</code>
						<button
							class="copy-btn"
							onclick={() => copyToClipboard(getIngestUrl('ispindel'), 'ispindel')}
						>
							{copied === 'ispindel' ? '✓ Copied' : 'Copy'}
						</button>
					</div>
					<a href="https://www.ispindel.de/docs/README_en.html" target="_blank" rel="noopener" class="docs-link">
						iSpindel Setup Guide →
					</a>
				</div>
			</div>

			<div class="token-section">
				<p class="token-note">
					Your ingest token: <code class="token-display">{ingestToken.slice(0, 8)}...{ingestToken.slice(-4)}</code>
				</p>
				<button class="btn-secondary btn-sm" onclick={regenerateToken} disabled={tokenLoading}>
					Regenerate Token
				</button>
				<p class="token-warning">
					⚠️ Regenerating will invalidate URLs configured in your devices
				</p>
			</div>

			<div class="setup-note">
				<strong>Tilt Hydrometers</strong> require a BrewSignal Gateway device for cloud connectivity.
				<a href="/system">Configure your gateway</a> in System Settings.
			</div>
		{:else}
			<div class="setup-error">Unable to load ingest token. Please try refreshing the page.</div>
		{/if}
	{/if}
</section>

{#if loading}
	<div class="loading-state">Loading devices...</div>
{:else if error}
	<div class="error-state">
		<p>{error}</p>
		<button onclick={() => loadDevices(true)} class="btn-secondary">Retry</button>
	</div>
{:else}
	<div class="devices-container">
		<!-- Paired Devices Section -->
		<section class="device-section">
			<h2 class="section-title">Paired Devices ({pairedDevices.length})</h2>
			<p class="section-description">These devices are actively logging readings</p>

			{#if pairedDevices.length === 0}
				<div class="empty-state">
					<p>No paired devices. Pair a device below to start logging readings.</p>
				</div>
			{:else}
				<div class="device-grid">
					{#each pairedDevices as device}
						<div class="device-card paired">
							<div class="device-header">
								<div class="device-info">
									{#if device.device_type === 'tilt' && device.color}
										<div class="device-color-badge" style="background: var(--tilt-{device.color.toLowerCase()})"></div>
									{:else}
										<div class="device-type-badge">
											<span class="device-type-label">{getDeviceTypeLabel(device.device_type)}</span>
										</div>
									{/if}
									<div>
										<h3 class="device-name">{getDeviceDisplayName(device)}</h3>
										<p class="device-id">{device.id}</p>
									</div>
								</div>
								<div class="device-status paired">
									<span class="status-dot"></span>
									Paired
								</div>
							</div>

							<div class="device-details">
								{#if device.beer_name}
									<div class="detail-row">
										<span class="detail-label">Beer Name:</span>
										<span class="detail-value">{device.beer_name}</span>
									</div>
								{/if}
								<div class="detail-row">
									<span class="detail-label">Last Seen:</span>
									<span class="detail-value">{timeSince(device.last_seen)}</span>
								</div>
								{#if device.device_type === 'tilt' && device.mac}
									<div class="detail-row">
										<span class="detail-label">MAC:</span>
										<span class="detail-value mono">{device.mac}</span>
									</div>
								{/if}
								{#if (device.device_type === 'ispindel' || device.device_type === 'gravitymon') && device.battery_voltage !== null && Number.isFinite(device.battery_voltage)}
									<div class="detail-row">
										<span class="detail-label">Battery:</span>
										<span class="detail-value">{device.battery_voltage.toFixed(2)}V</span>
									</div>
								{/if}
								{#if device.firmware_version}
									<div class="detail-row">
										<span class="detail-label">Firmware:</span>
										<span class="detail-value">{device.firmware_version}</span>
									</div>
								{/if}
							</div>

							<button
								onclick={() => handleUnpair(device.id)}
								class="btn-secondary btn-sm"
							>
								Unpair Device
							</button>
						</div>
					{/each}
				</div>
			{/if}
		</section>

		<!-- Unpaired Devices Section -->
		<section class="device-section">
			<h2 class="section-title">Detected Devices ({unpairedDevices.length})</h2>
			<p class="section-description">These devices are detected but not logging readings</p>

			{#if unpairedDevices.length === 0}
				<div class="empty-state">
					<p>No unpaired devices detected. Make sure your devices are broadcasting and within range.</p>
				</div>
			{:else}
				<div class="device-grid">
					{#each unpairedDevices as device}
						<div class="device-card unpaired">
							<div class="device-header">
								<div class="device-info">
									{#if device.device_type === 'tilt' && device.color}
										<div class="device-color-badge" style="background: var(--tilt-{device.color.toLowerCase()})"></div>
									{:else}
										<div class="device-type-badge">
											<span class="device-type-label">{getDeviceTypeLabel(device.device_type)}</span>
										</div>
									{/if}
									<div>
										<h3 class="device-name">{getDeviceDisplayName(device)}</h3>
										<p class="device-id">{device.id}</p>
									</div>
								</div>
								<div class="device-status unpaired">
									<span class="status-dot"></span>
									Unpaired
								</div>
							</div>

							<div class="device-details">
								<div class="detail-row">
									<span class="detail-label">Last Seen:</span>
									<span class="detail-value">{timeSince(device.last_seen)}</span>
								</div>
								{#if device.device_type === 'tilt' && device.mac}
									<div class="detail-row">
										<span class="detail-label">MAC:</span>
										<span class="detail-value mono">{device.mac}</span>
									</div>
								{/if}
								{#if (device.device_type === 'ispindel' || device.device_type === 'gravitymon') && device.battery_voltage !== null && Number.isFinite(device.battery_voltage)}
									<div class="detail-row">
										<span class="detail-label">Battery:</span>
										<span class="detail-value">{device.battery_voltage.toFixed(2)}V</span>
									</div>
								{/if}
								{#if device.firmware_version}
									<div class="detail-row">
										<span class="detail-label">Firmware:</span>
										<span class="detail-value">{device.firmware_version}</span>
									</div>
								{/if}
							</div>

							<button
								onclick={() => handlePair(device.id)}
								class="btn-primary btn-sm"
							>
								Pair Device
							</button>
						</div>
					{/each}
				</div>
			{/if}
		</section>
	</div>
{/if}

<style>
	.page-header {
		margin-bottom: 2rem;
	}

	.page-title {
		font-size: 1.875rem;
		font-weight: 700;
		color: var(--text-primary);
		margin-bottom: 0.5rem;
	}

	.page-description {
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	.devices-container {
		display: flex;
		flex-direction: column;
		gap: 3rem;
	}

	.device-section {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.5rem;
		padding: 1.5rem;
	}

	.section-title {
		font-size: 1.25rem;
		font-weight: 600;
		color: var(--text-primary);
		margin-bottom: 0.25rem;
	}

	.section-description {
		font-size: 0.875rem;
		color: var(--text-muted);
		margin-bottom: 1.5rem;
	}

	.device-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
		gap: 1rem;
	}

	.device-card {
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
		border-radius: 0.5rem;
		padding: 1.25rem;
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.device-card.paired {
		border-left: 3px solid var(--positive);
	}

	.device-card.unpaired {
		border-left: 3px solid var(--text-muted);
	}

	.device-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 1rem;
	}

	.device-info {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		flex: 1;
		min-width: 0;
	}

	.device-color-badge {
		width: 2.5rem;
		height: 2.5rem;
		border-radius: 0.375rem;
		flex-shrink: 0;
	}

	.device-type-badge {
		width: 2.5rem;
		height: 2.5rem;
		border-radius: 0.375rem;
		flex-shrink: 0;
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.device-type-label {
		font-size: 0.625rem;
		font-weight: 600;
		color: var(--text-secondary);
		text-transform: uppercase;
		text-align: center;
		line-height: 1.1;
	}

	.device-name {
		font-size: 1rem;
		font-weight: 600;
		color: var(--text-primary);
		margin-bottom: 0.125rem;
	}

	.device-id {
		font-size: 0.75rem;
		color: var(--text-muted);
		font-family: monospace;
	}

	.device-status {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		font-size: 0.75rem;
		font-weight: 500;
		padding: 0.25rem 0.625rem;
		border-radius: 9999px;
		white-space: nowrap;
	}

	.device-status.paired {
		background: var(--positive-muted);
		color: var(--positive);
	}

	.device-status.unpaired {
		background: var(--bg-hover);
		color: var(--text-muted);
	}

	.status-dot {
		width: 0.5rem;
		height: 0.5rem;
		border-radius: 50%;
		background: currentColor;
	}

	.device-details {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		padding: 0.75rem 0;
		border-top: 1px solid var(--border-subtle);
		border-bottom: 1px solid var(--border-subtle);
	}

	.detail-row {
		display: flex;
		justify-content: space-between;
		font-size: 0.8125rem;
	}

	.detail-label {
		color: var(--text-muted);
	}

	.detail-value {
		color: var(--text-secondary);
		font-weight: 500;
	}

	.detail-value.mono {
		font-family: monospace;
		font-size: 0.75rem;
	}

	.btn-primary,
	.btn-secondary {
		padding: 0.5rem 1rem;
		border-radius: 0.375rem;
		font-size: 0.875rem;
		font-weight: 500;
		cursor: pointer;
		transition: all var(--transition);
		border: 1px solid transparent;
	}

	.btn-primary {
		background: var(--accent);
		color: white;
	}

	.btn-primary:hover {
		background: var(--accent-hover);
	}

	.btn-secondary {
		background: var(--bg-surface);
		border-color: var(--border-default);
		color: var(--text-secondary);
	}

	.btn-secondary:hover {
		background: var(--bg-hover);
		color: var(--text-primary);
	}

	.btn-sm {
		padding: 0.375rem 0.75rem;
		font-size: 0.8125rem;
	}

	.empty-state {
		padding: 2rem;
		text-align: center;
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	.loading-state {
		padding: 3rem;
		text-align: center;
		color: var(--text-muted);
	}

	.error-state {
		padding: 2rem;
		text-align: center;
		color: var(--negative);
	}

	.error-state button {
		margin-top: 1rem;
	}

	/* HTTP Device Setup Section */
	.setup-section {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.5rem;
		padding: 1.5rem;
		margin-bottom: 2rem;
	}

	.setup-cards {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
		gap: 1rem;
		margin-bottom: 1rem;
	}

	.setup-card {
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
		border-radius: 0.5rem;
		padding: 1.25rem;
	}

	.setup-card-header {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-bottom: 0.5rem;
	}

	.setup-card-header h3 {
		font-size: 1rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
	}

	.setup-icon {
		font-size: 1.25rem;
	}

	.setup-description {
		font-size: 0.8125rem;
		color: var(--text-muted);
		margin-bottom: 0.75rem;
	}

	.url-display {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 0.375rem;
		padding: 0.5rem 0.75rem;
		margin-bottom: 0.75rem;
	}

	.url-display code {
		flex: 1;
		font-family: var(--font-mono);
		font-size: 0.75rem;
		color: var(--accent);
		word-break: break-all;
	}

	.copy-btn {
		padding: 0.25rem 0.5rem;
		font-size: 0.75rem;
		font-weight: 500;
		background: var(--accent);
		color: white;
		border: none;
		border-radius: 0.25rem;
		cursor: pointer;
		white-space: nowrap;
		transition: background var(--transition);
	}

	.copy-btn:hover {
		background: var(--accent-hover);
	}

	.docs-link {
		font-size: 0.8125rem;
		color: var(--accent);
		text-decoration: none;
	}

	.docs-link:hover {
		text-decoration: underline;
	}

	.setup-note {
		font-size: 0.8125rem;
		color: var(--text-muted);
		padding: 0.75rem;
		background: var(--bg-elevated);
		border-radius: 0.375rem;
		border-left: 3px solid var(--accent);
	}

	.setup-note a {
		color: var(--accent);
		text-decoration: none;
	}

	.setup-note a:hover {
		text-decoration: underline;
	}

	.setup-loading,
	.setup-error {
		padding: 1.5rem;
		text-align: center;
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	.setup-error {
		color: var(--negative);
	}

	.token-section {
		margin-top: 1rem;
		padding: 1rem;
		background: var(--bg-elevated);
		border-radius: 0.375rem;
		border: 1px solid var(--border-subtle);
	}

	.token-note {
		font-size: 0.8125rem;
		color: var(--text-secondary);
		margin-bottom: 0.5rem;
	}

	.token-display {
		font-family: var(--font-mono);
		font-size: 0.75rem;
		padding: 0.125rem 0.375rem;
		background: var(--bg-surface);
		border-radius: 0.25rem;
		color: var(--text-muted);
	}

	.token-warning {
		font-size: 0.75rem;
		color: var(--warning);
		margin-top: 0.5rem;
	}
</style>
