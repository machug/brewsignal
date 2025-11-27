<script lang="ts">
	import { onMount } from 'svelte';
	import { tiltsState, connectWebSocket, disconnectWebSocket } from '$lib/stores/tilts.svelte';
	import TiltCard from '$lib/components/TiltCard.svelte';

	onMount(() => {
		connectWebSocket();
		return () => disconnectWebSocket();
	});

	let tiltsList = $derived(Array.from(tiltsState.tilts.values()));
</script>

<div class="min-h-screen bg-slate-900 text-white">
	<!-- Header -->
	<header class="bg-slate-800 border-b border-slate-700 px-6 py-4">
		<div class="flex items-center justify-between">
			<div>
				<h1 class="text-2xl font-bold">Tilt UI</h1>
				<p class="text-sm text-slate-400">Hydrometer monitoring dashboard</p>
			</div>
			<div class="flex items-center gap-2">
				<span
					class="w-2 h-2 rounded-full {tiltsState.connected ? 'bg-green-500' : 'bg-red-500'}"
				></span>
				<span class="text-sm text-slate-400">
					{tiltsState.connected ? 'Connected' : 'Disconnected'}
				</span>
			</div>
		</div>
	</header>

	<!-- Main content -->
	<main class="p-6">
		{#if tiltsList.length === 0}
			<div class="text-center py-20">
				<div class="text-6xl mb-4">🍺</div>
				<h2 class="text-xl font-semibold mb-2">No Tilts Detected</h2>
				<p class="text-slate-400">
					{#if tiltsState.connected}
						Waiting for Tilt hydrometers to broadcast...
					{:else}
						Connecting to server...
					{/if}
				</p>
			</div>
		{:else}
			<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
				{#each tiltsList as tilt (tilt.id)}
					<TiltCard {tilt} />
				{/each}
			</div>
		{/if}
	</main>
</div>
