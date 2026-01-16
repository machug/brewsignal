<script lang="ts">
	import { useAgent } from '$lib/ag-ui';
	import { onMount } from 'svelte';
	import type { Message, ToolCall, Thread } from '$lib/ag-ui/types';

	// Configuration
	let batchSize = $state(19);
	let efficiency = $state(72);
	let showDebugPanel = $state(false);
	let showSidebar = $state(false); // Start collapsed, especially important for mobile
	let isMobile = $state(false);

	// Thread state
	let threads = $state<Thread[]>([]);
	let currentThreadId = $state<string | null>(null);
	let loadingThreads = $state(false);

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

	// Reactive tool calls array - toolCalls is now an array in the client
	let toolCallsArray = $derived(agent.toolCalls);

	// Input state
	let input = $state('');
	let inputRef = $state<HTMLTextAreaElement | null>(null);

	// Thread management functions
	async function fetchThreads() {
		loadingThreads = true;
		try {
			const res = await fetch('/api/ag-ui/threads?limit=50');
			if (res.ok) {
				threads = await res.json();
			}
		} catch (e) {
			console.error('Failed to fetch threads:', e);
		} finally {
			loadingThreads = false;
		}
	}

	async function loadThread(threadId: string) {
		try {
			const res = await fetch(`/api/ag-ui/threads/${threadId}`);
			if (res.ok) {
				const thread = await res.json();
				currentThreadId = threadId;
				// Convert thread messages to agent messages format
				const messages: Message[] = thread.messages
					.filter((m: any) => m.role === 'user' || m.role === 'assistant')
					.map((m: any) => ({
						id: String(m.id),
						role: m.role,
						content: m.content,
						createdAt: m.created_at
					}));
				agent.loadMessages(messages, threadId);
			}
		} catch (e) {
			console.error('Failed to load thread:', e);
		}
	}

	async function deleteThread(threadId: string) {
		if (!confirm('Delete this conversation?')) return;
		try {
			const res = await fetch(`/api/ag-ui/threads/${threadId}`, { method: 'DELETE' });
			if (res.ok) {
				threads = threads.filter(t => t.id !== threadId);
				if (currentThreadId === threadId) {
					startNewConversation();
				}
			}
		} catch (e) {
			console.error('Failed to delete thread:', e);
		}
	}

	function startNewConversation() {
		currentThreadId = null;
		agent.clear();
		inputRef?.focus();
	}

	// Update agent state when settings change
	function updateBatchSize(value: number) {
		batchSize = value;
		agent.setState({ batchSize: value });
	}

	function updateEfficiency(value: number) {
		efficiency = value;
		agent.setState({ efficiency: value });
	}

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

		await agent.send(content, currentThreadId || undefined);

		// Update currentThreadId after first message (agent creates new thread)
		if (!currentThreadId && agent.threadId) {
			currentThreadId = agent.threadId;
			// Refresh thread list to show new conversation
			fetchThreads();
		}
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

	// Format relative time
	function formatRelativeTime(dateStr: string): string {
		const date = new Date(dateStr);
		const now = new Date();
		const diffMs = now.getTime() - date.getTime();
		const diffMins = Math.floor(diffMs / 60000);
		const diffHours = Math.floor(diffMs / 3600000);
		const diffDays = Math.floor(diffMs / 86400000);

		if (diffMins < 1) return 'just now';
		if (diffMins < 60) return `${diffMins}m ago`;
		if (diffHours < 24) return `${diffHours}h ago`;
		if (diffDays < 7) return `${diffDays}d ago`;
		return date.toLocaleDateString();
	}

	// Check if mobile on mount and on resize
	function checkMobile() {
		isMobile = window.innerWidth < 768;
	}

	onMount(() => {
		inputRef?.focus();
		fetchThreads();
		checkMobile();
		window.addEventListener('resize', checkMobile);
		return () => window.removeEventListener('resize', checkMobile);
	});

	// Close sidebar on mobile after selecting a thread
	function handleThreadSelect(threadId: string) {
		loadThread(threadId);
		if (isMobile) {
			showSidebar = false;
		}
	}
