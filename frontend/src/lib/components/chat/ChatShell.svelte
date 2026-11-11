<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		title: string;
		model?: string;
		onToggleDrawer: () => void;
		onNew: () => void;
		/** True while the pane follows new content (user is at the bottom). Set true to jump to the end. */
		follow?: boolean;
		drawer: Snippet;
		children: Snippet;
		footer: Snippet;
	}
	let { title, model = '', onToggleDrawer, onNew, follow = $bindable(true), drawer, children, footer }: Props = $props();
	let paneEl = $state<HTMLElement | null>(null);
	let colEl = $state<HTMLElement | null>(null);

	// Scroll events from our own scrollTo can land after the content grew again; ignore those.
	let lastAuto = 0;
	function onScroll() {
		if (performance.now() - lastAuto < 150) return;
		if (paneEl) follow = paneEl.scrollHeight - paneEl.scrollTop - paneEl.clientHeight < 80;
	}
	const toEnd = () => {
		lastAuto = performance.now();
		paneEl?.scrollTo({ top: paneEl.scrollHeight });
	};
	// Content growth (streaming text, cards loading) keeps the end in view while following.
	$effect(() => {
		if (!colEl) return;
		const ro = new ResizeObserver(() => follow && toEnd());
		ro.observe(colEl);
		return () => ro.disconnect();
	});
	$effect(() => {
		if (follow) toEnd();
	});
</script>

<div class="shell">
	<header class="bar">
		<button type="button" class="btn" onclick={onToggleDrawer}>
			<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M3 6h18M3 12h18M3 18h18" /></svg>
			<span>Chats</span>
		</button>
		<div class="ttl">
			<h1>{title}</h1>
			{#if model}<span class="model">{model}</span>{/if}
		</div>
		<button type="button" class="btn" onclick={onNew}>
			<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
			<span>New</span>
		</button>
	</header>

	<div class="pane" bind:this={paneEl} onscroll={onScroll}>
		<div class="col" bind:this={colEl}>{@render children()}</div>
	</div>

	<div class="foot"><div class="col">{@render footer()}</div></div>

	{@render drawer()}
</div>

<style>
	.shell {
		position: relative; display: flex; flex-direction: column; overflow: hidden;
		height: calc(100dvh - 56px - 2 * var(--space-lg));
		border: 1px solid var(--rule-hairline); background: var(--bg-canvas);
	}
	@media (max-width: 760px) {
		.shell {
			height: calc(100dvh - 56px - var(--tabbar-h) - env(safe-area-inset-bottom, 0px) - 2 * var(--space-md));
			border-left: 0; border-right: 0; margin-inline: calc(-1 * var(--space-md));
		}
	}
	.bar { display: flex; align-items: center; gap: var(--space-sm); padding: 0 var(--space-sm); border-bottom: 1px solid var(--rule-hairline); background: var(--bg-surface); flex: none; }
	.btn {
		display: inline-flex; align-items: center; gap: 6px; min-height: 44px; padding: 0 var(--space-sm); font: inherit; font-size: var(--text-sm);
		background: none; border: 0; color: var(--ink-secondary); cursor: pointer;
	}
	.btn:hover { color: var(--ink-primary); }
	.btn:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
	.ttl { flex: 1; min-width: 0; display: flex; align-items: baseline; justify-content: center; gap: var(--space-sm); }
	h1 { margin: 0; font-family: var(--font-display); font-size: var(--text-base); font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.model { font-family: var(--font-num); font-size: 0.8125rem; color: var(--ink-secondary); white-space: nowrap; }
	@media (max-width: 520px) { .model { display: none; } }
	.pane { flex: 1; min-height: 0; overflow-y: auto; overscroll-behavior: contain; }
	.col { max-width: 780px; margin: 0 auto; padding: var(--space-md); display: flex; flex-direction: column; gap: var(--space-md); min-height: 100%; }
	.foot { flex: none; border-top: 1px solid var(--rule-hairline); background: var(--bg-canvas); }
	.foot .col { min-height: 0; padding: var(--space-sm) var(--space-md); gap: 0; }
</style>
