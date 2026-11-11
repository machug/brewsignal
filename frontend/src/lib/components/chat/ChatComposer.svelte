<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		value: string;
		busy: boolean;
		disabled?: boolean;
		placeholder?: string;
		onSend: () => void;
		onStop: () => void;
		context?: Snippet;
		inputEl?: HTMLTextAreaElement | null;
	}
	let { value = $bindable(), busy, disabled = false, placeholder = 'Ask about a recipe or batch', onSend, onStop, context, inputEl = $bindable(null) }: Props = $props();

	// Grow from 1 to 6 rows.
	$effect(() => {
		value;
		if (!inputEl) return;
		// Empty: let CSS min-height (one row) win, so a long placeholder cannot inflate the box.
		inputEl.style.height = 'auto';
		if (value) inputEl.style.height = Math.min(inputEl.scrollHeight, 6 * 24 + 20) + 'px';
	});

	function onKey(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
			e.preventDefault();
			if (!busy && !disabled && value.trim()) onSend();
		}
	}
</script>

<div class="composer">
	{@render context?.()}
	<form
		class="box"
		onsubmit={(e) => {
			e.preventDefault();
			if (!busy && !disabled && value.trim()) onSend();
		}}
	>
		<textarea
			bind:this={inputEl}
			bind:value
			onkeydown={onKey}
			rows="1"
			{placeholder}
			aria-label="Message"
			{disabled}
		></textarea>
		{#if busy}
			<button type="button" class="act stop" onclick={onStop} aria-label="Stop">
				<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="5" y="5" width="14" height="14" /></svg>
			</button>
		{:else}
			<button type="submit" class="act send" disabled={disabled || !value.trim()} aria-label="Send">
				<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.25" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7" /></svg>
			</button>
		{/if}
	</form>
</div>

<style>
	.composer { display: flex; flex-direction: column; gap: var(--space-xs); }
	.box {
		display: flex; align-items: flex-end; gap: var(--space-xs);
		padding: 4px 4px 4px var(--space-sm);
		background: var(--bg-surface); border: 1px solid var(--rule-strong);
	}
	.box:focus-within { border-color: var(--accent); }
	.box:has(textarea:disabled) { background: var(--bg-canvas); border-color: var(--rule-hairline); cursor: not-allowed; }
	textarea:disabled::placeholder { color: var(--ink-muted); }
	textarea {
		flex: 1; min-width: 0; resize: none; border: 0; outline: 0; background: transparent;
		min-height: 44px; box-sizing: border-box; padding: 10px 0; font: inherit; font-size: var(--text-base); line-height: 24px; color: var(--ink-primary);
		max-height: 164px;
	}
	textarea::placeholder { color: var(--ink-secondary); }
	.act {
		flex: none; width: 44px; height: 44px; display: grid; place-items: center; cursor: pointer;
		border: 1px solid var(--rule-strong); background: var(--bg-elevated); color: var(--ink-primary);
	}
	.send { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); }
	.send:hover:not(:disabled) { background: var(--accent-hover); }
	.send:disabled { background: transparent; border-color: transparent; color: var(--ink-muted); opacity: 0.5; cursor: not-allowed; }
	.stop { animation: ring 1.4s ease-in-out infinite; }
	.act:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
	@keyframes ring { 50% { border-color: var(--accent); } }
	@media (prefers-reduced-motion: reduce) { .stop { animation: none; } }
</style>
