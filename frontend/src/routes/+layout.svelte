<script lang="ts">
	import '../app.css';

	let { children } = $props();
</script>

<svelte:head>
	<title>Tilt UI</title>
</svelte:head>

{@render children()}
