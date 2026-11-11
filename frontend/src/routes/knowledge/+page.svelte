<script lang="ts">
	import { onMount } from 'svelte';
	import { getLearnings, updateLearning, deleteLearning } from '$lib/api';
	import type { BrewingLearningResponse } from '$lib/api';

	const categories = ['all', 'equipment', 'technique', 'recipe', 'ingredient', 'correction'] as const;

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
				<span class="tab-label">{cat.charAt(0).toUpperCase() + cat.slice(1)}</span>
			</button>
		{/each}
	</div>

	<!-- Count -->
	{#if !loading}
		<div class="count-indicator">
			<span class="num">{filtered.length}</span> learning{filtered.length !== 1 ? 's' : ''}
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
				<article class="learning-card">
					<div class="card-header">
						<span
							class="category-badge"
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
				</article>
			{/each}
		</div>
	{/if}
</div>

<style>
	.knowledge-page { max-width: 1400px; margin: 0 auto; padding: var(--space-lg) var(--space-xl) var(--space-xl); }
	.page-header { margin-bottom: var(--space-lg); }
	.page-title { font-family: var(--font-display); font-size: var(--text-xl); font-weight: 700; letter-spacing: -0.02em; line-height: 1.15; color: var(--ink-primary); }
	.page-subtitle { font-size: var(--text-sm); color: var(--ink-secondary); margin-top: var(--space-2xs); }

	.category-tabs { display: flex; flex-wrap: nowrap; gap: var(--space-2xs); box-shadow: inset 0 -1px 0 var(--rule-hairline); margin-bottom: var(--space-md); overflow-x: auto; overflow-y: hidden; scrollbar-width: none; }
	.category-tabs::-webkit-scrollbar { display: none; }
	.category-tab { display: flex; align-items: center; gap: var(--space-xs); min-height: 44px; padding: 0 var(--space-sm); font-family: var(--font-display); font-size: var(--text-sm); font-weight: 600; color: var(--ink-secondary); border-bottom: 2px solid transparent; cursor: pointer; white-space: nowrap; flex-shrink: 0; transition: color 140ms var(--ease-out-quart); }
	.category-tab:hover { color: var(--ink-primary); }
	.category-tab.active { color: var(--accent); border-bottom-color: var(--accent); }
	.category-tab:focus-visible, .btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
	.tab-label { line-height: 1; }

	.count-indicator { font-family: var(--font-display); font-size: var(--text-xs); font-weight: 600; text-transform: uppercase; letter-spacing: 0.07em; color: var(--ink-muted); margin-bottom: var(--space-sm); }
	.num { font-family: var(--font-num); font-variant-numeric: tabular-nums; }

	.loading-state { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: var(--space-2xl) 0; color: var(--ink-muted); }
	.spinner { width: 2rem; height: 2rem; border: 2px solid var(--rule-hairline); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.8s linear infinite; margin-bottom: var(--space-md); }
	@keyframes spin { to { transform: rotate(360deg); } }
	@media (prefers-reduced-motion: reduce) { .spinner { animation-duration: 3s; } }

	.empty-state { max-width: 68ch; padding: var(--space-xl) 0; border-top: 1px solid var(--rule-hairline); border-bottom: 1px solid var(--rule-hairline); }
	.empty-title { font-family: var(--font-display); font-size: var(--text-lg); font-weight: 600; color: var(--ink-primary); margin-bottom: var(--space-xs); }
	.empty-text { font-size: var(--text-sm); color: var(--ink-secondary); line-height: 1.6; max-width: 56ch; }

	.learnings-list { display: flex; flex-direction: column; max-width: 68ch; }
	.learning-card { padding: var(--space-md) 0; border-top: 1px solid var(--rule-hairline); }
	.learning-card:last-child { border-bottom: 1px solid var(--rule-hairline); }
	.card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--space-xs); }
	.category-badge { display: inline-block; padding: 1px var(--space-xs); font-family: var(--font-display); font-size: 0.6875rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.07em; color: var(--ink-muted); border: 1px solid var(--rule-strong); border-radius: 3px; line-height: 1.4; }
	.card-date { font-family: var(--font-num); font-variant-numeric: tabular-nums; font-size: var(--text-xs); color: var(--ink-muted); }
	.learning-text { font-size: var(--text-base); color: var(--ink-primary); line-height: 1.65; white-space: pre-wrap; }
	.card-source { margin-top: var(--space-xs); font-size: var(--text-xs); color: var(--ink-muted); line-height: 1.5; }
	.card-actions { display: flex; align-items: center; gap: var(--space-xs); margin-top: var(--space-xs); }

	.edit-textarea { width: 100%; padding: var(--space-sm); font-size: var(--text-sm); font-family: inherit; color: var(--ink-primary); background: var(--bg-surface); border: 1px solid var(--rule-strong); border-radius: 4px; resize: vertical; line-height: 1.6; }
	.edit-textarea:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; border-color: var(--accent); }
	.edit-actions { display: flex; gap: var(--space-xs); margin-top: var(--space-sm); }

	.btn { display: inline-flex; align-items: center; justify-content: center; font-family: var(--font-display); font-size: var(--text-sm); font-weight: 600; border-radius: 4px; cursor: pointer; }
	.btn-primary { min-height: 44px; padding: 0 var(--space-md); background: var(--accent); color: var(--accent-ink); }
	.btn-primary:hover { background: var(--accent-hover); }
	.btn-ghost { min-height: 44px; padding: 0 var(--space-md); background: var(--bg-surface); color: var(--ink-primary); border: 1px solid var(--rule-strong); }
	.btn-ghost:hover { background: var(--accent-tint); border-color: var(--accent-rule); }
	.btn-ghost-sm, .btn-danger-sm { min-height: 44px; padding: 0 var(--space-sm); font-size: var(--text-xs); background: transparent; color: var(--ink-secondary); }
	.btn-ghost-sm:hover { color: var(--ink-primary); text-decoration: underline; }
	.btn-danger-sm { color: var(--status-danger); border: 1px solid color-mix(in oklch, var(--status-danger) 55%, transparent); }
	.btn-danger-sm:hover { background: var(--negative-muted); }
	.btn-danger-text { color: var(--ink-secondary); }
	.btn-danger-text:hover, .btn-danger-text:focus-visible { color: var(--status-danger); }
	.delete-confirm-text { font-size: var(--text-xs); color: var(--status-danger); margin-right: auto; }
@media (max-width: 640px) {
		.knowledge-page { padding: var(--space-md); }
		.category-tabs { padding-right: 28px; -webkit-mask-image: linear-gradient(to right, var(--ink-primary) calc(100% - 28px), transparent); mask-image: linear-gradient(to right, var(--ink-primary) calc(100% - 28px), transparent); }
	}
</style>
