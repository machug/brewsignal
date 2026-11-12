<script lang="ts">
	import { batchUrl } from '$lib/urls';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import type { BatchCreate } from '$lib/api';
	import { createBatch } from '$lib/api';
	import BatchForm from '$lib/components/BatchForm.svelte';

	let recipeId = $derived(
		$page.url.searchParams.get('recipe_id')
			? parseInt($page.url.searchParams.get('recipe_id')!, 10)
			: undefined
	);

	async function handleSubmit(data: BatchCreate) {
		const batch = await createBatch(data);
		goto(batchUrl(batch));
	}

	function handleCancel() {
		goto('/batches');
	}
</script>

<svelte:head>
	<title>New Batch | BrewSignal</title>
</svelte:head>

<div class="page-container">
	<div class="back-link">
		<a href="/batches" class="back-btn">
			<svg class="back-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
			</svg>
			Back to Batches
		</a>
	</div>

	<div class="form-container">
		<BatchForm onSubmit={handleSubmit} onCancel={handleCancel} initialRecipeId={recipeId} />
	</div>
</div>

<style>
	.page-container {
		max-width: 760px;
		margin: 0 auto;
		padding: var(--space-lg) var(--space-md) var(--space-xl);
	}
	.back-link {
		margin-bottom: var(--space-md);
	}
	.back-btn {
		display: inline-flex;
		align-items: center;
		gap: var(--space-xs);
		min-height: 44px;
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--ink-secondary);
		transition: color 140ms var(--ease-out-quart);
	}
	.back-btn:hover {
		color: var(--ink-primary);
	}
	.back-icon {
		width: 1rem;
		height: 1rem;
	}
	.form-container {
		animation: fade-in 200ms var(--ease-out-quart);
	}
	@keyframes fade-in {
		from {
			opacity: 0;
			transform: translateY(8px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.form-container {
			animation: none;
		}
	}
</style>
