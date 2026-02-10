<script lang="ts">
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

	// Simple markdown formatting (inline subset)
	function formatMarkdown(text: string): string {
		if (!text) return '';

		let html = text
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;');

		// Code blocks
		html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code class="language-$1">$2</code></pre>');

		// Inline code
		html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

		// Headers
		html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>');
		html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>');
		html = html.replace(/^# (.+)$/gm, '<h2>$1</h2>');

		// Bold
		html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

		// Italic
		html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');

		// Unordered lists
		html = html.replace(/(?:^|\n)((?:- .+\n?)+)/g, (_match, listContent) => {
			const items = listContent.trim().split('\n')
				.map((line: string) => line.replace(/^- (.+)$/, '<li>$1</li>'))
				.join('');
			return '\n<ul>' + items + '</ul>\n';
		});

		// Ordered lists
		html = html.replace(/(?:^|\n)((?:\d+\. .+\n?)+)/g, (_match, listContent) => {
			const items = listContent.trim().split('\n')
				.map((line: string) => line.replace(/^\d+\. (.+)$/, '<li>$1</li>'))
				.join('');
			return '\n<ol>' + items + '</ol>\n';
		});

		// Line breaks (not after block elements)
		html = html.replace(/\n(?!<\/?(ul|ol|li|pre|h[1-6]))/g, '<br>');

		// Clean up extra breaks around block elements
		html = html.replace(/<br><(ul|ol|pre|h[1-6])/g, '<$1');
		html = html.replace(/<\/(ul|ol|pre|h[1-6])><br>/g, '</$1>');

		return html;
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
			{#each agent.messages as message (message.id)}
				<div class="tp-message {message.role}">
					{#if message.role === 'user'}
						<div class="tp-message-bubble tp-user-bubble">
							{message.content}
						</div>
					{:else if message.role === 'assistant' && agent.isStreaming && message.id === agent._agentState.streamingMessageId}
						<div class="tp-message-bubble tp-assistant-bubble streaming">
							{@html formatMarkdown(agent.streamingContent || '')}
							<span class="cursor"></span>
						</div>
					{:else}
						<div class="tp-message-bubble tp-assistant-bubble">
							{@html formatMarkdown(message.content)}
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
	/* Collapsed bar */
	.tasting-panel-collapsed {
		position: fixed;
		bottom: 16px;
		right: 16px;
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 10px 16px;
		background: var(--accent, #3b82f6);
		color: white;
		border: none;
		border-radius: 24px;
		cursor: pointer;
		font-size: 0.875rem;
		font-weight: 500;
		box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
		z-index: 1000;
		transition: background 0.15s ease, transform 0.15s ease;
	}

	.tasting-panel-collapsed:hover {
		background: var(--accent-hover, #2563eb);
		transform: translateY(-1px);
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
		opacity: 0.8;
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
		background: var(--bg-surface, #1a1a2e);
		border-left: 1px solid var(--border-subtle, #2a2a3e);
		box-shadow: -4px 0 24px rgba(0, 0, 0, 0.3);
		z-index: 1000;
		animation: slideIn 0.25s ease-out;
	}

	@keyframes slideIn {
		from {
			transform: translateX(100%);
		}
		to {
			transform: translateX(0);
		}
	}

	/* Mobile: full width */
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
		padding: 12px 16px;
		background: var(--bg-elevated, #16213e);
		border-bottom: 1px solid var(--border-subtle, #2a2a3e);
		flex-shrink: 0;
	}

	.header-title {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 0.9375rem;
		font-weight: 600;
		color: var(--text-primary, #e0e0e0);
	}

	.header-actions {
		display: flex;
		align-items: center;
		gap: 4px;
	}

	.header-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 30px;
		height: 30px;
		background: none;
		border: none;
		border-radius: 6px;
		color: var(--text-muted, #888);
		cursor: pointer;
		transition: background 0.15s ease, color 0.15s ease;
	}

	.header-btn:hover {
		background: rgba(255, 255, 255, 0.1);
		color: var(--text-primary, #e0e0e0);
	}

	/* Messages area */
	.tasting-panel-messages {
		flex: 1;
		overflow-y: auto;
		padding: 16px;
		display: flex;
		flex-direction: column;
		gap: 12px;
		min-height: 0;
	}

	/* Message container */
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

	/* Message bubbles */
	.tp-message-bubble {
		max-width: 85%;
		padding: 10px 14px;
		border-radius: 12px;
		font-size: 0.875rem;
		line-height: 1.55;
		word-wrap: break-word;
		overflow-wrap: break-word;
	}

	.tp-user-bubble {
		background: var(--accent-muted, rgba(59, 130, 246, 0.15));
		color: var(--text-primary, #e0e0e0);
		border-bottom-right-radius: 4px;
	}

	.tp-assistant-bubble {
		background: var(--bg-elevated, #16213e);
		color: var(--text-primary, #e0e0e0);
		border-bottom-left-radius: 4px;
	}

	/* Markdown styles inside assistant bubbles */
	.tp-assistant-bubble :global(strong) {
		font-weight: 600;
		color: var(--text-primary, #e0e0e0);
	}

	.tp-assistant-bubble :global(em) {
		font-style: italic;
	}

	.tp-assistant-bubble :global(code) {
		font-family: var(--font-mono, monospace);
		background: rgba(255, 255, 255, 0.08);
		padding: 1px 5px;
		border-radius: 3px;
		font-size: 0.85em;
	}

	.tp-assistant-bubble :global(pre) {
		background: rgba(0, 0, 0, 0.3);
		padding: 10px;
		border-radius: 6px;
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
		margin: 8px 0 4px;
		font-weight: 600;
		color: var(--text-primary, #e0e0e0);
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

	/* Streaming cursor */
	.streaming .cursor {
		display: inline-block;
		width: 2px;
		height: 1em;
		background: var(--text-primary, #e0e0e0);
		margin-left: 2px;
		animation: blink 1s infinite;
		vertical-align: text-bottom;
	}

	@keyframes blink {
		0%, 50% { opacity: 1; }
		51%, 100% { opacity: 0; }
	}

	/* Typing indicator */
	.typing-indicator {
		display: flex;
		gap: 4px;
		padding: 4px 0;
	}

	.typing-indicator span {
		width: 7px;
		height: 7px;
		background: var(--text-muted, #888);
		border-radius: 50%;
		animation: bounce 1.4s infinite ease-in-out both;
	}

	.typing-indicator span:nth-child(1) { animation-delay: -0.32s; }
	.typing-indicator span:nth-child(2) { animation-delay: -0.16s; }

	@keyframes bounce {
		0%, 80%, 100% { transform: scale(0); }
		40% { transform: scale(1); }
	}

	/* Error display */
	.tp-error {
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 8px 12px;
		margin: 0 12px;
		background: var(--error-bg, rgba(239, 68, 68, 0.1));
		border-radius: 6px;
		color: var(--negative, #ef4444);
		font-size: 0.8125rem;
		flex-shrink: 0;
	}

	.tp-error button {
		margin-left: auto;
		padding: 2px 8px;
		background: none;
		border: 1px solid currentColor;
		border-radius: 3px;
		color: inherit;
		cursor: pointer;
		font-size: 0.75rem;
	}

	/* Input area */
	.tasting-panel-input {
		padding: 12px 16px;
		border-top: 1px solid var(--border-subtle, #2a2a3e);
		background: var(--bg-surface, #1a1a2e);
		flex-shrink: 0;
	}

	.tp-input-wrapper {
		display: flex;
		gap: 8px;
		align-items: center;
		background: var(--bg-elevated, #16213e);
		border: 1px solid var(--border-subtle, #2a2a3e);
		border-radius: 10px;
		padding: 4px 4px 4px 12px;
	}

	.tp-input-wrapper:focus-within {
		border-color: var(--accent, #3b82f6);
	}

	.tp-input-wrapper input {
		flex: 1;
		padding: 6px 0;
		background: none;
		border: none;
		color: var(--text-primary, #e0e0e0);
		font-family: inherit;
		font-size: 0.875rem;
		line-height: 1.4;
		min-width: 0;
	}

	.tp-input-wrapper input:focus {
		outline: none;
	}

	.tp-input-wrapper input::placeholder {
		color: var(--text-muted, #888);
	}

	.tp-input-wrapper input:disabled {
		opacity: 0.6;
	}

	.tp-send-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 32px;
		height: 32px;
		background: var(--accent, #3b82f6);
		border: none;
		border-radius: 8px;
		color: white;
		cursor: pointer;
		flex-shrink: 0;
		transition: background 0.15s ease;
	}

	.tp-send-btn:hover:not(:disabled) {
		background: var(--accent-hover, #2563eb);
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
