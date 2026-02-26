<script lang="ts">
	import { onMount } from 'svelte';
	import { getLearnings, updateLearning, deleteLearning } from '$lib/api';
	import type { BrewingLearningResponse } from '$lib/api';

	const categories = ['all', 'equipment', 'technique', 'recipe', 'ingredient', 'correction'] as const;
	const categoryColors: Record<string, string> = {
		equipment: '#d97706',
		technique: '#2563eb',
		recipe: '#16a34a',
		ingredient: '#9333ea',
		correction: '#dc2626',
	};

	let learnings = $state<BrewingLearningResponse[]>([]);
	let activeCategory = $state<string>('all');
	let loading = $state(true);
	let editingId = $state<number | null>(null);
	let editText = $state('');
	let deletingId = $state<number | null>(null);

	let filtered = $derived(
		activeCategory === 'all'
			? learnings
			: learnings.filter(l => l.category === activeCategory)
	);

	async function fetchLearnings() {
		loading = true;
		try {
			learnings = await getLearnings();
		} catch (e) {
			console.error('Failed to fetch learnings:', e);
		} finally {
			loading = false;
		}
	}

	function startEdit(learning: BrewingLearningResponse) {
		editingId = learning.id;
		editText = learning.learning;
	}

	async function saveEdit(id: number) {
		try {
			const updated = await updateLearning(id, { learning: editText });
			learnings = learnings.map(l => l.id === id ? updated : l);
			editingId = null;
		} catch (e) {
			console.error('Failed to update learning:', e);
		}
	}

	function cancelEdit() {
		editingId = null;
		editText = '';
	}

	async function confirmDelete(id: number) {
		try {
			await deleteLearning(id);
			learnings = learnings.filter(l => l.id !== id);
			deletingId = null;
		} catch (e) {
			console.error('Failed to delete learning:', e);
		}
	}

	onMount(fetchLearnings);
</script>

