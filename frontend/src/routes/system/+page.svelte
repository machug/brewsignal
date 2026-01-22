<script lang="ts">
	import { onMount } from 'svelte';
	import { configState, updateConfig, fahrenheitToCelsius, celsiusToFahrenheit } from '$lib/stores/config.svelte';

	interface GPUInfo {
		vendor: string;  // "nvidia", "amd", "intel", "apple", "none"
		name: string | null;
		vram_mb: number | null;
	}

	interface PlatformInfo {
		is_raspberry_pi: boolean;
		model: string | null;
		architecture: string;
		gpu: GPUInfo;
	}

	interface SystemInfo {
		hostname: string;
		ip_addresses: string[];
		uptime_seconds: number | null;
		version: string;
		platform: PlatformInfo | null;
	}

	interface StorageStats {
		total_readings: number;
		oldest_reading: string | null;
		newest_reading: string | null;
		estimated_size_bytes: number;
	}

	interface AIAcceleratorDevice {
		path: string;
		architecture: string;
		firmware_version: string;
		tops: number;
	}

	interface AIAcceleratorStatus {
		available: boolean;
		device: AIAcceleratorDevice | null;
	}

	let systemInfo = $state<SystemInfo | null>(null);
	let storageStats = $state<StorageStats | null>(null);
	let aiAccelerator = $state<AIAcceleratorStatus | null>(null);
	let timezones = $state<string[]>([]);
	let currentTimezone = $state('');
	let loading = $state(true);
	let actionInProgress = $state<string | null>(null);

	// Config form state
	let tempUnits = $state<'C' | 'F'>('C');
	let sgUnits = $state<'sg' | 'plato' | 'brix'>('sg');
	let minRssi = $state(-100);
	let smoothingEnabled = $state(false);
	let smoothingSamples = $state(5);
	let idByMac = $state(false);
	let configSaving = $state(false);
	let configError = $state<string | null>(null);
	let configSuccess = $state(false);

	// Cleanup state
	let cleanupRetentionDays = $state(30);
	let cleanupPreview = $state<{ readings_to_delete: number } | null>(null);

	// Home Assistant state
	let haEnabled = $state(false);
	let haUrl = $state('');
	let haToken = $state('');
	let haAmbientTempEntityId = $state('');
	let haAmbientHumidityEntityId = $state('');
	let haChamberTempEntityId = $state('');
	let haChamberHumidityEntityId = $state('');
	let haWeatherEntityId = $state('');
	let haTesting = $state(false);
	let haTestResult = $state<{ success: boolean; message: string } | null>(null);
	let haStatus = $state<{ enabled: boolean; connected: boolean; url: string } | null>(null);
	let haSaving = $state(false);
	let haError = $state<string | null>(null);
	let haSuccess = $state(false);

	// Temperature Control state
	let tempControlEnabled = $state(false);
	let tempTarget = $state(68.0);
	let tempHysteresis = $state(1.0);
	let controlSaving = $state(false);
	let controlError = $state<string | null>(null);
	let controlSuccess = $state(false);

	// Weather Alerts state
	let weatherAlertsEnabled = $state(false);
	let alertTempThreshold = $state(3.0);
	let alertsSaving = $state(false);
	let alertsError = $state<string | null>(null);
	let alertsSuccess = $state(false);

	// AI Assistant state
	let aiEnabled = $state(false);
	let aiProvider = $state('local');
	let aiModel = $state('');
	let aiApiKey = $state('');
	let aiBaseUrl = $state('');
	let aiTemperature = $state(0.7);
	let aiMaxTokens = $state(2000);
	let aiSaving = $state(false);
	let aiError = $state<string | null>(null);
	let aiSuccess = $state(false);
	let aiTesting = $state(false);
	let aiTestResult = $state<{ success: boolean; response?: string; error?: string } | null>(null);
	let aiProviders = $state<Array<{ id: string; name: string; description: string; requires_api_key: boolean; setup_url: string }>>([]);
	let aiModels = $state<Array<{ id: string; name: string; description: string }>>([]);
	let aiHasEnvKey = $state(false);

	// Section expansion state
	let expandedSection = $state<string | null>('display');

	// Derived unit helpers
	let useCelsius = $derived(configState.config.temp_units === 'C');
	let tempUnitSymbol = $derived(useCelsius ? '°C' : '°F');

	// Convert temperature from display units to Fahrenheit for storage
	function toFahrenheit(temp: number): number {
		if (useCelsius) {
			return celsiusToFahrenheit(temp);
		}
		return temp;
	}

	// Convert temperature from Fahrenheit to display units
	function fromFahrenheit(tempF: number): number {
		if (useCelsius) {
			return fahrenheitToCelsius(tempF);
		}
		return tempF;
	}

	function toggleSection(section: string) {
		expandedSection = expandedSection === section ? null : section;
	}

	async function loadSystemInfo() {
		try {
			const response = await fetch('/api/system/info');
			if (response.ok) {
				systemInfo = await response.json();
			}
		} catch (e) {
			console.error('Failed to load system info:', e);
		}
	}

	async function loadStorageStats() {
		try {
			const response = await fetch('/api/system/storage');
			if (response.ok) {
				storageStats = await response.json();
			}
		} catch (e) {
			console.error('Failed to load storage stats:', e);
		}
	}

	async function loadAiAccelerator() {
		try {
			const response = await fetch('/api/system/ai-accelerator');
			if (response.ok) {
				aiAccelerator = await response.json();
			}
		} catch (e) {
			console.error('Failed to load AI accelerator status:', e);
		}
	}

	async function loadTimezones() {
		try {
			const [tzListRes, tzCurrentRes] = await Promise.all([
				fetch('/api/system/timezones'),
				fetch('/api/system/timezone')
			]);
			if (tzListRes.ok) {
				const data = await tzListRes.json();
				timezones = data.timezones || [];
			}
			if (tzCurrentRes.ok) {
				const data = await tzCurrentRes.json();
				currentTimezone = data.timezone || 'UTC';
			}
		} catch (e) {
			console.error('Failed to load timezones:', e);
		}
	}

	function syncConfigFromStore() {
		tempUnits = configState.config.temp_units;
		sgUnits = configState.config.sg_units;
		minRssi = configState.config.min_rssi;
		smoothingEnabled = configState.config.smoothing_enabled;
		smoothingSamples = configState.config.smoothing_samples;
		idByMac = configState.config.id_by_mac;
		// Home Assistant
		haEnabled = configState.config.ha_enabled;
		haUrl = configState.config.ha_url;
		haToken = configState.config.ha_token;
		haAmbientTempEntityId = configState.config.ha_ambient_temp_entity_id;
		haAmbientHumidityEntityId = configState.config.ha_ambient_humidity_entity_id;
		haChamberTempEntityId = configState.config.ha_chamber_temp_entity_id;
		haChamberHumidityEntityId = configState.config.ha_chamber_humidity_entity_id;
		haWeatherEntityId = configState.config.ha_weather_entity_id;
		// Temperature Control - convert from Fahrenheit to display units
		tempControlEnabled = configState.config.temp_control_enabled;
		tempTarget = Math.round(fromFahrenheit(configState.config.temp_target) * 2) / 2; // Round to nearest 0.5
		// Hysteresis: convert delta (°F delta to °C delta uses same ratio), round to 2 decimal places
		tempHysteresis = configState.config.temp_units === 'C'
			? Math.round(configState.config.temp_hysteresis * (5 / 9) * 100) / 100
			: configState.config.temp_hysteresis;
		// Weather Alerts
		weatherAlertsEnabled = configState.config.weather_alerts_enabled;
		alertTempThreshold = configState.config.alert_temp_threshold;
		// AI Assistant
		aiEnabled = configState.config.ai_enabled ?? false;
		aiProvider = configState.config.ai_provider ?? 'local';
		aiModel = configState.config.ai_model ?? '';
		aiApiKey = configState.config.ai_api_key ?? '';
		aiBaseUrl = configState.config.ai_base_url ?? '';
		aiTemperature = configState.config.ai_temperature ?? 0.7;
		aiMaxTokens = configState.config.ai_max_tokens ?? 2000;
	}

	async function loadAiProviders() {
		try {
			const response = await fetch('/api/assistant/providers');
			if (response.ok) {
				aiProviders = await response.json();
			}
		} catch (e) {
			console.error('Failed to load AI providers:', e);
		}
	}

	async function loadAiModels(provider: string) {
		try {
			const response = await fetch(`/api/assistant/models/${provider}`);
			if (response.ok) {
				const data = await response.json();
				aiModels = data.models;
			}
		} catch (e) {
			console.error('Failed to load AI models:', e);
			aiModels = [];
		}
	}

	async function loadAiStatus() {
		try {
			const response = await fetch('/api/assistant/status');
			if (response.ok) {
				const data = await response.json();
				aiHasEnvKey = data.has_env_api_key ?? false;
			}
		} catch (e) {
			console.error('Failed to load AI status:', e);
		}
	}

	async function saveAiConfig() {
		aiSaving = true;
		aiError = null;
		aiSuccess = false;

		try {
			await updateConfig({
				ai_enabled: aiEnabled,
				ai_provider: aiProvider,
				ai_model: aiModel,
				ai_api_key: aiApiKey,
				ai_base_url: aiBaseUrl,
				ai_temperature: aiTemperature,
				ai_max_tokens: aiMaxTokens
			});
			aiSuccess = true;
			setTimeout(() => (aiSuccess = false), 3000);
		} catch (e) {
			aiError = e instanceof Error ? e.message : 'Failed to save AI settings';
		} finally {
			aiSaving = false;
		}
	}

	async function testAiConnection() {
		aiTesting = true;
		aiTestResult = null;

		try {
			// First save the current config
			await updateConfig({
				ai_enabled: aiEnabled,
				ai_provider: aiProvider,
				ai_model: aiModel,
				ai_api_key: aiApiKey,
				ai_base_url: aiBaseUrl,
				ai_temperature: aiTemperature,
				ai_max_tokens: aiMaxTokens
			});

			// Then test the connection
			const response = await fetch('/api/assistant/test', { method: 'POST' });
			const result = await response.json();
			aiTestResult = result;
		} catch (e) {
			aiTestResult = { success: false, error: e instanceof Error ? e.message : 'Connection test failed' };
		} finally {
			aiTesting = false;
		}
	}

	// Watch for provider changes to load models
	$effect(() => {
		if (aiProvider) {
			loadAiModels(aiProvider);
		}
	});

	async function saveConfig() {
		configSaving = true;
		configError = null;
		configSuccess = false;
		try {
			const result = await updateConfig({
				temp_units: tempUnits,
				sg_units: sgUnits,
				min_rssi: minRssi,
				smoothing_enabled: smoothingEnabled,
				smoothing_samples: smoothingSamples,
				id_by_mac: idByMac
			});
			if (result.success) {
				configSuccess = true;
				setTimeout(() => (configSuccess = false), 3000);
			} else {
				configError = result.error || 'Failed to save settings';
			}
		} finally {
			configSaving = false;
		}
	}

	async function saveHAConfig() {
		haSaving = true;
		haError = null;
		haSuccess = false;
		try {
			const result = await updateConfig({
				ha_enabled: haEnabled,
				ha_url: haUrl,
				ha_token: haToken,
				ha_ambient_temp_entity_id: haAmbientTempEntityId,
				ha_ambient_humidity_entity_id: haAmbientHumidityEntityId,
				ha_chamber_temp_entity_id: haChamberTempEntityId,
				ha_chamber_humidity_entity_id: haChamberHumidityEntityId,
				ha_weather_entity_id: haWeatherEntityId
			});
			if (result.success) {
				haSuccess = true;
				setTimeout(() => (haSuccess = false), 3000);
				// Reload HA status after saving
				await loadHAStatus();
			} else {
				haError = result.error || 'Failed to save settings';
			}
		} finally {
			haSaving = false;
		}
	}

	async function saveControlConfig() {
		controlSaving = true;
		controlError = null;
		controlSuccess = false;
		try {
			// Convert from display units back to Fahrenheit for storage
			const targetF = toFahrenheit(tempTarget);
			// Hysteresis delta: convert from display units to Fahrenheit
			const hysteresisF = useCelsius ? tempHysteresis * (9 / 5) : tempHysteresis;

			const result = await updateConfig({
				temp_control_enabled: tempControlEnabled,
				temp_target: targetF,
				temp_hysteresis: hysteresisF
			});
			if (result.success) {
				controlSuccess = true;
				setTimeout(() => (controlSuccess = false), 3000);
			} else {
				controlError = result.error || 'Failed to save settings';
			}
		} finally {
			controlSaving = false;
		}
	}

	async function saveAlertsConfig() {
		alertsSaving = true;
		alertsError = null;
		alertsSuccess = false;
		try {
			const result = await updateConfig({
				weather_alerts_enabled: weatherAlertsEnabled,
				alert_temp_threshold: alertTempThreshold
			});
			if (result.success) {
				alertsSuccess = true;
				setTimeout(() => (alertsSuccess = false), 3000);
			} else {
				alertsError = result.error || 'Failed to save settings';
			}
		} finally {
			alertsSaving = false;
		}
	}

	async function setTimezone(tz: string) {
		actionInProgress = 'timezone';
		try {
			const response = await fetch('/api/system/timezone', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ timezone: tz })
			});
			if (response.ok) {
				currentTimezone = tz;
			}
		} catch (e) {
			console.error('Failed to set timezone:', e);
		} finally {
			actionInProgress = null;
		}
	}

	async function previewCleanup() {
		actionInProgress = 'cleanup-preview';
		try {
			const response = await fetch('/api/system/cleanup', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ retention_days: cleanupRetentionDays, confirm: false })
			});
			if (response.ok) {
				cleanupPreview = await response.json();
			}
		} catch (e) {
			console.error('Failed to preview cleanup:', e);
		} finally {
			actionInProgress = null;
		}
	}

	async function executeCleanup() {
		if (!cleanupPreview || cleanupPreview.readings_to_delete === 0) return;

		if (!confirm(`Delete ${cleanupPreview.readings_to_delete.toLocaleString()} readings older than ${cleanupRetentionDays} days?`)) {
			return;
		}

		actionInProgress = 'cleanup';
		try {
			const response = await fetch('/api/system/cleanup', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ retention_days: cleanupRetentionDays, confirm: true })
			});
			if (response.ok) {
				cleanupPreview = null;
				await loadStorageStats();
			}
		} catch (e) {
			console.error('Failed to execute cleanup:', e);
		} finally {
			actionInProgress = null;
		}
	}

	async function rebootSystem() {
		if (!confirm('Are you sure you want to reboot the system? The UI will be unavailable until restart completes.')) {
			return;
		}
		actionInProgress = 'reboot';
		try {
			await fetch('/api/system/reboot', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ confirm: true })
			});
		} catch (e) {
			console.error('Reboot command failed:', e);
		} finally {
			actionInProgress = null;
		}
	}

	async function shutdownSystem() {
		if (!confirm('Are you sure you want to shut down the system? You will need physical access to restart.')) {
			return;
		}
		actionInProgress = 'shutdown';
		try {
			await fetch('/api/system/shutdown', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ confirm: true })
			});
		} catch (e) {
			console.error('Shutdown command failed:', e);
		} finally {
			actionInProgress = null;
		}
	}

	function formatUptime(seconds: number | null): string {
		if (!seconds) return 'Unknown';
		const days = Math.floor(seconds / 86400);
		const hours = Math.floor((seconds % 86400) / 3600);
		const minutes = Math.floor((seconds % 3600) / 60);

		const parts = [];
		if (days > 0) parts.push(`${days}d`);
		if (hours > 0) parts.push(`${hours}h`);
		if (minutes > 0) parts.push(`${minutes}m`);
		return parts.length > 0 ? parts.join(' ') : '< 1m';
	}

	function formatBytes(bytes: number): string {
		if (!Number.isFinite(bytes) || bytes < 0) return '0 B';
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	}

	function formatNumber(n: number): string {
		return n.toLocaleString();
	}

	async function testHAConnection() {
		haTesting = true;
		haTestResult = null;
		try {
			const response = await fetch('/api/ha/test', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ url: haUrl, token: haToken })
			});
			if (response.ok) {
				haTestResult = await response.json();
			} else {
				haTestResult = { success: false, message: 'Request failed' };
			}
		} catch (e) {
			haTestResult = { success: false, message: 'Network error' };
		} finally {
			haTesting = false;
		}
	}

	async function loadHAStatus() {
		try {
			const response = await fetch('/api/ha/status');
			if (response.ok) {
				haStatus = await response.json();
			}
		} catch (e) {
			console.error('Failed to load HA status:', e);
		}
	}

	onMount(async () => {
		await Promise.all([
			loadSystemInfo(),
			loadStorageStats(),
			loadAiAccelerator(),
			loadTimezones(),
			loadHAStatus(),
			loadAiProviders(),
			loadAiStatus()
		]);
		syncConfigFromStore();
		loading = false;
	});

	// Sync config when loaded
	$effect(() => {
		if (configState.loaded) {
			syncConfigFromStore();
		}
	});
