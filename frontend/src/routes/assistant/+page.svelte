<script lang="ts">
	import { useAgent } from '$lib/ag-ui';
	import { onMount } from 'svelte';
	import type { Message } from '$lib/ag-ui/types';

	// Configuration
	let batchSize = $state(19);
	let efficiency = $state(72);

	// Initialize AG-UI agent
	const agent = useAgent({
		url: '/api/ag-ui/run',
		initialState: {
			batchSize,
			efficiency
		},
		onStateChange: (state) => {
			// Handle recipe extraction from agent
			if (state.recipe) {
				console.log('Recipe extracted:', state.recipe);
			}
		},
		onError: (error) => {
			console.error('Agent error:', error);
		}
	});

	// Input state
	let input = $state('');
	let inputRef = $state<HTMLTextAreaElement | null>(null);

	// Update agent state when settings change
	$effect(() => {
		agent.setState({ batchSize, efficiency });
	});

	// Auto-resize textarea
	function autoResize(textarea: HTMLTextAreaElement) {
		textarea.style.height = 'auto';
		textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
	}

	// Handle send
	async function handleSend() {
		const content = input.trim();
		if (!content || agent.isRunning) return;

		input = '';
		if (inputRef) {
			inputRef.style.height = 'auto';
		}

		await agent.send(content);
	}

	// Handle keyboard shortcuts
	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			handleSend();
		}
	}

	// Example prompts
	const examplePrompts = [
		'Help me create an American IPA recipe',
		'What temperature should I ferment a Belgian Tripel?',
		'Create a simple wheat beer recipe for summer',
		'Explain the difference between ale and lager yeast'
	];

	function usePrompt(prompt: string) {
		input = prompt;
		if (inputRef) {
			inputRef.focus();
			autoResize(inputRef);
		}
	}

	onMount(() => {
		inputRef?.focus();
	});
</script>

<svelte:head>
	<title>AI Assistant | BrewSignal</title>
</svelte:head>

