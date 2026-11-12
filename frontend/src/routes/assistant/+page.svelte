<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { page } from '$app/state';
	import { goto, replaceState } from '$app/navigation';
	import { Chat } from '@ai-sdk/svelte';
	import { DefaultChatTransport, lastAssistantMessageIsCompleteWithApprovalResponses, type UIMessage } from 'ai';
	import { authFetch, fetchBatch, type BatchResponse } from '$lib/api';
	import { getAccessToken } from '$lib/supabase';
	import { config } from '$lib/config';
	import { configState } from '$lib/stores/config.svelte';
	import { APPLY_TOOL, APPROVAL_TOOLS, buildChatRequest, isToolPart, newChatId, toolName, type ToolPart } from '$lib/chat/logic';
	import ChatShell from '$lib/components/chat/ChatShell.svelte';
	import ChatComposer from '$lib/components/chat/ChatComposer.svelte';
	import MessageTurn from '$lib/components/chat/MessageTurn.svelte';
	import ThreadDrawer, { type ThreadItem } from '$lib/components/chat/ThreadDrawer.svelte';

	// Redirect if AI is not enabled
	$effect(() => {
		if (configState.loaded && !configState.config.ai_enabled) goto('/');
	});

	const PROMPTS = [
		'Audit the hop schedule of my latest recipe',
		'Update my hop inventory: ',
		'Build a recipe from the stock I have',
		'Troubleshoot my active fermentation'
	];
	const STEER_KEEP = 'Apply those hop changes without removing my other hops.';

	async function getAuthHeaders(): Promise<Record<string, string>> {
		if (config.authEnabled) {
			const token = await getAccessToken();
			if (token) return { Authorization: `Bearer ${token}` };
		}
		return {};
	}

	let chat = $state<Chat | null>(null);
	let chatId = $state('');
	// 'error' blocks sending: the saved transcript could not be read, so a send would overwrite it.
	let loadState = $state<'loading' | 'ready' | 'error'>('loading');
	let loadToken = 0;
	let threads = $state<ThreadItem[]>([]);
	let loadingThreads = $state(false);
	let drawerOpen = $state(false);
	let input = $state('');
	let inputEl = $state<HTMLTextAreaElement | null>(null);
	let follow = $state(true);
	let pendingSteer = $state('');

	// Live batch context (?batch=<id>), toggleable chip above the composer.
	let batch = $state<BatchResponse | null>(null);
	let useContext = $state(true);
	const chatContext = $derived(batch && useContext ? { batch_id: batch.id } : null);

	function makeChat(id: string, messages: UIMessage[]) {
		return new Chat({
			id,
			messages,
			transport: new DefaultChatTransport({
				api: '/api/chat',
				headers: getAuthHeaders,
				prepareSendMessagesRequest: ({ id, messages, trigger }) => ({
					body: buildChatRequest({ id, messages, trigger, context: chatContext })
				})
			}),
			sendAutomaticallyWhen: lastAssistantMessageIsCompleteWithApprovalResponses,
			onFinish: () => fetchThreads()
		});
	}

	function setUrlChat(id: string) {
		const url = new URL(page.url);
		url.searchParams.set('chat', id);
		url.searchParams.delete('q');
		url.searchParams.delete('batch');
		try {
			replaceState(url, {});
		} catch {
			/* router not ready */
		}
	}

	function startNew() {
		chat?.stop();
		loadToken++;
		chatId = newChatId();
		chat = makeChat(chatId, []);
		loadState = 'ready';
		pendingSteer = '';
		drawerOpen = false;
		setUrlChat(chatId);
		focusInput();
	}

	// No autofocus on touch screens: it pops the keyboard and lights the composer.
	function focusInput() {
		if (matchMedia('(pointer: coarse)').matches) return;
		tick().then(() => inputEl?.focus());
	}

	async function openThread(id: string) {
		chat?.stop();
		const token = ++loadToken;
		loadState = 'loading';
		chatId = id;
		chat = null;
		drawerOpen = false;
		pendingSteer = '';
		try {
			const res = await authFetch(`/api/chat/threads/${encodeURIComponent(id)}`);
			if (token !== loadToken) return;
			if (res.status === 404) {
				// Missing (or not ours): never reuse the id, start clean under a new one.
				startNew();
				return;
			}
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			const data = await res.json();
			if (token !== loadToken) return;
			chat = makeChat(id, data.messages ?? []);
			loadState = 'ready';
			setUrlChat(id);
			follow = true;
		} catch {
			if (token === loadToken) loadState = 'error';
		}
	}

	async function fetchThreads() {
		loadingThreads = true;
		try {
			const res = await authFetch('/api/chat/threads');
			if (res.ok) threads = await res.json();
		} catch {
			/* list is optional */
		} finally {
			loadingThreads = false;
		}
	}

	async function renameThread(id: string, title: string) {
		const res = await authFetch(`/api/chat/threads/${encodeURIComponent(id)}`, {
			method: 'PATCH',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ title })
		});
		if (res.ok) {
			const t = await res.json();
			threads = threads.map((x) => (x.id === id ? { ...x, title: t.title ?? title } : x));
		}
	}

	async function deleteThread(id: string) {
		if (!confirm('Delete this chat?')) return;
		const res = await authFetch(`/api/chat/threads/${encodeURIComponent(id)}`, { method: 'DELETE' });
		if (res.ok || res.status === 404) {
			threads = threads.filter((t) => t.id !== id);
			if (id === chatId) startNew();
		}
	}

	onMount(() => {
		const params = page.url.searchParams;
		const q = params.get('q');
		if (q) input = q;
		const b = Number(params.get('batch'));
		if (b > 0) fetchBatch(b).then((r) => (batch = r)).catch(() => {});
		fetchThreads();
		const id = params.get('chat');
		if (id) openThread(id);
		else startNew();
	});

	const busy = $derived(chat?.status === 'submitted' || chat?.status === 'streaming');
	const messages = $derived(chat?.messages ?? []);
	const lastAssistant = $derived(messages.findLast((m) => m.role === 'assistant'));
	const model = $derived(((lastAssistant?.metadata as any)?.model as string) || '');
	const title = $derived(threads.find((t) => t.id === chatId)?.title || 'Assistant');
	// A rejected approval answers HTTP 400 {"detail"} before any stream: show it on the card, not as a stream error.
	const approvalPending = $derived(
		!!lastAssistant?.parts.some((p) => isToolPart(p) && (p as unknown as ToolPart).state === 'approval-responded')
	);
	const approvalError = $derived.by(() => {
		if (!chat?.error || !approvalPending) return '';
		try {
			const d = JSON.parse(chat.error.message)?.detail;
			if (typeof d === 'string') return d;
		} catch {
			/* not JSON */
		}
		return 'The approval was rejected. It may have been used already.';
	});
	const awaitingApproval = $derived(
		!!lastAssistant?.parts.some((p) => isToolPart(p) && APPROVAL_TOOLS.has(toolName(p)) && (p as unknown as ToolPart).state === 'approval-requested')
	);
	const composerOff = $derived(!chat || loadState !== 'ready' || awaitingApproval);
	const placeholder = $derived(awaitingApproval ? 'Approve or cancel the proposal above' : loadState === 'error' ? 'Chat locked: could not load it' : undefined);

	function send() {
		const text = input.trim();
		if (!text || busy || composerOff || !chat) return;
		input = '';
		follow = true;
		chat.sendMessage({ text }).then(fetchThreads);
	}

	const approve = (id: string) => chat?.addToolApprovalResponse({ id, approved: true });
	const cancel = (id: string) => chat?.addToolApprovalResponse({ id, approved: false, reason: 'Cancelled by user' });
	function keepUnlisted(id: string) {
		pendingSteer = STEER_KEEP;
		chat?.addToolApprovalResponse({ id, approved: false, reason: 'User wants unlisted hops kept' });
	}
	// Send the steering message only after the denial round trip finished (no tool awaiting a result).
	$effect(() => {
		if (!pendingSteer || !chat || chat.status !== 'ready') return;
		const waiting = chat.messages.some((m) => m.parts.some((p) => isToolPart(p) && (p as unknown as ToolPart).state === 'approval-responded'));
		if (waiting) return;
		const text = pendingSteer;
		pendingSteer = '';
		chat.sendMessage({ text });
	});

	const retryApply = () => {
		if (!busy && !composerOff && chat) chat.sendMessage({ text: 'Prepare that hop inventory update again.' });
	};

	function usePrompt(p: string) {
		input = p;
		tick().then(() => {
			inputEl?.focus();
			inputEl?.setSelectionRange(p.length, p.length);
		});
	}