</script>

<svelte:head>
	<title>System | BrewSignal</title>
</svelte:head>

<div class="system-page">
	{#if loading}
		<div class="loading-state">
			<div class="loading-spinner"></div>
			<span>Loading system information...</span>
		</div>
	{:else}
		<!-- System Status Banner -->
		<header class="status-banner">
			<div class="status-grid">
				<div class="status-item">
					<span class="status-label">Hostname</span>
					<span class="status-value">{systemInfo?.hostname ?? 'Unknown'}</span>
				</div>
				<div class="status-item">
					<span class="status-label">Version</span>
					<span class="status-value">v{systemInfo?.version ?? '?'}</span>
				</div>
				<div class="status-item">
					<span class="status-label">Uptime</span>
					<span class="status-value">{formatUptime(systemInfo?.uptime_seconds ?? null)}</span>
				</div>
				<div class="status-item">
					<span class="status-label">IP Address</span>
					<span class="status-value">{systemInfo?.ip_addresses?.[0] ?? 'Unknown'}</span>
				</div>
				<div class="status-item">
					<span class="status-label">Readings</span>
					<span class="status-value">{storageStats ? formatNumber(storageStats.total_readings) : '—'}</span>
				</div>
				<div class="status-item ai-status" class:active={aiAccelerator?.available}>
					<span class="status-label">AI Accelerator</span>
					<span class="status-value">
						{#if aiAccelerator?.available && aiAccelerator.device}
							<span class="ai-chip">
								<span class="ai-dot"></span>
								{aiAccelerator.device.architecture}
								<span class="ai-tops">{aiAccelerator.device.tops} TOPS</span>
							</span>
						{:else}
							<span class="ai-unavailable">Not detected</span>
						{/if}
					</span>
				</div>
			</div>
		</header>

		<!-- Quick Links -->
		<nav class="quick-links">
			<a href="/devices" class="quick-link">
				<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
					<path stroke-linecap="round" stroke-linejoin="round" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
				</svg>
				<span>Devices</span>
			</a>
			<a href="/calibration" class="quick-link">
				<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
					<path stroke-linecap="round" stroke-linejoin="round" d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
				</svg>
				<span>Calibration</span>
			</a>
			<a href="/logging" class="quick-link">
				<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
					<path stroke-linecap="round" stroke-linejoin="round" d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
				</svg>
				<span>Logging</span>
			</a>
			<a href="/system/maintenance" class="quick-link">
				<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
					<path stroke-linecap="round" stroke-linejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
					<path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
				</svg>
				<span>Maintenance</span>
			</a>
		</nav>

		<!-- Settings Sections -->
		<div class="settings-container">
			<!-- Display & Units Section -->
			<section class="settings-section">
				<button
					type="button"
					class="section-header"
					onclick={() => toggleSection('display')}
					aria-expanded={expandedSection === 'display'}
				>
					<div class="section-title-group">
						<svg class="section-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
							<path stroke-linecap="round" stroke-linejoin="round" d="M10.5 6h9.75M10.5 6a1.5 1.5 0 11-3 0m3 0a1.5 1.5 0 10-3 0M3.75 6H7.5m3 12h9.75m-9.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-3.75 0H7.5m9-6h3.75m-3.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-9.75 0h9.75" />
						</svg>
						<h2>Display & Units</h2>
					</div>
					<svg class="chevron" class:rotated={expandedSection === 'display'} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
					</svg>
				</button>
				{#if expandedSection === 'display'}
					<div class="section-content">
						<div class="settings-grid">
							<div class="setting-group">
								<label class="setting-label">Temperature</label>
								<div class="toggle-group">
									<button type="button" class="toggle-btn" class:active={tempUnits === 'C'} onclick={() => (tempUnits = 'C')}>°C</button>
									<button type="button" class="toggle-btn" class:active={tempUnits === 'F'} onclick={() => (tempUnits = 'F')}>°F</button>
								</div>
							</div>
							<div class="setting-group">
								<label class="setting-label">Gravity</label>
								<div class="toggle-group triple">
									<button type="button" class="toggle-btn" class:active={sgUnits === 'sg'} onclick={() => (sgUnits = 'sg')}>SG</button>
									<button type="button" class="toggle-btn" class:active={sgUnits === 'plato'} onclick={() => (sgUnits = 'plato')}>°P</button>
									<button type="button" class="toggle-btn" class:active={sgUnits === 'brix'} onclick={() => (sgUnits = 'brix')}>°Bx</button>
								</div>
							</div>
							<div class="setting-group">
								<label class="setting-label">Min Signal</label>
								<div class="input-group">
									<input type="number" min="-100" max="0" bind:value={minRssi} class="num-input" />
									<span class="input-unit">dBm</span>
								</div>
							</div>
							<div class="setting-group">
								<label class="setting-label">Timezone</label>
								<select
									class="select-input"
									value={currentTimezone}
									onchange={(e) => setTimezone(e.currentTarget.value)}
									disabled={actionInProgress === 'timezone'}
								>
									{#each timezones as tz}
										<option value={tz}>{tz}</option>
									{/each}
								</select>
							</div>
						</div>

						<div class="settings-divider"></div>

						<div class="toggle-settings">
							<div class="toggle-setting">
								<div class="toggle-info">
									<span class="toggle-label">Reading Smoothing</span>
									<span class="toggle-desc">Average readings to reduce noise</span>
								</div>
								<div class="toggle-controls">
									{#if smoothingEnabled}
										<select bind:value={smoothingSamples} class="mini-select">
											<option value={3}>3</option>
											<option value={5}>5</option>
											<option value={10}>10</option>
											<option value={15}>15</option>
											<option value={20}>20</option>
										</select>
									{/if}
									<button
										type="button"
										class="switch"
										class:on={smoothingEnabled}
										onclick={() => (smoothingEnabled = !smoothingEnabled)}
										aria-pressed={smoothingEnabled}
									>
										<span class="switch-thumb"></span>
									</button>
								</div>
							</div>
							<div class="toggle-setting">
								<div class="toggle-info">
									<span class="toggle-label">Identify by MAC</span>
									<span class="toggle-desc">Use MAC address instead of broadcast ID</span>
								</div>
								<button
									type="button"
									class="switch"
									class:on={idByMac}
									onclick={() => (idByMac = !idByMac)}
									aria-pressed={idByMac}
								>
									<span class="switch-thumb"></span>
								</button>
							</div>
						</div>

						<div class="section-actions">
							<button type="button" class="save-btn" onclick={saveConfig} disabled={configSaving}>
								{configSaving ? 'Saving...' : 'Save Changes'}
							</button>
							{#if configError}<span class="error-msg">{configError}</span>{/if}
							{#if configSuccess}<span class="success-msg">Saved</span>{/if}
						</div>
					</div>
				{/if}
			</section>

			<!-- Home Assistant Section -->
			<section class="settings-section">
				<button
					type="button"
					class="section-header"
					onclick={() => toggleSection('homeassistant')}
					aria-expanded={expandedSection === 'homeassistant'}
				>
					<div class="section-title-group">
						<svg class="section-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
							<path stroke-linecap="round" stroke-linejoin="round" d="M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25" />
						</svg>
						<h2>Home Assistant</h2>
						{#if haStatus?.connected}
							<span class="status-pill connected">Connected</span>
						{:else if haEnabled}
							<span class="status-pill disconnected">Disconnected</span>
						{/if}
					</div>
					<svg class="chevron" class:rotated={expandedSection === 'homeassistant'} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
					</svg>
				</button>
				{#if expandedSection === 'homeassistant'}
					<div class="section-content">
						<div class="toggle-setting prominent">
							<div class="toggle-info">
								<span class="toggle-label">Enable Integration</span>
								<span class="toggle-desc">Connect to Home Assistant for environmental data and control</span>
							</div>
							<button
								type="button"
								class="switch"
								class:on={haEnabled}
								onclick={() => (haEnabled = !haEnabled)}
								aria-pressed={haEnabled}
							>
								<span class="switch-thumb"></span>
							</button>
						</div>

						{#if haEnabled}
							<div class="form-grid">
								<div class="form-field full">
									<label for="ha-url">Home Assistant URL</label>
									<input id="ha-url" type="url" bind:value={haUrl} placeholder="http://192.168.1.100:8123" />
								</div>
								<div class="form-field full">
									<label for="ha-token">Access Token</label>
									<input id="ha-token" type="password" bind:value={haToken} placeholder="Long-lived access token" />
								</div>
								<div class="form-field">
									<label for="ha-ambient-temp">Ambient Temp Entity</label>
									<input id="ha-ambient-temp" type="text" bind:value={haAmbientTempEntityId} placeholder="sensor.xxx_temperature" />
								</div>
								<div class="form-field">
									<label for="ha-ambient-humidity">Ambient Humidity</label>
									<input id="ha-ambient-humidity" type="text" bind:value={haAmbientHumidityEntityId} placeholder="sensor.xxx_humidity" />
								</div>
								<div class="form-field">
									<label for="ha-chamber-temp">Chamber Temp</label>
									<input id="ha-chamber-temp" type="text" bind:value={haChamberTempEntityId} placeholder="sensor.chamber_temperature" />
								</div>
								<div class="form-field">
									<label for="ha-chamber-humidity">Chamber Humidity</label>
									<input id="ha-chamber-humidity" type="text" bind:value={haChamberHumidityEntityId} placeholder="sensor.chamber_humidity" />
								</div>
								<div class="form-field full">
									<label for="ha-weather">Weather Entity</label>
									<input id="ha-weather" type="text" bind:value={haWeatherEntityId} placeholder="weather.home" />
								</div>
							</div>

							<div class="inline-actions">
								<button type="button" class="test-btn" onclick={testHAConnection} disabled={haTesting || !haUrl || !haToken}>
									{haTesting ? 'Testing...' : 'Test Connection'}
								</button>
								{#if haTestResult}
									<span class="test-result" class:success={haTestResult.success}>{haTestResult.message}</span>
								{/if}
							</div>

							{#if haEnabled && haWeatherEntityId}
								<div class="subsection">
									<h3>Weather Alerts</h3>
									<div class="toggle-setting">
										<div class="toggle-info">
											<span class="toggle-label">Enable Alerts</span>
											<span class="toggle-desc">Notify when forecast may affect fermentation</span>
										</div>
										<button
											type="button"
											class="switch"
											class:on={weatherAlertsEnabled}
											onclick={() => (weatherAlertsEnabled = !weatherAlertsEnabled)}
											aria-pressed={weatherAlertsEnabled}
										>
											<span class="switch-thumb"></span>
										</button>
									</div>
									{#if weatherAlertsEnabled}
										<div class="inline-setting">
											<label>Alert when forecast differs by more than</label>
											<div class="input-group compact">
												<input type="number" min="1" max="15" step="0.5" bind:value={alertTempThreshold} class="num-input" />
												<span class="input-unit">°C</span>
											</div>
										</div>
									{/if}
								</div>
							{/if}

							{#if haEnabled}
								<div class="subsection">
									<h3>Temperature Control</h3>
									<div class="toggle-setting">
										<div class="toggle-info">
											<span class="toggle-label">Enable Control</span>
											<span class="toggle-desc">Automatically manage heaters for batches</span>
										</div>
										<button
											type="button"
											class="switch"
											class:on={tempControlEnabled}
											onclick={() => (tempControlEnabled = !tempControlEnabled)}
											aria-pressed={tempControlEnabled}
										>
											<span class="switch-thumb"></span>
										</button>
									</div>
									{#if tempControlEnabled}
										<div class="control-defaults">
											<div class="inline-setting">
												<label>Default target</label>
												<div class="input-group compact">
													<input type="number" bind:value={tempTarget} min={useCelsius ? 0 : 32} max={useCelsius ? 38 : 100} step="0.5" class="num-input" />
													<span class="input-unit">{tempUnitSymbol}</span>
												</div>
											</div>
											<div class="inline-setting">
												<label>Hysteresis</label>
												<div class="input-group compact">
													<input type="number" bind:value={tempHysteresis} min={useCelsius ? 0.3 : 0.5} max={useCelsius ? 5.5 : 10} step={useCelsius ? 0.25 : 0.5} class="num-input" />
													<span class="input-unit">±{tempUnitSymbol}</span>
												</div>
											</div>
										</div>
									{/if}
								</div>
							{/if}
						{/if}

						<div class="section-actions">
							<button type="button" class="save-btn" onclick={saveHAConfig} disabled={haSaving}>
								{haSaving ? 'Saving...' : 'Save HA Settings'}
							</button>
							{#if haError}<span class="error-msg">{haError}</span>{/if}
							{#if haSuccess}<span class="success-msg">Saved</span>{/if}
						</div>
					</div>
				{/if}
			</section>

			<!-- AI Assistant Section -->
			<section class="settings-section">
				<button
					type="button"
					class="section-header"
					onclick={() => toggleSection('ai')}
					aria-expanded={expandedSection === 'ai'}
				>
					<div class="section-title-group">
						<svg class="section-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
							<path stroke-linecap="round" stroke-linejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456zM16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 001.423 1.423l1.183.394-1.183.394a2.25 2.25 0 00-1.423 1.423z" />
						</svg>
						<h2>AI Brewing Assistant</h2>
						{#if aiEnabled}
							<span class="status-pill enabled">Enabled</span>
						{/if}
					</div>
					<svg class="chevron" class:rotated={expandedSection === 'ai'} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
					</svg>
				</button>
				{#if expandedSection === 'ai'}
					<div class="section-content">
						<p class="section-intro">
							Get AI-powered help with recipe creation, fermentation troubleshooting, and brewing advice.
							Use a local model for privacy or connect to cloud providers.
						</p>

						<div class="toggle-setting prominent">
							<div class="toggle-info">
								<span class="toggle-label">Enable AI Assistant</span>
								<span class="toggle-desc">Activate brewing AI features</span>
							</div>
							<button
								type="button"
								class="switch"
								class:on={aiEnabled}
								onclick={() => (aiEnabled = !aiEnabled)}
								aria-pressed={aiEnabled}
							>
								<span class="switch-thumb"></span>
							</button>
						</div>

						{#if aiEnabled}
							<div class="form-grid">
								<div class="form-field">
									<label for="ai-provider">Provider</label>
									<select id="ai-provider" bind:value={aiProvider}>
										{#each aiProviders as provider}
											<option value={provider.id}>{provider.name}</option>
										{/each}
									</select>
								</div>
								<div class="form-field">
									<label for="ai-model">Model</label>
									<select id="ai-model" bind:value={aiModel}>
										<option value="">Default</option>
										{#each aiModels as model}
											<option value={model.id}>{model.name}</option>
										{/each}
									</select>
								</div>
							</div>

							{#if aiProvider === 'local'}
								<div class="info-box">
									<h4>Ollama Setup</h4>
									{#if systemInfo?.platform?.is_raspberry_pi}
										<!-- Running on Raspberry Pi -->
										<p><strong>Option 1: Remote (Recommended)</strong> — Run Ollama on a PC/Mac with GPU for fast responses.</p>
										<ol>
											<li>Install from <a href="https://ollama.ai/download" target="_blank" rel="noopener">ollama.ai</a></li>
											<li>Run: <code>OLLAMA_HOST=0.0.0.0 ollama serve</code></li>
											<li>Pull a model: <code>ollama pull llama3:8b</code></li>
											<li>Enter the remote machine's IP below</li>
										</ol>
										<p><strong>Option 2: Local on Pi</strong> — Requires <a href="https://www.raspberrypi.com/products/ai-hat-plus-2/" target="_blank" rel="noopener">AI HAT+</a> for acceptable speed.
											{#if aiAccelerator?.available}
												<span class="ai-detected">✓ AI HAT+ detected ({aiAccelerator.device?.tops} TOPS)</span>
											{/if}
										</p>
									{:else if systemInfo?.platform?.gpu?.vendor === 'nvidia' || systemInfo?.platform?.gpu?.vendor === 'amd' || systemInfo?.platform?.gpu?.vendor === 'apple'}
										<!-- Running on desktop/server with GPU -->
										<p class="gpu-detected">
											<strong>GPU detected:</strong> {systemInfo.platform.gpu.name ?? systemInfo.platform.gpu.vendor.toUpperCase()}
											{#if systemInfo.platform.gpu.vram_mb}
												({(systemInfo.platform.gpu.vram_mb / 1024).toFixed(0)} GB VRAM)
											{/if}
										</p>
										<p>Local Ollama is recommended for this system.</p>
										<ol>
											<li>Install from <a href="https://ollama.ai/download" target="_blank" rel="noopener">ollama.ai</a></li>
											<li>Pull a model: <code>ollama pull llama3:8b</code></li>
											<li>Keep the default URL (localhost)</li>
										</ol>
									{:else}
										<!-- Generic/unknown platform -->
										<ol>
											<li>Install from <a href="https://ollama.ai/download" target="_blank" rel="noopener">ollama.ai</a></li>
											<li>Pull a model: <code>ollama pull llama3:8b</code></li>
										</ol>
										<p class="hint">For remote Ollama, run: <code>OLLAMA_HOST=0.0.0.0 ollama serve</code></p>
									{/if}
								</div>
								<div class="form-field full">
									<label for="ai-url">Ollama URL</label>
									<input id="ai-url" type="text" bind:value={aiBaseUrl} placeholder="http://localhost:11434" />
								</div>
							{:else if aiProviders.find(p => p.id === aiProvider)?.requires_api_key}
								<div class="form-field full">
									<label for="ai-key">API Key</label>
									<input id="ai-key" type="password" bind:value={aiApiKey} placeholder={aiHasEnvKey ? '(using environment variable)' : 'sk-...'} />
									{#if aiHasEnvKey && !aiApiKey}
										<span class="field-hint success">API key detected from environment</span>
									{/if}
								</div>
							{/if}

							<details class="advanced-settings">
								<summary>Advanced Settings</summary>
								<div class="form-grid">
									<div class="form-field">
										<label for="ai-temp">Temperature</label>
										<input id="ai-temp" type="number" bind:value={aiTemperature} min="0" max="2" step="0.1" />
										<span class="field-hint">Higher = more creative</span>
									</div>
									<div class="form-field">
										<label for="ai-tokens">Max Tokens</label>
										<input id="ai-tokens" type="number" bind:value={aiMaxTokens} min="100" max="8000" step="100" />
									</div>
								</div>
							</details>

							<div class="inline-actions">
								<button type="button" class="test-btn" onclick={testAiConnection} disabled={aiTesting}>
									{aiTesting ? 'Testing...' : 'Test Connection'}
								</button>
								{#if aiTestResult}
									{#if aiTestResult.success}
										<span class="test-result success">Connected! "{aiTestResult.response}"</span>
									{:else}
										<span class="test-result">{aiTestResult.error}</span>
									{/if}
								{/if}
							</div>
						{/if}

						<div class="section-actions">
							<button type="button" class="save-btn" onclick={saveAiConfig} disabled={aiSaving}>
								{aiSaving ? 'Saving...' : 'Save AI Settings'}
							</button>
							{#if aiError}<span class="error-msg">{aiError}</span>{/if}
							{#if aiSuccess}<span class="success-msg">Saved</span>{/if}
						</div>
					</div>
				{/if}
			</section>

			<!-- Storage Section -->
			<section class="settings-section">
				<button
					type="button"
					class="section-header"
					onclick={() => toggleSection('storage')}
					aria-expanded={expandedSection === 'storage'}
				>
					<div class="section-title-group">
						<svg class="section-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
							<path stroke-linecap="round" stroke-linejoin="round" d="M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375m16.5 0v3.75m-16.5-3.75v3.75m16.5 0v3.75C20.25 16.153 16.556 18 12 18s-8.25-1.847-8.25-4.125v-3.75m16.5 0c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125" />
						</svg>
						<h2>Storage & Cleanup</h2>
						{#if storageStats}
							<span class="storage-badge">{formatBytes(storageStats.estimated_size_bytes)}</span>
						{/if}
					</div>
					<svg class="chevron" class:rotated={expandedSection === 'storage'} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
					</svg>
				</button>
				{#if expandedSection === 'storage'}
					<div class="section-content">
						<div class="storage-stats">
							<div class="stat">
								<span class="stat-value">{storageStats ? formatNumber(storageStats.total_readings) : '—'}</span>
								<span class="stat-label">Total Readings</span>
							</div>
							<div class="stat">
								<span class="stat-value">{storageStats ? formatBytes(storageStats.estimated_size_bytes) : '—'}</span>
								<span class="stat-label">Database Size</span>
							</div>
						</div>

						<div class="cleanup-section">
							<p>Remove old readings to free storage. This action is permanent.</p>
							<div class="cleanup-controls">
								<label>Keep readings from last</label>
								<div class="input-group compact">
									<input type="number" min="1" max="365" bind:value={cleanupRetentionDays} class="num-input" />
									<span class="input-unit">days</span>
								</div>
								<button type="button" class="secondary-btn" onclick={previewCleanup} disabled={actionInProgress !== null}>
									{actionInProgress === 'cleanup-preview' ? 'Checking...' : 'Preview'}
								</button>
								{#if cleanupPreview && cleanupPreview.readings_to_delete > 0}
									<button type="button" class="danger-btn" onclick={executeCleanup} disabled={actionInProgress !== null}>
										{actionInProgress === 'cleanup' ? 'Deleting...' : `Delete ${formatNumber(cleanupPreview.readings_to_delete)}`}
									</button>
								{/if}
							</div>
							{#if cleanupPreview && cleanupPreview.readings_to_delete === 0}
								<p class="cleanup-result">No readings older than {cleanupRetentionDays} days.</p>
							{/if}
						</div>
					</div>
				{/if}
			</section>

			<!-- Power Controls -->
			<section class="settings-section danger-section">
				<button
					type="button"
					class="section-header"
					onclick={() => toggleSection('power')}
					aria-expanded={expandedSection === 'power'}
				>
					<div class="section-title-group">
						<svg class="section-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
							<path stroke-linecap="round" stroke-linejoin="round" d="M5.636 5.636a9 9 0 1012.728 0M12 3v9" />
						</svg>
						<h2>Power Controls</h2>
					</div>
					<svg class="chevron" class:rotated={expandedSection === 'power'} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
					</svg>
				</button>
				{#if expandedSection === 'power'}
					<div class="section-content">
						<p class="warning-text">These actions affect the entire system. Ensure all work is saved.</p>
						<div class="power-actions">
							<button type="button" class="warning-btn" onclick={rebootSystem} disabled={actionInProgress !== null}>
								<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
								</svg>
								{actionInProgress === 'reboot' ? 'Rebooting...' : 'Reboot'}
							</button>
							<button type="button" class="danger-btn large" onclick={shutdownSystem} disabled={actionInProgress !== null}>
								<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M5.636 5.636a9 9 0 1012.728 0M12 3v9" />
								</svg>
								{actionInProgress === 'shutdown' ? 'Shutting down...' : 'Shutdown'}
							</button>
						</div>
					</div>
				{/if}
			</section>
		</div>
	{/if}
</div>

<style>
	/* Page Layout */
	.system-page {
		max-width: 52rem;
		margin: 0 auto;
	}

	/* Loading State */
	.loading-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 1rem;
		padding: 6rem 2rem;
		color: var(--text-muted);
	}

	.loading-spinner {
		width: 2.5rem;
		height: 2.5rem;
		border: 2px solid var(--gray-800);
		border-top-color: var(--recipe-accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	/* Status Banner */
	.status-banner {
		background: linear-gradient(135deg, var(--gray-900) 0%, var(--gray-850) 100%);
		border: 1px solid var(--gray-800);
		border-radius: 0.75rem;
		padding: 1.25rem 1.5rem;
		margin-bottom: 1rem;
	}

	.status-grid {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 1rem;
	}

	@media (min-width: 640px) {
		.status-grid {
			grid-template-columns: repeat(6, 1fr);
		}
	}

	.status-item {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.status-label {
		font-size: 0.625rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-muted);
	}

	.status-value {
		font-family: var(--font-mono);
		font-size: 0.8125rem;
		color: var(--text-primary);
	}

	/* AI Status */
	.ai-status.active .ai-chip {
		background: linear-gradient(135deg, rgba(245, 158, 11, 0.15) 0%, rgba(251, 146, 60, 0.1) 100%);
		border: 1px solid rgba(245, 158, 11, 0.3);
		color: var(--recipe-accent);
	}

	.ai-chip {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		padding: 0.25rem 0.5rem;
		background: var(--gray-800);
		border: 1px solid var(--gray-700);
		border-radius: 0.375rem;
		font-size: 0.6875rem;
		font-weight: 600;
	}

	.ai-dot {
		width: 6px;
		height: 6px;
		background: var(--recipe-accent);
		border-radius: 50%;
		animation: pulse-dot 2s ease-in-out infinite;
	}

	@keyframes pulse-dot {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.5; }
	}

	.ai-tops {
		color: var(--text-muted);
		font-weight: 500;
	}

	.ai-unavailable {
		color: var(--text-muted);
		font-size: 0.75rem;
	}

	/* Quick Links */
	.quick-links {
		display: flex;
		gap: 0.5rem;
		margin-bottom: 1.5rem;
		flex-wrap: wrap;
	}

	.quick-link {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.5rem 0.875rem;
		background: var(--gray-900);
		border: 1px solid var(--gray-800);
		border-radius: 0.5rem;
		font-size: 0.8125rem;
		font-weight: 500;
		color: var(--text-secondary);
		text-decoration: none;
		transition: all 0.15s ease;
	}

	.quick-link:hover {
		background: var(--gray-850);
		border-color: var(--gray-700);
		color: var(--text-primary);
	}

	.quick-link .icon {
		width: 1rem;
		height: 1rem;
	}

	/* Settings Container */
	.settings-container {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	/* Settings Sections */
	.settings-section {
		background: var(--gray-900);
		border: 1px solid var(--gray-800);
		border-radius: 0.625rem;
		overflow: hidden;
	}

	.settings-section.danger-section {
		border-color: rgba(239, 68, 68, 0.2);
	}

	.section-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		width: 100%;
		padding: 1rem 1.25rem;
		background: transparent;
		border: none;
		cursor: pointer;
		text-align: left;
	}

	.section-header:hover {
		background: var(--gray-850);
	}

	.section-title-group {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}

	.section-icon {
		width: 1.25rem;
		height: 1.25rem;
		color: var(--text-muted);
	}

	.section-header h2 {
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
	}

	.chevron {
		width: 1.25rem;
		height: 1.25rem;
		color: var(--text-muted);
		transition: transform 0.2s ease;
	}

	.chevron.rotated {
		transform: rotate(180deg);
	}

	/* Section Content */
	.section-content {
		padding: 0 1.25rem 1.25rem;
		border-top: 1px solid var(--gray-800);
	}

	.section-intro {
		font-size: 0.8125rem;
		color: var(--text-muted);
		line-height: 1.5;
		margin: 1rem 0;
	}

	/* Status Pills */
	.status-pill {
		font-size: 0.625rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		padding: 0.25rem 0.5rem;
		border-radius: 9999px;
	}

	.status-pill.connected {
		background: rgba(34, 197, 94, 0.15);
		color: var(--tilt-green);
	}

	.status-pill.disconnected {
		background: rgba(239, 68, 68, 0.15);
		color: var(--tilt-red);
	}

	.status-pill.enabled {
		background: rgba(59, 130, 246, 0.15);
		color: var(--accent);
	}

	.storage-badge {
		font-family: var(--font-mono);
		font-size: 0.6875rem;
		padding: 0.25rem 0.5rem;
		background: var(--gray-800);
		border-radius: 0.25rem;
		color: var(--text-secondary);
	}

	/* Settings Grid */
	.settings-grid {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 1rem;
		padding: 1rem 0;
	}

	@media (min-width: 640px) {
		.settings-grid {
			grid-template-columns: repeat(4, 1fr);
		}
	}

	.setting-group {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.setting-label {
		font-size: 0.6875rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-muted);
	}

	/* Toggle Groups */
	.toggle-group {
		display: flex;
		background: var(--gray-850);
		border: 1px solid var(--gray-700);
		border-radius: 0.375rem;
		overflow: hidden;
	}

	.toggle-group.triple .toggle-btn {
		min-width: 2.5rem;
	}

	.toggle-btn {
		flex: 1;
		padding: 0.5rem 0.75rem;
		font-size: 0.75rem;
		font-weight: 600;
		background: transparent;
		border: none;
		color: var(--text-muted);
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.toggle-btn:hover {
		color: var(--text-secondary);
	}

	.toggle-btn.active {
		background: var(--accent);
		color: white;
	}

	/* Input Groups */
	.input-group {
		display: flex;
		align-items: center;
		gap: 0.375rem;
	}

	.input-group.compact {
		gap: 0.25rem;
	}

	.num-input {
		width: 4rem;
		padding: 0.5rem 0.5rem;
		font-family: var(--font-mono);
		font-size: 0.8125rem;
		text-align: center;
		background: var(--gray-850);
		border: 1px solid var(--gray-700);
		border-radius: 0.375rem;
		color: var(--text-primary);
	}

	.num-input:focus {
		outline: none;
		border-color: var(--accent);
	}

	.input-unit {
		font-size: 0.75rem;
		color: var(--text-muted);
		font-family: var(--font-mono);
	}

	/* Select Input */
	.select-input {
		width: 100%;
		padding: 0.5rem 2rem 0.5rem 0.75rem;
		font-size: 0.8125rem;
		background: var(--gray-850);
		border: 1px solid var(--gray-700);
		border-radius: 0.375rem;
		color: var(--text-primary);
		cursor: pointer;
		appearance: none;
		background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%2371717a'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'/%3E%3C/svg%3E");
		background-repeat: no-repeat;
		background-position: right 0.5rem center;
		background-size: 1rem;
	}

	.select-input:focus {
		outline: none;
		border-color: var(--accent);
	}

	.mini-select {
		padding: 0.25rem 1.5rem 0.25rem 0.5rem;
		font-size: 0.75rem;
		font-family: var(--font-mono);
		background: var(--gray-800);
		border: 1px solid var(--gray-700);
		border-radius: 0.25rem;
		color: var(--text-primary);
		appearance: none;
		background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%2371717a'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'/%3E%3C/svg%3E");
		background-repeat: no-repeat;
		background-position: right 0.25rem center;
		background-size: 0.75rem;
	}

	/* Divider */
	.settings-divider {
		height: 1px;
		background: var(--gray-800);
		margin: 0.5rem 0;
	}

	/* Toggle Settings */
	.toggle-settings {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		padding: 0.75rem 0;
	}

	.toggle-setting {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.5rem 0;
	}

	.toggle-setting.prominent {
		padding: 1rem;
		background: var(--gray-850);
		border-radius: 0.5rem;
		margin: 0.75rem 0;
	}

	.toggle-info {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
	}

	.toggle-label {
		font-size: 0.8125rem;
		font-weight: 500;
		color: var(--text-primary);
	}

	.toggle-desc {
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	.toggle-controls {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}

	/* Switch */
	.switch {
		position: relative;
		width: 2.75rem;
		height: 1.5rem;
		background: var(--gray-700);
		border: none;
		border-radius: 0.75rem;
		cursor: pointer;
		transition: background 0.2s ease;
	}

	.switch.on {
		background: var(--accent);
	}

	.switch-thumb {
		position: absolute;
		top: 2px;
		left: 2px;
		width: 1.25rem;
		height: 1.25rem;
		background: var(--gray-400);
		border-radius: 50%;
		transition: all 0.2s ease;
	}

	.switch.on .switch-thumb {
		left: calc(100% - 1.25rem - 2px);
		background: white;
	}

	/* Form Grid */
	.form-grid {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 1rem;
		padding: 1rem 0;
	}

	.form-field {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
	}

	.form-field.full {
		grid-column: 1 / -1;
	}

	.form-field label {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-secondary);
	}

	.form-field input,
	.form-field select {
		padding: 0.625rem 0.75rem;
		font-size: 0.8125rem;
		background: var(--gray-850);
		border: 1px solid var(--gray-700);
		border-radius: 0.375rem;
		color: var(--text-primary);
	}

	.form-field input:focus,
	.form-field select:focus {
		outline: none;
		border-color: var(--accent);
	}

	.form-field input::placeholder {
		color: var(--text-muted);
	}

	.field-hint {
		font-size: 0.6875rem;
		color: var(--text-muted);
	}

	.field-hint.success {
		color: var(--tilt-green);
	}

	/* Subsections */
	.subsection {
		margin-top: 1.5rem;
		padding-top: 1rem;
		border-top: 1px solid var(--gray-800);
	}

	.subsection h3 {
		font-size: 0.75rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-muted);
		margin-bottom: 0.75rem;
	}

	/* Inline Settings */
	.inline-setting {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 0.5rem 0;
		font-size: 0.8125rem;
		color: var(--text-secondary);
	}

	.control-defaults {
		display: flex;
		flex-wrap: wrap;
		gap: 1rem;
		margin-top: 0.75rem;
	}

	/* Info Box */
	.info-box {
		background: var(--gray-850);
		border: 1px solid var(--gray-700);
		border-radius: 0.5rem;
		padding: 1rem;
		margin: 0.75rem 0;
	}

	.info-box h4 {
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-primary);
		margin-bottom: 0.5rem;
	}

	.info-box p {
		font-size: 0.75rem;
		color: var(--text-secondary);
		line-height: 1.5;
		margin: 0.5rem 0;
	}

	.info-box ol {
		font-size: 0.75rem;
		color: var(--text-secondary);
		padding-left: 1.25rem;
		margin: 0.5rem 0;
	}

	.info-box li {
		margin: 0.25rem 0;
	}

	.info-box code {
		font-family: var(--font-mono);
		font-size: 0.6875rem;
		padding: 0.125rem 0.375rem;
		background: var(--gray-800);
		border-radius: 0.25rem;
		color: var(--accent);
	}

	.info-box a {
		color: var(--accent);
	}

	.info-box a:hover {
		text-decoration: underline;
	}

	.info-box .gpu-detected {
		color: var(--positive);
		font-size: 0.8125rem;
		margin-bottom: 0.5rem;
	}

	.info-box .ai-detected {
		color: var(--recipe-accent);
		font-size: 0.75rem;
		margin-left: 0.5rem;
	}

	.info-box .hint {
		font-size: 0.75rem;
		color: var(--text-muted);
		margin-top: 0.5rem;
	}

	/* Advanced Settings */
	.advanced-settings {
		margin-top: 0.75rem;
	}

	.advanced-settings summary {
		font-size: 0.75rem;
		color: var(--text-muted);
		cursor: pointer;
		padding: 0.5rem 0;
	}

	.advanced-settings summary:hover {
		color: var(--text-secondary);
	}

	/* Actions */
	.inline-actions {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		flex-wrap: wrap;
		padding: 0.75rem 0;
	}

	.section-actions {
		display: flex;
		align-items: center;
		gap: 1rem;
		padding-top: 1rem;
		border-top: 1px solid var(--gray-800);
		margin-top: 1rem;
	}

	/* Buttons */
	.save-btn {
		padding: 0.625rem 1.25rem;
		font-size: 0.8125rem;
		font-weight: 600;
		background: var(--accent);
		border: none;
		border-radius: 0.5rem;
		color: white;
		cursor: pointer;
		transition: background 0.15s ease;
	}

	.save-btn:hover:not(:disabled) {
		background: var(--accent-hover);
	}

	.save-btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.test-btn,
	.secondary-btn {
		padding: 0.5rem 0.875rem;
		font-size: 0.75rem;
		font-weight: 500;
		background: var(--gray-800);
		border: 1px solid var(--gray-700);
		border-radius: 0.375rem;
		color: var(--text-secondary);
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.test-btn:hover:not(:disabled),
	.secondary-btn:hover:not(:disabled) {
		background: var(--gray-700);
		color: var(--text-primary);
	}

	.test-btn:disabled,
	.secondary-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.warning-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.625rem 1rem;
		font-size: 0.8125rem;
		font-weight: 600;
		background: rgba(251, 146, 60, 0.1);
		border: 1px solid rgba(251, 146, 60, 0.25);
		border-radius: 0.5rem;
		color: var(--tilt-orange);
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.warning-btn:hover:not(:disabled) {
		background: rgba(251, 146, 60, 0.15);
	}

	.warning-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.warning-btn svg {
		width: 1rem;
		height: 1rem;
	}

	.danger-btn {
		padding: 0.5rem 0.875rem;
		font-size: 0.75rem;
		font-weight: 600;
		background: rgba(239, 68, 68, 0.1);
		border: 1px solid rgba(239, 68, 68, 0.25);
		border-radius: 0.375rem;
		color: var(--tilt-red);
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.danger-btn:hover:not(:disabled) {
		background: rgba(239, 68, 68, 0.15);
	}

	.danger-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.danger-btn.large {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.625rem 1rem;
		font-size: 0.8125rem;
		border-radius: 0.5rem;
	}

	.danger-btn.large svg {
		width: 1rem;
		height: 1rem;
	}

	/* Feedback Messages */
	.error-msg {
		font-size: 0.75rem;
		color: var(--tilt-red);
	}

	.success-msg {
		font-size: 0.75rem;
		color: var(--tilt-green);
	}

	.test-result {
		font-size: 0.75rem;
		color: var(--tilt-red);
	}

	.test-result.success {
		color: var(--tilt-green);
	}

	/* Storage Section */
	.storage-stats {
		display: flex;
		gap: 2rem;
		padding: 1rem 0;
	}

	.stat {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.stat-value {
		font-family: var(--font-mono);
		font-size: 1.5rem;
		font-weight: 600;
		color: var(--recipe-accent);
	}

	.stat-label {
		font-size: 0.6875rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-muted);
	}

	.cleanup-section {
		padding-top: 1rem;
		border-top: 1px solid var(--gray-800);
	}

	.cleanup-section > p {
		font-size: 0.8125rem;
		color: var(--text-muted);
		margin-bottom: 0.75rem;
	}

	.cleanup-controls {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		flex-wrap: wrap;
	}

	.cleanup-controls label {
		font-size: 0.8125rem;
		color: var(--text-secondary);
	}

	.cleanup-result {
		font-size: 0.75rem;
		color: var(--text-muted);
		margin-top: 0.5rem;
	}

	/* Power Section */
	.warning-text {
		font-size: 0.8125rem;
		color: var(--tilt-red);
		margin: 1rem 0;
	}

	.power-actions {
		display: flex;
		gap: 0.75rem;
	}

	/* Responsive */
	@media (max-width: 640px) {
		.status-grid {
			grid-template-columns: repeat(2, 1fr);
		}

		.settings-grid {
			grid-template-columns: 1fr;
		}

		.form-grid {
			grid-template-columns: 1fr;
		}

		.form-field.full {
			grid-column: 1;
		}

		.storage-stats {
			flex-direction: column;
			gap: 1rem;
		}

		.power-actions {
			flex-direction: column;
		}

		.cleanup-controls {
			flex-direction: column;
			align-items: flex-start;
		}
	}
</style>
