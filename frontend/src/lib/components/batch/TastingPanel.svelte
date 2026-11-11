<script lang="ts">
	import { renderMarkdown } from '$lib/markdown';
	import { useAgent } from '$lib/ag-ui';
	import type { Message } from '$lib/ag-ui/types';
	import type { BatchResponse } from '$lib/api';
	import { getAccessToken } from '$lib/supabase';
	import { config } from '$lib/config';

	interface Props {
		batch: BatchResponse;
		onClose: () => void;
		onSaved: () => void;
	}

	let { batch, onClose, onSaved }: Props = $props();

	// Panel state
	let minimized = $state(false);
	let input = $state('');
	let inputRef = $state<HTMLInputElement | null>(null);
	let messagesContainer = $state<HTMLElement | null>(null);
	let started = $state(false);

	// Async function to get auth headers (same pattern as assistant page)
	async function getAuthHeaders(): Promise<Record<string, string>> {
		if (config.authEnabled) {
			const token = await getAccessToken();
			if (token) {
				return { 'Authorization': `Bearer ${token}` };
			}
		}
		return {};
	}

	// Initialize AG-UI agent
	const agent = useAgent({
		url: '/api/ag-ui/run',
		headers: getAuthHeaders,
		initialState: {},
		onStateChange: (state) => {
			// Check if tasting note was saved
			if (state.tastingNoteSaved) {
				onSaved();
			}
		},
		onError: (error) => {
			console.error('Tasting agent error:', error);
		}
	});

	// Auto-scroll when messages update
	$effect(() => {
		// Track message count and streaming content
		const _ = agent.messages.length;
		const __ = agent.streamingContent;

		if (messagesContainer) {
			requestAnimationFrame(() => {
				messagesContainer?.scrollTo({
					top: messagesContainer.scrollHeight,
					behavior: 'smooth'
				});
			});
		}
	});

	// Auto-start the guided tasting session on mount
	$effect(() => {
		if (!started) {
			started = true;
			const prompt = `Start a guided tasting session for batch ${batch.id} (${batch.name}). Walk me through a BJCP-style evaluation using scoring_version 2. Use the start_tasting_session tool first to get the batch context and style guidelines, then guide me through each category (Aroma, Appearance, Flavor, Mouthfeel, Overall). At the end, summarize scores and use save_tasting_note with scoring_version=2 to save.`;
			agent.send(prompt);
		}
	});

	// Send a user message
	async function handleSend() {
		const content = input.trim();
		if (!content || agent.isRunning) return;
		input = '';
		await agent.send(content);
	}

	// Handle Enter to send
	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			handleSend();
		}
	}

</script>

