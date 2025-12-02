import { fetchApi } from './index';

export interface DeviceResponse {
	id: string;
	color: string;
	beer_name: string;
	paired: boolean;
	last_seen: string | null;
	mac: string | null;
}

export async function fetchAllDevices(): Promise<DeviceResponse[]> {
	return fetchApi('/api/tilts');
}

export async function pairDevice(deviceId: string): Promise<DeviceResponse> {
	return fetchApi(`/api/tilts/${deviceId}/pair`, {
		method: 'POST'
	});
}

export async function unpairDevice(deviceId: string): Promise<DeviceResponse> {
	return fetchApi(`/api/tilts/${deviceId}/unpair`, {
		method: 'POST'
	});
}
