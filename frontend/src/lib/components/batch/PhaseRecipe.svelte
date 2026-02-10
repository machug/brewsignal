<script lang="ts">
	import type { BatchResponse } from '$lib/api';
	import BatchRecipeTargetsCard from './BatchRecipeTargetsCard.svelte';

	interface Props {
		batch: BatchResponse;
		statusUpdating: boolean;
		onStartBrewDay: () => void;
	}

	let { batch, statusUpdating, onStartBrewDay }: Props = $props();
</script>

<div class="planning-phase">
	{#if batch.status === 'planning'}
		<!-- Active: show Start Brew Day action -->
		<div class="phase-action-card">
			<div class="phase-icon">📋</div>
			<h2 class="phase-title">Ready to Brew?</h2>
			<p class="phase-description">
				Review your recipe below, then start brew day when you're ready to begin.
			</p>
			<button
				type="button"
				class="start-brewday-btn"
				onclick={onStartBrewDay}
				disabled={statusUpdating}
			>
				{#if statusUpdating}
					<span class="btn-spinner"></span>
					Starting...
				{:else}
					<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
						<path stroke-linecap="round" stroke-linejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
					</svg>
					Start Brew Day
				{/if}
			</button>
		</div>
	{:else}
		<!-- Historical: show recipe link -->
		{#if batch.recipe}
			<div class="recipe-summary-card">
				<h2 class="recipe-name">{batch.recipe.name}</h2>
				{#if batch.recipe.style?.name}
					<p class="recipe-style">{batch.recipe.style.name}</p>
				{/if}
				<a href="/recipes/{batch.recipe.id}" class="view-recipe-link">
					View Full Recipe →
				</a>
			</div>
		{/if}
	{/if}

	{#if batch.recipe}
		<BatchRecipeTargetsCard recipe={batch.recipe} yeastStrain={batch.yeast_strain} />
	{/if}
</div>

<style>
	.planning-phase {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.phase-action-card {
		background: linear-gradient(135deg, var(--bg-surface) 0%, var(--bg-elevated) 100%);
		border: 1px solid var(--border-subtle);
		border-radius: 1rem;
		padding: 2rem;
		text-align: center;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 1rem;
	}

	.phase-icon {
		font-size: 3rem;
		line-height: 1;
	}

	.phase-title {
		font-size: 1.5rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
	}

	.phase-description {
		font-size: 0.9375rem;
		color: var(--text-secondary);
		max-width: 400px;
		line-height: 1.5;
		margin: 0;
	}

	.start-brewday-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		padding: 0.875rem 1.5rem;
		font-size: 1rem;
		font-weight: 600;
		border-radius: 0.5rem;
		cursor: pointer;
		transition: all var(--transition);
		margin-top: 0.5rem;
		color: white;
		background: var(--accent);
		border: none;
	}

	.start-brewday-btn:hover:not(:disabled) {
		background: var(--accent-hover);
		transform: translateY(-1px);
	}

	.start-brewday-btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
		transform: none;
	}

	.btn-spinner {
		width: 1rem;
		height: 1rem;
		border: 2px solid rgba(255, 255, 255, 0.3);
		border-top-color: white;
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	.btn-icon {
		width: 1rem;
		height: 1rem;
	}

	.recipe-summary-card {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 1rem;
		padding: 2rem;
		text-align: center;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.5rem;
	}

	.recipe-name {
		font-size: 1.25rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
	}

	.recipe-style {
		font-size: 0.875rem;
		color: var(--text-secondary);
		margin: 0;
	}

	.view-recipe-link {
		display: inline-block;
		margin-top: 0.5rem;
		padding: 0.5rem 1rem;
		font-size: 0.875rem;
		font-weight: 500;
		color: var(--accent);
		text-decoration: none;
		border: 1px solid var(--accent);
		border-radius: 0.375rem;
		transition: all 0.15s ease;
	}

	.view-recipe-link:hover {
		background: rgba(99, 102, 241, 0.1);
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}
</style>
