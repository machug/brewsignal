<script lang="ts">
	import { renderMarkdown } from '$lib/markdown';
	import { segmentParts, type ToolPart } from '$lib/chat/logic';
	import ActivityGroup from './ActivityGroup.svelte';
	import HopApprovalCard from './HopApprovalCard.svelte';

	interface Props {
		message: { id: string; role: string; parts: any[]; metadata?: any };
		approvalError?: string;
		onApprove: (approvalId: string) => void;
		onCancel: (approvalId: string) => void;
		onKeepUnlisted: (approvalId: string) => void;
	}
	let { message, approvalError = '', onApprove, onCancel, onKeepUnlisted }: Props = $props();

	const segments = $derived(segmentParts(message.parts));

	// Right-align numeric table cells (amounts, IBU, times) after the markdown renders.
	const NUMERIC = /^[-+~<>]?\s*\d[\d.,:\s/-]*\s*(g|kg|oz|lb|%|ibu|srm|ebc|min|mins|h|°[cf]|c|f|l|gal|ppm)?$/i;
	function enhance(node: HTMLElement, _html: string) {
		const run = () => {
			for (const cell of node.querySelectorAll('td, th')) {
				if (NUMERIC.test((cell.textContent ?? '').trim())) cell.classList.add('num');
			}
		};
		run();
		return { update: run };
	}
</script>

{#if message.role === 'user'}
	<div class="turn user">
		<p class="user-text">{message.parts.filter((p) => p.type === 'text').map((p) => p.text).join('')}</p>
	</div>
{:else}
	<div class="turn assistant">
		{#each segments as seg, i (i)}
			{#if seg.kind === 'activity'}
				<ActivityGroup parts={seg.parts} />
			{:else if seg.kind === 'text'}
				{@const html = renderMarkdown(seg.part.text)}
				{#if html}<div class="md" use:enhance={html}>{@html html}</div>{/if}
			{:else}
				<HopApprovalCard part={seg.part as ToolPart} error={approvalError} {onApprove} {onCancel} {onKeepUnlisted} />
			{/if}
		{/each}
	</div>
{/if}

<style>
	.turn { min-width: 0; }
	.turn.user { align-self: flex-end; max-width: min(85%, 60ch); }
	.user-text {
		margin: 0; padding: var(--space-sm) var(--space-md);
		white-space: pre-wrap; overflow-wrap: anywhere;
		background: var(--bg-elevated); border: 1px solid var(--rule-hairline); color: var(--ink-primary);
	}
	.turn.assistant { align-self: stretch; }

	.md { max-width: 68ch; line-height: 1.6; color: var(--ink-primary); overflow-wrap: anywhere; }
	.md :global(> :first-child) { margin-top: 0; }
	.md :global(> :last-child) { margin-bottom: 0; }
	.md :global(p), .md :global(ul), .md :global(ol) { margin: 0 0 var(--space-sm); }
	.md :global(ul), .md :global(ol) { padding-left: 1.4em; }
	.md :global(li) { margin: 2px 0; }
	.md :global(h1), .md :global(h2), .md :global(h3), .md :global(h4) {
		font-family: var(--font-display); font-weight: 600; line-height: 1.25; margin: var(--space-md) 0 var(--space-xs);
	}
	.md :global(h1) { font-size: var(--text-lg); }
	.md :global(h2) { font-size: 1.125rem; }
	.md :global(h3), .md :global(h4) { font-size: var(--text-base); }
	.md :global(a) { color: var(--accent); text-underline-offset: 2px; }
	.md :global(strong) { font-weight: 700; }
	.md :global(code) { font-family: var(--font-num); font-size: 0.875em; padding: 0 4px; background: var(--bg-elevated); }
	.md :global(pre) {
		margin: 0 0 var(--space-sm); padding: var(--space-sm); overflow-x: auto;
		background: var(--bg-surface); border: 1px solid var(--rule-hairline);
	}
	.md :global(pre code) { padding: 0; background: none; }
	.md :global(blockquote) { margin: 0 0 var(--space-sm); padding: 0 0 0 var(--space-md); color: var(--ink-secondary); }
	.md :global(hr) { border: 0; border-top: 1px solid var(--rule-hairline); margin: var(--space-md) 0; }

	/* Tables scroll inside their own box with a sticky header; width is not capped by the prose measure. */
	.md :global(table) {
		display: block; width: max-content; max-width: min(100%, 780px); max-height: 24rem; overflow: auto;
		margin: 0 0 var(--space-sm); border-collapse: separate; border-spacing: 0;
		border: 1px solid var(--rule-hairline); font-size: var(--text-sm);
	}
	.md :global(th), .md :global(td) { padding: 6px var(--space-sm); text-align: left; border-bottom: 1px solid var(--rule-hairline); white-space: nowrap; }
	.md :global(tbody tr:last-child td) { border-bottom: 0; }
	.md :global(th) {
		position: sticky; top: 0; background: var(--bg-elevated); z-index: 1;
		font-family: var(--font-display); font-size: 0.8125rem; font-weight: 600;
		text-transform: uppercase; letter-spacing: 0.05em; color: var(--ink-secondary);
	}
	.md :global(td.num), .md :global(th.num) { text-align: right; font-family: var(--font-num); font-variant-numeric: tabular-nums; }
	.md :global(tbody tr:nth-child(even) td) { background: color-mix(in oklch, var(--bg-elevated) 55%, transparent); }
</style>