{#if minimized}
	<!-- Collapsed bar -->
	<button
		type="button"
		class="tasting-panel-collapsed"
		onclick={() => { minimized = false; }}
	>
		<span class="collapsed-icon">
			<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
				<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
			</svg>
		</span>
		<span class="collapsed-text">Guided Tasting in progress...</span>
		<span class="collapsed-expand">
			<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
				<path d="M18 15l-6-6-6 6"/>
			</svg>
		</span>
	</button>
{:else}
	<!-- Full panel -->
	<div class="tasting-panel">
		<!-- Header -->
		<header class="tasting-panel-header">
			<div class="header-title">
				<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
				</svg>
				<span>Guided Tasting</span>
			</div>
			<div class="header-actions">
				<button
					type="button"
					class="header-btn"
					onclick={() => { minimized = true; }}
					title="Minimize"
				>
					<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path d="M6 15l6-6 6 6"/>
					</svg>
				</button>
				<button
					type="button"
					class="header-btn"
					onclick={onClose}
					title="Close"
				>
					<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path d="M18 6L6 18M6 6l12 12"/>
					</svg>
				</button>
			</div>
		</header>

		<!-- Messages area -->
		<div class="tasting-panel-messages" bind:this={messagesContainer}>
			{#each agent.messages.slice(1) as message (message.id)}
				<div class="tp-message {message.role}">
					{#if message.role === 'user'}
						<div class="tp-message-bubble tp-user-bubble">
							{message.content}
						</div>
					{:else if message.role === 'assistant' && agent.isStreaming && message.id === agent._agentState.streamingMessageId}
						<div class="tp-message-bubble tp-assistant-bubble streaming">
							{@html renderMarkdown(agent.streamingContent || '')}
							<span class="cursor"></span>
						</div>
					{:else}
						<div class="tp-message-bubble tp-assistant-bubble">
							{@html renderMarkdown(message.content)}
						</div>
					{/if}
				</div>
			{/each}

			{#if agent.isRunning && !agent.isStreaming}
				<div class="tp-message assistant">
					<div class="tp-message-bubble tp-assistant-bubble">
						<div class="typing-indicator">
							<span></span><span></span><span></span>
						</div>
					</div>
				</div>
			{/if}
		</div>

		<!-- Error display -->
		{#if agent.error}
			<div class="tp-error">
				<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
					<path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
				</svg>
				<span>{agent.error}</span>
				<button type="button" onclick={() => agent._agentState.clearError()}>Dismiss</button>
			</div>
		{/if}

		<!-- Input area -->
		<footer class="tasting-panel-input">
			<div class="tp-input-wrapper">
				<input
					bind:this={inputRef}
					bind:value={input}
					type="text"
					placeholder="Describe what you taste..."
					onkeydown={handleKeydown}
					disabled={agent.isRunning}
				/>
				<button
					type="button"
					class="tp-send-btn"
					onclick={handleSend}
					disabled={!input.trim() || agent.isRunning}
				>
					{#if agent.isRunning}
						<svg class="spinner" width="18" height="18" viewBox="0 0 24 24">
							<circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" fill="none" stroke-dasharray="31.4" stroke-dashoffset="10"/>
						</svg>
					{:else}
						<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
							<path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/>
						</svg>
					{/if}
				</button>
			</div>
		</footer>
	</div>
{/if}

<style>
	button:focus-visible,
	.tp-input-wrapper input:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	/* Collapsed bar */
	.tasting-panel-collapsed {
		position: fixed;
		bottom: 16px;
		right: 16px;
		display: flex;
		align-items: center;
		gap: var(--space-xs);
		min-height: 44px;
		padding: 0 var(--space-md);
		background: var(--accent);
		color: var(--accent-ink);
		border: 1px solid var(--accent);
		border-radius: 4px;
		cursor: pointer;
		font-size: var(--text-sm);
		font-weight: 700;
		z-index: 1000;
	}

	.tasting-panel-collapsed:hover {
		background: var(--accent-hover);
		border-color: var(--accent-hover);
	}

	.collapsed-icon {
		display: flex;
		align-items: center;
	}

	.collapsed-text {
		white-space: nowrap;
	}

	.collapsed-expand {
		display: flex;
		align-items: center;
	}

	/* Full panel */
	.tasting-panel {
		position: fixed;
		top: 0;
		right: 0;
		bottom: 0;
		width: 400px;
		display: flex;
		flex-direction: column;
		background: var(--bg-surface);
		border-left: 1px solid var(--rule-strong);
		z-index: 1000;
		animation: slideIn 0.25s var(--ease-out-quart);
	}

	@keyframes slideIn {
		from {
			transform: translateX(100%);
		}
		to {
			transform: translateX(0);
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.tasting-panel {
			animation: none;
		}
	}

	/* Phone: float above the bottom tab bar (--tabbar-h from +layout.svelte) */
	@media (max-width: 760px) {
		.tasting-panel-collapsed {
			bottom: calc(var(--tabbar-h, 0px) + 16px + env(safe-area-inset-bottom, 0px));
		}
	}

	@media (max-width: 767px) {
		.tasting-panel {
			width: 100%;
		}
	}

	/* Header */
	.tasting-panel-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: var(--space-xs) var(--space-md);
		border-bottom: 1px solid var(--rule-hairline);
		flex-shrink: 0;
	}

	.header-title {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--ink-secondary);
	}

	.header-actions {
		display: flex;
		align-items: center;
		gap: var(--space-2xs);
	}

	.header-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 44px;
		height: 44px;
		background: none;
		border: none;
		border-radius: 4px;
		color: var(--ink-muted);
		cursor: pointer;
	}

	.header-btn:hover {
		background: var(--bg-subtle);
		color: var(--ink-primary);
	}

	/* Messages */
	.tasting-panel-messages {
		flex: 1;
		overflow-y: auto;
		padding: var(--space-md);
		display: flex;
		flex-direction: column;
		gap: var(--space-sm);
		min-height: 0;
	}

	.tp-message {
		display: flex;
		flex-direction: column;
	}

	.tp-message.user {
		align-items: flex-end;
	}

	.tp-message.assistant {
		align-items: flex-start;
	}

	.tp-message-bubble {
		max-width: 88%;
		padding: var(--space-xs) var(--space-sm);
		border-radius: 4px;
		font-size: var(--text-sm);
		line-height: 1.55;
		word-wrap: break-word;
		overflow-wrap: break-word;
	}

	.tp-user-bubble {
		background: var(--accent-tint);
		border: 1px solid var(--accent-rule);
		color: var(--ink-primary);
	}

	.tp-assistant-bubble {
		background: var(--bg-elevated);
		border: 1px solid var(--rule-hairline);
		color: var(--ink-primary);
	}

	.tp-assistant-bubble :global(strong) {
		font-weight: 700;
		color: var(--ink-primary);
	}

	.tp-assistant-bubble :global(em) {
		font-style: italic;
	}

	.tp-assistant-bubble :global(code) {
		font-family: var(--font-num);
		background: var(--bg-subtle);
		padding: 1px 5px;
		border-radius: 3px;
		font-size: 0.85em;
	}

	.tp-assistant-bubble :global(pre) {
		background: var(--bg-canvas);
		border: 1px solid var(--rule-hairline);
		padding: var(--space-xs);
		border-radius: 4px;
		overflow-x: auto;
		margin: 6px 0;
	}

	.tp-assistant-bubble :global(pre code) {
		background: none;
		padding: 0;
	}

	.tp-assistant-bubble :global(h2),
	.tp-assistant-bubble :global(h3),
	.tp-assistant-bubble :global(h4) {
		margin: var(--space-xs) 0 var(--space-2xs);
		font-family: var(--font-display);
		font-weight: 600;
		color: var(--ink-primary);
		line-height: 1.3;
	}

	.tp-assistant-bubble :global(h2) { font-size: 1.1rem; }
	.tp-assistant-bubble :global(h3) { font-size: 1rem; }
	.tp-assistant-bubble :global(h4) { font-size: 0.9375rem; }

	.tp-assistant-bubble :global(h2:first-child),
	.tp-assistant-bubble :global(h3:first-child),
	.tp-assistant-bubble :global(h4:first-child) {
		margin-top: 0;
	}

	.tp-assistant-bubble :global(ul),
	.tp-assistant-bubble :global(ol) {
		margin: 6px 0;
		padding-left: 1.25rem;
	}

	.tp-assistant-bubble :global(li) {
		margin: 3px 0;
		line-height: 1.45;
	}

	.streaming .cursor {
		display: inline-block;
		width: 2px;
		height: 1em;
		background: var(--ink-primary);
		margin-left: 2px;
		animation: blink 1s infinite;
		vertical-align: text-bottom;
	}

	@keyframes blink {
		0%, 50% { opacity: 1; }
		51%, 100% { opacity: 0; }
	}

	/* Typing indicator: opacity pulse */
	.typing-indicator {
		display: flex;
		gap: var(--space-2xs);
		padding: var(--space-2xs) 0;
	}

	.typing-indicator span {
		width: 6px;
		height: 6px;
		background: var(--ink-muted);
		border-radius: 50%;
		animation: pulse 1.4s infinite ease-in-out both;
	}

	.typing-indicator span:nth-child(1) { animation-delay: -0.32s; }
	.typing-indicator span:nth-child(2) { animation-delay: -0.16s; }

	@keyframes pulse {
		0%, 80%, 100% { opacity: 0.25; }
		40% { opacity: 1; }
	}

	/* Error */
	.tp-error {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
		padding: var(--space-xs) var(--space-sm);
		margin: 0 var(--space-sm);
		border: 1px solid var(--negative);
		border-radius: 4px;
		color: var(--negative);
		font-size: var(--text-sm);
		flex-shrink: 0;
	}

	.tp-error button {
		margin-left: auto;
		min-height: 44px;
		padding: 0 var(--space-sm);
		background: none;
		border: 1px solid currentColor;
		border-radius: 4px;
		color: inherit;
		cursor: pointer;
		font-size: var(--text-xs);
	}

	/* Input */
	.tasting-panel-input {
		padding: var(--space-sm) var(--space-md);
		border-top: 1px solid var(--rule-hairline);
		background: var(--bg-surface);
		flex-shrink: 0;
	}

	.tp-input-wrapper {
		display: flex;
		gap: var(--space-xs);
		align-items: center;
		background: var(--bg-canvas);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		padding: var(--space-2xs) var(--space-2xs) var(--space-2xs) var(--space-sm);
	}

	.tp-input-wrapper:focus-within {
		border-color: var(--accent);
	}

	.tp-input-wrapper input {
		flex: 1;
		min-height: 36px;
		background: none;
		border: none;
		color: var(--ink-primary);
		font-family: inherit;
		font-size: var(--text-sm);
		line-height: 1.4;
		min-width: 0;
	}

	.tp-input-wrapper input:focus,
	.tp-input-wrapper input:focus-visible {
		outline: none;
	}

	.tp-input-wrapper input::placeholder {
		color: var(--ink-muted);
	}

	.tp-input-wrapper input:disabled {
		opacity: 0.6;
	}

	.tp-send-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 44px;
		height: 44px;
		background: var(--accent);
		border: none;
		border-radius: 4px;
		color: var(--accent-ink);
		cursor: pointer;
		flex-shrink: 0;
	}

	.tp-send-btn:hover:not(:disabled) {
		background: var(--accent-hover);
	}

	.tp-send-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.spinner {
		animation: spin 1s linear infinite;
	}

	@keyframes spin {
		from { transform: rotate(0deg); }
		to { transform: rotate(360deg); }
	}
</style>
