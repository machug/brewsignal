<script lang="ts">
	// Approval for a link the assistant composed itself (tilt_ui-eevz.10). Opening a
	// link sends the address to that site, so a hostile page could make the model
	// glue private data onto one. The full address is shown before anything is fetched.
	import type { ToolPart } from '$lib/chat/logic';

	interface Props {
		part: ToolPart;
		error?: string;
		onApprove: (approvalId: string) => void;
		onCancel: (approvalId: string) => void;
	}
	let { part, error = '', onApprove, onCancel }: Props = $props();

	const url = $derived(String(part.input?.url ?? '').trim()); // never let padding hide the address
	// The address exactly as written up to the first / ? #, not the browser's URL parser:
	// parsers disagree on tricks like "byo.com\\@attacker.example" (Gemini).
	const host = $derived(url.replace(/^[a-z][a-z0-9+.-]*:\/\//i, '').split(/[/?#]/)[0]);
	const approvalId = $derived(part.approval?.id ?? '');
	// A fetch that ran but failed (blocked, timed out, HTTP error) comes back as an {error} output
	const failure = $derived(
		error ||
			(part.state === 'output-error' ? part.errorText || 'The link could not be opened.' : '') ||
			(part.state === 'output-available' && part.output?.error ? String(part.output.error) : '')
	);
	const phase = $derived(
		failure
			? 'failed'
			: part.state === 'approval-requested'
				? 'asking'
				: part.state === 'output-denied'
					? 'denied'
					: part.state === 'output-available'
						? 'done'
						: 'opening'
	);
	const badge = $derived({ asking: 'Asking', opening: 'Opening', done: 'Opened', denied: 'Not opened', failed: 'Failed' }[phase]);
</script>

<section class="card" aria-label="Open a link?">
	<header>
		<h3>Open this link?</h3>
		<span class="badge {phase}" role="status" aria-live="polite">{badge}</span>
	</header>
	<p class="why">The assistant made up this address itself; it did not come from you or from a page it read. Opening it sends the whole address to {host || 'that site'}.</p>
	<p class="url">{#if host}<span class="host">{host}</span><br />{/if}<span class="full">{url}</span></p>
	{#if phase === 'failed'}
		<p class="alert" role="alert">{failure}</p>
	{:else if phase === 'asking'}
		<div class="actions">
			<button type="button" class="primary" onclick={() => onApprove(approvalId)}>Open link</button>
			<button type="button" onclick={() => onCancel(approvalId)}>Don't open</button>
		</div>
	{/if}
</section>

<style>
	.card { max-width: 640px; margin: var(--space-sm) 0; padding: var(--space-md); background: var(--bg-surface); border: 1px solid var(--rule-strong); }
	header { display: flex; align-items: center; justify-content: space-between; gap: var(--space-sm); margin-bottom: var(--space-xs); }
	h3 { margin: 0; font-family: var(--font-display); font-size: var(--text-base); font-weight: 600; color: var(--ink-primary); }
	.badge {
		font-family: var(--font-num); font-size: 0.8125rem; text-transform: uppercase; letter-spacing: 0.05em;
		padding: 1px 8px; border: 1px solid var(--rule-strong); color: var(--ink-secondary); white-space: nowrap;
	}
	.badge.asking { border-color: var(--accent-rule); color: var(--accent); }
	.badge.failed { border-color: var(--status-danger); color: var(--status-danger); }
	.why { margin: 0 0 var(--space-sm); font-size: var(--text-sm); color: var(--ink-secondary); }
	.url { margin: 0 0 var(--space-sm); padding: var(--space-sm); max-height: 10rem; overflow-y: auto; background: var(--bg-elevated); border: 1px solid var(--rule-hairline); overflow-wrap: anywhere; }
	.host { font-family: var(--font-display); font-weight: 600; color: var(--ink-primary); }
	.full { font-family: var(--font-num); font-size: var(--text-sm); color: var(--ink-secondary); }
	.alert { margin: var(--space-xs) 0; padding: var(--space-sm); font-size: var(--text-sm); color: var(--ink-primary); background: var(--error-bg); border: 1px solid color-mix(in oklch, var(--status-danger) 45%, transparent); }
	.actions { display: flex; flex-wrap: wrap; gap: var(--space-sm); }
	button { min-height: 44px; padding: 0 var(--space-md); font: inherit; font-size: var(--text-sm); color: var(--ink-primary); background: transparent; border: 1px solid var(--rule-strong); cursor: pointer; }
	button:hover { background: var(--bg-subtle); }
	button.primary { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); font-weight: 700; }
	button.primary:hover { background: var(--accent-hover); }
	button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
</style>
