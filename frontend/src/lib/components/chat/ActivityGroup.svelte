<script lang="ts">
	import { activitySummary, isToolPart, summarizeInput, toolLabel, toolName, type ToolPart } from '$lib/chat/logic';

	let { parts }: { parts: any[] } = $props();

	let open = $state(false);
	let debug = $state(false);
	const sum = $derived(activitySummary(parts));
	const stateText = (s: ToolPart['state']) =>
		s === 'output-available' ? 'done' : s === 'output-error' ? 'failed' : s === 'output-denied' ? 'denied' : 'running';
</script>

<div class="group" class:running={sum.running}>
	<button type="button" class="head" aria-expanded={open} onclick={() => (open = !open)}>
		<span class="dot" aria-hidden="true"></span>
		<span class="sum">{sum.text}</span>
		<span class="count">{sum.steps} {sum.steps === 1 ? 'step' : 'steps'}</span>
		<svg class="chev" class:open width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M9 6l6 6-6 6" /></svg>
	</button>

	{#if open}
		<ol class="steps">
			{#each parts as p, i (i)}
				<li>
					{#if p.type === 'reasoning'}
						<div class="kind">Reasoning</div>
						<div class="think">{p.text}</div>
					{:else if isToolPart(p)}
						{@const t = p as ToolPart}
						<div class="tool">
							<span>{toolLabel(toolName(t), t.state)}</span>
							<span class="st" class:err={t.state === 'output-error'}>{stateText(t.state)}</span>
						</div>
						{#if summarizeInput(t.input)}<div class="think">{summarizeInput(t.input)}</div>{/if}
						{#if t.state === 'output-error' && t.errorText}<div class="think">{t.errorText}</div>{/if}
						{#if debug}
							<pre class="json">{toolName(t)}
{JSON.stringify({ input: t.input, output: t.output }, null, 2)}</pre>
						{/if}
					{/if}
				</li>
			{/each}
		</ol>
		{#if parts.some(isToolPart)}
			<button type="button" class="dbg" aria-pressed={debug} onclick={() => (debug = !debug)}>{debug ? 'Hide raw data' : 'Show raw data'}</button>
		{/if}
	{/if}
</div>

<style>
	.group { margin: 0 0 var(--space-sm); border: 1px solid var(--rule-hairline); background: var(--bg-surface); max-width: 68ch; }
	.head {
		display: flex; align-items: center; gap: var(--space-sm); width: 100%; min-height: 44px;
		padding: 0 var(--space-sm); background: none; border: 0; cursor: pointer; text-align: left;
		font: inherit; font-size: var(--text-sm); color: var(--ink-secondary);
	}
	.head:hover { color: var(--ink-primary); }
	.head:focus-visible, .dbg:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
	.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--status-steady); flex: none; }
	.running .dot { background: var(--accent); animation: pulse 1.2s ease-in-out infinite; }
	.sum { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.count { font-family: var(--font-num); font-size: 0.8125rem; color: var(--ink-secondary); }
	.chev { transition: transform 150ms; flex: none; }
	.chev.open { transform: rotate(90deg); }
	.steps { list-style: none; margin: 0; padding: 0 var(--space-sm) var(--space-sm); border-top: 1px solid var(--rule-hairline); }
	.steps li { padding: var(--space-sm) 0 0; }
	.kind { font-family: var(--font-display); font-size: 0.8125rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--ink-secondary); }
	.think { margin-top: 2px; font-size: var(--text-sm); color: var(--ink-secondary); white-space: pre-wrap; max-height: 14rem; overflow: auto; }
	.tool { display: flex; justify-content: space-between; gap: var(--space-sm); font-size: var(--text-sm); color: var(--ink-primary); }
	.st { font-family: var(--font-num); font-size: 0.8125rem; color: var(--ink-secondary); }
	.st.err { color: var(--status-danger); }
	.json {
		margin: var(--space-xs) 0 0; padding: var(--space-sm); max-height: 16rem; overflow: auto;
		font-family: var(--font-num); font-size: 0.8125rem; line-height: 1.45;
		background: var(--bg-canvas); border: 1px solid var(--rule-hairline); color: var(--ink-secondary);
	}
	.dbg {
		display: block; min-height: 44px; margin: 0 var(--space-sm); padding: 0; background: none; border: 0;
		font: inherit; font-size: 0.8125rem; color: var(--ink-secondary); text-decoration: underline; cursor: pointer;
	}
	@keyframes pulse { 0%, 100% { opacity: 0.35; transform: scale(0.8); } 50% { opacity: 1; transform: scale(1.1); } }
	@media (prefers-reduced-motion: reduce) { .running .dot { animation: none; } .chev { transition: none; } }
</style>
