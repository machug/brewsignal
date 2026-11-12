<script lang="ts">
	// API key field that never holds the stored key (tilt_ui-eevz.3). The server
	// returns "****" + last 4; this shows that as text with Replace / Remove,
	// and `value` stays null (= keep the saved key) until the user types or removes.
	interface Props {
		id: string;
		label: string;
		/** Masked key from GET /api/config ("" when none is saved). */
		saved: string;
		/** null = unchanged, "" = remove, otherwise the new key. */
		value: string | null;
		placeholder?: string;
		hint?: string;
	}
	let { id, label, saved, value = $bindable(null), placeholder = '', hint = '' }: Props = $props();

	let mode = $state<'saved' | 'editing' | 'removed'>('saved');
	let typed = $state('');

	// After a save the parent resets value to null. While removing or with text typed,
	// value can only be null if the parent reset it: show the (new) saved key again.
	$effect(() => {
		if (value === null && (mode === 'removed' || typed.trim() !== '')) {
			typed = '';
			mode = 'saved';
		}
	});

	function startReplace() {
		typed = '';
		mode = 'editing';
	}
	function remove() {
		value = '';
		mode = 'removed';
	}
	function undo() {
		value = null;
		typed = '';
		mode = 'saved';
	}
	function onInput() {
		const t = typed.trim();
		value = t ? t : null;
	}
</script>

<div class="form-field full">
	<label for={id}>{label}</label>
	{#if saved && mode === 'saved'}
		<div class="saved">
			<span class="mono">Saved key {saved}</span>
			<button type="button" onclick={startReplace}>Replace</button>
			<button type="button" class="ghost" onclick={remove}>Remove</button>
		</div>
	{:else if mode === 'removed'}
		<div class="saved">
			<span>The key will be removed when you save.</span>
			<button type="button" onclick={undo}>Undo</button>
		</div>
	{:else}
		<div class="saved">
			<input {id} type="password" autocomplete="new-password" spellcheck="false" bind:value={typed} oninput={onInput} {placeholder} />
			{#if saved}<button type="button" class="ghost" onclick={undo}>Keep saved key</button>{/if}
		</div>
	{/if}
	{#if hint}<span class="field-hint">{hint}</span>{/if}
</div>

<style>
	.saved { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-sm); }
	.saved input { flex: 1 1 14rem; min-width: 0; }
	.mono { font-family: var(--font-num); font-size: var(--text-sm); color: var(--ink-primary); }
	.saved span { font-size: var(--text-sm); color: var(--ink-secondary); }
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
	button.ghost { border-color: var(--rule-hairline); color: var(--ink-secondary); }
	button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
</style>