<div class="knowledge-page">
	<!-- Header -->
	<div class="page-header">
		<h1 class="page-title">Brewing Knowledge</h1>
		<p class="page-subtitle">Learnings captured from your brewing sessions</p>
	</div>

	<!-- Category tabs -->
	<div class="category-tabs">
		{#each categories as cat}
			<button
				type="button"
				class="category-tab"
				class:active={activeCategory === cat}
				onclick={() => activeCategory = cat}
			>
				{#if cat !== 'all'}
					<span class="tab-dot" style="background: {categoryColors[cat]}"></span>
				{/if}
				<span class="tab-label">{cat.charAt(0).toUpperCase() + cat.slice(1)}</span>
			</button>
		{/each}
	</div>

	<!-- Count -->
	{#if !loading}
		<div class="count-indicator">
			{filtered.length} learning{filtered.length !== 1 ? 's' : ''}
		</div>
	{/if}

	<!-- Content -->
	{#if loading}
		<div class="loading-state">
			<div class="spinner"></div>
			<p>Loading learnings...</p>
		</div>
	{:else if filtered.length === 0}
		<div class="empty-state">
			<div class="empty-icon">📚</div>
			<h2 class="empty-title">No learnings yet</h2>
			<p class="empty-text">
				{#if activeCategory === 'all'}
					Learnings will appear here as they're captured during brewing conversations with the assistant.
				{:else}
					No learnings in the "{activeCategory}" category yet.
				{/if}
			</p>
		</div>
	{:else}
		<div class="learnings-list">
			{#each filtered as learning (learning.id)}
				<div class="learning-card">
					<div class="card-header">
						<span
							class="category-badge"
							style="background: {categoryColors[learning.category]}20; color: {categoryColors[learning.category]}"
						>
							{learning.category}
						</span>
						<span class="card-date">
							{new Date(learning.created_at).toLocaleDateString()}
						</span>
					</div>

					<div class="card-body">
						{#if editingId === learning.id}
							<textarea
								class="edit-textarea"
								bind:value={editText}
								rows="4"
							></textarea>
							<div class="edit-actions">
								<button
									type="button"
									class="btn btn-primary"
									onclick={() => saveEdit(learning.id)}
								>
									Save
								</button>
								<button
									type="button"
									class="btn btn-ghost"
									onclick={cancelEdit}
								>
									Cancel
								</button>
							</div>
						{:else}
							<p class="learning-text">{learning.learning}</p>
						{/if}
					</div>

					{#if learning.source_context}
						<div class="card-source">
							{learning.source_context}
						</div>
					{/if}

					{#if editingId !== learning.id}
						<div class="card-actions">
							{#if deletingId === learning.id}
								<span class="delete-confirm-text">Delete this learning?</span>
								<button
									type="button"
									class="btn btn-danger-sm"
									onclick={() => confirmDelete(learning.id)}
								>
									Confirm
								</button>
								<button
									type="button"
									class="btn btn-ghost-sm"
									onclick={() => deletingId = null}
								>
									Cancel
								</button>
							{:else}
								<button
									type="button"
									class="btn btn-ghost-sm"
									onclick={() => startEdit(learning)}
								>
									Edit
								</button>
								<button
									type="button"
									class="btn btn-ghost-sm btn-danger-text"
									onclick={() => deletingId = learning.id}
								>
									Delete
								</button>
							{/if}
						</div>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.knowledge-page {
		max-width: 48rem;
		margin: 0 auto;
	}

	/* Header */
	.page-header {
		margin-bottom: 1.5rem;
	}

	.page-title {
		font-size: 1.5rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0 0 0.25rem 0;
	}

	.page-subtitle {
		font-size: 0.875rem;
		color: var(--text-muted);
		margin: 0;
	}

	/* Category tabs */
	.category-tabs {
		display: flex;
		gap: 0.25rem;
		padding: 0.25rem;
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.5rem;
		margin-bottom: 1rem;
		overflow-x: auto;
	}

	.category-tab {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		padding: 0.5rem 0.75rem;
		font-size: 0.8125rem;
		font-weight: 500;
		color: var(--text-secondary);
		background: transparent;
		border: none;
		border-radius: 0.375rem;
		cursor: pointer;
		white-space: nowrap;
		transition: color 150ms, background 150ms;
	}

	.category-tab:hover {
		color: var(--text-primary);
		background: var(--bg-hover);
	}

	.category-tab.active {
		color: var(--text-primary);
		background: var(--bg-elevated);
	}

	.tab-dot {
		width: 0.5rem;
		height: 0.5rem;
		border-radius: 50%;
		flex-shrink: 0;
	}

	.tab-label {
		line-height: 1;
	}

	/* Count */
	.count-indicator {
		font-size: 0.75rem;
		color: var(--text-muted);
		margin-bottom: 1rem;
		font-family: var(--font-mono);
	}

	/* Loading */
	.loading-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 4rem 0;
		color: var(--text-muted);
	}

	.spinner {
		width: 2rem;
		height: 2rem;
		border: 2px solid var(--border-subtle);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
		margin-bottom: 1rem;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	/* Empty state */
	.empty-state {
		text-align: center;
		padding: 4rem 1rem;
	}

	.empty-icon {
		font-size: 2.5rem;
		margin-bottom: 1rem;
	}

	.empty-title {
		font-size: 1.125rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0 0 0.5rem 0;
	}

	.empty-text {
		font-size: 0.875rem;
		color: var(--text-muted);
		max-width: 24rem;
		margin: 0 auto;
		line-height: 1.5;
	}

	/* Learnings list */
	.learnings-list {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	/* Card */
	.learning-card {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.5rem;
		overflow: hidden;
	}

	.card-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.75rem 1rem;
		border-bottom: 1px solid var(--border-subtle);
	}

	.category-badge {
		display: inline-block;
		padding: 0.125rem 0.5rem;
		font-size: 0.6875rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		border-radius: 9999px;
	}

	.card-date {
		font-size: 0.75rem;
		color: var(--text-muted);
		font-family: var(--font-mono);
	}

	.card-body {
		padding: 1rem;
	}

	.learning-text {
		font-size: 0.875rem;
		color: var(--text-primary);
		line-height: 1.6;
		margin: 0;
		white-space: pre-wrap;
	}

	.card-source {
		padding: 0.75rem 1rem;
		font-size: 0.75rem;
		color: var(--text-muted);
		background: var(--bg-elevated);
		border-top: 1px solid var(--border-subtle);
	}

	.card-actions {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.5rem 1rem;
		border-top: 1px solid var(--border-subtle);
	}

	/* Edit textarea */
	.edit-textarea {
		width: 100%;
		padding: 0.75rem;
		font-size: 0.875rem;
		font-family: inherit;
		color: var(--text-primary);
		background: var(--bg-elevated);
		border: 1px solid var(--border-default);
		border-radius: 0.375rem;
		resize: vertical;
		line-height: 1.6;
	}

	.edit-textarea:focus {
		outline: none;
		border-color: var(--accent);
	}

	.edit-actions {
		display: flex;
		gap: 0.5rem;
		margin-top: 0.75rem;
	}

	/* Buttons */
	.btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		font-size: 0.8125rem;
		font-weight: 500;
		border: none;
		border-radius: 0.375rem;
		cursor: pointer;
		transition: background 150ms, color 150ms;
	}

	.btn-primary {
		padding: 0.5rem 1rem;
		background: var(--accent);
		color: #fff;
	}

	.btn-primary:hover {
		filter: brightness(1.1);
	}

	.btn-ghost {
		padding: 0.5rem 1rem;
		background: transparent;
		color: var(--text-secondary);
	}

	.btn-ghost:hover {
		background: var(--bg-hover);
		color: var(--text-primary);
	}

	.btn-ghost-sm {
		padding: 0.25rem 0.625rem;
		font-size: 0.75rem;
		background: transparent;
		color: var(--text-muted);
	}

	.btn-ghost-sm:hover {
		background: var(--bg-hover);
		color: var(--text-primary);
	}

	.btn-danger-sm {
		padding: 0.25rem 0.625rem;
		font-size: 0.75rem;
		background: rgba(220, 38, 38, 0.15);
		color: #dc2626;
	}

	.btn-danger-sm:hover {
		background: rgba(220, 38, 38, 0.25);
	}

	.btn-danger-text {
		color: var(--text-muted);
	}

	.btn-danger-text:hover {
		color: #dc2626;
		background: rgba(220, 38, 38, 0.1);
	}

	.delete-confirm-text {
		font-size: 0.75rem;
		color: #dc2626;
		margin-right: auto;
	}
</style>
