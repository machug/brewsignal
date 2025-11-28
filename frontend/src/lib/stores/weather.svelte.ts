// Svelte 5 runes-based store for weather/alerts data

export interface WeatherForecast {
	datetime: string;
	condition: string;
	temperature: number | null;
	templow: number | null;
}

export interface Alert {
	level: string;
	message: string;
	day: string;
}

export interface WeatherState {
	forecast: WeatherForecast[];
	alerts: Alert[];
	weather_entity: string | null;
	alerts_enabled: boolean;
	loading: boolean;
	loaded: boolean;
}

export const weatherState = $state<WeatherState>({
	forecast: [],
	alerts: [],
	weather_entity: null,
	alerts_enabled: false,
	loading: false,
	loaded: false
});

let refreshTimer: ReturnType<typeof setInterval> | null = null;

export async function loadWeather(): Promise<void> {
	weatherState.loading = true;
	try {
		const response = await fetch('/api/alerts');
		if (response.ok) {
			const data = await response.json();
			weatherState.forecast = data.forecast || [];
			weatherState.alerts = data.alerts || [];
			weatherState.weather_entity = data.weather_entity;
			weatherState.alerts_enabled = data.alerts_enabled;
			weatherState.loaded = true;
		}
	} catch (e) {
		console.error('Failed to load weather:', e);
	} finally {
		weatherState.loading = false;
	}
}

export function startWeatherPolling(intervalMs: number = 30 * 60 * 1000): void {
	// Initial fetch
	loadWeather();
	// Poll at interval (default 30 minutes)
	if (refreshTimer) {
		clearInterval(refreshTimer);
	}
	refreshTimer = setInterval(loadWeather, intervalMs);
}

export function stopWeatherPolling(): void {
	if (refreshTimer) {
		clearInterval(refreshTimer);
		refreshTimer = null;
	}
}

// Helper: Get weather icon based on condition
export function getWeatherIcon(condition: string): string {
	const icons: Record<string, string> = {
		'sunny': '☀️',
		'clear-night': '🌙',
		'partlycloudy': '⛅',
		'cloudy': '☁️',
		'rainy': '🌧️',
		'pouring': '🌧️',
		'snowy': '❄️',
		'fog': '🌫️',
		'windy': '💨',
		'lightning': '⚡',
		'lightning-rainy': '⛈️',
		'hail': '🌨️',
	};
	return icons[condition] || '🌡️';
}

// Helper: Format day name from datetime
export function formatDayName(datetime: string): string {
	try {
		const date = new Date(datetime);
		const today = new Date();
		const tomorrow = new Date(today);
		tomorrow.setDate(tomorrow.getDate() + 1);

		if (date.toDateString() === today.toDateString()) return 'Today';
		if (date.toDateString() === tomorrow.toDateString()) return 'Tomorrow';
		return date.toLocaleDateString('en-US', { weekday: 'short' });
	} catch {
		return 'Day';
	}
}
