<script lang="ts">
	import { formatGrams } from '$lib/chat/logic';

	// Hop plan from POST /api/inventory/hops/bulk (dry run) or the apply tool output.
	interface Plan {
		add?: { variety: string; amount_grams: number; in_library?: boolean; fuzzy_from?: string[] }[];
		update?: { variety: string; from_grams: number; to_grams: number; fuzzy_from?: string[]; guessed_as?: string | null }[];
		remove?: { variety: string; amount_grams: number; crop_year?: number | null; form?: string; reason?: string; replace_only?: boolean; guessed_as?: string | null }[];
		unchanged?: { variety: string }[];
		not_in_library?: string[];
	}
	interface Props {
		plan: Plan;
		/** Whether unlisted hops are being removed. Rows that only go when replacing are hidden otherwise. */
		replace?: boolean;
		applied?: boolean;
	}
	let { plan, replace = true, applied = false }: Props = $props();

	// A listed hop whose amount did not change is noise in the diff.
	const updates = $derived((plan.update ?? []).filter((u) => u.from_grams !== u.to_grams));
	const removals = $derived((plan.remove ?? []).filter((r) => replace || !r.replace_only));
	const oldCrop = (y?: number | null) => !!y && y < new Date().getFullYear() - 1;
	const detail = (r: { crop_year?: number | null; form?: string }) => [r.form].filter(Boolean).join(', ');
</script>

<div class="plan">
	<ul class="rows">
		{#each plan.add ?? [] as a}
			<li class="row">
				<span class="tag add">{applied ? 'Added' : 'Add'}</span>
				<span class="what">
					{a.variety}
					{#if a.in_library === false}<span class="note">not in hop library</span>{/if}
					{#if a.fuzzy_from?.length}<span class="note">matched from “{a.fuzzy_from.join('”, “')}”</span>{/if}
				</span>
				<span class="num">{formatGrams(a.amount_grams)}</span>
			</li>
		{/each}
		{#each updates as u}
			<li class="row">
				<span class="tag upd">{applied ? 'Updated' : 'Update'}</span>
				<span class="what">
					{u.variety}
					{#if u.fuzzy_from?.length}<span class="note">matched from “{u.fuzzy_from.join('”, “')}”</span>{/if}
					{#if u.guessed_as}<span class="note">read as {u.guessed_as}</span>{/if}
				</span>
				<span class="num">{formatGrams(u.from_grams)} → {formatGrams(u.to_grams)}</span>
			</li>
		{/each}
	</ul>

	{#if removals.length}
		<div class="removals" class:soft={applied}>
			<p class="rm-head">{applied ? 'Removed' : 'Removes'} {removals.length} {removals.length === 1 ? 'hop' : 'hops'} not in your list</p>
			<ul class="rows">
				{#each removals as r}
					<li class="row">
						<span class="tag del">{applied ? 'Removed' : 'Remove'}</span>
						<span class="what">
							{r.variety}
							{#if r.crop_year}<span class="pill" class:old={oldCrop(r.crop_year)}>{r.crop_year}</span>{/if}
							{#if detail(r)}<span class="muted">{detail(r)}</span>{/if}
							{#if r.reason === 'zero'}<span class="muted">listed as 0 g</span>{/if}
							{#if r.guessed_as}<span class="note">read as {r.guessed_as}</span>{/if}
						</span>
						<span class="num">{formatGrams(r.amount_grams)}</span>
					</li>
				{/each}
			</ul>
		</div>
	{/if}

	{#if plan.unchanged?.length}<p class="foot">No change: {plan.unchanged.map((u) => u.variety).join(', ')}</p>{/if}
	{#if plan.not_in_library?.length}<p class="foot">Not in hop library: {plan.not_in_library.join(', ')}</p>{/if}
</div>

<style>
	.rows { list-style: none; margin: 0; padding: 0; }
	.row {
		display: grid;
		grid-template-columns: 4.75rem minmax(0, 1fr) auto;
		column-gap: var(--space-sm);
		align-items: baseline;
		padding: 7px 0;
		border-bottom: 1px solid var(--rule-hairline);
		font-size: var(--text-sm);
	}
	.rows > .row:last-child { border-bottom: 0; }
	.tag {
		font-family: var(--font-num);
		font-size: 0.8125rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}
	.add { color: var(--status-steady); }
	.upd { color: var(--accent); }
	.del { color: var(--status-danger); }
	.what { display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px var(--space-sm); min-width: 0; overflow-wrap: anywhere; }
	.num {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		text-align: right;
		white-space: nowrap;
		color: var(--ink-primary);
	}
	.note { color: var(--status-warn); font-size: 0.8125rem; }
	.muted { color: var(--ink-secondary); font-size: 0.8125rem; }
	.pill {
		font-family: var(--font-num);
		font-size: 0.8125rem;
		padding: 0 6px;
		border: 1px solid var(--rule-strong);
		color: var(--ink-secondary);
	}
	.pill.old { border-color: var(--status-warn); color: var(--status-warn); }
	.removals {
		/* Bleed so inner rows share the outer column tracks (box border + padding = 12px). */
		margin: var(--space-sm) calc(-1 * var(--space-sm)) 0;
		padding: 0 calc(var(--space-sm) - 1px);
		background: var(--error-bg);
		border: 1px solid color-mix(in oklch, var(--status-danger) 35%, transparent);
	}
	.removals.soft { background: transparent; border-color: var(--rule-hairline); }
	.rm-head { margin: 0; padding: 8px 0 2px; font-size: 0.8125rem; color: var(--ink-secondary); }
	.removals .row { border-bottom-color: color-mix(in oklch, var(--status-danger) 20%, transparent); }
	.foot { margin: var(--space-sm) 0 0; font-size: 0.8125rem; color: var(--ink-secondary); }
	@media (max-width: 480px) {
		.row { grid-template-columns: 4rem minmax(0, 1fr) auto; column-gap: var(--space-xs); }
	}
</style>
