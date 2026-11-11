<script lang="ts">
	import { onMount } from 'svelte';
	import { getMemory, deleteMemoryItem, deleteAllMemory } from '$lib/api';
	import type { MemoryItem } from '$lib/api';

	let items = $state<MemoryItem[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let confirmingId = $state<string | null>(null);
	let confirmingAll = $state(false);
	let busy = $state(false);

	function fmtDate(iso: string | null): string {
		if (!iso) return '';
		const d = new Date(iso);
		return isNaN(d.getTime()) ? '' : d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
	}

	async function load() {
		loading = true;
		error = null;
		try {
			items = await getMemory();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load memory';
		} finally {
			loading = false;
		}
	}

	async function removeOne(id: string) {
		busy = true;
		error = null;
		try {
			await deleteMemoryItem(id);
			items = items.filter((i) => i.id !== id);
			confirmingId = null;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to delete';
		} finally {
			busy = false;
		}
	}

	async function removeAll() {
		busy = true;
		error = null;
		try {
			await deleteAllMemory();
			items = [];
			confirmingAll = false;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to delete';
		} finally {
			busy = false;
		}
	}

	onMount(load);
</script>

<svelte:head><title>Memory - BrewSignal</title></svelte:head>

<div class="memory-page">
	<a class="back" href="/system">System</a>
	<header class="head">
		<h1>Memory</h1>
		<p class="sub">What the assistant remembers about you. Saved learnings and facts picked up from chats.</p>
	</header>

	<p class="privacy">Memory text is sent to OpenAI's embedding model (via OpenRouter) to find related memories.</p>

	{#if error}<p class="error" role="alert">{error}</p>{/if}

	{#if loading}
		<p class="empty">Loading...</p>
	{:else if items.length === 0}
		<p class="empty">Nothing remembered yet. Learnings appear here as you chat with the assistant.</p>
	{:else}
		<div class="list-head">
			<p class="count"><span class="num">{items.length}</span> {items.length === 1 ? 'memory' : 'memories'}</p>
			{#if confirmingAll}
				<div class="confirm-bar" role="alert">
					<span>Delete all {items.length}? This cannot be undone.</span>
					<span class="actions">
						<button type="button" class="danger" disabled={busy} onclick={removeAll}>{busy ? 'Deleting...' : 'Delete all'}</button>
						<button type="button" class="quiet" disabled={busy} onclick={() => (confirmingAll = false)}>Cancel</button>
					</span>
				</div>
			{:else}
				<button type="button" class="quiet delete-all" onclick={() => (confirmingAll = true)}>Delete all</button>
			{/if}
		</div>
		<ul class="ledger">
			{#each items as item (item.id)}
				<li class="row">
					<div class="meta">
						<span class="pill">{item.source === 'learning' ? 'Learning' : 'Chat'}</span>
						<time class="num date">{fmtDate(item.created_at)}</time>
						<span class="row-actions">
							{#if confirmingId === item.id}
								<span class="ask">Delete?</span>
								<button type="button" class="danger" disabled={busy} onclick={() => removeOne(item.id)}>Yes, delete</button>
								<button type="button" class="quiet" disabled={busy} onclick={() => (confirmingId = null)}>Cancel</button>
							{:else}
								<button type="button" class="quiet" aria-label="Delete memory: {item.text.slice(0, 40)}" onclick={() => (confirmingId = item.id)}>Delete</button>
							{/if}
						</span>
					</div>
					<p class="text">{item.text}</p>
				</li>
			{/each}
		</ul>
	{/if}
</div>

<style>
	.memory-page { max-width: 48rem; margin: 0 auto; display: flex; flex-direction: column; gap: var(--space-md); }
	.back { font-size: var(--text-sm); color: var(--ink-secondary); text-decoration: none; width: fit-content; }
	.back:hover { color: var(--accent); }
	h1 { font-family: var(--font-display); font-size: var(--text-xl); font-weight: 600; margin: 0; color: var(--ink-primary); }
	.sub { margin: var(--space-xs) 0 0; color: var(--ink-secondary); font-size: var(--text-sm); }
	.privacy { margin: 0; font-size: var(--text-xs); color: var(--ink-secondary); }
	.count { margin: 0; font-size: var(--text-sm); color: var(--ink-secondary); }
	.num { font-family: var(--font-num); font-variant-numeric: tabular-nums; }
	.empty { color: var(--ink-muted); font-size: var(--text-sm); padding: var(--space-lg) 0; border-top: 1px solid var(--rule-hairline); margin: 0; }
	.error { color: var(--status-danger); font-size: var(--text-sm); margin: 0; }

	.list-head { display: flex; justify-content: space-between; align-items: center; gap: var(--space-md); flex-wrap: wrap; }

	.ledger { list-style: none; margin: 0; padding: 0; border-top: 1px solid var(--rule-hairline); }
	.row { display: flex; flex-direction: column; gap: var(--space-xs); padding: var(--space-sm) 0; border-bottom: 1px solid var(--rule-hairline); }
	.meta { display: grid; grid-template-columns: auto auto minmax(0, 1fr); gap: var(--space-sm); align-items: center; }
	.date { font-size: var(--text-xs); color: var(--ink-muted); }
	.pill {
		font-size: var(--text-xs); text-transform: uppercase; letter-spacing: 0.06em;
		padding: 1px 6px; border: 1px solid var(--rule-strong); border-radius: 4px; color: var(--ink-secondary);
	}
	.text { margin: 0; font-size: var(--text-base); color: var(--ink-primary); overflow-wrap: anywhere; white-space: pre-wrap; }
	.row-actions { display: flex; gap: 12px; align-items: center; justify-content: flex-end; flex-wrap: nowrap; white-space: nowrap; }
	.ask { font-size: var(--text-sm); color: var(--ink-secondary); }

	button { font: inherit; font-size: var(--text-sm); background: none; border: 1px solid var(--rule-hairline); border-radius: 4px; padding: 4px 10px; cursor: pointer; color: var(--ink-secondary); min-height: 2rem; }
	button:hover:not(:disabled) { border-color: var(--rule-strong); color: var(--ink-primary); }
	button:disabled { opacity: 0.5; cursor: default; }
	button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
	.delete-all { border-color: var(--rule-strong); }
	.delete-all:hover:not(:disabled), .delete-all:focus-visible { color: var(--status-danger); border-color: var(--status-danger); }
	.danger { color: var(--status-danger); border-color: color-mix(in oklch, var(--status-danger) 55%, transparent); }
	.danger:hover:not(:disabled) { color: var(--status-danger); border-color: var(--status-danger); background: var(--negative-muted); }
	.confirm-bar { display: flex; align-items: center; gap: var(--space-md); flex-wrap: wrap; font-size: var(--text-sm); color: var(--ink-primary); }
	.actions { display: flex; gap: 12px; }

	@media (pointer: coarse), (max-width: 760px) {
		button { min-height: 44px; padding: 8px 14px; }
	}
	@media (max-width: 760px) {
		.meta { display: flex; flex-wrap: wrap; }
		.row-actions { margin-left: auto; }
	}
</style>
