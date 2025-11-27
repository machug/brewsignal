// Svelte 5 runes-based store for Tilt readings

export interface TiltReading {
	id: string;
	color: string;
	beer_name: string;
	sg: number;
	sg_raw: number;
	temp: number;
	temp_raw: number;
	rssi: number;
	last_seen: string;
}

// Shared reactive state using Svelte 5 $state rune
export const tiltsState = $state<{ tilts: Map<string, TiltReading>; connected: boolean }>({
	tilts: new Map(),
	connected: false
});

let ws: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

export function connectWebSocket() {
	if (ws?.readyState === WebSocket.OPEN) return;

	const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
	const wsUrl = `${protocol}//${window.location.host}/ws`;

	console.log('Connecting to WebSocket:', wsUrl);
	ws = new WebSocket(wsUrl);

	ws.onopen = () => {
		console.log('WebSocket connected');
		tiltsState.connected = true;
		if (reconnectTimer) {
			clearTimeout(reconnectTimer);
			reconnectTimer = null;
		}
	};

	ws.onmessage = (event) => {
		try {
			const reading: TiltReading = JSON.parse(event.data);
			tiltsState.tilts.set(reading.id, reading);
			// Trigger reactivity by reassigning
			tiltsState.tilts = new Map(tiltsState.tilts);
		} catch (e) {
			console.error('Failed to parse WebSocket message:', e);
		}
	};

	ws.onclose = () => {
		console.log('WebSocket disconnected');
		tiltsState.connected = false;
		ws = null;
		// Reconnect after 3 seconds
		reconnectTimer = setTimeout(connectWebSocket, 3000);
	};

	ws.onerror = (error) => {
		console.error('WebSocket error:', error);
		ws?.close();
	};
}

export function disconnectWebSocket() {
	if (reconnectTimer) {
		clearTimeout(reconnectTimer);
		reconnectTimer = null;
	}
	ws?.close();
	ws = null;
}
