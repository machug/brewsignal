<script lang="ts">
	import { authFetch } from '$lib/api';
	import { applyOutcome, type ToolPart } from '$lib/chat/logic';
	import HopPlan from './HopPlan.svelte';

	interface Props {
		part: ToolPart;
		/** Server rejected the approval (HTTP 400 before any stream). */
		error?: string;
		onApprove: (approvalId: string) => void;
		onCancel: (approvalId: string) => void;
		/** Deny this call and steer the agent to apply without removing unlisted hops. */
		onKeepUnlisted: (approvalId: string) => void;
		/** Ask the assistant to prepare the update again (after a failure). */
		onRetry: () => void;
		retryDisabled?: boolean;
	}
	let { part, error = '', onApprove, onCancel, onKeepUnlisted, onRetry, retryDisabled = false }: Props = $props();

	const outcome = $derived(error ? ({ phase: 'failed', message: error } as const) : applyOutcome(part));
	const replace = $derived(Boolean(part.input?.replace));
	const count = $derived(part.input?.items?.length ?? 0);

	// Diff for the proposal: dry run of the same items/replace the tool will apply.
	let diff = $state<any>(null);
	let diffState = $state<'idle' | 'loading' | 'ready' | 'error'>('idle');
	let diffKey = '';

	async function loadDiff() {
		diffState = 'loading';
		try {
			const res = await authFetch('/api/inventory/hops/bulk', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ items: part.input?.items ?? [], replace, dry_run: true })
			});
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			diff = await res.json();
			diffState = 'ready';
		} catch {
			diffState = 'error';
		}
	}

	$effect(() => {
		if (outcome.phase !== 'proposed') return;
		const key = JSON.stringify(part.input ?? null);
		if (key === diffKey) return;
		diffKey = key;
		loadDiff();
	});

	const titles = {
		proposed: 'Proposed hop stock update',
		running: 'Updating hop stock',
		applied: 'Hop stock updated',
		failed: 'Hop stock not updated',
		denied: 'Update cancelled',
		pending: 'Hop stock update'
	} as const;
	const badge = $derived(
		{ proposed: 'Proposed', running: 'Applying', applied: 'Applied', failed: 'Failed', denied: 'Cancelled', pending: 'Pending' }[outcome.phase]
	);
	// Plan to show: the live dry-run while deciding, the real output once applied.
	const shown = $derived(outcome.phase === 'applied' ? outcome.plan : diff);
	const showPlan = $derived(outcome.phase === 'applied' || outcome.phase === 'running' || outcome.phase === 'proposed');
	const approvalId = $derived(part.approval?.id ?? '');
</script>

<section class="card" class:applied={outcome.phase === 'applied'} aria-label="Hop stock update" aria-live="polite">
	<header>
		<h3>{titles[outcome.phase]}</h3>
		<span class="badge {outcome.phase}">{badge}</span>
	</header>

	{#if outcome.phase === 'denied'}
		<p class="muted">Nothing was changed.</p>
	{:else if outcome.phase === 'failed'}
		<p class="alert" role="alert">{outcome.message}</p>
		<p class="muted">Nothing was changed.</p>
		<div class="actions"><button type="button" onclick={onRetry} disabled={retryDisabled}>Prepare again</button></div>
	{:else if showPlan}
		{#if shown}
			<HopPlan plan={shown} {replace} applied={outcome.phase === 'applied'} />
		{:else if diffState === 'error'}
			<p class="alert" role="alert">Could not load the change preview ({count} {count === 1 ? 'hop' : 'hops'} proposed).</p>
			<div class="actions">
				<button type="button" onclick={loadDiff}>Retry preview</button>
				<button type="button" class="ghost" onclick={() => onCancel(approvalId)}>Cancel</button>
			</div>
		{:else}
			<p class="muted">Loading changes…</p>
		{/if}

		{#if outcome.phase === 'proposed' && shown}
			<p class="question">{replace ? 'Replace your whole hop stock with this list?' : 'Apply these changes to your hop stock?'}</p>
			<div class="actions">
				<button type="button" class="primary" onclick={() => onApprove(approvalId)}>{replace ? 'Replace all' : 'Update stock'}</button>
				<button type="button" onclick={() => onCancel(approvalId)}>Cancel</button>
				{#if replace}
					<button type="button" class="ghost" onclick={() => onKeepUnlisted(approvalId)}>Keep unlisted hops instead</button>
				{/if}
			</div>
		{:else if outcome.phase === 'running'}
			<p class="muted">Applying…</p>
		{/if}
	{/if}
</section>

<style>
	.card {
		max-width: 640px;
		margin: var(--space-sm) 0;
		padding: var(--space-md);
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
	}
	.card.applied { border-color: var(--rule-hairline); }
	header { display: flex; align-items: center; justify-content: space-between; gap: var(--space-sm); margin-bottom: var(--space-xs); }
	h3 { margin: 0; word-spacing: 0.08em; font-family: var(--font-display); font-size: var(--text-base); font-weight: 600; color: var(--ink-primary); }
	.badge {
		font-family: var(--font-num);
		font-size: 0.8125rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		padding: 1px 8px;
		border: 1px solid var(--rule-strong);
		color: var(--ink-secondary);
		white-space: nowrap;
	}
	.badge.proposed { border-color: var(--accent-rule); color: var(--accent); }
	.badge.applied { border-color: var(--status-steady); color: var(--status-steady); }
	.badge.failed { border-color: var(--status-danger); color: var(--status-danger); }
	.muted { margin: var(--space-xs) 0 0; font-size: var(--text-sm); color: var(--ink-secondary); }
	.alert {
		margin: var(--space-xs) 0;
		padding: var(--space-sm);
		font-size: var(--text-sm);
		color: var(--ink-primary);
		background: var(--error-bg);
		border: 1px solid color-mix(in oklch, var(--status-danger) 45%, transparent);
	}
	.question { margin: var(--space-md) 0 var(--space-sm); font-size: var(--text-sm); color: var(--ink-primary); }
	.actions { display: flex; flex-wrap: wrap; gap: var(--space-sm); }
	button {
		min-height: 44px;
		padding: 0 var(--space-md);
		font: inherit;
		font-size: var(--text-sm);
		color: var(--ink-primary);
		background: transparent;
		border: 1px solid var(--rule-strong);
		cursor: pointer;
	}
	button:hover { background: var(--bg-subtle); }
	button.primary { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); font-weight: 700; }
	button.primary:hover { background: var(--accent-hover); }
	button.ghost { background: var(--bg-elevated); border-color: var(--rule-hairline); color: var(--ink-primary); }
	button.ghost:hover { background: var(--bg-subtle); }
	button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
</style>