</script>

<svelte:head>
	<title>AI Assistant | BrewSignal</title>
</svelte:head>

<div class="assistant-page" class:sidebar-open={showSidebar}>
	<!-- Mobile backdrop overlay -->
	{#if showSidebar && isMobile}
		<button
			type="button"
			class="sidebar-backdrop"
			onclick={() => showSidebar = false}
			aria-label="Close sidebar"
		></button>
	{/if}

	<!-- Sidebar with conversation history -->
	<aside class="sidebar" class:open={showSidebar}>
		<div class="sidebar-header">
			<h2>History</h2>
			<button type="button" class="new-chat-btn" onclick={startNewConversation} title="New conversation">
				<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<path d="M12 5v14M5 12h14"/>
				</svg>
			</button>
		</div>
		<div class="sidebar-content">
			{#if loadingThreads}
				<div class="sidebar-loading">Loading...</div>
			{:else if threads.length === 0}
				<div class="sidebar-empty">No conversations yet</div>
			{:else}
				<div class="thread-list">
					{#each threads as thread (thread.id)}
						<div
							class="thread-item"
							class:active={currentThreadId === thread.id}
							role="button"
							tabindex="0"
							onclick={() => handleThreadSelect(thread.id)}
							onkeydown={(e) => e.key === 'Enter' && handleThreadSelect(thread.id)}
						>
							<div class="thread-title">{thread.title || 'Untitled'}</div>
							<div class="thread-meta">
								<span>{thread.message_count} msgs</span>
								<span>{formatRelativeTime(thread.updated_at)}</span>
							</div>
							<button
								type="button"
								class="thread-delete"
								onclick={(e) => { e.stopPropagation(); deleteThread(thread.id); }}
								title="Delete conversation"
							>
								<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
									<path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
								</svg>
							</button>
						</div>
					{/each}
				</div>
			{/if}
		</div>
	</aside>

	<!-- Main content -->
	<div class="main-content">
		<header class="page-header">
			<div class="header-left">
				<button
					type="button"
					class="sidebar-toggle"
					onclick={() => showSidebar = !showSidebar}
					title={showSidebar ? 'Hide sidebar' : 'Show sidebar'}
				>
					<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path d="M3 12h18M3 6h18M3 18h18"/>
					</svg>
				</button>
				<div class="header-content">
					<h1>Brewing Assistant</h1>
					<p class="subtitle">AI-powered recipe creation and brewing advice</p>
				</div>
			</div>
			<div class="settings">
				<label class="setting">
					<span>Batch Size</span>
					<input type="number" value={batchSize} min="1" max="100" onchange={(e) => updateBatchSize(Number(e.currentTarget.value))} /> L
				</label>
				<label class="setting">
					<span>Efficiency</span>
					<input type="number" value={efficiency} min="50" max="100" onchange={(e) => updateEfficiency(Number(e.currentTarget.value))} /> %
				</label>
				<button
					type="button"
					class="debug-toggle"
					class:active={showDebugPanel}
					onclick={() => showDebugPanel = !showDebugPanel}
					title="Toggle agent debug panel"
				>
					<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path d="M12 20h9M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
					</svg>
				</button>
			</div>
		</header>

		<main class="chat-container">
		{#if agent.messages.length === 0}
			<!-- Empty state with example prompts -->
			<div class="empty-state">
				<div class="empty-icon">
					<svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
						<path d="M12 2L2 7l10 5 10-5-10-5z"/>
						<path d="M2 17l10 5 10-5"/>
						<path d="M2 12l10 5 10-5"/>
					</svg>
				</div>
				<h2>Start a conversation</h2>
				<p class="empty-description">Ask about recipes, techniques, or ingredients</p>
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

		{#if showDebugPanel}
			<div class="debug-panel">
				<div class="debug-header">
					<h3>Agent Debug</h3>
					<button type="button" class="debug-close" onclick={() => showDebugPanel = false}>×</button>
				</div>
				<div class="debug-content">
					<div class="debug-section">
						<div class="debug-label">Status</div>
						<div class="debug-value">
							<span class="status-badge" class:running={agent.isRunning} class:streaming={agent.isStreaming}>
								{agent.status}
								{#if agent.isStreaming}(streaming){/if}
							</span>
						</div>
					</div>

					{#if agent.threadId}
						<div class="debug-section">
							<div class="debug-label">Thread</div>
							<div class="debug-value mono">{agent.threadId.slice(0, 8)}...</div>
						</div>
					{/if}

					<div class="debug-section">
						<div class="debug-label">Messages</div>
						<div class="debug-value">{agent.messages.length}</div>
					</div>

					{#if toolCallsArray.length > 0}
						<div class="debug-section tool-calls-section">
							<div class="debug-label">Tool Calls ({toolCallsArray.length})</div>
							<div class="tool-calls-list">
								{#each toolCallsArray as tool (tool.id)}
									<div class="tool-call" class:running={tool.status === 'running'} class:completed={tool.status === 'completed'}>
										<div class="tool-call-header">
											<span class="tool-name">{tool.name}</span>
											<span class="tool-status">{tool.status}</span>
										</div>
										{#if tool.args}
											<details class="tool-details">
												<summary>Arguments</summary>
												<pre class="tool-json">{formatJson(tool.args)}</pre>
											</details>
										{/if}
										{#if tool.result}
											<details class="tool-details">
												<summary>Result</summary>
												<pre class="tool-json">{formatJson(tool.result)}</pre>
											</details>
										{/if}
									</div>
								{/each}
							</div>
						</div>
					{/if}

					{#if Object.keys(agent.sharedState).length > 0}
						<div class="debug-section">
							<div class="debug-label">Shared State</div>
							<details class="tool-details">
								<summary>{Object.keys(agent.sharedState).length} keys</summary>
								<pre class="tool-json">{JSON.stringify(agent.sharedState, null, 2)}</pre>
							</details>
						</div>
					{/if}
				</div>
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
	</div><!-- end main-content -->
</div>

<script lang="ts" module>
	// Format JSON for display
	function formatJson(str: string): string {
		try {
			const parsed = JSON.parse(str);
			return JSON.stringify(parsed, null, 2);
		} catch {
			return str;
		}
	}

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
		flex-direction: row;
		/* Account for nav (56px) + layout padding (24px top + 24px bottom) */
		height: calc(100vh - 56px - 48px);
		max-height: calc(100vh - 56px - 48px);
		background: var(--bg-base);
		margin: -24px -16px; /* Offset the layout padding */
		width: calc(100% + 32px);
	}

	@media (min-width: 640px) {
		.assistant-page {
			margin: -24px -24px;
			width: calc(100% + 48px);
		}
	}

	@media (min-width: 1024px) {
		.assistant-page {
			margin: -24px -32px;
			width: calc(100% + 64px);
		}
	}

	/* Sidebar backdrop for mobile */
	.sidebar-backdrop {
		display: none;
	}

	@media (max-width: 767px) {
		.sidebar-backdrop {
			display: block;
			position: fixed;
			inset: 0;
			background: rgba(0, 0, 0, 0.5);
			z-index: 40;
			border: none;
			cursor: pointer;
		}
	}

	/* Sidebar */
	.sidebar {
		width: 280px;
		flex-shrink: 0;
		display: none;
		flex-direction: column;
		background: var(--bg-surface);
		border-right: 1px solid var(--border-subtle);
	}

	.sidebar.open {
		display: flex;
	}

	/* Mobile: sidebar as fixed drawer overlay */
	@media (max-width: 767px) {
		.sidebar {
			position: fixed;
			left: 0;
			top: 0;
			bottom: 0;
			z-index: 50;
			transform: translateX(-100%);
			transition: transform 0.2s ease-out;
			display: flex;
		}

		.sidebar.open {
			transform: translateX(0);
		}
	}

	.sidebar-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: var(--space-4);
		border-bottom: 1px solid var(--border-subtle);
	}

	.sidebar-header h2 {
		margin: 0;
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--text-secondary);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.new-chat-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 28px;
		height: 28px;
		background: var(--accent);
		border: none;
		border-radius: 6px;
		color: white;
		cursor: pointer;
		transition: background var(--transition);
	}

	.new-chat-btn:hover {
		background: var(--accent-hover);
	}

	.sidebar-content {
		flex: 1;
		overflow-y: auto;
		padding: var(--space-2);
	}

	.sidebar-loading,
	.sidebar-empty {
		padding: var(--space-4);
		text-align: center;
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	.thread-list {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.thread-item {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		width: 100%;
		padding: var(--space-3);
		background: transparent;
		border: none;
		border-radius: 8px;
		cursor: pointer;
		text-align: left;
		transition: background var(--transition);
		position: relative;
	}

	.thread-item:hover {
		background: var(--bg-hover);
	}

	.thread-item.active {
		background: var(--accent-muted);
	}

	.thread-title {
		font-size: 0.875rem;
		font-weight: 500;
		color: var(--text-primary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		width: 100%;
		padding-right: 24px;
	}

	.thread-meta {
		display: flex;
		gap: var(--space-2);
		margin-top: var(--space-1);
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	.thread-delete {
		position: absolute;
		top: 50%;
		right: var(--space-2);
		transform: translateY(-50%);
		display: flex;
		align-items: center;
		justify-content: center;
		width: 24px;
		height: 24px;
		background: none;
		border: none;
		border-radius: 4px;
		color: var(--text-muted);
		cursor: pointer;
		opacity: 0;
		transition: all var(--transition);
	}

	.thread-item:hover .thread-delete {
		opacity: 1;
	}

	.thread-delete:hover {
		background: var(--negative-muted, rgba(239, 68, 68, 0.1));
		color: var(--negative);
	}

	/* Main content */
	.main-content {
		flex: 1;
		display: flex;
		flex-direction: column;
		min-width: 0;
		min-height: 0; /* Critical for flex shrinking */
		overflow: hidden;
	}

	/* Main content takes full width when sidebar is closed */
	.assistant-page:not(.sidebar-open) .main-content {
		width: 100%;
	}

	/* On mobile, main content always takes full width */
	@media (max-width: 767px) {
		.assistant-page .main-content {
			width: 100%;
		}
	}

	.header-left {
		display: flex;
		align-items: center;
		gap: var(--space-3);
	}

	.sidebar-toggle {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 36px;
		height: 36px;
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
		border-radius: 8px;
		color: var(--text-muted);
		cursor: pointer;
		transition: all var(--transition);
	}

	.sidebar-toggle:hover {
		background: var(--bg-hover);
		color: var(--text-secondary);
	}

	.page-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		padding: var(--space-4) var(--space-6);
		border-bottom: 1px solid var(--border-subtle);
		background: var(--bg-surface);
		gap: var(--space-3);
	}

	@media (max-width: 767px) {
		.page-header {
			padding: var(--space-3) var(--space-4);
			flex-wrap: wrap;
		}
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

	@media (max-width: 767px) {
		.subtitle {
			display: none;
		}

		.header-content h1 {
			font-size: 1.125rem;
		}
	}

	.settings {
		display: flex;
		gap: var(--space-4);
	}

	@media (max-width: 767px) {
		.settings {
			display: none;
		}
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
		padding: var(--space-4);
		min-height: 0; /* Allow flex shrinking */
	}

	@media (max-width: 767px) {
		.chat-container {
			padding: var(--space-3);
		}
	}

	.empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		min-height: 200px;
		padding: var(--space-4) 0;
		text-align: center;
		color: var(--text-secondary);
	}

	.empty-icon {
		color: var(--text-muted);
		margin-bottom: var(--space-2);
	}

	.empty-state h2 {
		margin: 0 0 var(--space-1);
		font-size: 1rem;
		font-weight: 500;
		color: var(--text-primary);
	}

	.empty-description {
		margin: 0 0 var(--space-3);
		font-size: 0.875rem;
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
		border-radius: 16px;
		color: var(--text-secondary);
		font-size: 0.8125rem;
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

	@media (max-width: 767px) {
		.input-area {
			padding: var(--space-3) var(--space-4);
		}
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

	@media (max-width: 767px) {
		.input-hint {
			display: none;
		}
	}

	/* Debug toggle button */
	.debug-toggle {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 32px;
		height: 32px;
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
		border-radius: 6px;
		color: var(--text-muted);
		cursor: pointer;
		transition: all var(--transition);
	}

	.debug-toggle:hover {
		background: var(--bg-hover);
		color: var(--text-secondary);
	}

	.debug-toggle.active {
		background: var(--accent-muted);
		border-color: var(--accent);
		color: var(--accent);
	}

	/* Debug panel */
	.debug-panel {
		position: fixed;
		bottom: 80px;
		right: var(--space-4);
		width: 360px;
		max-height: 60vh;
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 12px;
		box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
		overflow: hidden;
		display: flex;
		flex-direction: column;
		z-index: 100;
	}

	.debug-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: var(--space-3) var(--space-4);
		background: var(--bg-elevated);
		border-bottom: 1px solid var(--border-subtle);
	}

	.debug-header h3 {
		margin: 0;
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--text-primary);
	}

	.debug-close {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 24px;
		height: 24px;
		background: none;
		border: none;
		border-radius: 4px;
		color: var(--text-muted);
		font-size: 1.25rem;
		cursor: pointer;
	}

	.debug-close:hover {
		background: var(--bg-hover);
		color: var(--text-primary);
	}

	.debug-content {
		flex: 1;
		overflow-y: auto;
		padding: var(--space-3);
	}

	.debug-section {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		padding: var(--space-2) 0;
		border-bottom: 1px solid var(--border-subtle);
	}

	.debug-section:last-child {
		border-bottom: none;
	}

	.debug-label {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.debug-value {
		font-size: 0.875rem;
		color: var(--text-primary);
	}

	.debug-value.mono {
		font-family: var(--font-mono);
		font-size: 0.8125rem;
	}

	.status-badge {
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		padding: var(--space-1) var(--space-2);
		background: var(--bg-elevated);
		border-radius: 4px;
		font-size: 0.75rem;
		font-weight: 500;
	}

	.status-badge.running {
		background: var(--accent-muted);
		color: var(--accent);
	}

	.status-badge.streaming {
		background: var(--positive-muted, rgba(34, 197, 94, 0.1));
		color: var(--positive);
	}

	/* Tool calls */
	.tool-calls-section {
		flex-direction: column;
	}

	.tool-calls-list {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		margin-top: var(--space-2);
	}

	.tool-call {
		background: var(--bg-elevated);
		border-radius: 8px;
		padding: var(--space-2) var(--space-3);
		border-left: 3px solid var(--text-muted);
	}

	.tool-call.running {
		border-left-color: var(--accent);
		background: var(--accent-muted);
	}

	.tool-call.completed {
		border-left-color: var(--positive);
	}

	.tool-call-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.tool-name {
		font-family: var(--font-mono);
		font-size: 0.8125rem;
		font-weight: 500;
		color: var(--text-primary);
	}

	.tool-status {
		font-size: 0.6875rem;
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-muted);
	}

	.tool-call.running .tool-status {
		color: var(--accent);
	}

	.tool-call.completed .tool-status {
		color: var(--positive);
	}

	.tool-details {
		margin-top: var(--space-2);
	}

	.tool-details summary {
		font-size: 0.75rem;
		color: var(--text-muted);
		cursor: pointer;
		user-select: none;
	}

	.tool-details summary:hover {
		color: var(--text-secondary);
	}

	.tool-json {
		margin: var(--space-2) 0 0;
		padding: var(--space-2);
		background: var(--bg-deep);
		border-radius: 4px;
		font-family: var(--font-mono);
		font-size: 0.6875rem;
		line-height: 1.5;
		color: var(--text-secondary);
		overflow-x: auto;
		max-height: 150px;
		overflow-y: auto;
	}
</style>
