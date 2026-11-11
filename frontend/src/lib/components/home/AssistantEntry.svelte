<script lang="ts">
	import { goto } from '$app/navigation';

	const SUGGESTED = ['Review my last recipe', 'Plan a dry hop', 'What hops do I have?'];

	let text = $state('');

	function ask(q: string) {
		const v = q.trim();
		goto(v ? `/assistant?q=${encodeURIComponent(v)}` : '/assistant');
	}
</script>

<section class="panel" aria-labelledby="ask-h">
	<h2 id="ask-h" class="eyebrow">Assistant</h2>
	<p class="lede">Ask about a recipe, a fermentation, or your stock.</p>
	<form
		class="input-row"
		onsubmit={(e) => {
			e.preventDefault();
			ask(text);
		}}
	>
		<input type="text" bind:value={text} placeholder="Ask the assistant" aria-label="Message for the assistant" autocomplete="off" />
		<button type="submit" class="send">Ask &rarr;</button>
	</form>
	<ul class="chips">
		{#each SUGGESTED as s}
			<li><button type="button" class="chip" onclick={() => ask(s)}>{s}</button></li>
		{/each}
	</ul>
</section>

<style>
	.panel {
		padding: var(--space-xl) var(--space-lg) var(--space-lg);
		border-bottom: 1px solid var(--rule-hairline);
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
	}
	.eyebrow {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--ink-muted);
	}
	.lede {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}
	.input-row {
		display: flex;
		align-items: center;
		border: 1px solid var(--rule-hairline);
		background-color: var(--bg-surface);
		padding: 2px 6px 2px var(--space-sm);
	}
	.input-row:focus-within {
		border-color: var(--accent);
	}
	input {
		flex: 1;
		min-width: 0;
		min-height: 40px;
		font: inherit;
		font-size: var(--text-sm);
		color: var(--ink-primary);
		background: none;
		border: none;
	}
	input::placeholder {
		color: var(--ink-muted);
	}
	input:focus {
		outline: none;
	}
	.send {
		min-height: 36px;
		padding: 0 var(--space-sm);
		font-family: var(--font-num);
		font-size: var(--text-xs);
		color: var(--ink-secondary);
		cursor: pointer;
	}
	.send:hover {
		color: var(--accent);
	}
	.chips {
		list-style: none;
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-xs);
	}
	.chip {
		min-height: 36px;
		padding: 0 var(--space-sm);
		border: 1px solid var(--rule-hairline);
		border-radius: 3px;
		font-size: var(--text-xs);
		color: var(--ink-secondary);
		cursor: pointer;
		transition: border-color 150ms var(--ease-out-quart), color 150ms var(--ease-out-quart);
	}
	.chip:hover {
		border-color: var(--accent-rule);
		color: var(--ink-primary);
	}
	@media (max-width: 760px) {
		.panel {
			padding: var(--space-lg) var(--space-md);
		}
	}
</style>
