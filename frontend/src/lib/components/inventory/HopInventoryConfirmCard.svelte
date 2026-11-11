<script lang="ts">
	import { authFetch } from '$lib/api';

	// Plan returned by the assistant's update_hop_inventory tool (preview only).
	interface Plan {
		add: { variety: string; amount_grams: number; in_library: boolean; fuzzy_from: string[] }[];
		update: {
			variety: string;
			from_grams: number;
			to_grams: number;
			fuzzy_from: string[];
			guessed_as?: string | null;
		}[];
		remove: {
			variety: string;
			amount_grams: number;
			crop_year: number | null;
			form: string;
			reason: 'not_listed' | 'zero' | 'merged';
			replace_only: boolean;
			guessed_as?: string | null;
		}[];
		unchanged: { variety: string }[];
		not_in_library: string[];
		stock_version: string;
		confirmation: { items: { name: string; amount_grams: number }[] };
	}

	let { plan }: { plan: Plan } = $props();

	// 'stale' = server refused (409): stock changed, only a fresh preview can help.
	// 'error' = other failure: buttons stay so the user can retry.
	let status = $state<'pending' | 'saving' | 'done' | 'cancelled' | 'error' | 'stale'>('pending');
	let message = $state('');

	const replaceOnly = $derived(plan.remove.filter((r) => r.replace_only).length);
	const g = (n: number) => `${Math.round(n * 10) / 10} g`;
	const reasonText = { not_listed: 'only if replacing', zero: 'listed as 0 g', merged: 'merged into one row' };
	const rowDetail = (r: Plan['remove'][number]) => [r.crop_year, r.form].filter(Boolean).join(', ');

	async function apply(replace: boolean) {
		status = 'saving';
		try {
			const res = await authFetch('/api/inventory/hops/bulk', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					items: plan.confirmation.items,
					replace,
					dry_run: false,
					expected_stock_version: plan.stock_version
				})
			});
			if (res.status === 409) {
				status = 'stale';
				message = (await res.json()).detail;
				return;
			}
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			const r = await res.json();
			status = 'done';
			message = `Saved: ${r.add.length} added, ${r.update.length} updated, ${r.remove.length} removed.`;
		} catch (e) {
			status = 'error';
			message = `Could not save: ${e instanceof Error ? e.message : 'unknown error'}`;
		}
	}
</script>

<div class="card" role="group" aria-label="Confirm hop inventory update">
	<div class="title">Update hop inventory?</div>

	<ul class="changes">
		{#each plan.add as a}
			<li><span class="tag add">Add</span>{a.variety} <span class="num">{g(a.amount_grams)}</span>{#if !a.in_library}<span class="warn"> · not in library</span>{/if}{#if a.fuzzy_from?.length}<span class="warn"> · you typed “{a.fuzzy_from.join('”, “')}”</span>{/if}</li>
		{/each}
		{#each plan.update as u}
			<li><span class="tag upd">Update</span>{u.variety} <span class="num">{g(u.from_grams)} → {g(u.to_grams)}</span>{#if u.fuzzy_from?.length}<span class="warn"> · you typed “{u.fuzzy_from.join('”, “')}”</span>{/if}{#if u.guessed_as}<span class="warn"> · guessed to be {u.guessed_as}</span>{/if}</li>
		{/each}
		{#each plan.remove as r}
			<li class="removal"><span class="tag del">Remove</span>{r.variety}{#if rowDetail(r)}<span class="muted"> ({rowDetail(r)})</span>{/if} <span class="num">{g(r.amount_grams)}</span><span class="muted"> · {reasonText[r.reason] ?? (r.replace_only ? reasonText.not_listed : reasonText.zero)}</span>{#if r.guessed_as}<span class="warn"> · guessed to be {r.guessed_as}</span>{/if}</li>
		{/each}
	</ul>
	{#if plan.add.length}
		<p class="muted">New hops get a typical alpha acid from the hop library. Set your packet value on the Inventory page if it differs.</p>
	{/if}
	{#if plan.unchanged.length}
		<p class="muted">No change: {plan.unchanged.map((u) => u.variety).join(', ')}</p>
	{/if}

	{#if status === 'error'}
		<p class="error">{message}</p>
	{/if}
	{#if status === 'pending' || status === 'error'}
		<p class="question">Replace all your existing hops with this list?</p>
		<div class="actions">
			<button class="primary" onclick={() => apply(true)}>
				Yes, replace all{plan.remove.length ? ` (removes ${plan.remove.length})` : ''}
			</button>
			<button onclick={() => apply(false)}>
				No, add & update only{plan.remove.length - replaceOnly ? ` (removes ${plan.remove.length - replaceOnly})` : ''}
			</button>
			<button class="ghost" onclick={() => (status = 'cancelled')}>Cancel</button>
		</div>
	{:else if status === 'saving'}
		<p class="muted">Saving…</p>
	{:else if status === 'cancelled'}
		<p class="muted">Cancelled. Nothing was changed.</p>
	{:else}
		<p class={status === 'stale' ? 'error' : 'ok'}>{message}</p>
	{/if}
</div>

<style>
	.card {
		margin: 0 0 var(--space-4) 48px;
		padding: var(--space-3) var(--space-4);
		border: 1px solid var(--border-subtle);
		border-radius: 12px;
		background: var(--bg-surface);
		color: var(--text-primary);
		max-width: 640px;
	}
	.title {
		font-weight: 600;
		margin-bottom: var(--space-2);
	}
	.changes {
		list-style: none;
		margin: 0;
		padding: 0;
		font-size: 0.9em;
	}
	.changes li {
		padding: 2px 0;
	}
	.tag {
		display: inline-block;
		min-width: 4.5em;
		font-family: var(--font-mono);
		font-size: 0.8em;
		text-transform: uppercase;
	}
	.add { color: var(--positive); }
	.upd { color: var(--accent); }
	.del { color: var(--negative); }
	.num {
		font-family: var(--font-mono);
		color: var(--text-secondary);
	}
	.muted { color: var(--text-muted); font-size: 0.85em; }
	.warn { color: var(--negative); font-size: 0.85em; }
	.question { margin: var(--space-3) 0 var(--space-2); }
	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
	}
	button {
		padding: var(--space-2) var(--space-3);
		border-radius: 8px;
		border: 1px solid var(--border-default);
		background: var(--bg-elevated);
		color: var(--text-primary);
		cursor: pointer;
		font: inherit;
		font-size: 0.9em;
	}
	button:hover { background: var(--bg-hover); }
	button.primary {
		background: var(--accent);
		border-color: var(--accent);
		color: var(--accent-ink);
	}
	button.primary:hover { background: var(--accent-hover); color: var(--accent-ink); }
	button.ghost { background: transparent; border-color: transparent; color: var(--text-muted); }
	.ok { color: var(--positive); }
	.error { color: var(--negative); }
</style>
