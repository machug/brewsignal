<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import type { RecipeResponse } from '$lib/api';
	import { fetchRecipe, deleteRecipe } from '$lib/api';
	import FermentablesList from '$lib/components/recipe/FermentablesList.svelte';
	import HopSchedule from '$lib/components/recipe/HopSchedule.svelte';
	import MashSchedule from '$lib/components/recipe/MashSchedule.svelte';
	import FermentationSchedule from '$lib/components/recipe/FermentationSchedule.svelte';
	import WaterAdditions from '$lib/components/recipe/WaterAdditions.svelte';
	import RecipeStatsPanel from '$lib/components/recipe/RecipeStatsPanel.svelte';

	let recipe = $state<RecipeResponse | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let showDeleteConfirm = $state(false);
	let deleting = $state(false);

	let recipeId = $derived.by(() => {
		const id = parseInt($page.params.id || '', 10);
		return isNaN(id) || id <= 0 ? null : id;
	});

	onMount(async () => {
		if (!recipeId) {
			error = 'Invalid recipe ID';
			loading = false;
			return;
		}

		try {
			recipe = await fetchRecipe(recipeId);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load recipe';
		} finally {
			loading = false;
		}
	});

	async function handleDelete() {
		if (!recipe) return;

		deleting = true;
		try {
			await deleteRecipe(recipe.id);
			goto('/recipes');
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to delete recipe';
			deleting = false;
			showDeleteConfirm = false;
		}
	}

	function handleBrewThis() {
		if (!recipe) return;
		goto(`/batches/new?recipe_id=${recipe.id}`);
	}
</script>

<svelte:head>
	<title>{recipe?.name || 'Recipe'} | BrewSignal</title>
</svelte:head>

