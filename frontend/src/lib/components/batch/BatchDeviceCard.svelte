<script lang="ts">
	import type { BatchResponse } from '$lib/api';
	import type { TiltReading } from '$lib/stores/tilts.svelte';
	import { getSignalStrength, timeSince } from '$lib/utils/signal';
	import BatchCard from './BatchCard.svelte';

	interface Props {
		batch: BatchResponse;
		liveReading: TiltReading | null;
		onEdit?: () => void;
	}

	let { batch, liveReading, onEdit }: Props = $props();

	// Signal strength only applies to BLE devices (Tilt)
	// GravityMon/iSpindel use HTTP push, so RSSI is not meaningful
	let isBleDevice = $derived(liveReading?.device_type === 'tilt');
	let signal = $derived(isBleDevice && liveReading?.rssi ? getSignalStrength(liveReading.rssi) : null);
	let lastSeenText = $derived(liveReading?.last_seen ? timeSince(liveReading.last_seen) : null);

	// Battery info (GravityMon/iSpindel)
	let hasBattery = $derived(liveReading?.battery_percent != null || liveReading?.battery_voltage != null);
	let batteryPercent = $derived(liveReading?.battery_percent);
	let batteryVoltage = $derived(liveReading?.battery_voltage);
	let batteryColor = $derived.by(() => {
		if (!batteryPercent) return 'var(--text-muted)';
		if (batteryPercent > 50) return 'var(--positive)';
		if (batteryPercent > 20) return '#f59e0b';
		return 'var(--negative)';
	});

	// Format device display name based on type
	let deviceDisplayName = $derived.by(() => {
		if (!liveReading) return batch.device_id || 'Unknown';
		const deviceType = liveReading.device_type;
		if (deviceType === 'tilt') {
			return `${liveReading.color} Tilt`;
		} else if (deviceType === 'gravitymon') {
			return `GravityMon (${liveReading.id})`;
		} else if (deviceType === 'ispindel') {
			return `iSpindel (${liveReading.id})`;
		} else if (deviceType === 'floaty') {
			return `Floaty (${liveReading.id})`;
		}
		return liveReading.color || liveReading.id;
	});
</script>

<BatchCard title="Tracking Device" compact>
	{#if batch.device_id}
		<div class="device-info">
			{#if liveReading}
				<div class="device-row">
					<div class="device-status online">
						<span class="device-dot"></span>
						{deviceDisplayName}
					</div>
					{#if lastSeenText}
						<span class="device-last-seen">{lastSeenText}</span>
					{/if}
				</div>

				{#if signal || hasBattery}
					<div class="device-metrics">
						{#if signal}
							<div class="metric-item">
								<div class="signal-bars">
									{#each Array(4) as _, i}
										<div
											class="signal-bar"
											style="height: {4 + i * 2}px; background: {i < signal.bars ? signal.color : 'var(--bg-hover)'}; opacity: {i < signal.bars ? 1 : 0.4};"
										></div>
									{/each}
								</div>
								<span class="metric-text" style="color: {signal.color}">{liveReading.rssi}dBm</span>
							</div>
						{/if}
						{#if hasBattery}
							<div class="metric-item battery">
								<svg class="battery-icon" viewBox="0 0 24 24" fill="none" stroke={batteryColor} stroke-width="2">
									<rect x="2" y="7" width="18" height="10" rx="2" />
									<rect x="4" y="9" width="{(batteryPercent ?? 50) * 0.14}" height="6" fill={batteryColor} stroke="none" rx="1" />
									<path d="M20 10v4h2v-4z" fill={batteryColor} stroke="none" />
								</svg>
								<span class="metric-text" style="color: {batteryColor}">
									{#if batteryPercent != null}
										{batteryPercent.toFixed(0)}%
									{:else if batteryVoltage != null}
										{batteryVoltage.toFixed(2)}V
									{/if}
								</span>
							</div>
						{/if}
					</div>
				{/if}
			{:else}
				<div class="device-row">
					<div class="device-status offline">
						<span class="device-dot"></span>
						{batch.device_id}
					</div>
					<span class="device-last-seen">No data</span>
				</div>
			{/if}
		</div>
	{:else}
		<div class="no-device">
			<span>No device assigned</span>
			{#if onEdit}
				<button type="button" class="link-btn" onclick={onEdit}>Link device</button>
			{/if}
		</div>
	{/if}
</BatchCard>

<style>
	.device-info {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
	}

	.device-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
	}

	.device-status {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		font-size: 0.8125rem;
		font-weight: 500;
	}

	.device-status.online {
		color: var(--positive);
	}

	.device-status.offline {
		color: var(--text-muted);
	}

	.device-dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: currentColor;
	}

	.device-last-seen {
		font-size: 0.6875rem;
		color: var(--text-muted);
	}

	.device-metrics {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 0.375rem 0.5rem;
		background: var(--bg-elevated);
		border-radius: 0.25rem;
	}

	.metric-item {
		display: flex;
		align-items: center;
		gap: 0.375rem;
	}

	.signal-bars {
		display: flex;
		align-items: flex-end;
		gap: 2px;
	}

	.signal-bar {
		width: 2px;
		border-radius: 1px;
		transition: all 0.2s ease;
	}

	.metric-text {
		font-size: 0.6875rem;
		font-weight: 500;
		font-family: var(--font-mono);
	}

	.battery-icon {
		width: 1rem;
		height: 1rem;
	}

	.no-device {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		font-size: 0.8125rem;
		color: var(--text-muted);
	}

	.link-btn {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--accent);
		background: none;
		border: none;
		padding: 0;
		cursor: pointer;
	}

	.link-btn:hover {
		text-decoration: underline;
	}
</style>
