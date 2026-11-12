<script lang="ts">
	// Approval card for the assistant's save_recipe / update_recipe (tilt_ui-eevz.1).
	// Shows a server dry run (nothing stored) so the brewer approves plain-language
	// changes and calculated numbers, never raw JSON Patch paths.
	import { authFetch } from '$lib/api';
	import { applyOutcome, toolName, type ToolPart } from '$lib/chat/logic';
	import { recipeUrl } from '$lib/urls';

	interface Props {
		part: ToolPart;
		error?: string;
		onApprove: (approvalId: string) => void;
		onCancel: (approvalId: string) => void;
		onRetry: () => void;
		retryDisabled?: boolean;
	}
	let { part, error = '', onApprove, onCancel, onRetry, retryDisabled = false }: Props = $props();

	const isEdit = $derived(toolName(part) === 'update_recipe');
	const outcome = $derived(error ? ({ phase: 'failed', message: error } as const) : applyOutcome(part));
	const approvalId = $derived(part.approval?.id ?? '');

	let preview = $state<any>(null);
	let previewState = $state<'idle' | 'loading' | 'ready' | 'error'>('idle');
	let previewKey = '';
	let seq = 0;

	async function loadPreview() {
		const mine = ++seq; // a slower earlier request must not overwrite a newer one
		preview = null; // never show an old preview's Approve button for new input
		previewState = 'loading';
		const input = part.input ?? {};
		const body = isEdit ? { recipe_id: input.recipe_id, operations: input.operations } : { document: input.document };
		try {
			const res = await authFetch('/api/recipes/assistant-preview', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body)
			});
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			const data = await res.json();
			if (mine !== seq) return;
			preview = data;
			previewState = 'ready';
		} catch {
			if (mine === seq) previewState = 'error';
		}
	}

	$effect(() => {
		if (outcome.phase !== 'proposed') return;
		const key = JSON.stringify(part.input ?? null);
		if (key === previewKey) return;
		previewKey = key;
		loadPreview();
	});

	const STATS: [string, string, (v: number) => string][] = [
		['og', 'OG', (v) => v.toFixed(3)],
		['fg', 'FG', (v) => v.toFixed(3)],
		['abv', 'ABV', (v) => `${v.toFixed(1)}%`],
		['ibu', 'IBU', (v) => v.toFixed(0)],
		['srm', 'SRM', (v) => v.toFixed(1)]
	];
	const fmt = (f: (v: number) => string, v: unknown) => (typeof v === 'number' ? f(v) : '—');

	// Once applied, show the tool's real result; before that, the dry run.
	const shown = $derived(outcome.phase === 'applied' ? outcome.plan : preview);
	// The saved result has no diff; keep showing what was approved.
	const before = $derived(shown?.before ?? preview?.before);
	const changes = $derived(shown?.changes ?? preview?.changes);
	const sections = $derived(shown?.sections ?? preview?.sections);
	const name = $derived(shown?.name ?? part.input?.document?.recipe?.name ?? '');
	const titles = $derived({
		proposed: isEdit ? 'Proposed recipe change' : 'Proposed new recipe',
		running: isEdit ? 'Updating recipe' : 'Saving recipe',
		applied: isEdit ? 'Recipe updated' : 'Recipe saved',
		failed: isEdit ? 'Recipe not updated' : 'Recipe not saved',
		denied: 'Cancelled',
		pending: 'Recipe'
	});
	const badge = $derived(
		{ proposed: 'Proposed', running: 'Saving', applied: 'Saved', failed: 'Failed', denied: 'Cancelled', pending: 'Pending' }[outcome.phase]
	);
</script>

