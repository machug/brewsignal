<script lang="ts">
	import { batchUrl } from '$lib/urls';
	import type { BatchResponse } from '$lib/api';

	interface Props {
		/** All non-deleted batches; the log picks planning first, then latest completed. */
		batches: BatchResponse[];
		max?: number;
	}

	let { batches, max = 5 }: Props = $props();

	function ts(b: BatchResponse, ...keys: Array<'brew_date' | 'completed_at' | 'end_time' | 'created_at'>): number {
		for (const k of keys) {
			const v = b[k];
			if (v) return new Date(v).getTime();
		}
		return 0;
	}

	let rows = $derived.by(() => {
		const planning = batches.filter((b) => b.status === 'planning').sort((a, b) => ts(a, 'brew_date', 'created_at') - ts(b, 'brew_date', 'created_at'));
		const done = batches
			.filter((b) => b.status === 'completed')
			.sort((a, b) => ts(b, 'completed_at', 'end_time', 'brew_date') - ts(a, 'completed_at', 'end_time', 'brew_date'));
		return [...planning, ...done].slice(0, max);
	});
	let total = $derived(batches.length);

	function fmtDate(iso?: string): string {
		return iso ? new Date(iso).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' }) : '';
	}
	function figure(b: BatchResponse): string {
		if (b.status === 'planning') return b.brew_date ? `Brew ${fmtDate(b.brew_date)}` : 'Not scheduled';
		const date = fmtDate(b.completed_at ?? b.end_time ?? b.brew_date);
		const abv = b.measured_abv != null ? `${b.measured_abv.toFixed(1)}% ABV` : null;
		return [abv, date].filter(Boolean).join(' · ');
	}
</script>

<section class="log" aria-labelledby="log-h">
	<div class="head">
		<h2 id="log-h" class="eyebrow">Batch log</h2>
		<a class="link" href="/batches">All batches ({total}) &rarr;</a>
	</div>
	{#if rows.length === 0}
		<p class="empty">No planned or completed batches yet.</p>
	{:else}
		<ul class="ledger">
			{#each rows as b (b.id)}
				<li>
					<a class="row" href={batchUrl(b)}>
						<span class="n num">#{b.batch_number ?? b.id}</span>
						<span class="name">{b.name || b.recipe?.name || `Batch #${b.batch_number}`}</span>
						<span class="badge" class:planning={b.status === 'planning'}>{b.status}</span>
						<span class="meta num">{figure(b)}</span>
					</a>
				</li>
			{/each}
		</ul>
	{/if}
</section>

<style>
	.log {
		padding: var(--space-lg) var(--space-xl) var(--space-xl);
	}
	.head {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: var(--space-md);
		margin-bottom: var(--space-md);
	}
	.eyebrow {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--ink-muted);
	}
	.link {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-secondary);
		border-bottom: 1px solid transparent;
		padding-bottom: 1px;
	}
	.link:hover {
		color: var(--ink-primary);
		border-bottom-color: var(--accent);
	}
	.empty {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}
	.ledger {
		list-style: none;
		border-top: 1px solid var(--rule-hairline);
	}
	.row {
		display: grid;
		grid-template-columns: 52px minmax(0, 1.5fr) 112px minmax(120px, 1fr);
		align-items: center;
		gap: var(--space-sm);
		padding: var(--space-sm) var(--space-xs);
		min-height: 48px;
		border-bottom: 1px solid var(--rule-hairline);
		font-size: var(--text-sm);
		transition: background-color 140ms var(--ease-out-quart);
	}
	.row:hover {
		background-color: var(--bg-surface);
	}
	.num {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums lining-nums;
	}
	.n {
		font-size: var(--text-xs);
		color: var(--ink-muted);
	}
	.name {
		font-weight: 700;
		color: var(--ink-primary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.badge {
		justify-self: start;
		font-family: var(--font-display);
		font-size: 0.6875rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		padding: 2px 7px;
		border-radius: 2px;
		border: 1px solid var(--rule-strong);
		color: var(--ink-secondary);
	}
	.badge.planning {
		border-color: var(--accent-rule);
		color: var(--accent);
		background-color: var(--accent-tint);
	}
	.meta {
		font-size: var(--text-xs);
		color: var(--ink-secondary);
		text-align: right;
	}
	@media (max-width: 760px) {
		.log {
			padding: var(--space-lg) var(--space-md);
		}
		.row {
			grid-template-columns: 42px minmax(0, 1fr) auto;
			row-gap: 4px;
		}
		.meta {
			grid-column: 2 / -1;
			text-align: left;
		}
	}
</style>
