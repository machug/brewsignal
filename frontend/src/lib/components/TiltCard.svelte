<script lang="ts">
	import type { TiltReading } from '$lib/stores/tilts.svelte';

	interface Props {
		tilt: TiltReading;
	}

	let { tilt }: Props = $props();

	const colorMap: Record<string, string> = {
		RED: 'bg-red-500',
		GREEN: 'bg-green-500',
		BLACK: 'bg-slate-800',
		PURPLE: 'bg-purple-500',
		ORANGE: 'bg-orange-500',
		BLUE: 'bg-blue-500',
		YELLOW: 'bg-yellow-400',
		PINK: 'bg-pink-400'
	};

	function formatSG(sg: number): string {
		return sg.toFixed(3);
	}

	function formatTemp(temp: number): string {
		return `${temp.toFixed(1)}°F`;
	}

	function getSignalStrength(rssi: number): { label: string; color: string; bars: number } {
		if (rssi >= -50) return { label: 'Excellent', color: 'text-green-400', bars: 4 };
		if (rssi >= -60) return { label: 'Good', color: 'text-green-400', bars: 3 };
		if (rssi >= -70) return { label: 'Fair', color: 'text-yellow-400', bars: 2 };
		return { label: 'Weak', color: 'text-red-400', bars: 1 };
	}

	function timeSince(isoString: string): string {
		const seconds = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000);
		if (seconds < 10) return 'just now';
		if (seconds < 60) return `${seconds}s ago`;
		const minutes = Math.floor(seconds / 60);
		if (minutes < 60) return `${minutes}m ago`;
		const hours = Math.floor(minutes / 60);
		return `${hours}h ago`;
	}

	let signal = $derived(getSignalStrength(tilt.rssi));
	let lastSeenText = $derived(timeSince(tilt.last_seen));
</script>

<div class="bg-slate-800 rounded-lg overflow-hidden shadow-lg">
	<!-- Color bar -->
	<div class={`h-2 ${colorMap[tilt.color] || 'bg-gray-500'}`}></div>

	<div class="p-4">
		<!-- Header -->
		<div class="flex justify-between items-start mb-3">
			<div>
				<h3 class="text-lg font-semibold text-white">{tilt.beer_name}</h3>
				<p class="text-sm text-slate-400">{tilt.color} Tilt</p>
			</div>
			<div class="text-right">
				<div class="flex items-center gap-1 {signal.color}">
					{#each Array(4) as _, i}
						<div
							class="w-1 rounded-sm {i < signal.bars ? 'bg-current' : 'bg-slate-600'}"
							style="height: {6 + i * 3}px"
						></div>
					{/each}
				</div>
				<p class="text-xs text-slate-500 mt-1">{tilt.rssi} dBm</p>
			</div>
		</div>

		<!-- Main readings -->
		<div class="grid grid-cols-2 gap-4 mb-3">
			<div class="bg-slate-700/50 rounded-lg p-3 text-center">
				<p class="text-2xl font-bold text-white">{formatSG(tilt.sg)}</p>
				<p class="text-xs text-slate-400 uppercase tracking-wide">Specific Gravity</p>
			</div>
			<div class="bg-slate-700/50 rounded-lg p-3 text-center">
				<p class="text-2xl font-bold text-white">{formatTemp(tilt.temp)}</p>
				<p class="text-xs text-slate-400 uppercase tracking-wide">Temperature</p>
			</div>
		</div>

		<!-- Raw values (smaller) -->
		{#if tilt.sg !== tilt.sg_raw || tilt.temp !== tilt.temp_raw}
			<div class="text-xs text-slate-500 mb-2">
				Raw: SG {formatSG(tilt.sg_raw)} / {formatTemp(tilt.temp_raw)}
			</div>
		{/if}

		<!-- Last seen -->
		<p class="text-xs text-slate-500 text-right">{lastSeenText}</p>
	</div>
</div>
