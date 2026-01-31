// Svelte 5 runes-based store for app configuration

import { authFetch } from '$lib/api';

export interface AppConfig {
	temp_units: 'C' | 'F';
	sg_units: 'sg' | 'plato' | 'brix';
	local_logging_enabled: boolean;
	local_interval_minutes: number;
	min_rssi: number;
	smoothing_enabled: boolean;
	smoothing_samples: number;
	id_by_mac: boolean;
	// Home Assistant settings
	ha_enabled: boolean;
	ha_url: string;
	ha_token: string;
	ha_ambient_temp_entity_id: string;
	ha_ambient_humidity_entity_id: string;
	// Chamber sensors
	ha_chamber_temp_entity_id: string;
	ha_chamber_humidity_entity_id: string;
	// Temperature control
	temp_control_enabled: boolean;
	temp_target: number;
	temp_hysteresis: number;
	ha_heater_entity_id: string;
	// Weather
	ha_weather_entity_id: string;
	// Alerts
	weather_alerts_enabled: boolean;
	alert_temp_threshold: number;
	// AI Assistant
	ai_enabled: boolean;
	ai_lite_enabled: boolean; // Use Hailo for lightweight tasks
	ai_provider: string;
	ai_model: string;
	ai_api_key: string;
	ai_base_url: string;
	ai_temperature: number;
	ai_max_tokens: number;
	// MQTT for Home Assistant
	mqtt_enabled: boolean;
	mqtt_host: string;
	mqtt_port: number;
	mqtt_username: string;
	mqtt_password: string;
	mqtt_topic_prefix: string;
}

const DEFAULT_CONFIG: AppConfig = {
	temp_units: 'C',
	sg_units: 'sg',
	local_logging_enabled: true,
	local_interval_minutes: 15,
	min_rssi: -100,
	smoothing_enabled: false,
	smoothing_samples: 5,
	id_by_mac: false,
	// Home Assistant
	ha_enabled: false,
	ha_url: '',
	ha_token: '',
	ha_ambient_temp_entity_id: '',
	ha_ambient_humidity_entity_id: '',
	// Chamber sensors
	ha_chamber_temp_entity_id: '',
	ha_chamber_humidity_entity_id: '',
	// Temperature control
	temp_control_enabled: false,
	temp_target: 68.0,
	temp_hysteresis: 1.0,
	ha_heater_entity_id: '',
	// Weather
	ha_weather_entity_id: '',
	// Alerts
	weather_alerts_enabled: false,
	alert_temp_threshold: 3.0,
	// AI Assistant
	ai_enabled: false,
	ai_lite_enabled: false,
	ai_provider: 'local',
	ai_model: '',
	ai_api_key: '',
	ai_base_url: '',
	ai_temperature: 0.7,
	ai_max_tokens: 2000,
	// MQTT for Home Assistant
	mqtt_enabled: false,
	mqtt_host: '',
	mqtt_port: 1883,
	mqtt_username: '',
	mqtt_password: '',
	mqtt_topic_prefix: 'brewsignal'
};

export const configState = $state<{ config: AppConfig; loaded: boolean }>({
	config: DEFAULT_CONFIG,
	loaded: false
});

export async function loadConfig(): Promise<void> {
	try {
		const response = await authFetch('/api/config');
		if (response.ok) {
			const data = await response.json();
			configState.config = { ...DEFAULT_CONFIG, ...data };
		}
	} catch (e) {
		console.error('Failed to load config:', e);
	} finally {
		configState.loaded = true;
	}
}

export interface ConfigUpdateResult {
	success: boolean;
	error?: string;
}

export async function updateConfig(updates: Partial<AppConfig>): Promise<ConfigUpdateResult> {
	try {
		const response = await authFetch('/api/config', {
			method: 'PATCH',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(updates)
		});
		if (response.ok) {
			const data = await response.json();
			configState.config = { ...DEFAULT_CONFIG, ...data };
			return { success: true };
		}
		// Handle validation errors
		const errorData = await response.json();
		if (errorData.detail && Array.isArray(errorData.detail)) {
			const messages = errorData.detail.map((d: { msg: string }) => d.msg).join(', ');
			return { success: false, error: messages };
		}
		return { success: false, error: 'Failed to save settings' };
	} catch (e) {
		console.error('Failed to update config:', e);
		return { success: false, error: 'Network error saving settings' };
	}
}

// Temperature conversion utilities
export function fahrenheitToCelsius(f: number): number {
	return (f - 32) * (5 / 9);
}

export function celsiusToFahrenheit(c: number): number {
	return c * (9 / 5) + 32;
}

export function formatTemp(tempC: number, units?: 'C' | 'F'): string {
	// Backend now sends temperatures in Celsius
	// Default to user preference, fallback to Celsius if not yet loaded
	const displayUnits = units ?? configState.config.temp_units ?? 'C';

	if (displayUnits === 'F') {
		return celsiusToFahrenheit(tempC).toFixed(1);
	}
	return tempC.toFixed(1);
}

export function getTempUnit(): string {
	const units = configState.config.temp_units ?? 'C';
	return units === 'C' ? '°C' : '°F';
}

// Gravity unit conversion utilities
export function sgToPlato(sg: number): number {
	// Approximation: P = -616.868 + 1111.14*SG - 630.272*SG^2 + 135.997*SG^3
	return -616.868 + 1111.14 * sg - 630.272 * sg ** 2 + 135.997 * sg ** 3;
}

export function sgToBrix(sg: number): number {
	// For wort/beer, Brix ≈ Plato
	return sgToPlato(sg);
}

export function formatGravity(
	sg: number,
	units: 'sg' | 'plato' | 'brix' = configState.config.sg_units
): string {
	switch (units) {
		case 'plato':
			return sgToPlato(sg).toFixed(1);
		case 'brix':
			return sgToBrix(sg).toFixed(1);
		default:
			return sg.toFixed(3);
	}
}

export function getGravityUnit(): string {
	switch (configState.config.sg_units) {
		case 'plato':
			return '°P';
		case 'brix':
			return '°Bx';
		default:
			return 'SG';
	}
}
