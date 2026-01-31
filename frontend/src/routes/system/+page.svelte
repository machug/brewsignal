<script lang="ts">
	import { onMount } from 'svelte';
	import { configState, updateConfig, fahrenheitToCelsius, celsiusToFahrenheit } from '$lib/stores/config.svelte';
	import { config, onConfigLoaded, configStores } from '$lib/config';
	import { authState } from '$lib/stores/auth.svelte';
	import { signInWithEmail, signUpWithEmail, signInWithGoogle, signOut } from '$lib/supabase';
	import { authFetch } from '$lib/api';

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

	interface HailoOllamaStatus {
		running: boolean;
		url: string;
		models_available: string[];
		models_loaded: string[];
	}

	interface AIAcceleratorStatus {
		available: boolean;
		device: AIAcceleratorDevice | null;
		ollama_server: HailoOllamaStatus | null;
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

	// Auth config state (reactive for template)
	let authEnabled = $state(config.authEnabled);

	// Update authEnabled when config loads
	onConfigLoaded(() => {
		authEnabled = config.authEnabled;
	});

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

	// Device Control Backend state
	let deviceControlBackend = $state<'ha' | 'shelly'>('ha');
	let shellyEnabled = $state(false);
	let shellyDevices = $state<string[]>([]);
	let newShellyIp = $state('');
	let shellyTesting = $state<string | null>(null); // IP being tested
	let shellyTestResult = $state<{ ip: string; success: boolean; message: string; gen?: number } | null>(null);
	let shellySaving = $state(false);
	let shellyError = $state<string | null>(null);
	let shellySuccess = $state(false);

	// Weather Alerts state
	let weatherAlertsEnabled = $state(false);
	let alertTempThreshold = $state(3.0);
	let alertsSaving = $state(false);
	let alertsError = $state<string | null>(null);
	let alertsSuccess = $state(false);

	// AI Assistant state
	let aiEnabled = $state(false);
	let aiLiteEnabled = $state(false); // Use Hailo for lightweight tasks (summaries)
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
	let localModeActive = $state(true); // Reactive flag for deployment mode

	// MQTT state
	let mqttEnabled = $state(false);
	let mqttHost = $state('');
	let mqttPort = $state(1883);
	let mqttUsername = $state('');
	let mqttPassword = $state('');
	let mqttTopicPrefix = $state('brewsignal');
	let mqttSaving = $state(false);
	let mqttError = $state<string | null>(null);
	let mqttSuccess = $state(false);
	let mqttTesting = $state(false);
	let mqttTestResult = $state<{ success: boolean; message: string } | null>(null);

	// Cloud Sync state
	interface CloudStatus {
		connected: boolean;
		user_id: string | null;
		email: string | null;
		unclaimed: { devices: number; recipes: number; batches: number };
		has_unclaimed_data: boolean;
	}
	let cloudStatus = $state<CloudStatus | null>(null);
	let cloudLoading = $state(false);
	let cloudAuthMode = $state<'signin' | 'signup' | null>(null);
	let cloudEmail = $state('');
	let cloudPassword = $state('');
	let cloudAuthLoading = $state(false);
	let cloudAuthError = $state<string | null>(null);
	let cloudClaimLoading = $state(false);
	let cloudClaimResult = $state<{ success: boolean; message: string } | null>(null);
	let cloudSyncLoading = $state(false);
	let cloudSyncResult = $state<{ success: boolean; message: string; details?: { devices: number; recipes: number; batches: number } } | null>(null);

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
		// AI accelerator (Hailo HAT+) only relevant in local mode
		if (!config.isLocalMode) return;
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

	async function loadCloudStatus() {
		if (!config.authEnabled) return;
		cloudLoading = true;
		try {
			const response = await authFetch('/api/users/cloud-status');
			if (response.ok) {
				cloudStatus = await response.json();
			}
		} catch (e) {
			console.error('Failed to load cloud status:', e);
		} finally {
			cloudLoading = false;
		}
	}

	async function handleCloudSignIn(e: Event) {
		e.preventDefault();
		cloudAuthLoading = true;
		cloudAuthError = null;
		try {
			if (cloudAuthMode === 'signup') {
				await signUpWithEmail(cloudEmail, cloudPassword);
				cloudAuthError = 'Check your email for a confirmation link!';
				cloudAuthMode = 'signin';
			} else {
				await signInWithEmail(cloudEmail, cloudPassword);
				cloudAuthMode = null;
				cloudEmail = '';
				cloudPassword = '';
				await loadCloudStatus();
			}
		} catch (err) {
			cloudAuthError = err instanceof Error ? err.message : 'Authentication failed';
		} finally {
			cloudAuthLoading = false;
		}
	}

	async function handleCloudGoogleSignIn() {
		cloudAuthLoading = true;
		cloudAuthError = null;
		try {
			await signInWithGoogle();
		} catch (err) {
			cloudAuthError = err instanceof Error ? err.message : 'Google sign-in failed';
			cloudAuthLoading = false;
		}
	}

	async function handleCloudSignOut() {
		try {
			await signOut();
			cloudStatus = null;
			await loadCloudStatus();
		} catch (err) {
			console.error('Sign out failed:', err);
		}
	}

	async function claimUnclaimedData() {
		cloudClaimLoading = true;
		cloudClaimResult = null;
		try {
			const response = await authFetch('/api/users/claim-data', { method: 'POST' });
			if (response.ok) {
				const data = await response.json();
				cloudClaimResult = { success: true, message: data.message };
				await loadCloudStatus();
			} else {
				cloudClaimResult = { success: false, message: 'Failed to claim data' };
			}
		} catch (err) {
			cloudClaimResult = { success: false, message: err instanceof Error ? err.message : 'Error claiming data' };
		} finally {
			cloudClaimLoading = false;
		}
	}

	async function syncToCloud() {
		cloudSyncLoading = true;
		cloudSyncResult = null;
		try {
			const response = await authFetch('/api/sync/push', { method: 'POST' });
			if (response.ok) {
				const data = await response.json();
				const devices = data.results?.devices?.synced ?? 0;
				const recipes = data.results?.recipes?.synced ?? 0;
				const batches = data.results?.batches?.synced ?? 0;
				const totalErrors = data.total_errors ?? 0;

				cloudSyncResult = {
					success: data.status === 'success',
					message: totalErrors > 0
						? `Synced ${data.total_synced} items with ${totalErrors} errors`
						: `Synced ${devices} devices, ${recipes} recipes, ${batches} batches`,
					details: { devices, recipes, batches }
				};
			} else {
				const errData = await response.json().catch(() => ({}));
				cloudSyncResult = { success: false, message: errData.detail || 'Failed to sync data' };
			}
		} catch (err) {
			cloudSyncResult = { success: false, message: err instanceof Error ? err.message : 'Error syncing data' };
		} finally {
			cloudSyncLoading = false;
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
		// Device Control Backend
		deviceControlBackend = (configState.config.device_control_backend as 'ha' | 'shelly') ?? 'ha';
		shellyEnabled = configState.config.shelly_enabled ?? false;
		const shellyDevicesStr = configState.config.shelly_devices ?? '';
		shellyDevices = shellyDevicesStr ? shellyDevicesStr.split(',').map((ip: string) => ip.trim()).filter(Boolean) : [];
		// Weather Alerts
		weatherAlertsEnabled = configState.config.weather_alerts_enabled;
		alertTempThreshold = configState.config.alert_temp_threshold;
		// AI Assistant
		aiEnabled = configState.config.ai_enabled ?? false;
		aiLiteEnabled = configState.config.ai_lite_enabled ?? false;
		aiProvider = configState.config.ai_provider ?? 'local';
		aiModel = configState.config.ai_model ?? '';
		aiApiKey = configState.config.ai_api_key ?? '';
		aiBaseUrl = configState.config.ai_base_url ?? '';
		aiTemperature = configState.config.ai_temperature ?? 0.7;
		aiMaxTokens = configState.config.ai_max_tokens ?? 2000;
		// MQTT
		mqttEnabled = configState.config.mqtt_enabled ?? false;
		mqttHost = configState.config.mqtt_host ?? '';
		mqttPort = configState.config.mqtt_port ?? 1883;
		mqttUsername = configState.config.mqtt_username ?? '';
		mqttPassword = configState.config.mqtt_password ?? '';
		mqttTopicPrefix = configState.config.mqtt_topic_prefix ?? 'brewsignal';
	}

	async function loadAiProviders() {
		try {
			const response = await authFetch('/api/assistant/providers');
			if (response.ok) {
				aiProviders = await response.json();
				// Auto-select valid provider once config is loaded
				onConfigLoaded(() => {
					selectValidProvider();
				});
				// Also select immediately if config is already loaded
				if (config.initialized) {
					selectValidProvider();
				}
			}
		} catch (e) {
			console.error('Failed to load AI providers:', e);
		}
	}

	function selectValidProvider() {
		// In cloud mode, ensure selected provider is valid (not local-only)
		if (!config.isLocalMode && aiProviders.length > 0) {
			const validProviders = aiProviders.filter(p => p.id !== 'local');
			if (!validProviders.find(p => p.id === aiProvider) && validProviders.length > 0) {
				aiProvider = validProviders[0].id;
			}
		}
	}

	async function loadAiModels(provider: string) {
		try {
			const response = await authFetch(`/api/assistant/models/${provider}`);
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
			const response = await authFetch('/api/assistant/status');
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
				ai_lite_enabled: aiLiteEnabled,
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
			const response = await authFetch('/api/assistant/test', { method: 'POST' });
			const result = await response.json();
			aiTestResult = result;
		} catch (e) {
			aiTestResult = { success: false, error: e instanceof Error ? e.message : 'Connection test failed' };
		} finally {
			aiTesting = false;
		}
	}

	async function saveMqttConfig() {
		mqttSaving = true;
		mqttError = null;
		mqttSuccess = false;

		try {
			const result = await updateConfig({
				mqtt_enabled: mqttEnabled,
				mqtt_host: mqttHost,
				mqtt_port: mqttPort,
				mqtt_username: mqttUsername,
				mqtt_password: mqttPassword,
				mqtt_topic_prefix: mqttTopicPrefix
			});
			if (result.success) {
				mqttSuccess = true;
				setTimeout(() => (mqttSuccess = false), 3000);
			} else {
				mqttError = result.error || 'Failed to save settings';
			}
		} finally {
			mqttSaving = false;
		}
	}

	async function testMqttConnection() {
		mqttTesting = true;
		mqttTestResult = null;

		try {
			// First save the current config
			await updateConfig({
				mqtt_enabled: mqttEnabled,
				mqtt_host: mqttHost,
				mqtt_port: mqttPort,
				mqtt_username: mqttUsername,
				mqtt_password: mqttPassword,
				mqtt_topic_prefix: mqttTopicPrefix
			});

			// Then test the connection
			const response = await fetch('/api/mqtt/test', { method: 'POST' });
			if (response.ok) {
				mqttTestResult = await response.json();
			} else {
				mqttTestResult = { success: false, message: 'Request failed' };
			}
		} catch (e) {
			mqttTestResult = { success: false, message: 'Network error' };
		} finally {
			mqttTesting = false;
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

	// Shelly device functions
	async function testShellyDevice(ip: string) {
		shellyTesting = ip;
		shellyTestResult = null;
		try {
			const response = await fetch('/api/device-control/shelly/test', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ ip })
			});
			if (response.ok) {
				const result = await response.json();
				shellyTestResult = { ip, ...result };
			} else {
				shellyTestResult = { ip, success: false, message: 'Request failed' };
			}
		} catch (e) {
			shellyTestResult = { ip, success: false, message: 'Network error' };
		} finally {
			shellyTesting = null;
		}
	}

	function addShellyDevice() {
		const ip = newShellyIp.trim();
		if (!ip) return;
		// Basic IP validation
		if (!/^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(:\d+)?$/.test(ip)) {
			shellyError = 'Invalid IP address format';
			return;
		}
		if (shellyDevices.includes(ip)) {
			shellyError = 'Device already added';
			return;
		}
		shellyDevices = [...shellyDevices, ip];
		newShellyIp = '';
		shellyError = null;
	}

	function removeShellyDevice(ip: string) {
		shellyDevices = shellyDevices.filter(d => d !== ip);
		if (shellyTestResult?.ip === ip) {
			shellyTestResult = null;
		}
	}

	async function saveDeviceControlConfig() {
		shellySaving = true;
		shellyError = null;
		shellySuccess = false;
		try {
			const response = await fetch('/api/config', {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					device_control_backend: deviceControlBackend,
					shelly_enabled: shellyEnabled,
					shelly_devices: shellyDevices.join(',')
				})
			});
			if (response.ok) {
				shellySuccess = true;
				setTimeout(() => (shellySuccess = false), 2000);
			} else {
				const error = await response.json();
				shellyError = error.detail || 'Failed to save';
			}
		} catch (e) {
			shellyError = 'Network error';
		} finally {
			shellySaving = false;
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
			loadAiStatus(),
			loadCloudStatus()
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

	// Subscribe to deployment mode changes for reactive template updates
	$effect(() => {
		const unsubscribe = configStores.isLocalMode.subscribe((value) => {
			localModeActive = value;
			// Also reselect provider when mode changes
			if (aiProviders.length > 0) {
				selectValidProvider();
			}
		});
		return unsubscribe;
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
				{#if localModeActive}
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
					{#if aiAccelerator?.available}
						<div class="status-item ai-status" class:active={aiAccelerator?.ollama_server?.running}>
							<span class="status-label">Hailo-Ollama</span>
							<span class="status-value">
								{#if aiAccelerator?.ollama_server?.running}
									<span class="ai-chip">
										<span class="ai-dot"></span>
										{aiAccelerator.ollama_server.models_loaded.length} model{aiAccelerator.ollama_server.models_loaded.length !== 1 ? 's' : ''} loaded
									</span>
								{:else}
									<span class="ai-unavailable">Not running</span>
								{/if}
							</span>
						</div>
					{/if}
				{/if}
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

			<!-- Device Control Backend Section -->
			<section class="settings-section">
				<button
					type="button"
					class="section-header"
					onclick={() => toggleSection('devicecontrol')}
					aria-expanded={expandedSection === 'devicecontrol'}
				>
					<div class="section-title-group">
						<svg class="section-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
							<path stroke-linecap="round" stroke-linejoin="round" d="M5.636 18.364a9 9 0 010-12.728m12.728 0a9 9 0 010 12.728m-9.9-2.829a5 5 0 010-7.07m7.072 0a5 5 0 010 7.07M13 12a1 1 0 11-2 0 1 1 0 012 0z" />
						</svg>
						<h2>Device Control</h2>
						{#if deviceControlBackend === 'shelly' && shellyDevices.length > 0}
							<span class="status-pill connected">{shellyDevices.length} device{shellyDevices.length !== 1 ? 's' : ''}</span>
						{:else if deviceControlBackend === 'ha' && haEnabled}
							<span class="status-pill connected">Via HA</span>
						{/if}
					</div>
					<svg class="chevron" class:rotated={expandedSection === 'devicecontrol'} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
					</svg>
				</button>
				{#if expandedSection === 'devicecontrol'}
					<div class="section-content">
						<p class="section-desc">Choose how BrewSignal controls heating/cooling devices for temperature control.</p>

						<div class="radio-group">
							<label class="radio-option" class:selected={deviceControlBackend === 'ha'}>
								<input type="radio" name="device-backend" value="ha" bind:group={deviceControlBackend} />
								<div class="radio-content">
									<span class="radio-label">Home Assistant</span>
									<span class="radio-desc">Control devices through Home Assistant (local or remote via Nabu Casa/port forwarding)</span>
								</div>
							</label>
							<label class="radio-option" class:selected={deviceControlBackend === 'shelly'}>
								<input type="radio" name="device-backend" value="shelly" bind:group={deviceControlBackend} />
								<div class="radio-content">
									<span class="radio-label">Direct Shelly</span>
									<span class="radio-desc">Control Shelly smart plugs directly via HTTP (local network only)</span>
								</div>
							</label>
						</div>

						{#if deviceControlBackend === 'ha'}
							<div class="info-box">
								<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
									<path stroke-linecap="round" stroke-linejoin="round" d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z" />
								</svg>
								<div>
									<span>Configure Home Assistant connection in the section above. Assign heater/cooler entities to batches in batch settings.</span>
									<p class="info-hint">For cloud access: use <a href="https://www.nabucasa.com/" target="_blank" rel="noopener">Nabu Casa</a> or port forward your HA instance.</p>
								</div>
							</div>
						{:else}
							<div class="subsection">
								<h3>Shelly Devices</h3>
								<p class="subsection-desc">Add your Shelly device IP addresses. Supports Gen1 (original) and Gen2 (Plus/Pro) devices.</p>
								<p class="local-only-note">⚠️ Direct Shelly control requires BrewSignal and Shelly devices on the same local network.</p>

								<div class="device-list">
									{#each shellyDevices as ip}
										<div class="device-item">
											<span class="device-ip">{ip}</span>
											<div class="device-actions">
												<button
													type="button"
													class="test-btn small"
													onclick={() => testShellyDevice(ip)}
													disabled={shellyTesting === ip}
												>
													{shellyTesting === ip ? 'Testing...' : 'Test'}
												</button>
												<button type="button" class="remove-btn" onclick={() => removeShellyDevice(ip)} title="Remove device">
													<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
														<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
													</svg>
												</button>
											</div>
											{#if shellyTestResult?.ip === ip}
												<span class="test-result" class:success={shellyTestResult.success}>
													{shellyTestResult.message}
												</span>
											{/if}
										</div>
									{/each}
								</div>

								<div class="add-device-form">
									<input
										type="text"
										bind:value={newShellyIp}
										placeholder="192.168.1.50"
										onkeydown={(e) => e.key === 'Enter' && addShellyDevice()}
									/>
									<button type="button" class="add-btn" onclick={addShellyDevice}>Add Device</button>
								</div>

								<div class="help-text">
									<p>Entity format for batches: <code>shelly://IP/channel</code></p>
									<p>Example: <code>shelly://192.168.1.50/0</code> for first relay</p>
									<p class="help-detail">
										<strong>IP:</strong> Find in your router's DHCP list or the
										<a href="https://shelly.cloud/" target="_blank" rel="noopener">Shelly app</a><br>
										<strong>Channel:</strong> Use <code>0</code> for single-relay devices (Plug, 1, 1PM).
										Multi-relay devices (2.5, 4PM) use <code>0</code>, <code>1</code>, etc.
									</p>
								</div>
							</div>
						{/if}

						<div class="section-actions">
							<button type="button" class="save-btn" onclick={saveDeviceControlConfig} disabled={shellySaving}>
								{shellySaving ? 'Saving...' : 'Save Device Settings'}
							</button>
							{#if shellyError}<span class="error-msg">{shellyError}</span>{/if}
							{#if shellySuccess}<span class="success-msg">Saved</span>{/if}
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

						{#if aiAccelerator?.available && aiAccelerator?.ollama_server?.running}
							<div class="toggle-setting">
								<div class="toggle-info">
									<span class="toggle-label">Local Lite LLM</span>
									<span class="toggle-desc">Use Hailo AI HAT+ for summaries and lightweight tasks (free, on-device)</span>
								</div>
								<button
									type="button"
									class="switch"
									class:on={aiLiteEnabled}
									onclick={() => (aiLiteEnabled = !aiLiteEnabled)}
									aria-pressed={aiLiteEnabled}
								>
									<span class="switch-thumb"></span>
								</button>
							</div>
							{#if aiLiteEnabled}
								<div class="info-box success compact">
									<p>✓ Hailo AI HAT+ will handle thread summaries and other lightweight tasks locally.</p>
								</div>
							{/if}
						{/if}

						{#if aiEnabled}
							<div class="form-grid">
								<div class="form-field">
									<label for="ai-provider">Provider</label>
									<select id="ai-provider" bind:value={aiProvider}>
										{#each aiProviders.filter(p => localModeActive || p.id !== 'local') as provider}
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
										<!-- Running on Raspberry Pi - suggest remote Ollama -->
										<p><strong>Remote Ollama (Recommended)</strong> — Run Ollama on a PC/Mac with GPU for fast responses.</p>
										<ol>
											<li>Install from <a href="https://ollama.ai/download" target="_blank" rel="noopener">ollama.ai</a></li>
											<li>Run: <code>OLLAMA_HOST=0.0.0.0 ollama serve</code></li>
											<li>Pull a model: <code>ollama pull llama3:8b</code></li>
											<li>Enter the remote machine's IP below</li>
										</ol>
										{#if localModeActive && aiAccelerator?.available && aiAccelerator?.ollama_server?.running}
											<p class="hint">Tip: Enable <strong>Local Lite LLM</strong> above to use the Hailo HAT for summaries (free).</p>
										{/if}
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

			<!-- MQTT Section -->
			<section class="settings-section">
				<button
					type="button"
					class="section-header"
					onclick={() => toggleSection('mqtt')}
					aria-expanded={expandedSection === 'mqtt'}
				>
					<div class="section-title-group">
						<svg class="section-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
							<path stroke-linecap="round" stroke-linejoin="round" d="M8.288 15.038a5.25 5.25 0 017.424 0M5.106 11.856c3.807-3.808 9.98-3.808 13.788 0M1.924 8.674c5.565-5.565 14.587-5.565 20.152 0M12.53 18.22l-.53.53-.53-.53a.75.75 0 011.06 0z" />
						</svg>
						<h2>MQTT Publishing</h2>
						{#if mqttEnabled}
							<span class="status-pill enabled">Enabled</span>
						{/if}
					</div>
					<svg class="chevron" class:rotated={expandedSection === 'mqtt'} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
					</svg>
				</button>
				{#if expandedSection === 'mqtt'}
					<div class="section-content">
						<p class="section-intro">
							Publish batch fermentation data to an MQTT broker for Home Assistant auto-discovery.
							Sensors are created automatically when batches start fermenting.
						</p>

						<div class="toggle-setting prominent">
							<div class="toggle-info">
								<span class="toggle-label">Enable MQTT Publishing</span>
								<span class="toggle-desc">Send batch data to MQTT broker</span>
							</div>
							<button
								type="button"
								class="switch"
								class:on={mqttEnabled}
								onclick={() => (mqttEnabled = !mqttEnabled)}
								aria-pressed={mqttEnabled}
							>
								<span class="switch-thumb"></span>
							</button>
						</div>

						{#if mqttEnabled}
							<div class="form-grid">
								<div class="form-field">
									<label for="mqtt-host">Broker Host</label>
									<input id="mqtt-host" type="text" bind:value={mqttHost} placeholder="192.168.1.100 or localhost" />
								</div>
								<div class="form-field">
									<label for="mqtt-port">Port</label>
									<input id="mqtt-port" type="number" bind:value={mqttPort} min="1" max="65535" placeholder="1883" />
								</div>
								<div class="form-field">
									<label for="mqtt-username">Username</label>
									<input id="mqtt-username" type="text" bind:value={mqttUsername} placeholder="Optional" />
								</div>
								<div class="form-field">
									<label for="mqtt-password">Password</label>
									<input id="mqtt-password" type="password" bind:value={mqttPassword} placeholder="Optional" />
								</div>
								<div class="form-field full">
									<label for="mqtt-prefix">Topic Prefix</label>
									<input id="mqtt-prefix" type="text" bind:value={mqttTopicPrefix} placeholder="brewsignal" />
									<span class="field-hint">Topics: {mqttTopicPrefix || 'brewsignal'}/batch/&lt;id&gt;/gravity, temperature, etc.</span>
								</div>
							</div>

							<div class="info-box">
								<h4>Home Assistant Setup</h4>
								<p>Ensure your Home Assistant has MQTT integration configured (typically via Mosquitto add-on).</p>
								<p>BrewSignal publishes discovery messages to <code>homeassistant/sensor/...</code> so entities appear automatically.</p>
								<p class="hint">Sensors: gravity, temperature, ABV, status, days fermenting. Binary sensors: heater/cooler active.</p>
							</div>

							<div class="inline-actions">
								<button type="button" class="test-btn" onclick={testMqttConnection} disabled={mqttTesting || !mqttHost}>
									{mqttTesting ? 'Testing...' : 'Test Connection'}
								</button>
								{#if mqttTestResult}
									<span class="test-result" class:success={mqttTestResult.success}>{mqttTestResult.message}</span>
								{/if}
							</div>
						{/if}

						<div class="section-actions">
							<button type="button" class="save-btn" onclick={saveMqttConfig} disabled={mqttSaving}>
								{mqttSaving ? 'Saving...' : 'Save MQTT Settings'}
							</button>
							{#if mqttError}<span class="error-msg">{mqttError}</span>{/if}
							{#if mqttSuccess}<span class="success-msg">Saved</span>{/if}
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

			<!-- Cloud Sync Section -->
			{#if authEnabled}
				<section class="settings-section">
					<button
						type="button"
						class="section-header"
						onclick={() => toggleSection('cloud')}
						aria-expanded={expandedSection === 'cloud'}
					>
						<div class="section-title-group">
							<svg class="section-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
								<path stroke-linecap="round" stroke-linejoin="round" d="M2.25 15a4.5 4.5 0 004.5 4.5H18a3.75 3.75 0 001.332-7.257 3 3 0 00-3.758-3.848 5.25 5.25 0 00-10.233 2.33A4.502 4.502 0 002.25 15z" />
							</svg>
							<h2>Cloud Sync</h2>
							{#if authState.user}
								<span class="status-pill enabled">Connected</span>
							{/if}
						</div>
						<svg class="chevron" class:rotated={expandedSection === 'cloud'} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
						</svg>
					</button>
					{#if expandedSection === 'cloud'}
						<div class="section-content">
							{#if cloudLoading}
								<div class="loading-inline">Loading...</div>
							{:else if authState.user}
								<!-- Connected State -->
								<div class="cloud-connected">
									<div class="connected-status">
										<svg class="check-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
											<path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
										</svg>
										<div>
											<span class="connected-label">Connected as</span>
											<span class="connected-email">{authState.user.email}</span>
										</div>
									</div>

									{#if cloudStatus?.has_unclaimed_data}
										<div class="claim-data-box">
											<h4>Claim Existing Data</h4>
											<p>Associate your existing data with your account:</p>
											<ul class="unclaimed-list">
												{#if cloudStatus.unclaimed.batches > 0}
													<li>{cloudStatus.unclaimed.batches} batch{cloudStatus.unclaimed.batches !== 1 ? 'es' : ''}</li>
												{/if}
												{#if cloudStatus.unclaimed.recipes > 0}
													<li>{cloudStatus.unclaimed.recipes} recipe{cloudStatus.unclaimed.recipes !== 1 ? 's' : ''}</li>
												{/if}
												{#if cloudStatus.unclaimed.devices > 0}
													<li>{cloudStatus.unclaimed.devices} device{cloudStatus.unclaimed.devices !== 1 ? 's' : ''}</li>
												{/if}
											</ul>
											<button
												type="button"
												class="claim-btn"
												onclick={claimUnclaimedData}
												disabled={cloudClaimLoading}
											>
												{cloudClaimLoading ? 'Claiming...' : 'Claim My Data'}
											</button>
											{#if cloudClaimResult}
												<span class="claim-result" class:success={cloudClaimResult.success}>{cloudClaimResult.message}</span>
											{/if}
										</div>
									{/if}

									<div class="sync-to-cloud-box">
										<h4>Sync to Cloud</h4>
										<p>Push your local data to the cloud for backup and access from anywhere.</p>
										<button
											type="button"
											class="sync-btn"
											onclick={syncToCloud}
											disabled={cloudSyncLoading}
										>
											{#if cloudSyncLoading}
												<svg class="spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
													<path stroke-linecap="round" stroke-linejoin="round" d="M4 12a8 8 0 018-8V2m0 2a8 8 0 018 8h2" />
												</svg>
												Syncing...
											{:else}
												<svg class="sync-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
													<path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
												</svg>
												Sync Now
											{/if}
										</button>
										{#if cloudSyncResult}
											<div class="sync-result" class:success={cloudSyncResult.success} class:error={!cloudSyncResult.success}>
												{cloudSyncResult.message}
											</div>
										{/if}
									</div>

									<button type="button" class="disconnect-btn" onclick={handleCloudSignOut}>
										Disconnect Account
									</button>
								</div>
							{:else}
								<!-- Not Connected State -->
								<p class="section-intro">
									Connect your BrewSignal account to enable cloud sync features.
									Your data stays on your device until you choose to sync.
								</p>

								{#if cloudAuthMode}
									<!-- Auth Form -->
									<div class="cloud-auth-form">
										<h3>{cloudAuthMode === 'signup' ? 'Create Account' : 'Sign In'}</h3>

										{#if cloudAuthError}
											<div class="auth-message" class:error={!cloudAuthError.includes('Check your email')}>
												{cloudAuthError}
											</div>
										{/if}

										<!-- Google OAuth only in cloud mode (requires pre-registered redirect URLs) -->
										{#if config.isCloudMode}
											<button
												type="button"
												class="google-btn"
												onclick={handleCloudGoogleSignIn}
												disabled={cloudAuthLoading}
											>
												<svg class="google-icon" viewBox="0 0 24 24">
													<path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
													<path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
													<path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
													<path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
												</svg>
												Continue with Google
											</button>

											<div class="divider">
												<span>or</span>
											</div>
										{/if}

										<form onsubmit={handleCloudSignIn}>
											<div class="form-field">
												<label for="cloud-email">Email</label>
												<input
													type="email"
													id="cloud-email"
													bind:value={cloudEmail}
													required
													placeholder="you@example.com"
												/>
											</div>
											<div class="form-field">
												<label for="cloud-password">Password</label>
												<input
													type="password"
													id="cloud-password"
													bind:value={cloudPassword}
													required
													minlength="6"
													placeholder="••••••••"
												/>
											</div>
											<button type="submit" class="submit-btn" disabled={cloudAuthLoading}>
												{cloudAuthLoading ? 'Please wait...' : cloudAuthMode === 'signup' ? 'Create Account' : 'Sign In'}
											</button>
										</form>

										<div class="auth-footer">
											<button type="button" class="link-btn" onclick={() => cloudAuthMode = cloudAuthMode === 'signup' ? 'signin' : 'signup'}>
												{cloudAuthMode === 'signup' ? 'Already have an account? Sign in' : "Don't have an account? Sign up"}
											</button>
											<button type="button" class="link-btn" onclick={() => { cloudAuthMode = null; cloudAuthError = null; }}>
												Cancel
											</button>
										</div>
									</div>
								{:else}
									<!-- Connect Buttons -->
									<div class="connect-actions">
										<button type="button" class="primary-btn" onclick={() => cloudAuthMode = 'signin'}>
											Sign In
										</button>
										<button type="button" class="secondary-btn" onclick={() => cloudAuthMode = 'signup'}>
											Create Account
										</button>
									</div>

									<div class="cloud-benefits">
										<h4>Why connect?</h4>
										<ul class="benefits-list">
											<li>
												<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
													<path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
												</svg>
												Sync batches & recipes to the cloud
											</li>
											<li>
												<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
													<path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
												</svg>
												Access your data from anywhere
											</li>
											<li>
												<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
													<path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
												</svg>
												Share with brew buddies (coming soon)
											</li>
										</ul>
									</div>
								{/if}
							{/if}
						</div>
					{/if}
				</section>
			{/if}

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

	.info-box .warning {
		color: var(--error);
		font-size: 0.85rem;
		font-weight: 500;
	}

	.info-box.hailo {
		border-left: 3px solid var(--recipe-accent);
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

	/* Cloud Sync Styles */
	.loading-inline {
		padding: 1rem;
		color: var(--text-muted);
		text-align: center;
	}

	.cloud-connected {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
	}

	.connected-status {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 1rem;
		background: var(--green-900);
		border: 1px solid var(--green-700);
		border-radius: 0.5rem;
	}

	.connected-status .check-icon {
		width: 1.5rem;
		height: 1.5rem;
		color: var(--green-400);
		flex-shrink: 0;
	}

	.connected-label {
		display: block;
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	.connected-email {
		display: block;
		font-weight: 500;
		color: var(--text-primary);
	}

	.claim-data-box {
		padding: 1rem;
		background: var(--amber-900);
		border: 1px solid var(--amber-700);
		border-radius: 0.5rem;
	}

	.claim-data-box h4 {
		margin: 0 0 0.5rem 0;
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--amber-200);
	}

	.claim-data-box p {
		margin: 0 0 0.75rem 0;
		font-size: 0.8125rem;
		color: var(--text-secondary);
	}

	.unclaimed-list {
		margin: 0 0 1rem 1.25rem;
		padding: 0;
		font-size: 0.8125rem;
		color: var(--text-primary);
	}

	.unclaimed-list li {
		margin-bottom: 0.25rem;
	}

	.claim-btn {
		padding: 0.5rem 1rem;
		background: var(--amber-600);
		color: white;
		border: none;
		border-radius: 0.375rem;
		font-size: 0.875rem;
		font-weight: 500;
		cursor: pointer;
		transition: background-color 0.15s;
	}

	.claim-btn:hover:not(:disabled) {
		background: var(--amber-500);
	}

	.claim-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.claim-result {
		display: inline-block;
		margin-left: 0.75rem;
		font-size: 0.8125rem;
		color: var(--red-400);
	}

	.claim-result.success {
		color: var(--green-400);
	}

	.sync-to-cloud-box {
		padding: 1rem;
		background: var(--blue-900);
		border: 1px solid var(--blue-700);
		border-radius: 0.5rem;
	}

	.sync-to-cloud-box h4 {
		margin: 0 0 0.5rem 0;
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--blue-200);
	}

	.sync-to-cloud-box p {
		margin: 0 0 0.75rem 0;
		font-size: 0.8125rem;
		color: var(--text-secondary);
	}

	.sync-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.5rem 1rem;
		background: var(--blue-600);
		color: white;
		border: none;
		border-radius: 0.375rem;
		font-size: 0.875rem;
		font-weight: 500;
		cursor: pointer;
		transition: background-color 0.15s;
	}

	.sync-btn:hover:not(:disabled) {
		background: var(--blue-500);
	}

	.sync-btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.sync-btn .sync-icon,
	.sync-btn .spinner {
		width: 1rem;
		height: 1rem;
	}

	.sync-btn .spinner {
		animation: spin 1s linear infinite;
	}

	@keyframes spin {
		from { transform: rotate(0deg); }
		to { transform: rotate(360deg); }
	}

	.sync-result {
		display: block;
		margin-top: 0.75rem;
		padding: 0.5rem 0.75rem;
		border-radius: 0.375rem;
		font-size: 0.8125rem;
	}

	.sync-result.success {
		background: var(--green-900);
		border: 1px solid var(--green-700);
		color: var(--green-300);
	}

	.sync-result.error {
		background: var(--red-900);
		border: 1px solid var(--red-700);
		color: var(--red-300);
	}

	.cloud-features, .cloud-benefits {
		padding: 1rem;
		background: var(--gray-850);
		border: 1px solid var(--gray-800);
		border-radius: 0.5rem;
	}

	.cloud-features h4, .cloud-benefits h4 {
		margin: 0 0 0.75rem 0;
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--text-secondary);
	}

	.features-list, .benefits-list {
		margin: 0;
		padding: 0;
		list-style: none;
	}

	.features-list li {
		padding: 0.25rem 0;
		font-size: 0.8125rem;
		color: var(--text-muted);
	}

	.benefits-list li {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.375rem 0;
		font-size: 0.8125rem;
		color: var(--text-secondary);
	}

	.benefits-list li svg {
		width: 1rem;
		height: 1rem;
		color: var(--green-500);
		flex-shrink: 0;
	}

	.disconnect-btn {
		padding: 0.5rem 1rem;
		background: transparent;
		color: var(--red-400);
		border: 1px solid var(--red-700);
		border-radius: 0.375rem;
		font-size: 0.8125rem;
		cursor: pointer;
		transition: all 0.15s;
	}

	.disconnect-btn:hover {
		background: var(--red-900);
		border-color: var(--red-600);
	}

	.cloud-auth-form {
		max-width: 24rem;
	}

	.cloud-auth-form h3 {
		margin: 0 0 1rem 0;
		font-size: 1.125rem;
		font-weight: 600;
		color: var(--text-primary);
	}

	.auth-message {
		padding: 0.75rem;
		margin-bottom: 1rem;
		border-radius: 0.375rem;
		font-size: 0.8125rem;
		background: var(--green-900);
		border: 1px solid var(--green-700);
		color: var(--green-300);
	}

	.auth-message.error {
		background: var(--red-900);
		border: 1px solid var(--red-700);
		color: var(--red-300);
	}

	.google-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.75rem;
		width: 100%;
		padding: 0.625rem 1rem;
		background: white;
		color: #374151;
		border: none;
		border-radius: 0.375rem;
		font-size: 0.875rem;
		font-weight: 500;
		cursor: pointer;
		transition: background-color 0.15s;
	}

	.google-btn:hover:not(:disabled) {
		background: #f3f4f6;
	}

	.google-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.google-icon {
		width: 1.25rem;
		height: 1.25rem;
	}

	.divider {
		display: flex;
		align-items: center;
		margin: 1rem 0;
	}

	.divider::before, .divider::after {
		content: '';
		flex: 1;
		height: 1px;
		background: var(--gray-700);
	}

	.divider span {
		padding: 0 0.75rem;
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	.cloud-auth-form form {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.submit-btn {
		width: 100%;
		padding: 0.625rem 1rem;
		background: var(--amber-600);
		color: white;
		border: none;
		border-radius: 0.375rem;
		font-size: 0.875rem;
		font-weight: 500;
		cursor: pointer;
		transition: background-color 0.15s;
	}

	.submit-btn:hover:not(:disabled) {
		background: var(--amber-500);
	}

	.submit-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.auth-footer {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.5rem;
		margin-top: 1rem;
	}

	.link-btn {
		background: none;
		border: none;
		color: var(--text-muted);
		font-size: 0.8125rem;
		cursor: pointer;
		padding: 0.25rem 0;
	}

	.link-btn:hover {
		color: var(--text-secondary);
		text-decoration: underline;
	}

	.connect-actions {
		display: flex;
		gap: 0.75rem;
		margin-bottom: 1.5rem;
	}

	.primary-btn {
		padding: 0.625rem 1.25rem;
		background: var(--amber-600);
		color: white;
		border: none;
		border-radius: 0.375rem;
		font-size: 0.875rem;
		font-weight: 500;
		cursor: pointer;
		transition: background-color 0.15s;
	}

	.primary-btn:hover {
		background: var(--amber-500);
	}

	/* Device Control Section */
	.section-desc {
		font-size: 0.8125rem;
		color: var(--text-secondary);
		margin-bottom: 1rem;
	}

	.radio-group {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		margin-bottom: 1rem;
	}

	.radio-option {
		display: flex;
		align-items: flex-start;
		gap: 0.75rem;
		padding: 0.75rem 1rem;
		background: var(--gray-850);
		border: 1px solid var(--gray-700);
		border-radius: 0.5rem;
		cursor: pointer;
		transition: all 0.15s;
	}

	.radio-option:hover {
		border-color: var(--gray-600);
	}

	.radio-option.selected {
		border-color: var(--accent);
		background: var(--gray-800);
	}

	.radio-option input[type="radio"] {
		margin-top: 0.125rem;
		accent-color: var(--accent);
	}

	.radio-content {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
	}

	.radio-label {
		font-size: 0.875rem;
		font-weight: 500;
		color: var(--text-primary);
	}

	.radio-desc {
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	.info-box svg {
		width: 1rem;
		height: 1rem;
		flex-shrink: 0;
		color: var(--accent);
	}

	.info-box > span {
		font-size: 0.8125rem;
		color: var(--text-secondary);
		line-height: 1.5;
	}

	.section-content > .info-box {
		display: flex;
		align-items: flex-start;
		gap: 0.75rem;
	}

	.subsection-desc {
		font-size: 0.75rem;
		color: var(--text-muted);
		margin-bottom: 0.75rem;
	}

	.device-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		margin-bottom: 0.75rem;
	}

	.device-item {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 0.5rem;
		padding: 0.5rem 0.75rem;
		background: var(--gray-850);
		border: 1px solid var(--gray-700);
		border-radius: 0.375rem;
	}

	.device-ip {
		font-family: var(--font-mono);
		font-size: 0.8125rem;
		color: var(--text-primary);
		flex: 1;
	}

	.device-actions {
		display: flex;
		align-items: center;
		gap: 0.375rem;
	}

	.test-btn.small {
		padding: 0.25rem 0.5rem;
		font-size: 0.6875rem;
	}

	.remove-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 1.5rem;
		height: 1.5rem;
		padding: 0;
		background: transparent;
		border: none;
		border-radius: 0.25rem;
		color: var(--text-muted);
		cursor: pointer;
		transition: all 0.15s;
	}

	.remove-btn:hover {
		background: var(--gray-700);
		color: var(--error);
	}

	.remove-btn svg {
		width: 0.875rem;
		height: 0.875rem;
	}

	.device-item .test-result {
		width: 100%;
		font-size: 0.75rem;
		margin-top: 0.25rem;
	}

	.add-device-form {
		display: flex;
		gap: 0.5rem;
		margin-bottom: 0.75rem;
	}

	.add-device-form input {
		flex: 1;
		padding: 0.5rem 0.75rem;
		font-family: var(--font-mono);
		font-size: 0.8125rem;
		background: var(--gray-900);
		border: 1px solid var(--gray-700);
		border-radius: 0.375rem;
		color: var(--text-primary);
	}

	.add-device-form input:focus {
		outline: none;
		border-color: var(--accent);
	}

	.add-btn {
		padding: 0.5rem 0.75rem;
		background: var(--gray-700);
		color: var(--text-primary);
		border: none;
		border-radius: 0.375rem;
		font-size: 0.8125rem;
		font-weight: 500;
		cursor: pointer;
		transition: background-color 0.15s;
	}

	.add-btn:hover {
		background: var(--gray-600);
	}

	.help-text {
		font-size: 0.75rem;
		color: var(--text-muted);
		line-height: 1.6;
	}

	.help-text code {
		font-family: var(--font-mono);
		font-size: 0.6875rem;
		padding: 0.125rem 0.375rem;
		background: var(--gray-800);
		border-radius: 0.25rem;
		color: var(--accent);
	}

	.help-text p {
		margin: 0.25rem 0;
	}

	.help-text a {
		color: var(--accent);
		text-decoration: none;
	}

	.help-text a:hover {
		text-decoration: underline;
	}

	.help-text .help-detail {
		margin-top: 0.5rem;
		padding-top: 0.5rem;
		border-top: 1px solid var(--gray-700);
	}

	.info-hint {
		font-size: 0.75rem;
		color: var(--text-muted);
		margin-top: 0.5rem;
	}

	.info-hint a {
		color: var(--accent);
	}

	.info-hint a:hover {
		text-decoration: underline;
	}

	.local-only-note {
		font-size: 0.75rem;
		color: var(--warning, #f59e0b);
		background: rgba(245, 158, 11, 0.1);
		padding: 0.5rem 0.75rem;
		border-radius: 0.375rem;
		margin-bottom: 0.75rem;
	}
</style>