<div class="assistant-page">
	<header class="page-header">
		<div class="header-content">
			<h1>Brewing Assistant</h1>
			<p class="subtitle">AI-powered recipe creation and brewing advice</p>
		</div>
		<div class="settings">
			<label class="setting">
				<span>Batch Size</span>
				<input type="number" bind:value={batchSize} min="1" max="100" /> L
			</label>
			<label class="setting">
				<span>Efficiency</span>
				<input type="number" bind:value={efficiency} min="50" max="100" /> %
			</label>
		</div>
	</header>

	<main class="chat-container">
		{#if agent.messages.length === 0}
			<!-- Empty state with example prompts -->
			<div class="empty-state">
				<div class="empty-icon">
					<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
						<path d="M12 2L2 7l10 5 10-5-10-5z"/>
						<path d="M2 17l10 5 10-5"/>
						<path d="M2 12l10 5 10-5"/>
					</svg>
				</div>
				<h2>Start a conversation</h2>
				<p>Ask me about beer recipes, brewing techniques, or ingredient substitutions.</p>
				<div class="example-prompts">
					{#each examplePrompts as prompt}
						<button type="button" class="prompt-chip" onclick={() => usePrompt(prompt)}>
							{prompt}
						</button>
					{/each}
				</div>
			</div>
		{:else}
			<!-- Message list -->
			<div class="messages">
				{#each agent.messages as message (message.id)}
					<div class="message {message.role}">
						<div class="message-avatar">
							{#if message.role === 'user'}
								<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
									<path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 3c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3zm0 14.2c-2.5 0-4.71-1.28-6-3.22.03-1.99 4-3.08 6-3.08 1.99 0 5.97 1.09 6 3.08-1.29 1.94-3.5 3.22-6 3.22z"/>
								</svg>
							{:else}
								<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
									<path d="M12 2L2 7l10 5 10-5-10-5z"/>
									<path d="M2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" stroke-width="2" fill="none"/>
								</svg>
							{/if}
						</div>
						<div class="message-content">
							{#if message.role === 'assistant' && agent.isStreaming && message.id === agent._agentState.streamingMessageId}
								<!-- Streaming message -->
								<div class="message-text streaming">
									{@html formatMarkdown(agent.streamingContent || '')}
									<span class="cursor"></span>
								</div>
							{:else}
								<div class="message-text">
									{@html formatMarkdown(message.content)}
								</div>
							{/if}
						</div>
					</div>
				{/each}

				{#if agent.isRunning && !agent.isStreaming}
					<!-- Loading indicator -->
					<div class="message assistant">
						<div class="message-avatar">
							<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
								<path d="M12 2L2 7l10 5 10-5-10-5z"/>
								<path d="M2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" stroke-width="2" fill="none"/>
							</svg>
						</div>
						<div class="message-content">
							<div class="typing-indicator">
								<span></span><span></span><span></span>
							</div>
						</div>
					</div>
				{/if}
			</div>
		{/if}

		{#if agent.error}
			<div class="error-banner">
				<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
					<path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
				</svg>
				<span>{agent.error}</span>
				<button type="button" onclick={() => agent._agentState.clearError()}>Dismiss</button>
			</div>
		{/if}
	</main>

	<footer class="input-area">
		<div class="input-wrapper">
			<textarea
				bind:this={inputRef}
				bind:value={input}
				placeholder="Ask about brewing..."
				rows="1"
				oninput={(e) => autoResize(e.currentTarget)}
				onkeydown={handleKeydown}
				disabled={agent.isRunning}
			></textarea>
			<button
				type="button"
				class="send-button"
				onclick={handleSend}
				disabled={!input.trim() || agent.isRunning}
			>
				{#if agent.isRunning}
					<svg class="spinner" width="20" height="20" viewBox="0 0 24 24">
						<circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" fill="none" stroke-dasharray="31.4" stroke-dashoffset="10"/>
					</svg>
				{:else}
					<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/>
					</svg>
				{/if}
			</button>
		</div>
		<div class="input-hint">
			Press Enter to send, Shift+Enter for new line
		</div>
	</footer>
</div>

<script lang="ts" module>
	// Simple markdown formatting
	function formatMarkdown(text: string): string {
		if (!text) return '';

		// Escape HTML first
		let html = text
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;');

		// Code blocks
		html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code class="language-$1">$2</code></pre>');

		// Inline code
		html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

		// Bold
		html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

		// Italic
		html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');

		// Links
		html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

		// Line breaks
		html = html.replace(/\n/g, '<br>');

		return html;
	}
</script>

<style>
	.assistant-page {
		display: flex;
		flex-direction: column;
		height: 100vh;
		max-height: 100vh;
		background: var(--bg-base);
	}

	.page-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		padding: var(--space-4) var(--space-6);
		border-bottom: 1px solid var(--border-subtle);
		background: var(--bg-surface);
	}

	.header-content h1 {
		margin: 0;
		font-size: 1.25rem;
		font-weight: 600;
		color: var(--text-primary);
	}

	.subtitle {
		margin: var(--space-1) 0 0;
		font-size: 0.875rem;
		color: var(--text-muted);
	}

	.settings {
		display: flex;
		gap: var(--space-4);
	}

	.setting {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		font-size: 0.875rem;
		color: var(--text-secondary);
	}

	.setting input {
		width: 60px;
		padding: var(--space-1) var(--space-2);
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
		border-radius: 4px;
		color: var(--text-primary);
		font-size: 0.875rem;
		text-align: right;
	}

	.setting input:focus {
		outline: none;
		border-color: var(--accent);
	}

	.chat-container {
		flex: 1;
		overflow-y: auto;
		padding: var(--space-6);
	}

	.empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		height: 100%;
		text-align: center;
		color: var(--text-secondary);
	}

	.empty-icon {
		color: var(--text-muted);
		margin-bottom: var(--space-4);
	}

	.empty-state h2 {
		margin: 0 0 var(--space-2);
		font-size: 1.125rem;
		font-weight: 500;
		color: var(--text-primary);
	}

	.empty-state p {
		margin: 0 0 var(--space-6);
		max-width: 400px;
	}

	.example-prompts {
		display: flex;
		flex-wrap: wrap;
		justify-content: center;
		gap: var(--space-2);
		max-width: 600px;
	}

	.prompt-chip {
		padding: var(--space-2) var(--space-3);
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
		border-radius: 20px;
		color: var(--text-secondary);
		font-size: 0.875rem;
		cursor: pointer;
		transition: all var(--transition);
	}

	.prompt-chip:hover {
		background: var(--bg-hover);
		border-color: var(--border-default);
		color: var(--text-primary);
	}

	.messages {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
		max-width: 800px;
		margin: 0 auto;
	}

	.message {
		display: flex;
		gap: var(--space-3);
	}

	.message-avatar {
		flex-shrink: 0;
		width: 32px;
		height: 32px;
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: 50%;
		background: var(--bg-elevated);
		color: var(--text-muted);
	}

	.message.user .message-avatar {
		background: var(--accent-muted);
		color: var(--accent);
	}

	.message.assistant .message-avatar {
		background: var(--recipe-accent-muted);
		color: var(--recipe-accent);
	}

	.message-content {
		flex: 1;
		min-width: 0;
	}

	.message-text {
		padding: var(--space-3) var(--space-4);
		background: var(--bg-surface);
		border-radius: 12px;
		border-top-left-radius: 4px;
		color: var(--text-primary);
		line-height: 1.6;
	}

	.message.user .message-text {
		background: var(--accent-muted);
		border-top-left-radius: 12px;
		border-top-right-radius: 4px;
	}

	.message-text :global(code) {
		font-family: var(--font-mono);
		background: var(--bg-elevated);
		padding: 2px 6px;
		border-radius: 4px;
		font-size: 0.9em;
	}

	.message-text :global(pre) {
		background: var(--bg-elevated);
		padding: var(--space-3);
		border-radius: 8px;
		overflow-x: auto;
		margin: var(--space-2) 0;
	}

	.message-text :global(pre code) {
		background: none;
		padding: 0;
	}

	.message-text :global(strong) {
		font-weight: 600;
		color: var(--text-primary);
	}

	.message-text :global(a) {
		color: var(--accent);
		text-decoration: none;
	}

	.message-text :global(a:hover) {
		text-decoration: underline;
	}

	.streaming .cursor {
		display: inline-block;
		width: 2px;
		height: 1em;
		background: var(--text-primary);
		margin-left: 2px;
		animation: blink 1s infinite;
	}

	@keyframes blink {
		0%, 50% { opacity: 1; }
		51%, 100% { opacity: 0; }
	}

	.typing-indicator {
		display: flex;
		gap: 4px;
		padding: var(--space-3) var(--space-4);
	}

	.typing-indicator span {
		width: 8px;
		height: 8px;
		background: var(--text-muted);
		border-radius: 50%;
		animation: bounce 1.4s infinite ease-in-out both;
	}

	.typing-indicator span:nth-child(1) { animation-delay: -0.32s; }
	.typing-indicator span:nth-child(2) { animation-delay: -0.16s; }

	@keyframes bounce {
		0%, 80%, 100% { transform: scale(0); }
		40% { transform: scale(1); }
	}

	.error-banner {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-3) var(--space-4);
		background: var(--error-bg);
		border-radius: 8px;
		color: var(--negative);
		font-size: 0.875rem;
		margin-top: var(--space-4);
	}

	.error-banner button {
		margin-left: auto;
		padding: var(--space-1) var(--space-2);
		background: none;
		border: 1px solid currentColor;
		border-radius: 4px;
		color: inherit;
		cursor: pointer;
		font-size: 0.75rem;
	}

	.input-area {
		padding: var(--space-4) var(--space-6);
		border-top: 1px solid var(--border-subtle);
		background: var(--bg-surface);
	}

	.input-wrapper {
		display: flex;
		gap: var(--space-2);
		align-items: flex-end;
		max-width: 800px;
		margin: 0 auto;
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
		border-radius: 12px;
		padding: var(--space-2);
	}

	.input-wrapper:focus-within {
		border-color: var(--accent);
	}

	.input-wrapper textarea {
		flex: 1;
		padding: var(--space-2) var(--space-3);
		background: none;
		border: none;
		color: var(--text-primary);
		font-family: var(--font-sans);
		font-size: 0.9375rem;
		line-height: 1.5;
		resize: none;
		min-height: 24px;
		max-height: 200px;
	}

	.input-wrapper textarea:focus {
		outline: none;
	}

	.input-wrapper textarea::placeholder {
		color: var(--text-muted);
	}

	.send-button {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 36px;
		height: 36px;
		background: var(--accent);
		border: none;
		border-radius: 8px;
		color: white;
		cursor: pointer;
		transition: background var(--transition);
	}

	.send-button:hover:not(:disabled) {
		background: var(--accent-hover);
	}

	.send-button:disabled {
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

	.input-hint {
		text-align: center;
		margin-top: var(--space-2);
		font-size: 0.75rem;
		color: var(--text-muted);
	}
</style>
