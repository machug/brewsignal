<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		title: string;
		icon?: string;
		highlight?: boolean;
		compact?: boolean;
		collapsible?: boolean;
		expanded?: boolean;
		onToggle?: () => void;
		children: Snippet;
	}

	let {
		title,
		icon,
		highlight = false,
		compact = false,
		collapsible = false,
		expanded = false,
		onToggle,
		children
	}: Props = $props();
</script>

<div class="batch-card" class:highlight class:compact>
	<div class="card-header">
		<div class="header-left">
			<h3 class="card-title">{title}</h3>
		</div>

		{#if collapsible && onToggle}
			<button
				type="button"
				class="expand-btn"
				onclick={onToggle}
				aria-label={expanded ? 'Collapse' : 'Expand'}
			>
				<svg
					class="expand-icon"
					aria-hidden="true"
					class:rotate-180={expanded}
					fill="none"
					viewBox="0 0 24 24"
					stroke="currentColor"
					stroke-width="2"
				>
					<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
				</svg>
			</button>
		{/if}
	</div>

	<div class="card-content" class:collapsed={collapsible && !expanded}>
		{@render children()}
	</div>
</div>

<style>
	/* Section, not a floating card: hairline rule on top */
	.batch-card {
		border-top: 1px solid var(--rule-strong);
		padding-top: var(--space-sm);
		min-width: 0;
	}
	.batch-card.highlight {
		border-top-color: var(--accent-rule);
	}
	.card-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: var(--space-sm);
	}
	.compact .card-header {
		margin-bottom: var(--space-xs);
	}
	.header-left {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
	}
	.card-title {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-muted);
		text-transform: uppercase;
		letter-spacing: 0.08em;
		margin: 0;
	}
	.expand-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 2.75rem;
		height: 2.75rem;
		margin: -0.5rem 0;
		border-radius: 3px;
		color: var(--ink-muted);
		cursor: pointer;
	}
	.expand-btn:hover {
		color: var(--ink-primary);
		background: var(--bg-subtle);
	}
	.expand-icon {
		width: 1rem;
		height: 1rem;
		transition: transform 150ms var(--ease-out-quart);
	}
	.expand-icon.rotate-180 {
		transform: rotate(180deg);
	}
	.card-content {
		padding-bottom: var(--space-xs);
		max-height: 5000px;
		overflow: hidden;
		transition: max-height 300ms var(--ease-out-quart), opacity 200ms var(--ease-out-quart);
		opacity: 1;
	}
	.card-content.collapsed {
		max-height: 0;
		padding-bottom: 0;
		opacity: 0;
	}
	@media (prefers-reduced-motion: reduce) {
		.card-content,
		.expand-icon {
			transition: none;
		}
	}
</style>
