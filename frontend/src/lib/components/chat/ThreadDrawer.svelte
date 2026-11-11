<script lang="ts">
	import { relativeTime } from '$lib/chat/logic';

	export interface ThreadItem {
		id: string;
		title: string | null;
		updated_at: string;
		message_count: number;
	}
	interface Props {
		open: boolean;
		threads: ThreadItem[];
		activeId: string;
		loading?: boolean;
		onSelect: (id: string) => void;
		onNew: () => void;
		onRename: (id: string, title: string) => void;
		onDelete: (id: string) => void;
		onClose: () => void;
	}
	let { open, threads, activeId, loading = false, onSelect, onNew, onRename, onDelete, onClose }: Props = $props();

	let editing = $state<string | null>(null);
	let draft = $state('');

	function startRename(t: ThreadItem) {
		editing = t.id;
		draft = t.title ?? '';
	}
	function commit() {
		if (editing && draft.trim()) onRename(editing, draft.trim());
		editing = null;
	}
	function onKey(e: KeyboardEvent) {
		if (e.key === 'Escape' && open) onClose();
	}
</script>

<svelte:window onkeydown={onKey} />

{#if open}<button type="button" class="backdrop" aria-label="Close chat list" onclick={onClose} tabindex="-1"></button>{/if}
<aside class="drawer" class:open inert={!open} aria-label="Saved chats">
	<div class="top">
		<h2>Chats</h2>
		<button type="button" class="new" onclick={onNew}>New chat</button>
	</div>
	<div class="list">
		{#if loading && threads.length === 0}
			<p class="empty">Loading…</p>
		{:else if threads.length === 0}
			<p class="empty">No saved chats yet.</p>
		{:else}
			<ul>
				{#each threads as t (t.id)}
					<li class:active={t.id === activeId}>
						{#if editing === t.id}
							<form class="edit" onsubmit={(e) => { e.preventDefault(); commit(); }}>
								<!-- svelte-ignore a11y_autofocus -->
								<input bind:value={draft} aria-label="Chat title" autofocus onkeydown={(e) => e.key === 'Escape' && (editing = null)} />
								<button type="submit" class="ic" aria-label="Save title">Save</button>
							</form>
						{:else}
							<button type="button" class="pick" onclick={() => onSelect(t.id)}>
								<span class="title">{t.title || 'Untitled chat'}</span>
								<span class="meta">{t.message_count} msgs · {relativeTime(t.updated_at)}</span>
							</button>
							<button type="button" class="ic" aria-label="Rename chat" onclick={() => startRename(t)}>
								<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z" /></svg>
							</button>
							<button type="button" class="ic" aria-label="Delete chat" onclick={() => onDelete(t.id)}>
								<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" /></svg>
							</button>
						{/if}
					</li>
				{/each}
			</ul>
		{/if}
	</div>
</aside>

<style>
	.backdrop { position: absolute; inset: 0; z-index: 9; background: color-mix(in oklch, var(--bg-canvas) 60%, transparent); border: 0; cursor: default; }
	.drawer {
		position: absolute; top: 0; bottom: 0; left: 0; z-index: 10; width: min(320px, 100%);
		display: flex; flex-direction: column;
		background: var(--bg-surface); border-right: 1px solid var(--rule-strong);
		transform: translateX(-100%); visibility: hidden;
		transition: transform 200ms var(--ease-out-quart, ease-out), visibility 0s linear 200ms;
	}
	.drawer.open { transform: none; visibility: visible; transition: transform 200ms var(--ease-out-quart, ease-out); }
	.top { display: flex; align-items: center; justify-content: space-between; gap: var(--space-sm); padding: var(--space-sm) var(--space-md); border-bottom: 1px solid var(--rule-hairline); }
	h2 { margin: 0; font-family: var(--font-display); font-size: var(--text-base); font-weight: 600; }
	.new {
		min-height: 44px; padding: 0 var(--space-md); font: inherit; font-size: var(--text-sm); cursor: pointer;
		background: transparent; border: 1px solid var(--rule-strong); color: var(--ink-primary);
	}
	.new:hover { background: var(--bg-subtle); }
	.list { flex: 1; overflow-y: auto; }
	.empty { padding: var(--space-md); margin: 0; font-size: var(--text-sm); color: var(--ink-secondary); }
	ul { list-style: none; margin: 0; padding: 0; }
	li { display: flex; align-items: stretch; border-bottom: 1px solid var(--rule-hairline); }
	li.active { background: var(--bg-elevated); }
	.pick {
		flex: 1; min-width: 0; min-height: 56px; display: flex; flex-direction: column; justify-content: center; gap: 2px;
		padding: var(--space-xs) var(--space-md); text-align: left; background: none; border: 0; font: inherit; color: var(--ink-primary); cursor: pointer;
	}
	.title { font-size: var(--text-sm); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.meta { font-family: var(--font-num); font-size: 0.8125rem; color: var(--ink-secondary); }
	.ic {
		flex: none; width: 44px; min-height: 44px; display: grid; place-items: center; background: none; border: 0;
		color: var(--ink-secondary); cursor: pointer; font: inherit; font-size: 0.8125rem;
	}
	.ic:hover { color: var(--ink-primary); background: var(--bg-subtle); }
	.edit { display: flex; flex: 1; align-items: center; gap: var(--space-xs); padding: var(--space-xs) var(--space-sm); }
	.edit input {
		flex: 1; min-width: 0; min-height: 44px; padding: 0 var(--space-sm); font: inherit; font-size: var(--text-sm);
		background: var(--bg-canvas); border: 1px solid var(--rule-strong); color: var(--ink-primary);
	}
	.edit .ic { width: auto; padding: 0 var(--space-sm); }
	button:focus-visible, input:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
	@media (prefers-reduced-motion: reduce) { .drawer, .drawer.open { transition: none; } }
</style>