</script>

<svelte:head><title>Assistant | BrewSignal</title></svelte:head>

<ChatShell {title} {model} onToggleDrawer={() => (drawerOpen = !drawerOpen)} onNew={startNew} bind:follow>
	{#snippet drawer()}
		<ThreadDrawer
			open={drawerOpen}
			{threads}
			activeId={chatId}
			loading={loadingThreads}
			onSelect={openThread}
			onNew={startNew}
			onRename={renameThread}
			onDelete={deleteThread}
			onClose={() => (drawerOpen = false)}
		/>
	{/snippet}

	{#if loadState === 'error'}
		<div class="callout" role="alert">
			<p>Could not load this chat. Sending is turned off so the saved conversation is not overwritten.</p>
			<div class="row">
				<button type="button" onclick={() => openThread(chatId)}>Retry</button>
				<button type="button" onclick={startNew}>Start a new chat</button>
			</div>
		</div>
	{:else if loadState === 'loading'}
		<p class="quiet">Loading chat…</p>
	{:else if messages.length === 0}
		<div class="empty">
			<h2>What are we brewing?</h2>
			<ul class="prompts">
				{#each PROMPTS as p}
					<li><button type="button" onclick={() => usePrompt(p)}>{p.trim().replace(/:$/, '')}</button></li>
				{/each}
			</ul>
		</div>
	{:else}
		{#each messages as m (m.id)}
			<MessageTurn message={m} approvalError={m.id === lastAssistant?.id ? approvalError : ''} onApprove={approve} onCancel={cancel} onKeepUnlisted={keepUnlisted} onRetry={retryApply} retryDisabled={busy || composerOff} />
		{/each}
		{#if chat?.status === 'submitted'}
			<p class="quiet working"><span class="dot" aria-hidden="true"></span>Thinking…</p>
		{/if}
	{/if}

	{#if chat?.error && !approvalError}
		<div class="callout" role="alert">
			<p>The assistant hit an error. Try again.</p>
			<div class="row"><button type="button" onclick={() => chat?.regenerate()}>Retry</button></div>
		</div>
	{/if}

	{#snippet footer()}
		<ChatComposer bind:value={input} bind:inputEl {busy} disabled={composerOff} {placeholder} onSend={send} onStop={() => chat?.stop()}>
			{#snippet context()}
				{#if batch}
					<div class="ctx" class:off={!useContext}>
						<span class="ctx-label">Context</span>
						<span class="ctx-text">Batch #{batch.batch_number ?? batch.id}{batch.name ? ` · ${batch.name}` : ''} · {batch.status}</span>
						<button type="button" aria-pressed={useContext} onclick={() => (useContext = !useContext)}>{useContext ? 'Remove' : 'Add'}</button>
					</div>
				{/if}
			{/snippet}
		</ChatComposer>
	{/snippet}
</ChatShell>

<style>
	.quiet { margin: 0; font-size: var(--text-sm); color: var(--ink-secondary); }
	.working { display: flex; align-items: center; gap: var(--space-sm); }
	.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent); animation: pulse 1.2s ease-in-out infinite; }
	@keyframes pulse { 0%, 100% { opacity: 0.35; transform: scale(0.8); } 50% { opacity: 1; transform: scale(1.1); } }
	@media (prefers-reduced-motion: reduce) { .dot { animation: none; } }

	.empty { margin: auto 0; display: flex; flex-direction: column; gap: var(--space-md); }
	.empty h2 { margin: 0; word-spacing: 0.08em; font-family: var(--font-display); font-size: var(--text-lg); font-weight: 600; }
	.prompts { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-sm); }
	.prompts button {
		width: 100%; min-height: 56px; padding: var(--space-sm) var(--space-md); text-align: left; cursor: pointer;
		font: inherit; font-size: var(--text-sm); color: var(--ink-primary); background: transparent; border: 1px solid var(--rule-strong);
		transition: border-color 150ms var(--ease-out-quart, ease-out);
	}
	.prompts button:hover { border-color: var(--accent-rule); background: var(--bg-surface); }
	.prompts button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
	@media (max-width: 560px) { .prompts { grid-template-columns: 1fr; } }

	.callout { padding: var(--space-md); background: var(--error-bg); border: 1px solid color-mix(in oklch, var(--status-danger) 45%, transparent); color: var(--ink-primary); font-size: var(--text-sm); }
	.callout p { margin: 0 0 var(--space-sm); }
	.row { display: flex; flex-wrap: wrap; gap: var(--space-sm); }
	.callout button { min-height: 44px; padding: 0 var(--space-md); font: inherit; font-size: var(--text-sm); color: var(--ink-primary); background: transparent; border: 1px solid var(--rule-strong); cursor: pointer; }
	.callout button:hover { background: var(--bg-subtle); }

	.ctx { display: flex; align-items: center; gap: var(--space-sm); min-height: 44px; padding: 0 var(--space-sm); border: 1px solid var(--rule-hairline); background: var(--bg-elevated); font-size: 0.8125rem; color: var(--ink-secondary); }
	.ctx::before { content: ''; width: 6px; height: 6px; border-radius: 50%; background: var(--status-steady); flex: none; }
	.ctx.off { background: transparent; }
	.ctx.off::before { background: var(--ink-muted); }
	.ctx-label { font-family: var(--font-display); text-transform: uppercase; letter-spacing: 0.06em; color: var(--ink-secondary); }
	.ctx-text { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.ctx button { min-height: 44px; padding: 0 var(--space-sm); font: inherit; font-size: 0.8125rem; background: none; border: 0; color: var(--ink-secondary); text-decoration: underline; cursor: pointer; }
</style>