<section class="card" class:applied={outcome.phase === 'applied'} aria-label={titles[outcome.phase]}>
	<header>
		<h3>{titles[outcome.phase]}{name ? `: ${name}` : ''}</h3>
		<span class="badge {outcome.phase}" role="status" aria-live="polite">{badge}</span>
	</header>

	{#if part.input?.summary && outcome.phase !== 'applied'}
		<p class="summary">{part.input.summary}</p>
	{/if}

	{#if outcome.phase === 'denied'}
		<p class="muted">Nothing was changed.</p>
	{:else if outcome.phase === 'failed'}
		<p class="alert" role="alert">{outcome.message}</p>
		<p class="muted">Nothing was changed.</p>
		<div class="actions"><button type="button" onclick={onRetry} disabled={retryDisabled}>Prepare again</button></div>
	{:else if shown?.error}
		<p class="alert" role="alert">{shown.error}{shown.details ? `: ${shown.details.join('; ')}` : ''}</p>
		<div class="actions"><button type="button" onclick={() => onCancel(approvalId)}>Cancel</button></div>
	{:else if shown}
		<div class="table-wrap">
			<table class="stats">
				<thead>
					<tr><td></td>{#each STATS as [, label]}<th scope="col">{label}</th>{/each}</tr>
				</thead>
				<tbody>
					{#if isEdit && before}
						<tr><th scope="row">Before</th>{#each STATS as [k, , f]}<td>{fmt(f, before.calculated?.[k])}</td>{/each}</tr>
					{/if}
					<tr><th scope="row">{isEdit && before ? 'After' : 'Calculated'}</th>{#each STATS as [k, , f]}<td>{fmt(f, shown.calculated?.[k])}</td>{/each}</tr>
					{#if STATS.some(([k]) => typeof shown.targets?.[k] === 'number')}
						<tr class="target"><th scope="row">Target</th>{#each STATS as [k, , f]}<td>{fmt(f, shown.targets?.[k])}</td>{/each}</tr>
					{/if}
				</tbody>
			</table>
		</div>

		{#if isEdit && changes?.length}
			<ul class="changes">
				{#each changes as line, i (i)}<li>{line}</li>{/each}
			</ul>
		{:else if !isEdit && sections}
			<dl class="sections">
				{#each Object.entries(sections) as [section, items] (section)}
					{#if (items as string[]).length}
						<dt>{section}</dt>
						{#each items as string[] as item, i (i)}<dd>{item}</dd>{/each}
					{/if}
				{/each}
			</dl>
		{/if}

		{#if shown.warnings?.length}
			<ul class="warnings">
				{#each shown.warnings as w, i (i)}<li>{w}</li>{/each}
			</ul>
		{/if}

		{#if outcome.phase === 'proposed'}
			<div class="actions">
				<button type="button" class="primary" onclick={() => onApprove(approvalId)}>{isEdit ? 'Apply change' : 'Save recipe'}</button>
				<button type="button" onclick={() => onCancel(approvalId)}>Cancel</button>
			</div>
		{:else if outcome.phase === 'running'}
			<p class="muted">Saving…</p>
		{:else if outcome.phase === 'applied' && shown.recipe_id}
			<p class="muted"><a href={recipeUrl({ id: shown.recipe_id, name: shown.name })}>Open the recipe</a></p>
		{/if}
	{:else if previewState === 'error'}
		<p class="alert" role="alert">Could not load the preview.</p>
		<div class="actions">
			<button type="button" onclick={loadPreview}>Retry preview</button>
			<button type="button" class="ghost" onclick={() => onCancel(approvalId)}>Cancel</button>
		</div>
	{:else}
		<p class="muted">Checking the recipe…</p>
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
	.summary { margin: 0 0 var(--space-sm); font-size: var(--text-sm); color: var(--ink-primary); }
	.muted { margin: var(--space-xs) 0 0; font-size: var(--text-sm); color: var(--ink-secondary); }
	.muted a { color: var(--accent); }
	.alert {
		margin: var(--space-xs) 0;
		padding: var(--space-sm);
		font-size: var(--text-sm);
		color: var(--ink-primary);
		background: var(--error-bg);
		border: 1px solid color-mix(in oklch, var(--status-danger) 45%, transparent);
	}
	.table-wrap { overflow-x: auto; margin: var(--space-xs) 0 var(--space-sm); }
	.stats { width: 100%; min-width: 22rem; border-collapse: collapse; font-size: var(--text-sm); }
	.stats th, .stats td { padding: 4px 6px; border-bottom: 1px solid var(--rule-hairline); text-align: right; }
	.stats th[scope='row'] { text-align: left; font-weight: 500; color: var(--ink-secondary); }
	.stats thead th { font-family: var(--font-display); font-weight: 600; color: var(--ink-secondary); }
	.stats td { font-family: var(--font-num); font-variant-numeric: tabular-nums; color: var(--ink-primary); }
	.stats tr.target td { color: var(--ink-secondary); }
	.changes, .warnings { margin: var(--space-xs) 0; padding-left: 1.2em; font-size: var(--text-sm); }
	.changes li { color: var(--ink-primary); margin: 2px 0; }
	.warnings li { color: var(--status-warn); margin: 2px 0; }
	.sections { margin: var(--space-xs) 0; font-size: var(--text-sm); }
	.sections dt { margin-top: var(--space-xs); font-family: var(--font-display); font-weight: 600; color: var(--ink-secondary); }
	.sections dd { margin: 0 0 0 var(--space-sm); color: var(--ink-primary); }
	.actions { display: flex; flex-wrap: wrap; gap: var(--space-sm); margin-top: var(--space-sm); }
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
