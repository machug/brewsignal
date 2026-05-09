<script lang="ts">
	import { marked } from 'marked';
	import type { RecipeReviewResponse } from '$lib/api';

	interface Props {
		open: boolean;
		loading: boolean;
		error: string | null;
		result: RecipeReviewResponse | null;
		styleName?: string;
		onClose: () => void;
	}

	let { open, loading, error, result, styleName = '', onClose }: Props = $props();

	// Track where a pointer interaction began. Only treat the overlay as
	// "clicked outside" when both mousedown AND mouseup land on the
	// overlay itself — otherwise dragging a text selection that ends on
	// the overlay would unexpectedly close the modal mid-highlight.
	let pointerDownOnOverlay = $state(false);

	function handleOverlayPointerDown(e: PointerEvent) {
		pointerDownOnOverlay = e.target === e.currentTarget;
	}

	function handleOverlayClick(e: MouseEvent) {
		if (pointerDownOnOverlay && e.target === e.currentTarget) {
			onClose();
		}
		pointerDownOnOverlay = false;
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') onClose();
	}
</script>

{#if open}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="modal-overlay"
		onpointerdown={handleOverlayPointerDown}
		onclick={handleOverlayClick}
		onkeydown={handleKeydown}
		role="presentation"
	>
		<div
			class="modal-content"
			role="dialog"
			aria-modal="true"
			aria-labelledby="review-modal-title"
			tabindex="-1"
			onkeydown={(e) => e.stopPropagation()}
		>
			<div class="modal-header">
				<h2 id="review-modal-title">AI Recipe Review</h2>
				<button class="modal-close" onclick={onClose} aria-label="Close">&times;</button>
			</div>
			<div class="modal-body">
				{#if loading}
					<div class="review-loading">
						<div class="spinner"></div>
						<p>Analyzing your recipe against {styleName || 'style guidelines'}...</p>
					</div>
				{:else if error}
					<div class="review-error">
						<p>{error}</p>
					</div>
				{:else if result}
					<div class="review-meta">
						{#if result.style_found}
							<span class="style-badge found">BJCP Style: {result.style_name}</span>
						{:else}
							<span class="style-badge not-found">Style not in BJCP database</span>
						{/if}
						<span class="model-badge">Model: {result.model}</span>
					</div>
					<div class="review-content markdown-body">
						{@html marked(result.review)}
					</div>
				{/if}
			</div>
			<div class="modal-footer">
				<button type="button" class="btn-close" onclick={onClose}>Close</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.modal-overlay {
		position: fixed;
		top: 0;
		left: 0;
		right: 0;
		bottom: 0;
		background: rgba(0, 0, 0, 0.7);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
		padding: var(--space-4);
	}

	.modal-content {
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 12px;
		max-width: 700px;
		width: 100%;
		max-height: 80vh;
		overflow: hidden;
		display: flex;
		flex-direction: column;
		box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
	}

	.modal-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: var(--space-4) var(--space-5);
		border-bottom: 1px solid var(--border-subtle);
	}

	.modal-header h2 {
		margin: 0;
		font-size: 18px;
		font-weight: 600;
		color: var(--text-primary);
	}

	.modal-close {
		background: none;
		border: none;
		font-size: 24px;
		color: var(--text-secondary);
		cursor: pointer;
		padding: 0;
		line-height: 1;
	}

	.modal-close:hover {
		color: var(--text-primary);
	}

	.modal-body {
		padding: var(--space-5);
		overflow-y: auto;
	}

	.modal-footer {
		display: flex;
		justify-content: flex-end;
		gap: var(--space-2);
		padding: var(--space-3) var(--space-5);
		border-top: 1px solid var(--border-subtle);
	}

	.btn-close {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		padding: 8px 16px;
		font-size: 13px;
		font-weight: 500;
		background: transparent;
		border: 1px solid var(--border-default);
		border-radius: 8px;
		color: var(--text-primary);
		cursor: pointer;
		transition: all 0.2s ease;
	}

	.btn-close:hover {
		background: var(--bg-hover);
		border-color: var(--text-secondary);
	}

	.review-loading {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-4);
		padding: var(--space-8) 0;
	}

	.spinner {
		width: 40px;
		height: 40px;
		border: 3px solid var(--border-default);
		border-top-color: var(--positive);
		border-radius: 50%;
		animation: spin 1s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	.review-loading p {
		color: var(--text-secondary);
		margin: 0;
	}

	.review-error {
		padding: var(--space-4);
		background: var(--negative-bg);
		border: 1px solid var(--negative);
		border-radius: 8px;
		color: var(--negative);
	}

	.review-meta {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
		margin-bottom: var(--space-4);
	}

	.style-badge,
	.model-badge {
		display: inline-block;
		padding: var(--space-1) var(--space-3);
		border-radius: 20px;
		font-size: 12px;
		font-weight: 500;
	}

	.style-badge.found {
		background: var(--positive-bg);
		color: var(--positive);
		border: 1px solid var(--positive);
	}

	.style-badge.not-found {
		background: var(--warning-bg);
		color: var(--warning);
		border: 1px solid var(--warning);
	}

	.model-badge {
		background: var(--bg-elevated);
		color: var(--text-secondary);
		border: 1px solid var(--border-default);
	}

	.review-content {
		line-height: 1.7;
		color: var(--text-primary);
	}

	.review-content :global(h3) {
		margin-top: var(--space-5);
		margin-bottom: var(--space-2);
		font-size: 16px;
		font-weight: 600;
		color: var(--text-primary);
	}

	.review-content :global(h3:first-child) {
		margin-top: 0;
	}

	.review-content :global(ul) {
		margin: var(--space-2) 0;
		padding-left: var(--space-5);
	}

	.review-content :global(li) {
		margin-bottom: var(--space-2);
	}

	.review-content :global(p) {
		margin: var(--space-3) 0;
	}

	.review-content :global(p:first-child) {
		margin-top: 0;
	}

	.review-content :global(strong) {
		font-weight: 600;
		color: var(--text-primary);
	}

	.review-content :global(em) {
		font-style: italic;
	}

	.review-content :global(hr) {
		border: none;
		border-top: 1px solid var(--border-subtle);
		margin: var(--space-4) 0;
	}
</style>
