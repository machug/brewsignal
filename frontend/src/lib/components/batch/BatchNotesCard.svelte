<script lang="ts">
	import BatchCard from './BatchCard.svelte';

	interface Props {
		notes: string;
	}

	let { notes }: Props = $props();
</script>

<BatchCard title="Notes">
	<p class="notes-content">{notes}</p>
</BatchCard>

<style>
	.notes-content {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		line-height: 1.6;
		white-space: pre-wrap;
		max-width: 65ch;
	}
</style>
