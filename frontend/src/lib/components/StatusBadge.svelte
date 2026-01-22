<script lang="ts">
	import type { BatchStatus } from '$lib/api';
	import { statusConfig } from './status';

	interface Props {
		status: BatchStatus;
		variant?: 'badge' | 'pill' | 'dot' | 'text';
		size?: 'sm' | 'md';
		showDot?: boolean;
	}

	let { status, variant = 'badge', size = 'md', showDot = false }: Props = $props();

	let config = $derived(statusConfig[status] || statusConfig.planning);
</script>

{#if variant === 'badge'}
	<span
		class="status-badge status-{status} size-{size}"
		style="--status-color: {config.color}; --status-bg: {config.bg};"
	>
		{#if showDot || status === 'fermenting'}
			<span class="status-dot"></span>
		{/if}
		{config.label}
	</span>
{:else if variant === 'pill'}
	<span
		class="status-pill status-{status} size-{size}"
		style="--status-color: {config.color};"
	>
		{#if showDot || status === 'fermenting'}
			<span class="status-dot"></span>
		{/if}
		{config.label}
	</span>
{:else if variant === 'dot'}
	<span class="status-dot-only status-{status}" style="--status-color: {config.color};"></span>
{:else}
	<span class="status-text status-{status}" style="--status-color: {config.color};">
		{#if showDot || status === 'fermenting'}
			<span class="status-dot"></span>
		{/if}
		{config.label}
	</span>
{/if}

<style>
	/* Badge variant - full background */
	.status-badge {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		padding: 0.25rem 0.625rem;
		border-radius: 9999px;
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--status-color);
		background: var(--status-bg);
		white-space: nowrap;
	}

	.status-badge.size-sm {
		padding: 0.125rem 0.5rem;
		font-size: 0.6875rem;
	}

	/* Pill variant - subtle outline style */
	.status-pill {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		padding: 0.125rem 0.5rem;
		border-radius: 9999px;
		font-size: 0.6875rem;
		font-weight: 600;
		color: var(--status-color);
		background: transparent;
		white-space: nowrap;
	}

	.status-pill.size-sm {
		padding: 0.0625rem 0.375rem;
		font-size: 0.625rem;
	}

	/* Text variant - just colored text */
	.status-text {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		font-size: 0.8125rem;
		font-weight: 500;
		color: var(--status-color);
		white-space: nowrap;
	}

	.status-text.size-sm {
		font-size: 0.75rem;
	}

	/* Animated dot for active statuses */
	.status-dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: currentColor;
		flex-shrink: 0;
	}

	.status-fermenting .status-dot {
		animation: pulse 2s ease-in-out infinite;
	}

	/* Standalone dot */
	.status-dot-only {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: var(--status-color);
	}

	.status-dot-only.status-fermenting {
		animation: pulse 2s ease-in-out infinite;
	}

	@keyframes pulse {
		0%, 100% { opacity: 1; transform: scale(1); }
		50% { opacity: 0.6; transform: scale(0.9); }
	}
</style>
