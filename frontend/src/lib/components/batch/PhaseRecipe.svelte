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
					<span class="btn-spinner" aria-hidden="true"></span>
					Starting...
				{:else}
					<svg class="btn-icon" aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
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
					View Full Recipe &rarr;
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
		gap: var(--space-lg);
	}
	.phase-action-card,
	.recipe-summary-card {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: var(--space-xs);
		padding: var(--space-lg) 0;
		border-top: 1px solid var(--rule-strong);
		border-bottom: 1px solid var(--rule-hairline);
	}
	.phase-title,
	.recipe-name {
		font-family: var(--font-display);
		font-size: var(--text-lg);
		font-weight: 700;
		letter-spacing: -0.01em;
		color: var(--ink-primary);
	}
	.phase-description {
		font-size: var(--text-base);
		color: var(--ink-secondary);
		max-width: 52ch;
		line-height: 1.5;
	}
	.recipe-style {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}
	.start-brewday-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: var(--space-xs);
		min-height: 48px;
		padding: 0 var(--space-lg);
		margin-top: var(--space-xs);
		font-family: var(--font-display);
		font-size: var(--text-base);
		font-weight: 600;
		border-radius: 4px;
		cursor: pointer;
		color: var(--accent-ink);
		background: var(--accent);
		transition: background-color 140ms var(--ease-out-quart);
	}
	.start-brewday-btn:hover:not(:disabled) {
		background: var(--accent-hover);
	}
	.start-brewday-btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}
	.btn-spinner {
		width: 1rem;
		height: 1rem;
		border: 2px solid color-mix(in oklch, var(--accent-ink) 30%, transparent);
		border-top-color: var(--accent-ink);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}
	.btn-icon {
		width: 1rem;
		height: 1rem;
	}
	.view-recipe-link {
		display: inline-flex;
		align-items: center;
		min-height: 44px;
		padding: 0 var(--space-md);
		margin-top: var(--space-xs);
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--accent);
		background: var(--accent-tint);
		border: 1px solid var(--accent-rule);
		border-radius: 4px;
	}
	.view-recipe-link:hover {
		border-color: var(--accent);
	}
	@keyframes spin {
		to { transform: rotate(360deg); }
	}
	@media (prefers-reduced-motion: reduce) {
		.btn-spinner {
			animation: none;
		}
	}
</style>
