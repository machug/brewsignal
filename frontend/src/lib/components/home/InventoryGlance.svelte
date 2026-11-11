<script lang="ts">
	import { onMount } from 'svelte';
	import {
		fetchHopInventory,
		fetchHopSummary,
		fetchYeastInventory,
		fetchYeastInventorySummary,
		type HopSummary,
		type YeastInventoryResponse,
		type YeastInventorySummary
	} from '$lib/api';

	const LOW_GRAMS = 50;
	const TOP = 5;

	let hops = $state<{ variety: string; grams: number }[]>([]);
	let hopSummary = $state<HopSummary | null>(null);
	let yeastSummary = $state<YeastInventorySummary | null>(null);
	let nearest = $state<YeastInventoryResponse | null>(null);
	let loaded = $state(false);
	let failed = $state(false);

	onMount(async () => {
		try {
			const [inv, hs, ys, yeast] = await Promise.all([
				fetchHopInventory({ limit: 200 }),
				fetchHopSummary(),
				fetchYeastInventorySummary(),
				fetchYeastInventory({ limit: 200 })
			]);
			const byVariety = new Map<string, number>();
			for (const h of inv) byVariety.set(h.variety, (byVariety.get(h.variety) ?? 0) + h.amount_grams);
			hops = [...byVariety].map(([variety, grams]) => ({ variety, grams })).sort((a, b) => b.grams - a.grams);
			hopSummary = hs;
			yeastSummary = ys;
			nearest =
				yeast
					.filter((y) => y.expiry_date && y.quantity > 0)
					.sort((a, b) => new Date(a.expiry_date!).getTime() - new Date(b.expiry_date!).getTime())[0] ?? null;
		} catch {
			failed = true;
		} finally {
			loaded = true;
		}
	});

	let top = $derived(hops.slice(0, TOP));
	let maxGrams = $derived(Math.max(1, ...top.map((h) => h.grams)));
	let lowCount = $derived(hops.filter((h) => h.grams < LOW_GRAMS).length);

	const grams = (n: number) => Math.round(n).toLocaleString('en-AU');
	function fmtDate(iso: string): string {
		return new Date(iso).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' });
	}
	let yeastName = $derived(nearest?.custom_name || nearest?.yeast_strain?.name || 'Yeast');
</script>

<section class="panel" aria-labelledby="inv-h">
	<div class="head">
		<h2 id="inv-h" class="eyebrow">Inventory</h2>
		<a class="link" href="/inventory">Open inventory &rarr;</a>
	</div>

	{#if !loaded}
		<p class="note">Loading inventory</p>
	{:else if failed}
		<p class="note">Inventory unavailable.</p>
	{:else}
		<div class="sub num">
			<span>{hopSummary ? `Hops \u00b7 ${grams(hopSummary.total_grams)}\u2009g total \u00b7 ${hopSummary.unique_varieties} varieties` : 'Hops'}</span>
		</div>
		{#if top.length === 0}
			<p class="note">No hops in stock.</p>
		{:else}
			<ul class="hops">
				{#each top as h (h.variety)}
					{@const low = h.grams < LOW_GRAMS}
					<li class="hop" data-low={low}>
						<span class="name">{h.variety}{#if low}<span class="low">Low</span>{/if}</span>
						<span class="meter" aria-hidden="true"><span class="fill" style="transform: scaleX({h.grams / maxGrams})"></span></span>
						<span class="mass num">{grams(h.grams)}&thinsp;g</span>
					</li>
				{/each}
			</ul>
			{#if lowCount > 0}<p class="note"><span class="warn num">{lowCount}</span> {lowCount === 1 ? 'variety' : 'varieties'} under {LOW_GRAMS}&thinsp;g</p>{/if}
		{/if}

		<div class="sub num yeast-head">
			<span>{yeastSummary ? `Yeast \u00b7 ${yeastSummary.total_quantity} ${yeastSummary.total_quantity === 1 ? 'pack' : 'packs'}` : 'Yeast'}</span>
		</div>
		{#if nearest?.expiry_date}
			<div class="yeast">
				<span class="y-name">{yeastName}</span>
				<span class="y-meta num">Expires {fmtDate(nearest.expiry_date)}</span>
			</div>
		{:else}
			<p class="note">No expiry dates recorded.</p>
		{/if}
		{#if yeastSummary && (yeastSummary.expired > 0 || yeastSummary.expiring_soon > 0)}
			<p class="note">
				{#if yeastSummary.expired > 0}<span class="warn num">{yeastSummary.expired}</span> expired{/if}{#if yeastSummary.expired > 0 && yeastSummary.expiring_soon > 0} &middot; {/if}{#if yeastSummary.expiring_soon > 0}<span class="warn num">{yeastSummary.expiring_soon}</span> expiring within 30 days{/if}
			</p>
		{/if}
	{/if}
</section>

<style>
	.panel {
		padding: var(--space-lg);
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
	}
	.head {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: var(--space-md);
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
	.num {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums lining-nums;
	}
	.sub {
		font-size: 0.72rem;
		color: var(--ink-muted);
		padding-bottom: 6px;
		border-bottom: 1px solid var(--rule-hairline);
	}
	.yeast-head {
		margin-top: var(--space-xs);
	}
	.note {
		font-size: var(--text-xs);
		color: var(--ink-secondary);
	}
	.warn {
		color: var(--status-warn);
	}
	.hops {
		list-style: none;
	}
	.hop {
		display: grid;
		grid-template-columns: minmax(0, 1.25fr) 1fr auto;
		align-items: center;
		gap: var(--space-sm);
		padding: 7px 0;
		border-bottom: 1px solid var(--rule-hairline);
		font-size: var(--text-sm);
	}
	.name {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		min-width: 0;
		color: var(--ink-primary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.low {
		font-family: var(--font-num);
		font-size: 0.65rem;
		font-weight: 600;
		text-transform: uppercase;
		padding: 1px 5px;
		border: 1px solid color-mix(in oklch, var(--status-warn) 50%, transparent);
		color: var(--status-warn);
		border-radius: 2px;
		flex-shrink: 0;
	}
	.meter {
		height: 4px;
		background-color: var(--bg-subtle);
		overflow: hidden;
	}
	.fill {
		display: block;
		height: 100%;
		background-color: var(--ink-muted);
		transform-origin: left center;
	}
	.hop[data-low='true'] .fill {
		background-color: var(--status-warn);
	}
	.mass {
		font-size: var(--text-xs);
		color: var(--ink-primary);
		min-width: 52px;
		text-align: right;
	}
	.yeast {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: var(--space-sm);
		font-size: var(--text-sm);
	}
	.y-name {
		color: var(--ink-primary);
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.y-meta {
		font-size: var(--text-xs);
		color: var(--ink-secondary);
		flex-shrink: 0;
	}
	@media (max-width: 760px) {
		.panel {
			padding: var(--space-lg) var(--space-md);
		}
	}
</style>
