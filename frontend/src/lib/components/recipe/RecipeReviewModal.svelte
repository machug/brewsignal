<script lang="ts">
	import { renderMarkdown } from '$lib/markdown';
	import type { SavedReviewSummary, StatCheck } from '$lib/api';

	// A saved review (recipe page) or a one-off draft review (recipe editor).
	interface ReviewView {
		review: string;
		model?: string | null;
		style_name?: string | null;
		style_found?: boolean;
		id?: number;
		created_at?: string | null;
		score?: number | null;
		stats_score?: number | null;
		fingerprint?: string;
		compliance?: Record<string, StatCheck> | null;
	}

	interface Props {
		open: boolean;
		loading: boolean;
		error: string | null;
		result: ReviewView | null;
		styleName?: string;
		history?: SavedReviewSummary[];
		currentFingerprint?: string;
		onRereview?: () => void;
		onSelect?: (reviewId: number) => void;
		onClose: () => void;
	}

	let {
		open, loading, error, result, styleName = '', history = [], currentFingerprint = '',
		onRereview, onSelect, onClose
	}: Props = $props();

	const saved = $derived(result?.id != null);
	const stale = $derived(
		saved && !!currentFingerprint && !!result?.fingerprint && result.fingerprint !== currentFingerprint
	);
	const checks = $derived(
		Object.entries(result?.compliance ?? {}).filter(([, c]) => c.status !== 'no_guideline')
	);

	const STATUS: Record<string, string> = { in_range: 'in range', below: 'low', above: 'high', unknown: '?' };
	const fmtScore = (n: number | null | undefined) => (n == null ? '–' : `${Number.isInteger(n) ? n : n.toFixed(1)}/10`);
	const fmtDate = (iso: string | null | undefined) =>
		iso ? new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '';

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
						<p>Reviewing your recipe against {styleName || 'style guidelines'}...</p>
					</div>
				{:else if error}
					<div class="review-error">
						<p>{error}</p>
					</div>
				{:else if result}
					{#if saved}
						<div class="scores">
							<div class="score">
								<span class="score-label">Judge score</span>
								<span class="score-value">{fmtScore(result.score)}</span>
							</div>
							<div class="score">
								<span class="score-label">Stats in range</span>
								<span class="score-value">{fmtScore(result.stats_score)}</span>
							</div>
							<div class="score-meta">
								{fmtDate(result.created_at)}{#if result.model} · {result.model}{/if}
							</div>
						</div>
						{#if checks.length}
							<ul class="checks" aria-label="Stats against the style range">
								{#each checks as [key, c] (key)}
									<li class="check {c.status}">
										<span class="check-name">{key.toUpperCase()}</span>
										<span class="check-val">{c.value ?? '–'}{c.unit}</span>
										<span class="check-range">{c.min}–{c.max}</span>
										<span class="check-status">{STATUS[c.status] ?? c.status}</span>
									</li>
								{/each}
							</ul>
						{/if}
						{#if stale}
							<p class="stale">The recipe has changed since this review. Re-review to score the current version.</p>
						{/if}
					{:else}
						<div class="review-meta">
							{#if result.style_found}
								<span class="style-badge found">BJCP Style: {result.style_name}</span>
							{:else}
								<span class="style-badge not-found">Style not in BJCP database</span>
							{/if}
							{#if result.model}<span class="model-badge">Model: {result.model}</span>{/if}
						</div>
						<p class="draft-note">Review of the unsaved draft. It is not added to the recipe's review history.</p>
					{/if}
					<div class="review-content markdown-body">
						{@html renderMarkdown(result.review)}
					</div>
					{#if history.length > 1}
						<div class="history">
							<h3>Review history</h3>
							<ol>
								{#each history as h (h.id)}
									<li>
										<button
											type="button"
											class="history-item"
											class:current={h.id === result.id}
											aria-current={h.id === result.id ? 'true' : undefined}
											onclick={() => onSelect?.(h.id)}
										>
											<span>{fmtDate(h.created_at)}</span>
											<span class="num">Judge {fmtScore(h.score)}</span>
											<span class="num">Stats {fmtScore(h.stats_score)}</span>
											{#if h.fingerprint !== currentFingerprint}<span class="older">older recipe</span>{/if}
										</button>
									</li>
								{/each}
							</ol>
						</div>
					{/if}
				{/if}
			</div>
			<div class="modal-footer">
				{#if onRereview}
					<button type="button" class="btn-rereview" class:highlight={stale} onclick={onRereview} disabled={loading}>
						Re-review
					</button>
				{/if}
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
		background: color-mix(in oklch, var(--bg-canvas) 80%, transparent);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
		padding: var(--space-4);
	}

	.modal-content {
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 6px;
		max-width: 700px;
		width: 100%;
		max-height: 80vh;
		overflow: hidden;
		display: flex;
		flex-direction: column;
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
		font-family: var(--font-display);
		font-size: var(--text-lg);
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
		border-radius: 4px;
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
		border-top-color: var(--accent);
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
		background: var(--negative-muted);
		border: 1px solid var(--negative);
		border-radius: 4px;
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
		border-radius: 4px;
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}

	.style-badge.found {
		background: var(--positive-muted);
		color: var(--positive);
		border: 1px solid var(--positive);
	}

	.style-badge.not-found {
		background: var(--warning-muted);
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

	.scores { display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-4); margin-bottom: var(--space-3); }
	.score { display: flex; flex-direction: column; gap: 2px; }
	.score-label { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-secondary); }
	.score-value { font-family: var(--font-num); font-variant-numeric: tabular-nums; font-size: 1.5rem; color: var(--text-primary); }
	.score-meta { margin-left: auto; font-size: 0.8125rem; color: var(--text-secondary); }
	.checks { display: flex; flex-wrap: wrap; gap: var(--space-2); list-style: none; padding: 0; margin: 0 0 var(--space-3); }
	.check { display: flex; gap: 6px; align-items: baseline; padding: 4px 8px; border: 1px solid var(--border-default); border-radius: 4px; font-size: 0.8125rem; }
	.check-name { font-weight: 600; }
	.check-val, .check-range { font-family: var(--font-num); font-variant-numeric: tabular-nums; }
	.check-range { color: var(--text-secondary); }
	.check-status { font-size: 0.75rem; }
	.check.below .check-status, .check.above .check-status { color: var(--status-danger); font-weight: 600; }
	.check.in_range { border-color: color-mix(in oklch, var(--status-steady) 50%, transparent); }
	.check.below, .check.above { border-color: color-mix(in oklch, var(--status-danger) 60%, transparent); }
	.stale, .draft-note { margin: 0 0 var(--space-3); padding: var(--space-2) var(--space-3); border-left: 2px solid var(--accent); font-size: 0.875rem; color: var(--text-primary); }
	.draft-note { border-left-color: var(--border-default); color: var(--text-secondary); }
	.history { margin-top: var(--space-4); border-top: 1px solid var(--border-default); padding-top: var(--space-3); }
	.history h3 { font-size: 0.875rem; margin: 0 0 var(--space-2); }
	.history ol { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 4px; }
	.history-item { display: flex; flex-wrap: wrap; gap: var(--space-3); width: 100%; text-align: left; padding: 6px 8px; background: none; border: 1px solid transparent; border-radius: 4px; color: var(--text-primary); font-size: 0.8125rem; cursor: pointer; }
	.history-item:hover { border-color: var(--border-default); }
	.history-item.current { border-color: var(--accent); }
	.history-item .num { font-family: var(--font-num); font-variant-numeric: tabular-nums; }
	.older { color: var(--text-secondary); }
	.btn-rereview { padding: 8px 16px; border-radius: 4px; border: 1px solid var(--border-default); background: none; color: var(--text-primary); cursor: pointer; margin-right: auto; }
	.btn-rereview.highlight { border-color: var(--accent); color: var(--accent); }
	.btn-rereview:disabled { opacity: 0.5; cursor: default; }
</style>
