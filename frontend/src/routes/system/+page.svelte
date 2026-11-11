<script lang="ts">
	import { onMount, tick } from 'svelte';
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

	// Chamber idle mode state
	let chamberIdleEnabled = $state(false);
	let chamberIdleTarget = $state(15.0);
	let chamberIdleHysteresis = $state(2.0);

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
		// Chamber idle mode - stored in Celsius, convert to display units
		chamberIdleEnabled = configState.config.chamber_idle_enabled;
		chamberIdleTarget = useCelsius
			? configState.config.chamber_idle_target
			: Math.round(celsiusToFahrenheit(configState.config.chamber_idle_target) * 2) / 2;
		chamberIdleHysteresis = useCelsius
			? configState.config.chamber_idle_hysteresis
			: Math.round(configState.config.chamber_idle_hysteresis * (9 / 5) * 100) / 100;
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
				// Provider may have changed while this request was in flight
				if (provider !== aiProvider) return;
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

			// Chamber idle: convert display units back to Celsius for storage
			const idleTargetC = useCelsius ? chamberIdleTarget : fahrenheitToCelsius(chamberIdleTarget);
			const idleHysteresisC = useCelsius ? chamberIdleHysteresis : chamberIdleHysteresis * (5 / 9);

			const result = await updateConfig({
				temp_control_enabled: tempControlEnabled,
				temp_target: targetF,
				temp_hysteresis: hysteresisF,
				chamber_idle_enabled: chamberIdleEnabled,
				chamber_idle_target: idleTargetC,
				chamber_idle_hysteresis: idleHysteresisC,
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

	// Left index: open the section and scroll to it
	const sectionIndex = $derived([
		{ label: 'AI', id: 'ai', open: 'ai' },
		{ label: 'Home Assistant', id: 'homeassistant', open: 'homeassistant' },
		{ label: 'MQTT', id: 'mqtt', open: 'mqtt' },
		...(haEnabled ? [{ label: 'Temperature control', id: 'temp-control', open: 'homeassistant' }] : []),
		{ label: 'Units', id: 'display', open: 'display' },
		{ label: 'Devices', id: 'devicecontrol', open: 'devicecontrol' },
		{ label: 'Data', id: 'storage', open: 'storage' },
		...(authEnabled ? [{ label: 'Cloud sync', id: 'cloud', open: 'cloud' }] : []),
		{ label: 'Power', id: 'power', open: 'power' },
		{ label: 'About', id: 'about', open: null as string | null }
	]);

	async function goSection(id: string, open: string | null) {
		if (open) expandedSection = open;
		await tick();
		const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
		document.getElementById('sec-' + id)?.scrollIntoView({ block: 'start', behavior: reduce ? 'auto' : 'smooth' });
	}

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
		<nav class="section-index" aria-label="Settings sections">
			<ul>
				{#each sectionIndex as item}
					<li>
						<button
							type="button"
							class="index-link"
							class:current={item.open !== null && item.id !== 'temp-control' && expandedSection === item.open}
							onclick={() => goSection(item.id, item.open)}
						>
							{item.label}
						</button>
					</li>
				{/each}
				{#each [{ href: '/devices', label: 'Paired devices' }, { href: '/calibration', label: 'Calibration' }, { href: '/logging', label: 'Logging' }, { href: '/system/maintenance', label: 'Maintenance' }] as l}
					<li class="index-page">
						<a href={l.href} class="index-link">{l.label}</a>
					</li>
				{/each}
			</ul>
		</nav>

		<div class="system-main">
		<!-- System Status Banner -->
		<header class="status-banner" id="sec-about">
			<h2 class="about-title">About this system</h2>
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

		<!-- Settings Sections -->
		<div class="settings-container">
			<!-- Display & Units Section -->
			<section class="settings-section" id="sec-display" style="order: 4">
				<button
					type="button"
					class="section-header"
					onclick={() => toggleSection('display')}
					aria-expanded={expandedSection === 'display'}
				>
					<div class="section-title-group">
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
								<span class="setting-label">Temperature</span>
								<div class="toggle-group" role="group" aria-label="Temperature units">
									<button type="button" class="toggle-btn" class:active={tempUnits === 'C'} onclick={() => (tempUnits = 'C')}>°C</button>
									<button type="button" class="toggle-btn" class:active={tempUnits === 'F'} onclick={() => (tempUnits = 'F')}>°F</button>
								</div>
							</div>
							<div class="setting-group">
								<span class="setting-label">Gravity</span>
								<div class="toggle-group triple" role="group" aria-label="Gravity units">
									<button type="button" class="toggle-btn" class:active={sgUnits === 'sg'} onclick={() => (sgUnits = 'sg')}>SG</button>
									<button type="button" class="toggle-btn" class:active={sgUnits === 'plato'} onclick={() => (sgUnits = 'plato')}>°P</button>
									<button type="button" class="toggle-btn" class:active={sgUnits === 'brix'} onclick={() => (sgUnits = 'brix')}>°Bx</button>
								</div>
							</div>
							<div class="setting-group">
								<label class="setting-label" for="min-rssi">Min Signal</label>
								<div class="input-group">
									<input id="min-rssi" type="number" min="-100" max="0" bind:value={minRssi} class="num-input" />
									<span class="input-unit">&thinsp;dBm</span>
								</div>
							</div>
							<div class="setting-group">
								<label class="setting-label" for="timezone">Timezone</label>
								<select
									id="timezone"
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
										<select bind:value={smoothingSamples} class="mini-select" aria-label="Smoothing samples">
											<option value={3}>3</option>
											<option value={5}>5</option>
											<option value={10}>10</option>
											<option value={15}>15</option>
											<option value={20}>20</option>
										</select>
									{/if}
									<button
										type="button"
										class="switch" aria-label="Reading Smoothing"
										class:on={smoothingEnabled}
										onclick={() => (smoothingEnabled = !smoothingEnabled)}
										aria-pressed={smoothingEnabled}
									>
										<span class="switch-state">{smoothingEnabled ? 'On' : 'Off'}</span>
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
									class="switch" aria-label="Identify by MAC"
									class:on={idByMac}
									onclick={() => (idByMac = !idByMac)}
									aria-pressed={idByMac}
								>
									<span class="switch-state">{idByMac ? 'On' : 'Off'}</span>
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
			<section class="settings-section" id="sec-homeassistant" style="order: 2">
				<button
					type="button"
					class="section-header"
					onclick={() => toggleSection('homeassistant')}
					aria-expanded={expandedSection === 'homeassistant'}
				>
					<div class="section-title-group">
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
								class="switch" aria-label="Enable Integration"
								class:on={haEnabled}
								onclick={() => (haEnabled = !haEnabled)}
								aria-pressed={haEnabled}
							>
								<span class="switch-state">{haEnabled ? 'On' : 'Off'}</span>
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
								{#if haTesting}<span class="checking" role="status">Checking&hellip;</span>{/if}
								{#if haTestResult}
									<span role="status" class="test-result" class:success={haTestResult.success}>{haTestResult.message}</span>
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
											class="switch" aria-label="Enable Alerts"
											class:on={weatherAlertsEnabled}
											onclick={() => (weatherAlertsEnabled = !weatherAlertsEnabled)}
											aria-pressed={weatherAlertsEnabled}
										>
											<span class="switch-state">{weatherAlertsEnabled ? 'On' : 'Off'}</span>
						<span class="switch-thumb"></span>
										</button>
									</div>
									{#if weatherAlertsEnabled}
										<div class="inline-setting">
	<span>Alert when forecast differs by more than</span>
											<div class="input-group compact">
												<input aria-label="Alert when forecast differs by more than" type="number" min="1" max="15" step="0.5" bind:value={alertTempThreshold} class="num-input" />
												<span class="input-unit">&thinsp;°C</span>
											</div>
										</div>
									{/if}
								</div>
							{/if}

							{#if haEnabled}
								<div class="subsection" id="sec-temp-control">
									<h3>Temperature Control</h3>
									<div class="toggle-setting">
										<div class="toggle-info">
											<span class="toggle-label">Enable Control</span>
											<span class="toggle-desc">Automatically manage heaters for batches</span>
										</div>
										<button
											type="button"
											class="switch" aria-label="Enable Control"
											class:on={tempControlEnabled}
											onclick={() => (tempControlEnabled = !tempControlEnabled)}
											aria-pressed={tempControlEnabled}
										>
											<span class="switch-state">{tempControlEnabled ? 'On' : 'Off'}</span>
						<span class="switch-thumb"></span>
										</button>
									</div>
									{#if tempControlEnabled}
										<div class="control-defaults">
											<div class="inline-setting">
	<span>Default target</span>
												<div class="input-group compact">
													<input aria-label="Default target" type="number" bind:value={tempTarget} min={useCelsius ? 0 : 32} max={useCelsius ? 38 : 100} step="0.5" class="num-input" />
													<span class="input-unit">{tempUnitSymbol}</span>
												</div>
											</div>
											<div class="inline-setting">
	<span>Hysteresis</span>
												<div class="input-group compact">
													<input aria-label="Hysteresis" type="number" bind:value={tempHysteresis} min={useCelsius ? 0.3 : 0.5} max={useCelsius ? 5.5 : 10} step={useCelsius ? 0.25 : 0.5} class="num-input" />
													<span class="input-unit">±{tempUnitSymbol}</span>
												</div>
											</div>
										</div>
									{/if}
								</div>
								{#if tempControlEnabled}
									<div class="subsection">
										<h3>Chamber Idle Mode</h3>
										<div class="toggle-setting">
											<div class="toggle-info">
												<span class="toggle-label">Enable Idle Control</span>
												<span class="toggle-desc">Control chamber temp when no batches are active</span>
											</div>
											<button
												type="button"
												class="switch" aria-label="Enable Idle Control"
												class:on={chamberIdleEnabled}
												onclick={() => (chamberIdleEnabled = !chamberIdleEnabled)}
												aria-pressed={chamberIdleEnabled}
											>
												<span class="switch-state">{chamberIdleEnabled ? 'On' : 'Off'}</span>
						<span class="switch-thumb"></span>
											</button>
										</div>
										{#if chamberIdleEnabled}
											<div class="control-defaults">
												<div class="inline-setting">
	<span>Idle target</span>
													<div class="input-group compact">
														<input aria-label="Idle target" type="number" bind:value={chamberIdleTarget} min={useCelsius ? 0 : 32} max={useCelsius ? 30 : 86} step="0.5" class="num-input" />
														<span class="input-unit">{tempUnitSymbol}</span>
													</div>
												</div>
												<div class="inline-setting">
	<span>Hysteresis</span>
													<div class="input-group compact">
														<input aria-label="Hysteresis" type="number" bind:value={chamberIdleHysteresis} min={useCelsius ? 0.5 : 1} max={useCelsius ? 5.5 : 10} step={useCelsius ? 0.25 : 0.5} class="num-input" />
														<span class="input-unit">±{tempUnitSymbol}</span>
													</div>
												</div>
											</div>
										{/if}
									</div>
								{/if}
								{#if tempControlEnabled}
									<div class="section-actions" style="margin-top: 0.75rem;">
										<button type="button" class="save-btn" onclick={saveControlConfig} disabled={controlSaving}>
											{controlSaving ? 'Saving...' : 'Save Temperature Settings'}
										</button>
										{#if controlError}<span class="error-msg">{controlError}</span>{/if}
										{#if controlSuccess}<span class="success-msg">Saved</span>{/if}
									</div>
								{/if}
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
			<section class="settings-section" id="sec-devicecontrol" style="order: 5">
				<button
					type="button"
					class="section-header"
					onclick={() => toggleSection('devicecontrol')}
					aria-expanded={expandedSection === 'devicecontrol'}
				>
					<div class="section-title-group">
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
								<p class="local-only-note"><span class="pill-tag">Note</span> Direct Shelly control requires BrewSignal and Shelly devices on the same local network.</p>

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
												<button type="button" class="remove-btn" onclick={() => removeShellyDevice(ip)} title="Remove device" aria-label="Remove device {ip}">
													<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
														<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
													</svg>
												</button>
											</div>
											{#if shellyTestResult?.ip === ip}
												<span role="status" class="test-result" class:success={shellyTestResult.success}>
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
			<section class="settings-section" id="sec-ai" style="order: 1">
				<button
					type="button"
					class="section-header"
					onclick={() => toggleSection('ai')}
					aria-expanded={expandedSection === 'ai'}
				>
					<div class="section-title-group">
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
								class="switch" aria-label="Enable AI Assistant"
								class:on={aiEnabled}
								onclick={() => (aiEnabled = !aiEnabled)}
								aria-pressed={aiEnabled}
							>
								<span class="switch-state">{aiEnabled ? 'On' : 'Off'}</span>
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
									class="switch" aria-label="Local Lite LLM"
									class:on={aiLiteEnabled}
									onclick={() => (aiLiteEnabled = !aiLiteEnabled)}
									aria-pressed={aiLiteEnabled}
								>
									<span class="switch-state">{aiLiteEnabled ? 'On' : 'Off'}</span>
						<span class="switch-thumb"></span>
								</button>
							</div>
							{#if aiLiteEnabled}
								<div class="info-box success compact">
									<p>Hailo AI HAT+ will handle thread summaries and other lightweight tasks locally.</p>
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
								{#if aiTesting}<span class="checking" role="status">Checking&hellip;</span>{/if}
								{#if aiTestResult}
									{#if aiTestResult.success}
										<span class="test-result success">Connected! "{aiTestResult.response}"</span>
									{:else}
										<span role="status" class="test-result">{aiTestResult.error}</span>
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
			<section class="settings-section" id="sec-mqtt" style="order: 3">
				<button
					type="button"
					class="section-header"
					onclick={() => toggleSection('mqtt')}
					aria-expanded={expandedSection === 'mqtt'}
				>
					<div class="section-title-group">
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
								class="switch" aria-label="Enable MQTT Publishing"
								class:on={mqttEnabled}
								onclick={() => (mqttEnabled = !mqttEnabled)}
								aria-pressed={mqttEnabled}
							>
								<span class="switch-state">{mqttEnabled ? 'On' : 'Off'}</span>
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
								{#if mqttTesting}<span class="checking" role="status">Checking&hellip;</span>{/if}
								{#if mqttTestResult}
									<span role="status" class="test-result" class:success={mqttTestResult.success}>{mqttTestResult.message}</span>
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
			<section class="settings-section" id="sec-storage" style="order: 6">
				<button
					type="button"
					class="section-header"
					onclick={() => toggleSection('storage')}
					aria-expanded={expandedSection === 'storage'}
				>
					<div class="section-title-group">
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
								<span class="cleanup-label">Keep readings from last</span>
								<div class="input-group compact">
									<input type="number" min="1" max="365" bind:value={cleanupRetentionDays} class="num-input" aria-label="Retention days" />
									<span class="input-unit">&thinsp;days</span>
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
				<section class="settings-section" id="sec-cloud" style="order: 7">
					<button
						type="button"
						class="section-header"
						onclick={() => toggleSection('cloud')}
						aria-expanded={expandedSection === 'cloud'}
					>
						<div class="section-title-group">
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
								<div class="loading-inline" role="status">Checking&hellip;</div>
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
												<svg class="google-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
													<path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
													<path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
													<path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
													<path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
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
			<section class="settings-section danger-section" id="sec-power" style="order: 8">
				<button
					type="button"
					class="section-header"
					onclick={() => toggleSection('power')}
					aria-expanded={expandedSection === 'power'}
				>
					<div class="section-title-group">
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
		</div>
	{/if}
</div>
<style>
	/* Page layout: sticky section index (desk) + main column */
	.system-page {
		display: grid;
		grid-template-columns: 12rem minmax(0, 1fr);
		gap: var(--space-xl);
		align-items: start;
		max-width: 64rem;
		margin: 0 auto;
	}
	.system-main {
		display: flex;
		flex-direction: column;
		min-width: 0;
	}
	.system-main > .settings-container {
		order: 1;
	}
	.system-main > .status-banner {
		order: 2;
	}

	/* Section index */
	.section-index {
		position: sticky;
		top: var(--space-lg);
		align-self: start;
	}
	.section-index ul {
		list-style: none;
		margin: 0;
		padding: 0;
		border-top: 1px solid var(--rule-hairline);
	}
	.index-link {
		display: flex;
		align-items: center;
		width: 100%;
		min-height: 44px;
		padding: 0 var(--space-xs);
		text-align: left;
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--ink-secondary);
		border-bottom: 1px solid var(--rule-hairline);
		cursor: pointer;
		transition: color 140ms var(--ease-out-quart);
	}
	.index-link:hover {
		color: var(--ink-primary);
		background: var(--bg-surface);
	}
	.index-link.current {
		color: var(--accent);
	}
	.index-page .index-link {
		color: var(--ink-muted);
		text-decoration: none;
	}
	.index-page .index-link:hover {
		color: var(--ink-primary);
	}
	.index-link:focus-visible,
	.section-header:focus-visible,
	.switch:focus-visible,
	.toggle-btn:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: -2px;
	}

	/* Loading */
	.loading-state {
		grid-column: 1 / -1;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: var(--space-md);
		padding: var(--space-xl) 0;
		color: var(--ink-muted);
		font-size: var(--text-sm);
	}
	.loading-spinner {
		width: 2rem;
		height: 2rem;
		border: 2px solid var(--rule-strong);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	/* About: readout grid */
	.status-banner {
		scroll-margin-top: var(--space-lg);
		margin-top: var(--space-xl);
		padding-top: var(--space-md);
		border-top: 1px solid var(--rule-strong);
	}
	.about-title {
		font-family: var(--font-display);
		font-size: var(--text-base);
		font-weight: 600;
		color: var(--ink-primary);
		margin-bottom: var(--space-sm);
	}
	.status-grid {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		border: 1px solid var(--rule-hairline);
		background: var(--bg-surface);
	}
	.status-item {
		display: flex;
		flex-direction: column;
		gap: var(--space-2xs);
		padding: var(--space-sm);
		border-right: 1px solid var(--rule-hairline);
		border-bottom: 1px solid var(--rule-hairline);
		min-width: 0;
	}
	.status-label {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--ink-muted);
	}
	.status-value {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: var(--text-sm);
		color: var(--ink-primary);
		overflow-wrap: anywhere;
	}
	.ai-chip {
		display: inline-flex;
		align-items: center;
		gap: var(--space-xs);
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
	.ai-status.active .ai-chip {
		color: var(--accent);
		border-color: var(--accent-rule);
		background: var(--accent-tint);
	}
	.ai-dot {
		width: 6px;
		height: 6px;
		background: var(--accent);
		border-radius: 50%;
	}
	.ai-tops {
		color: var(--ink-muted);
		font-family: var(--font-num);
		font-weight: 500;
	}
	.ai-unavailable {
		color: var(--ink-muted);
		font-size: var(--text-sm);
	}

	/* Settings sections: hairline, flat */
	.settings-container {
		display: flex;
		flex-direction: column;
	}
	.settings-section {
		scroll-margin-top: var(--space-lg);
		border-top: 1px solid var(--rule-strong);
		margin-bottom: var(--space-md);
	}
	.settings-section.danger-section {
		border-top-color: color-mix(in oklch, var(--status-danger) 55%, transparent);
	}
	.section-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		width: 100%;
		min-height: 52px;
		padding: var(--space-xs) var(--space-xs);
		background: transparent;
		cursor: pointer;
		text-align: left;
	}
	.section-header:hover {
		background: var(--bg-surface);
	}
	.section-title-group {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: var(--space-sm);
	}
	.section-header h2 {
		font-family: var(--font-display);
		font-size: var(--text-lg);
		font-weight: 600;
		color: var(--ink-primary);
		margin: 0;
	}
	.chevron {
		width: 1.125rem;
		height: 1.125rem;
		color: var(--ink-muted);
		transition: transform 140ms var(--ease-out-quart);
	}
	.chevron.rotated {
		transform: rotate(180deg);
	}
	.section-content {
		padding: 0 var(--space-xs) var(--space-md);
	}
	.section-intro {
		max-width: 44rem;
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		margin: 0 0 var(--space-sm);
	}

	/* Outlined status pills */
	.status-pill,
	.storage-badge,
	.pill-tag {
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
	.storage-badge {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		text-transform: none;
		letter-spacing: 0;
	}
	.status-pill.connected {
		color: var(--status-steady);
		border-color: currentColor;
	}
	.status-pill.disconnected {
		color: var(--status-danger);
		border-color: color-mix(in oklch, var(--status-danger) 60%, transparent);
	}
	.status-pill.enabled {
		color: var(--status-steady);
		border-color: currentColor;
	}
	.pill-tag {
		color: var(--status-warn);
		border-color: color-mix(in oklch, var(--status-warn) 60%, transparent);
	}

	/* Unit rows: one setting per row */
	.settings-grid {
		display: flex;
		flex-direction: column;
		padding: 0;
	}
	.setting-group {
		display: grid;
		grid-template-columns: 200px minmax(0, 1fr);
		align-items: center;
		gap: var(--space-xs) var(--space-md);
		padding: 12px 0;
		border-bottom: 1px solid var(--rule-hairline);
		min-width: 0;
	}
	.setting-group > .toggle-group,
	.setting-group > .input-group {
		justify-self: start;
	}
	.setting-group > .toggle-group {
		min-width: 12rem;
	}
	.toggle-group.triple {
		min-width: 15rem;
	}
	.setting-group > .select-input {
		max-width: 24rem;
	}
	.setting-label,
	.form-field label,
	.subsection h3 {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--ink-muted);
	}

	/* Segmented toggle */
	.toggle-group {
		display: flex;
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		overflow: hidden;
	}
	.toggle-btn {
		flex: 1;
		min-height: 42px;
		padding: 0 var(--space-sm);
		font-family: var(--font-num);
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--ink-muted);
		cursor: pointer;
		transition: background-color 140ms var(--ease-out-quart);
	}
	.toggle-btn + .toggle-btn {
		border-left: 1px solid var(--rule-strong);
	}
	.toggle-btn:hover {
		color: var(--ink-primary);
	}
	.toggle-btn.active {
		background: var(--bg-elevated);
		color: var(--ink-primary);
		box-shadow: inset 0 0 0 1px var(--rule-strong);
	}

	/* Fields */
	.input-group {
		display: flex;
		align-items: center;
		gap: var(--space-2xs);
	}
	.num-input,
	.select-input,
	.mini-select,
	.form-field input,
	.form-field select,
	.add-device-form input {
		min-height: 44px;
		padding: 0 var(--space-sm);
		font-size: var(--text-base);
		color: var(--ink-primary);
		background-color: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
	}
	.num-input {
		width: 5.5rem;
		font-family: var(--font-body);
		font-variant-numeric: tabular-nums;
		letter-spacing: 0;
		text-align: right;
	}
	.select-input,
	.mini-select,
	.form-field select {
		appearance: none;
		padding-right: 32px;
		text-overflow: ellipsis;
		cursor: pointer;
		background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%23888' stroke-width='2'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' d='M19 9l-7 7-7-7'/%3E%3C/svg%3E");
		background-repeat: no-repeat;
		background-position: right 0.5rem center;
		background-size: 1rem;
	}
	.select-input {
		width: 100%;
	}
	.mini-select {
		font-family: var(--font-num);
		font-size: var(--text-sm);
	}
	.num-input:focus-visible,
	.select-input:focus-visible,
	.mini-select:focus-visible,
	.form-field input:focus-visible,
	.form-field select:focus-visible,
	.add-device-form input:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
		border-color: var(--accent);
	}
	.input-unit {
		font-family: var(--font-num);
		font-size: var(--text-sm);
		color: var(--ink-muted);
	}
	.settings-divider {
		height: 0;
		border-top: 1px solid var(--rule-hairline);
	}

	/* Setting rows: label + help left, control right */
	.toggle-settings {
		display: flex;
		flex-direction: column;
	}
	.toggle-setting {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-md);
		min-height: 56px;
		padding: 12px 0;
		border-bottom: 1px solid var(--rule-hairline);
	}
	.toggle-setting.prominent {
		border-top: 1px solid var(--rule-hairline);
	}
	.toggle-info {
		display: flex;
		flex-direction: column;
		gap: 2px;
		min-width: 0;
	}
	.toggle-label {
		font-weight: 700;
		color: var(--ink-primary);
	}
	.toggle-desc {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}
	.toggle-controls {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
	}

	/* Switch with On/Off text */
	.switch {
		display: inline-flex;
		align-items: center;
		gap: var(--space-xs);
		min-height: 44px;
		padding: 0 var(--space-2xs);
		cursor: pointer;
	}
	.switch-state {
		min-width: 1.75rem;
		text-align: right;
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--ink-muted);
	}
	.switch.on .switch-state {
		color: var(--status-steady);
	}
	.switch-thumb {
		position: relative;
		flex: none;
		width: 2.5rem;
		height: 1.5rem;
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		background: var(--bg-subtle);
	}
	.switch-thumb::after {
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
	.switch.on .switch-thumb {
		border-color: var(--status-steady);
	}
	.switch.on .switch-thumb::after {
		transform: translateX(1rem);
		background: var(--status-steady);
	}

	/* Form rows */
	.form-grid {
		display: flex;
		flex-direction: column;
		padding: var(--space-xs) 0;
	}
	.form-field {
		display: grid;
		grid-template-columns: 200px minmax(0, 1fr);
		align-items: center;
		gap: var(--space-2xs) var(--space-md);
		padding: 12px 0;
		border-bottom: 1px solid var(--rule-hairline);
	}
	.form-field > :not(label) {
		grid-column: 2;
	}
	.form-field input::placeholder {
		color: var(--ink-muted);
	}
	.field-hint {
		font-size: var(--text-xs);
		color: var(--ink-muted);
	}
	.field-hint.success {
		color: var(--status-steady);
	}

	/* Subsections */
	.subsection {
		margin-top: var(--space-lg);
		padding-top: var(--space-sm);
		border-top: 1px solid var(--rule-hairline);
		scroll-margin-top: var(--space-lg);
	}
	.subsection h3 {
		margin-bottom: var(--space-xs);
	}
	.inline-setting {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: var(--space-sm);
		padding: var(--space-xs) 0;
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}
	.control-defaults {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-xs) var(--space-lg);
	}

	/* Info box: hairline, flat */
	.info-box {
		padding: var(--space-sm) var(--space-md);
		margin: var(--space-sm) 0;
		background: var(--bg-surface);
		border: 1px solid var(--rule-hairline);
		border-radius: 4px;
	}
	.info-box.success {
		border-color: color-mix(in oklch, var(--status-steady) 55%, transparent);
	}
	.info-box.compact {
		padding: var(--space-xs) var(--space-sm);
	}
	.info-box h4 {
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--ink-primary);
		margin-bottom: var(--space-xs);
	}
	.info-box p {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		margin: var(--space-xs) 0;
	}
	.info-box ol {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		padding-left: var(--space-lg);
		margin: var(--space-xs) 0;
	}
	.info-box li {
		margin: var(--space-2xs) 0;
	}
	.info-box code,
	.help-text code {
		font-family: var(--font-num);
		font-size: var(--text-xs);
		padding: 1px var(--space-xs);
		background: var(--bg-subtle);
		border-radius: 2px;
		color: var(--ink-primary);
	}
	.info-box a,
	.help-text a,
	.info-hint a {
		color: var(--accent);
	}
	.info-box a:hover,
	.help-text a:hover,
	.info-hint a:hover {
		text-decoration: underline;
	}
	.info-box .gpu-detected {
		color: var(--status-steady);
	}
	.info-box .hint,
	.info-hint {
		font-size: var(--text-xs);
		color: var(--ink-muted);
		margin-top: var(--space-xs);
	}
	.info-box svg {
		width: 1rem;
		height: 1rem;
		flex-shrink: 0;
		color: var(--ink-muted);
	}
	.section-content > .info-box {
		display: flex;
		align-items: flex-start;
		gap: var(--space-sm);
	}
	.section-content > .info-box > div > span {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}

	.advanced-settings {
		margin-top: var(--space-sm);
	}
	.advanced-settings summary {
		display: flex;
		align-items: center;
		min-height: 44px;
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		cursor: pointer;
	}
	.advanced-settings summary:hover {
		color: var(--ink-primary);
	}

	/* Actions */
	.inline-actions {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: var(--space-sm);
		padding: var(--space-sm) 0;
	}
	.section-actions {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: var(--space-md);
		margin-top: var(--space-md);
		padding-top: var(--space-md);
		border-top: 1px solid var(--rule-hairline);
	}
	.save-btn,
	.primary-btn,
	.submit-btn {
		min-height: 44px;
		padding: 0 var(--space-md);
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--accent-ink);
		background: var(--accent);
		border-radius: 4px;
		cursor: pointer;
		transition: background-color 140ms var(--ease-out-quart);
	}
	.save-btn:hover:not(:disabled),
	.primary-btn:hover:not(:disabled),
	.submit-btn:hover:not(:disabled) {
		background: var(--accent-hover);
	}
	.save-btn:disabled,
	.submit-btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}
	.submit-btn {
		width: 100%;
	}
	.test-btn,
	.secondary-btn,
	.sync-btn,
	.add-btn,
	.claim-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: var(--space-xs);
		min-height: 44px;
		padding: 0 var(--space-md);
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--ink-primary);
		background: var(--bg-subtle);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		cursor: pointer;
		transition: background-color 140ms var(--ease-out-quart);
	}
	.test-btn:hover:not(:disabled),
	.secondary-btn:hover:not(:disabled),
	.sync-btn:hover:not(:disabled),
	.add-btn:hover,
	.claim-btn:hover:not(:disabled) {
		background: var(--accent-tint);
		border-color: var(--accent-rule);
	}
	.test-btn:disabled,
	.secondary-btn:disabled,
	.sync-btn:disabled,
	.claim-btn:disabled,
	.google-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
	.test-btn.small {
		font-size: var(--text-xs);
		padding: 0 var(--space-sm);
	}
	.warning-btn,
	.danger-btn,
	.disconnect-btn {
		display: inline-flex;
		align-items: center;
		gap: var(--space-xs);
		min-height: 44px;
		padding: 0 var(--space-md);
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		background: var(--bg-surface);
		border: 1px solid;
		border-radius: 4px;
		cursor: pointer;
	}
	.warning-btn {
		color: var(--status-warn);
		border-color: color-mix(in oklch, var(--status-warn) 55%, transparent);
	}
	.danger-btn,
	.disconnect-btn {
		color: var(--status-danger);
		border-color: color-mix(in oklch, var(--status-danger) 55%, transparent);
	}
	.warning-btn:hover:not(:disabled) {
		background: var(--warning-muted);
	}
	.danger-btn:hover:not(:disabled),
	.disconnect-btn:hover {
		background: var(--negative-muted);
	}
	.warning-btn:disabled,
	.danger-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
	.warning-btn svg,
	.danger-btn.large svg,
	.sync-btn .sync-icon,
	.sync-btn .spinner {
		width: 1rem;
		height: 1rem;
	}
	.sync-btn .spinner {
		animation: spin 1s linear infinite;
	}

	/* Feedback: outlined messages, text carries meaning */
	.error-msg,
	.success-msg,
	.test-result,
	.claim-result {
		display: inline-flex;
		align-items: center;
		padding: 2px var(--space-xs);
		font-size: var(--text-sm);
		border: 1px solid;
		border-radius: 4px;
		overflow-wrap: anywhere;
	}
	.error-msg,
	.test-result,
	.claim-result {
		color: var(--status-danger);
		border-color: color-mix(in oklch, var(--status-danger) 60%, transparent);
	}
	.success-msg,
	.test-result.success,
	.claim-result.success {
		color: var(--status-steady);
		border-color: color-mix(in oklch, var(--status-steady) 60%, transparent);
	}

	.test-result::before,
	.claim-result::before {
		content: 'Failed';
		margin-right: var(--space-xs);
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.07em;
	}
	.test-result.success::before,
	.claim-result.success::before {
		content: 'OK';
	}
	.checking {
		font-size: var(--text-sm);
		color: var(--ink-muted);
	}

	/* Storage */
	.storage-stats {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		border: 1px solid var(--rule-hairline);
		background: var(--bg-surface);
		margin-bottom: var(--space-md);
	}
	.stat {
		display: flex;
		flex-direction: column-reverse;
		gap: var(--space-2xs);
		padding: var(--space-sm);
	}
	.stat + .stat {
		border-left: 1px solid var(--rule-hairline);
	}
	.stat-value {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: var(--text-lg);
		font-weight: 500;
		color: var(--ink-primary);
	}
	.stat-label {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--ink-muted);
	}
	.cleanup-section > p,
	.cleanup-result {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		margin-bottom: var(--space-sm);
	}
	.cleanup-controls {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: var(--space-sm);
	}
	.cleanup-label {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}

	/* Power */
	.warning-text {
		font-size: var(--text-sm);
		color: var(--status-danger);
		margin: 0 0 var(--space-md);
	}
	.power-actions {
		display: flex;
		gap: var(--space-sm);
	}

	/* Cloud sync */
	.loading-inline {
		padding: var(--space-md);
		color: var(--ink-muted);
	}
	.cloud-connected {
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
		align-items: flex-start;
	}
	.connected-status,
	.claim-data-box,
	.sync-to-cloud-box,
	.cloud-benefits {
		align-self: stretch;
		padding: var(--space-sm) var(--space-md);
		background: var(--bg-surface);
		border: 1px solid var(--rule-hairline);
		border-radius: 4px;
	}
	.connected-status {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		border-color: color-mix(in oklch, var(--status-steady) 55%, transparent);
	}
	.connected-status .check-icon {
		width: 1.25rem;
		height: 1.25rem;
		color: var(--status-steady);
		flex-shrink: 0;
	}
	.connected-label {
		display: block;
		font-size: var(--text-xs);
		color: var(--ink-muted);
	}
	.connected-email {
		display: block;
		font-weight: 700;
		color: var(--ink-primary);
	}
	.claim-data-box {
		border-color: color-mix(in oklch, var(--status-warn) 55%, transparent);
	}
	.claim-data-box h4,
	.sync-to-cloud-box h4,
	.cloud-benefits h4 {
		margin: 0 0 var(--space-xs);
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--ink-primary);
	}
	.claim-data-box p,
	.sync-to-cloud-box p {
		margin: 0 0 var(--space-sm);
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}
	.unclaimed-list {
		margin: 0 0 var(--space-sm) var(--space-lg);
		padding: 0;
		font-size: var(--text-sm);
		color: var(--ink-primary);
	}
	.claim-result {
		margin-left: var(--space-sm);
	}
	.sync-result {
		display: block;
		margin-top: var(--space-sm);
		padding: var(--space-xs) var(--space-sm);
		border: 1px solid;
		border-radius: 4px;
		font-size: var(--text-sm);
	}
	.sync-result.success {
		color: var(--status-steady);
		border-color: color-mix(in oklch, var(--status-steady) 60%, transparent);
	}
	.sync-result.error {
		color: var(--status-danger);
		border-color: color-mix(in oklch, var(--status-danger) 60%, transparent);
	}
	.benefits-list {
		margin: 0;
		padding: 0;
		list-style: none;
	}
	.benefits-list li {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
		padding: var(--space-2xs) 0;
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}
	.benefits-list li svg {
		width: 1rem;
		height: 1rem;
		color: var(--status-steady);
		flex-shrink: 0;
	}
	.cloud-auth-form {
		max-width: 24rem;
	}
	.cloud-auth-form h3 {
		margin: 0 0 var(--space-md);
		font-family: var(--font-display);
		font-size: var(--text-lg);
		font-weight: 600;
		color: var(--ink-primary);
	}
	.cloud-auth-form form {
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
	}
	.cloud-auth-form .form-field {
		display: flex;
		flex-direction: column;
		align-items: stretch;
		border-bottom: 0;
		padding: 0;
	}
	.auth-message {
		padding: var(--space-xs) var(--space-sm);
		margin-bottom: var(--space-md);
		border: 1px solid color-mix(in oklch, var(--status-steady) 60%, transparent);
		border-radius: 4px;
		font-size: var(--text-sm);
		color: var(--status-steady);
	}
	.auth-message.error {
		color: var(--status-danger);
		border-color: color-mix(in oklch, var(--status-danger) 60%, transparent);
	}
	.google-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: var(--space-sm);
		width: 100%;
		min-height: 44px;
		padding: 0 var(--space-md);
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--ink-primary);
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		cursor: pointer;
	}
	.google-btn:hover:not(:disabled) {
		background: var(--accent-tint);
		border-color: var(--accent-rule);
	}
	.google-icon {
		width: 1.125rem;
		height: 1.125rem;
	}
	.divider {
		display: flex;
		align-items: center;
		margin: var(--space-md) 0;
	}
	.divider::before,
	.divider::after {
		content: '';
		flex: 1;
		border-top: 1px solid var(--rule-hairline);
	}
	.divider span {
		padding: 0 var(--space-sm);
		font-family: var(--font-display);
		font-size: var(--text-xs);
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--ink-muted);
	}
	.auth-footer {
		display: flex;
		flex-direction: column;
		align-items: center;
		margin-top: var(--space-md);
	}
	.link-btn {
		min-height: 44px;
		color: var(--ink-secondary);
		font-size: var(--text-sm);
		cursor: pointer;
	}
	.link-btn:hover {
		color: var(--ink-primary);
		text-decoration: underline;
	}
	.connect-actions {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-sm);
		margin-bottom: var(--space-lg);
	}

	/* Device control */
	.section-desc {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		margin-bottom: var(--space-sm);
	}
	.radio-group {
		display: flex;
		flex-direction: column;
		margin-bottom: var(--space-md);
		border-top: 1px solid var(--rule-hairline);
	}
	.radio-option {
		display: flex;
		align-items: flex-start;
		gap: var(--space-sm);
		min-height: 56px;
		padding: var(--space-sm) var(--space-xs);
		border-bottom: 1px solid var(--rule-hairline);
		cursor: pointer;
	}
	.radio-option:hover {
		background: var(--bg-surface);
	}
	.radio-option.selected {
		background: var(--accent-tint);
	}
	.radio-option input[type='radio'] {
		margin-top: 0.25rem;
		accent-color: var(--accent);
	}
	.radio-content {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.radio-label {
		font-weight: 700;
		color: var(--ink-primary);
	}
	.radio-desc {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}
	.subsection-desc {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		margin-bottom: var(--space-sm);
	}
	.device-list {
		display: flex;
		flex-direction: column;
		margin-bottom: var(--space-sm);
		border-top: 1px solid var(--rule-hairline);
	}
	.device-item {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: var(--space-xs);
		min-height: 52px;
		padding: var(--space-2xs) var(--space-xs);
		border-bottom: 1px solid var(--rule-hairline);
	}
	.device-ip {
		flex: 1;
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		color: var(--ink-primary);
	}
	.device-actions {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
	}
	.remove-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 44px;
		height: 44px;
		color: var(--ink-muted);
		border-radius: 4px;
		cursor: pointer;
	}
	.remove-btn:hover {
		background: var(--negative-muted);
		color: var(--status-danger);
	}
	.remove-btn svg {
		width: 1rem;
		height: 1rem;
	}
	.device-item .test-result {
		margin-bottom: var(--space-2xs);
	}
	.add-device-form {
		display: flex;
		gap: var(--space-xs);
		margin-bottom: var(--space-md);
	}
	.add-device-form input {
		flex: 1;
		min-width: 0;
		font-family: var(--font-num);
	}
	.help-text {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		line-height: 1.6;
	}
	.help-text p {
		margin: var(--space-2xs) 0;
	}
	.help-text .help-detail {
		margin-top: var(--space-xs);
		padding-top: var(--space-xs);
		border-top: 1px solid var(--rule-hairline);
	}
	.local-only-note {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: var(--space-xs);
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		margin-bottom: var(--space-sm);
	}

	/* Tablet: index collapses to a horizontal strip */
	@media (max-width: 1040px) {
		.system-page {
			grid-template-columns: minmax(0, 1fr);
			gap: var(--space-md);
		}
		.section-index {
			position: static;
		}
		.section-index ul {
			display: flex;
			overflow-x: auto;
			scrollbar-width: none;
			-webkit-mask-image: linear-gradient(to right, black calc(100% - 2.5rem), transparent);
			mask-image: linear-gradient(to right, black calc(100% - 2.5rem), transparent);
			border-top: 0;
			border-bottom: 1px solid var(--rule-hairline);
		}
		.index-link {
			width: auto;
			white-space: nowrap;
			padding: 0 var(--space-md);
			border-bottom: 2px solid transparent;
			margin-bottom: -1px;
		}
		.index-link.current {
			border-bottom-color: var(--accent);
		}
	}
	@media (max-width: 760px) {
		.status-grid {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
		.setting-group {
			grid-template-columns: minmax(0, 1fr);
		}
		.form-field {
			grid-template-columns: minmax(0, 1fr);
		}
		.form-field > :not(label) {
			grid-column: 1;
		}
		.storage-stats {
			grid-template-columns: minmax(0, 1fr);
		}
		.stat + .stat {
			border-left: 0;
			border-top: 1px solid var(--rule-hairline);
		}
		.power-actions {
			flex-direction: column;
		}
		.power-actions > button,
		.add-device-form .add-btn {
			width: 100%;
			justify-content: center;
		}
		.cleanup-controls {
			flex-direction: column;
			align-items: flex-start;
		}
		.add-device-form {
			flex-direction: column;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.loading-spinner,
		.sync-btn .spinner {
			animation-duration: 3s;
		}
	}
</style>
