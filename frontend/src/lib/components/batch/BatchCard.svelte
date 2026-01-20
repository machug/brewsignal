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
	{#if highlight}
		<div class="accent-bar"></div>
	{/if}

	<div class="card-header">
		<div class="header-left">
			{#if icon}
				<span class="card-icon">{icon}</span>
			{/if}
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
	.batch-card {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.75rem;
		overflow: hidden;
		transition: border-color var(--transition);
	}

	.batch-card:hover {
		border-color: var(--border-default);
	}

	.batch-card.highlight {
		border-color: var(--recipe-accent-border);
	}

	.accent-bar {
		height: 2px;
		background: linear-gradient(90deg, var(--recipe-accent), var(--recipe-accent-hover));
	}

	.card-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 1.25rem 1.25rem 0 1.25rem;
		margin-bottom: 1rem;
	}

	.compact .card-header {
		padding: 0.875rem 1rem 0 1rem;
		margin-bottom: 0.625rem;
	}

	.header-left {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.card-icon {
		font-size: 1rem;
	}

	.card-title {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin: 0;
	}

	.expand-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 1.5rem;
		height: 1.5rem;
		border-radius: 0.25rem;
		color: var(--text-muted);
		background: transparent;
		border: none;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.expand-btn:hover {
		color: var(--text-primary);
		background: var(--bg-hover);
	}

	.expand-icon {
		width: 1rem;
		height: 1rem;
		transition: transform 0.2s ease;
	}

	.expand-icon.rotate-180 {
		transform: rotate(180deg);
	}

	.card-content {
		padding: 0 1.25rem 1.25rem 1.25rem;
		max-height: 5000px;
		overflow: hidden;
		transition: max-height 0.3s ease-out, opacity 0.2s ease-out;
		opacity: 1;
	}

	.compact .card-content {
		padding: 0 1rem 0.875rem 1rem;
	}

	.card-content.collapsed {
		max-height: 0;
		padding-top: 0;
		padding-bottom: 0;
		opacity: 0;
		transition: max-height 0.3s ease-in, opacity 0.2s ease-in;
	}
</style>