<div class="page-container">
	<div class="back-link">
		<a href="/recipes" class="back-btn">
			<svg class="back-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
			</svg>
			Back to Recipes
		</a>
	</div>

	{#if loading}
		<div class="loading-state">
			<div class="spinner"></div>
			<p>Loading recipe...</p>
		</div>
	{:else if error}
		<div class="error-state">
			<p class="error-message">{error}</p>
		</div>
	{:else if recipe}
		<!-- Hero Header -->
		<div class="recipe-hero">
			<div class="hero-content">
				<div class="hero-title-area">
					<h1 class="recipe-title">{recipe.name}</h1>
					<div class="recipe-meta">
						{#if recipe.type}
							<span class="meta-badge type">{recipe.type}</span>
						{/if}
						{#if recipe.author}
							<span class="meta-author">by {recipe.author}</span>
						{/if}
					</div>
				</div>
				<div class="header-actions">
					<a href="/recipes/{recipe.id}/edit" class="btn-secondary">
						<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
						</svg>
						Edit
					</a>
					<a href="/api/recipes/{recipe.id}/export/brewfather?download=true" class="btn-secondary" download>
						<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
						</svg>
						Export
					</a>
					<button type="button" class="btn-primary" onclick={handleBrewThis}>
						<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
						</svg>
						Brew This
					</button>
					<button type="button" class="btn-ghost-danger" onclick={() => (showDeleteConfirm = true)} aria-label="Delete recipe">
						<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
						</svg>
					</button>
				</div>
			</div>
		</div>

		<!-- Stats Panel with Beer Glass -->
		<RecipeStatsPanel
			og={recipe.og ?? 1.050}
			fg={recipe.fg ?? 1.010}
			abv={recipe.abv ?? 5.0}
			ibu={recipe.ibu ?? 30}
			colorSrm={recipe.color_srm ?? 8}
			batchSizeLiters={recipe.batch_size_liters ?? 20}
		/>

		<div class="recipe-content">
			<!-- Yeast Section -->
			{#if recipe.yeast_name}
				<section class="content-card">
					<h2 class="section-title">
						<svg class="section-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
						</svg>
						Yeast
					</h2>
					<div class="yeast-card">
						<div class="yeast-main">
							<span class="yeast-name">{recipe.yeast_name}</span>
							{#if recipe.yeast_lab}
								<span class="yeast-lab">{recipe.yeast_lab}</span>
							{/if}
						</div>
						<div class="yeast-stats">
							{#if recipe.yeast_temp_min != null && recipe.yeast_temp_max != null}
								<div class="yeast-stat">
									<span class="yeast-stat-label">Temp Range</span>
									<span class="yeast-stat-value">{recipe.yeast_temp_min.toFixed(0)}–{recipe.yeast_temp_max.toFixed(0)}°C</span>
								</div>
							{/if}
							{#if recipe.yeast_attenuation}
								<div class="yeast-stat">
									<span class="yeast-stat-label">Attenuation</span>
									<span class="yeast-stat-value">{recipe.yeast_attenuation.toFixed(0)}%</span>
								</div>
							{/if}
						</div>
					</div>
				</section>
			{/if}

			<!-- Fermentables Section -->
			{#if recipe.fermentables && recipe.fermentables.length > 0}
				<section class="content-card">
					<FermentablesList fermentables={recipe.fermentables} />
				</section>
			{/if}

			<!-- Hops Section -->
			{#if recipe.hops && recipe.hops.length > 0}
				<section class="content-card">
					<HopSchedule hops={recipe.hops} />
				</section>
			{/if}

			<!-- Mash Schedule Section -->
			{#if recipe.mash_steps && recipe.mash_steps.length > 0}
				<section class="content-card">
					<MashSchedule steps={recipe.mash_steps} />
				</section>
			{/if}

			<!-- Fermentation Schedule Section -->
			{#if recipe.fermentation_steps && recipe.fermentation_steps.length > 0}
				<section class="content-card">
					<FermentationSchedule steps={recipe.fermentation_steps} />
				</section>
			{/if}

			<!-- Water Additions Section -->
			{#if recipe.miscs && recipe.miscs.length > 0}
				<section class="content-card">
					<WaterAdditions miscs={recipe.miscs} />
				</section>
			{/if}

			<!-- Batch Details -->
			{#if recipe.batch_size_liters || recipe.efficiency_percent || recipe.boil_time_minutes}
				<section class="content-card">
					<h2 class="section-title">
						<svg class="section-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
						</svg>
						Batch Details
					</h2>
					<div class="details-grid">
						{#if recipe.batch_size_liters}
							<div class="detail-item">
								<span class="detail-label">Batch Size</span>
								<span class="detail-value">{recipe.batch_size_liters.toFixed(1)} L</span>
							</div>
						{/if}
						{#if recipe.efficiency_percent}
							<div class="detail-item">
								<span class="detail-label">Efficiency</span>
								<span class="detail-value">{recipe.efficiency_percent.toFixed(0)}%</span>
							</div>
						{/if}
						{#if recipe.boil_time_minutes}
							<div class="detail-item">
								<span class="detail-label">Boil Time</span>
								<span class="detail-value">{recipe.boil_time_minutes} min</span>
							</div>
						{/if}
					</div>
				</section>
			{/if}

			<!-- Notes Section -->
			{#if recipe.notes}
				<section class="content-card notes-card">
					<h2 class="section-title">
						<svg class="section-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
						</svg>
						Notes
					</h2>
					<div class="notes-content">
						{#each recipe.notes.split('\n') as line}
							{#if line.trim()}
								<p>{line}</p>
							{:else}
								<br />
							{/if}
						{/each}
					</div>
				</section>
			{/if}

			<!-- Footer -->
			<div class="recipe-footer">
				<span class="created-date">Created {new Date(recipe.created_at).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })}</span>
			</div>
		</div>
	{/if}
</div>

<!-- Delete Confirmation Modal -->
{#if showDeleteConfirm}
	<div
		class="modal-overlay"
		onclick={() => (showDeleteConfirm = false)}
		onkeydown={(e) => e.key === 'Escape' && (showDeleteConfirm = false)}
		role="presentation"
		aria-hidden="true"
	>
		<div
			class="modal"
			onclick={(e) => e.stopPropagation()}
			onkeydown={(e) => e.stopPropagation()}
			role="dialog"
			aria-modal="true"
			aria-labelledby="delete-recipe-title"
		>
			<div class="modal-header">
				<svg class="modal-icon danger" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
				</svg>
				<h2 id="delete-recipe-title" class="modal-title">Delete Recipe?</h2>
			</div>
			<p class="modal-text">
				Are you sure you want to delete <strong>"{recipe?.name}"</strong>? This action cannot be undone.
			</p>
			<div class="modal-actions">
				<button
					type="button"
					class="modal-btn cancel"
					onclick={() => (showDeleteConfirm = false)}
					disabled={deleting}
				>
					Cancel
				</button>
				<button type="button" class="modal-btn delete" onclick={handleDelete} disabled={deleting}>
					{#if deleting}
						<span class="btn-spinner"></span>
						Deleting...
					{:else}
						Delete Recipe
					{/if}
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.page-container {
		max-width: 900px;
		margin: 0 auto;
		padding: var(--space-6);
	}

	/* Back Link */
	.back-link {
		margin-bottom: var(--space-4);
	}

	.back-btn {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		font-size: 14px;
		font-weight: 500;
		color: var(--text-secondary);
		text-decoration: none;
		transition: color var(--transition);
	}

	.back-btn:hover {
		color: var(--text-primary);
	}

	.back-icon {
		width: 16px;
		height: 16px;
	}

	/* Loading & Error States */
	.loading-state,
	.error-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: var(--space-12) var(--space-6);
		text-align: center;
	}

	.spinner {
		width: 32px;
		height: 32px;
		border: 3px solid var(--gray-700);
		border-top-color: var(--recipe-accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	.error-message {
		color: var(--negative);
		font-size: 14px;
	}

	/* Hero Section */
	.recipe-hero {
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 12px;
		overflow: hidden;
		margin-bottom: var(--space-6);
	}

	.hero-content {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: var(--space-4);
		padding: var(--space-6);
	}

	.hero-title-area {
		flex: 1;
	}

	.recipe-title {
		font-family: var(--font-recipe-name);
		font-size: 32px;
		font-weight: 600;
		letter-spacing: -0.02em;
		color: var(--text-primary);
		margin: 0 0 var(--space-3) 0;
		line-height: 1.2;
	}

	.recipe-meta {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		flex-wrap: wrap;
	}

	.meta-badge {
		display: inline-flex;
		align-items: center;
		padding: var(--space-1) var(--space-3);
		font-size: 12px;
		font-weight: 500;
		font-family: var(--font-mono);
		border-radius: 4px;
		text-transform: uppercase;
		letter-spacing: 0.02em;
	}

	.meta-badge.type {
		background: rgba(245, 158, 11, 0.15);
		color: var(--recipe-accent);
		border: 1px solid rgba(245, 158, 11, 0.3);
	}

	.meta-author {
		font-size: 14px;
		color: var(--text-secondary);
	}

	/* Header Actions */
	.header-actions {
		display: flex;
		gap: var(--space-2);
		align-items: center;
		flex-shrink: 0;
	}

	.btn-icon {
		width: 16px;
		height: 16px;
	}

	.btn-secondary {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		padding: 9px 16px;
		font-size: 13px;
		font-weight: 500;
		background: transparent;
		border: 1px solid var(--border-default);
		border-radius: 8px;
		color: var(--text-secondary);
		text-decoration: none;
		cursor: pointer;
		transition: all 0.2s ease;
	}

	.btn-secondary:hover {
		border-color: var(--recipe-accent);
		color: var(--recipe-accent);
		background: rgba(245, 158, 11, 0.05);
	}

	.btn-primary {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		padding: 10px 20px;
		font-size: 14px;
		font-weight: 600;
		background: linear-gradient(135deg, var(--recipe-accent) 0%, var(--recipe-accent-hover) 100%);
		border: none;
		border-radius: 8px;
		color: var(--gray-950);
		cursor: pointer;
		transition: all 0.2s ease;
		box-shadow:
			0 2px 8px var(--recipe-accent-border),
			0 1px 2px rgba(0, 0, 0, 0.2),
			inset 0 1px 0 rgba(255, 255, 255, 0.15);
	}

	.btn-primary:hover {
		background: linear-gradient(135deg, var(--tilt-yellow) 0%, var(--recipe-accent) 100%);
		transform: translateY(-1px);
		box-shadow:
			0 4px 12px var(--recipe-accent-border),
			0 2px 4px rgba(0, 0, 0, 0.2),
			inset 0 1px 0 rgba(255, 255, 255, 0.2);
	}

	.btn-ghost-danger {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 36px;
		height: 36px;
		padding: 0;
		background: transparent;
		border: 1px solid transparent;
		border-radius: 8px;
		color: var(--text-muted);
		cursor: pointer;
		transition: all 0.2s ease;
	}

	.btn-ghost-danger:hover {
		border-color: var(--negative);
		color: var(--negative);
		background: rgba(239, 68, 68, 0.08);
	}

	/* Content Area */
	.recipe-content {
		display: flex;
		flex-direction: column;
		gap: var(--space-5);
	}

	.content-card {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 10px;
		padding: var(--space-5);
	}

	.section-title {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		font-size: 14px;
		font-weight: 600;
		color: var(--recipe-accent);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin: 0 0 var(--space-4) 0;
	}

	.section-icon {
		width: 18px;
		height: 18px;
		opacity: 0.8;
	}

	/* Yeast Card */
	.yeast-card {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: var(--space-4);
		flex-wrap: wrap;
	}

	.yeast-main {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.yeast-name {
		font-size: 16px;
		font-weight: 500;
		color: var(--text-primary);
	}

	.yeast-lab {
		font-size: 13px;
		color: var(--text-secondary);
	}

	.yeast-stats {
		display: flex;
		gap: var(--space-6);
	}

	.yeast-stat {
		display: flex;
		flex-direction: column;
		gap: 2px;
		text-align: right;
	}

	.yeast-stat-label {
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		color: var(--text-muted);
	}

	.yeast-stat-value {
		font-family: var(--font-mono);
		font-size: 14px;
		color: var(--text-primary);
	}

	/* Details Grid */
	.details-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
		gap: var(--space-4);
	}

	.detail-item {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.detail-label {
		font-size: 12px;
		color: var(--text-secondary);
	}

	.detail-value {
		font-family: var(--font-measurement);
		font-size: 18px;
		color: var(--text-primary);
	}

	/* Notes */
	.notes-card {
		background: linear-gradient(135deg, var(--bg-surface) 0%, rgba(245, 158, 11, 0.02) 100%);
	}

	.notes-content {
		font-size: 14px;
		color: var(--text-secondary);
		line-height: 1.7;
	}

	.notes-content p {
		margin: 0 0 var(--space-3) 0;
	}

	.notes-content p:last-child {
		margin-bottom: 0;
	}

	/* Footer */
	.recipe-footer {
		display: flex;
		justify-content: center;
		padding-top: var(--space-4);
	}

	.created-date {
		font-size: 12px;
		color: var(--text-muted);
		font-family: var(--font-mono);
	}

	/* Modal */
	.modal-overlay {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.7);
		backdrop-filter: blur(4px);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
		padding: var(--space-4);
	}

	.modal {
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 12px;
		padding: var(--space-6);
		max-width: 400px;
		width: 100%;
		box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
	}

	.modal-header {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		margin-bottom: var(--space-4);
	}

	.modal-icon {
		width: 24px;
		height: 24px;
		flex-shrink: 0;
	}

	.modal-icon.danger {
		color: var(--negative);
	}

	.modal-title {
		font-size: 18px;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
	}

	.modal-text {
		font-size: 14px;
		color: var(--text-secondary);
		line-height: 1.6;
		margin: 0 0 var(--space-6) 0;
	}

	.modal-text strong {
		color: var(--text-primary);
	}

	.modal-actions {
		display: flex;
		gap: var(--space-3);
		justify-content: flex-end;
	}

	.modal-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: var(--space-2);
		padding: var(--space-2) var(--space-4);
		border-radius: 8px;
		font-size: 14px;
		font-weight: 500;
		cursor: pointer;
		transition: all 0.2s ease;
		min-width: 100px;
	}

	.modal-btn.cancel {
		background: transparent;
		border: 1px solid var(--border-default);
		color: var(--text-primary);
	}

	.modal-btn.cancel:hover {
		background: var(--bg-hover);
	}

	.modal-btn.delete {
		background: var(--negative);
		border: none;
		color: white;
	}

	.modal-btn.delete:hover:not(:disabled) {
		background: #dc2626;
	}

	.modal-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.btn-spinner {
		width: 14px;
		height: 14px;
		border: 2px solid currentColor;
		border-top-color: transparent;
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	/* Responsive */
	@media (max-width: 640px) {
		.hero-content {
			flex-direction: column;
			gap: var(--space-4);
		}

		.header-actions {
			width: 100%;
			justify-content: flex-start;
		}

		.recipe-title {
			font-size: 24px;
		}

		.yeast-card {
			flex-direction: column;
			align-items: flex-start;
		}

		.yeast-stats {
			width: 100%;
			justify-content: flex-start;
		}

		.yeast-stat {
			text-align: left;
		}
	}
</style>
