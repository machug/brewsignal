<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	interface Message {
		role: 'user' | 'assistant';
		content: string;
		recipe?: Record<string, unknown>;
	}

	interface AssistantStatus {
		enabled: boolean;
		configured: boolean;
		provider: string | null;
		model: string | null;
	}

	let messages = $state<Message[]>([]);
	let inputMessage = $state('');
	let loading = $state(false);
	let conversationId = $state<string | null>(null);
	let status = $state<AssistantStatus | null>(null);
	let statusLoading = $state(true);
	let currentRecipe = $state<Record<string, unknown> | null>(null);
	let savingRecipe = $state(false);
	let saveError = $state<string | null>(null);
	let saveSuccess = $state(false);

	// Settings
	let batchSize = $state(19);
	let efficiency = $state(72);

	let messagesContainer: HTMLDivElement;

	onMount(async () => {
		await loadStatus();
	});

	async function loadStatus() {
		try {
			const response = await fetch('/api/assistant/status');
			if (response.ok) {
				status = await response.json();
			}
		} catch (e) {
			console.error('Failed to load assistant status:', e);
		} finally {
			statusLoading = false;
		}
	}

	async function sendMessage() {
		if (!inputMessage.trim() || loading) return;

		const userMessage = inputMessage.trim();
		inputMessage = '';

		// Add user message to chat
		messages = [...messages, { role: 'user', content: userMessage }];
		loading = true;

		// Scroll to bottom
		setTimeout(() => {
			if (messagesContainer) {
				messagesContainer.scrollTop = messagesContainer.scrollHeight;
			}
		}, 10);

		try {
			const response = await fetch('/api/assistant/recipe/chat', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					message: userMessage,
					conversation_id: conversationId,
					batch_size: batchSize,
					efficiency: efficiency
				})
			});

			if (!response.ok) {
				throw new Error('Failed to get response');
			}

			const data = await response.json();
			conversationId = data.conversation_id;

			// Add assistant response
			const assistantMessage: Message = {
				role: 'assistant',
				content: data.response
			};

			if (data.has_recipe && data.recipe) {
				assistantMessage.recipe = data.recipe;
				currentRecipe = data.recipe;
			}

			messages = [...messages, assistantMessage];
		} catch (e) {
			messages = [
				...messages,
				{
					role: 'assistant',
					content: 'Sorry, I encountered an error. Please try again.'
				}
			];
		} finally {
			loading = false;
			setTimeout(() => {
				if (messagesContainer) {
					messagesContainer.scrollTop = messagesContainer.scrollHeight;
				}
			}, 10);
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			sendMessage();
		}
	}

	async function saveRecipe() {
		if (!currentRecipe) return;

		savingRecipe = true;
		saveError = null;
		saveSuccess = false;

		try {
			const response = await fetch('/api/recipes', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					name: currentRecipe.name,
					author: 'BrewSignal AI',
					style_id: null,
					type: currentRecipe.type || 'all-grain',
					og: currentRecipe.og,
					fg: currentRecipe.fg,
					abv: currentRecipe.abv,
					ibu: currentRecipe.ibu,
					color_srm: currentRecipe.color_srm,
					batch_size_liters: currentRecipe.batch_size_liters,
					boil_time_minutes: currentRecipe.boil_time_minutes,
					efficiency_percent: currentRecipe.efficiency_percent,
					yeast_name: currentRecipe.yeast_name,
					yeast_lab: currentRecipe.yeast_lab,
					yeast_attenuation: currentRecipe.yeast_attenuation,
					yeast_temp_min: currentRecipe.yeast_temp_min,
					yeast_temp_max: currentRecipe.yeast_temp_max,
					notes: currentRecipe.notes
				})
			});

			if (!response.ok) {
				throw new Error('Failed to save recipe');
			}

			const savedRecipe = await response.json();
			saveSuccess = true;

			// Navigate to the saved recipe after a short delay
			setTimeout(() => {
				goto(`/recipes/${savedRecipe.id}`);
			}, 1500);
		} catch (e) {
			saveError = e instanceof Error ? e.message : 'Failed to save recipe';
		} finally {
			savingRecipe = false;
		}
	}

	function startNewConversation() {
		messages = [];
		conversationId = null;
		currentRecipe = null;
		saveError = null;
		saveSuccess = false;
	}

	function formatRecipePreview(recipe: Record<string, unknown>): string {
		const parts = [];
		if (recipe.name) parts.push(`**${recipe.name}**`);
		if (recipe.style) parts.push(`Style: ${recipe.style}`);
		if (recipe.og) parts.push(`OG: ${recipe.og}`);
		if (recipe.fg) parts.push(`FG: ${recipe.fg}`);
		if (recipe.abv) parts.push(`ABV: ${recipe.abv}%`);
		if (recipe.ibu) parts.push(`IBU: ${recipe.ibu}`);
		if (recipe.color_srm) parts.push(`SRM: ${recipe.color_srm}`);
		return parts.join(' | ');
	}
</script>

<svelte:head>
	<title>Recipe Assistant | BrewSignal</title>
</svelte:head>

<div class="page-container">
	<div class="page-header">
		<div class="header-left">
			<h1 class="page-title">Recipe Assistant</h1>
			{#if status?.model}
				<span class="model-badge">{status.model}</span>
			{/if}
		</div>
		<div class="header-actions">
			{#if messages.length > 0}
				<button class="new-btn" onclick={startNewConversation}>
					<svg class="icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
					</svg>
					New Chat
				</button>
			{/if}
		</div>
	</div>

	{#if statusLoading}
		<div class="loading-state">
			<div class="spinner"></div>
			<p>Loading...</p>
		</div>
	{:else if !status?.configured}
		<div class="empty-state">
			<div class="empty-icon">🤖</div>
			<h2 class="empty-title">AI Assistant Not Configured</h2>
			<p class="empty-description">
				Enable the AI Assistant in Settings to start creating recipes with natural language.
			</p>
			<a href="/system" class="empty-cta">Go to Settings</a>
		</div>
	{:else}
		<div class="chat-layout">
			<!-- Chat Panel -->
			<div class="chat-panel">
				<!-- Settings Bar -->
				<div class="settings-bar">
					<div class="setting">
						<label for="batch-size">Batch Size</label>
						<input
							id="batch-size"
							type="number"
							bind:value={batchSize}
							min="1"
							max="100"
							step="1"
						/>
						<span class="unit">L</span>
					</div>
					<div class="setting">
						<label for="efficiency">Efficiency</label>
						<input
							id="efficiency"
							type="number"
							bind:value={efficiency}
							min="50"
							max="95"
							step="1"
						/>
						<span class="unit">%</span>
					</div>
				</div>

				<!-- Messages -->
				<div class="messages" bind:this={messagesContainer}>
					{#if messages.length === 0}
						<div class="welcome-message">
							<h2>What would you like to brew?</h2>
							<p>
								I can help you create beer recipes. Try something like:
							</p>
							<div class="suggestions">
								<button onclick={() => { inputMessage = "I want to brew a light summer beer"; sendMessage(); }}>
									Light summer beer
								</button>
								<button onclick={() => { inputMessage = "Create a classic American IPA"; sendMessage(); }}>
									American IPA
								</button>
								<button onclick={() => { inputMessage = "Something dark and malty for winter"; sendMessage(); }}>
									Dark winter beer
								</button>
							</div>
						</div>
					{:else}
						{#each messages as message}
							<div class="message {message.role}">
								<div class="message-content">
									{#if message.role === 'assistant'}
										{@html message.content.replace(/\n/g, '<br>').replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')}
									{:else}
										{message.content}
									{/if}
								</div>
								{#if message.recipe}
									<div class="recipe-preview">
										<div class="recipe-preview-header">
											<span class="recipe-icon">📋</span>
											<span>Recipe Ready</span>
										</div>
										<div class="recipe-preview-content">
											{formatRecipePreview(message.recipe)}
										</div>
									</div>
								{/if}
							</div>
						{/each}
						{#if loading}
							<div class="message assistant">
								<div class="message-content typing">
									<span></span><span></span><span></span>
								</div>
							</div>
						{/if}
					{/if}
				</div>

				<!-- Input -->
				<div class="input-area">
					<textarea
						placeholder="Describe the beer you want to brew..."
						bind:value={inputMessage}
						onkeydown={handleKeydown}
						rows="2"
						disabled={loading}
					></textarea>
					<button class="send-btn" onclick={sendMessage} disabled={loading || !inputMessage.trim()}>
						{#if loading}
							<div class="spinner small"></div>
						{:else}
							<svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
							</svg>
						{/if}
					</button>
				</div>
			</div>

			<!-- Recipe Panel -->
			{#if currentRecipe}
				<div class="recipe-panel">
					<div class="recipe-panel-header">
						<h2>{currentRecipe.name || 'Generated Recipe'}</h2>
						{#if currentRecipe.style}
							<span class="style-badge">{currentRecipe.style}</span>
						{/if}
					</div>

					<div class="recipe-stats">
						<div class="stat">
							<span class="stat-label">OG</span>
							<span class="stat-value">{currentRecipe.og || '-'}</span>
						</div>
						<div class="stat">
							<span class="stat-label">FG</span>
							<span class="stat-value">{currentRecipe.fg || '-'}</span>
						</div>
						<div class="stat">
							<span class="stat-label">ABV</span>
							<span class="stat-value">{currentRecipe.abv || '-'}%</span>
						</div>
						<div class="stat">
							<span class="stat-label">IBU</span>
							<span class="stat-value">{currentRecipe.ibu || '-'}</span>
						</div>
						<div class="stat">
							<span class="stat-label">SRM</span>
							<span class="stat-value">{currentRecipe.color_srm || '-'}</span>
						</div>
					</div>

					{#if currentRecipe.yeast_name}
						<div class="recipe-section">
							<h3>Yeast</h3>
							<p>
								{currentRecipe.yeast_name}
								{#if currentRecipe.yeast_lab}
									({currentRecipe.yeast_lab})
								{/if}
							</p>
							{#if currentRecipe.yeast_temp_min && currentRecipe.yeast_temp_max}
								<p class="small">
									Ferment at {currentRecipe.yeast_temp_min}-{currentRecipe.yeast_temp_max}°C
								</p>
							{/if}
						</div>
					{/if}

					{#if currentRecipe.notes}
						<div class="recipe-section">
							<h3>Brewing Notes</h3>
							<div class="notes">
								{@html String(currentRecipe.notes).replace(/\n/g, '<br>').replace(/- /g, '• ')}
							</div>
						</div>
					{/if}

					<div class="recipe-actions">
						{#if saveSuccess}
							<div class="success-message">Recipe saved! Redirecting...</div>
						{:else if saveError}
							<div class="error-message">{saveError}</div>
						{/if}
						<button
							class="save-btn"
							onclick={saveRecipe}
							disabled={savingRecipe || saveSuccess}
						>
							{#if savingRecipe}
								<div class="spinner small"></div>
								Saving...
							{:else if saveSuccess}
								Saved!
							{:else}
								<svg class="icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
								</svg>
								Save to Library
							{/if}
						</button>
					</div>
				</div>
			{/if}
		</div>
	{/if}
</div>

<style>
	.page-container {
		max-width: 1400px;
		margin: 0 auto;
		padding: 1.5rem;
	}

	.page-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 1.5rem;
	}

	.header-left {
		display: flex;
		align-items: center;
		gap: 1rem;
	}

	.page-title {
		font-size: 1.75rem;
		font-weight: 700;
		color: var(--text-primary, #1f2937);
		margin: 0;
	}

	.model-badge {
		font-size: 0.75rem;
		padding: 0.25rem 0.5rem;
		background: var(--surface-secondary, #f3f4f6);
		color: var(--text-secondary, #6b7280);
		border-radius: 0.375rem;
	}

	.header-actions {
		display: flex;
		gap: 0.75rem;
	}

	.new-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.5rem 1rem;
		background: var(--primary, #3b82f6);
		color: white;
		border: none;
		border-radius: 0.5rem;
		font-weight: 500;
		cursor: pointer;
		text-decoration: none;
	}

	.new-btn:hover {
		background: var(--primary-hover, #2563eb);
	}

	.icon {
		width: 1.25rem;
		height: 1.25rem;
	}

	/* Loading & Empty States */
	.loading-state,
	.empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 4rem 2rem;
		text-align: center;
	}

	.spinner {
		width: 2rem;
		height: 2rem;
		border: 3px solid var(--surface-secondary, #e5e7eb);
		border-top-color: var(--primary, #3b82f6);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	.spinner.small {
		width: 1rem;
		height: 1rem;
		border-width: 2px;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	.empty-icon {
		font-size: 3rem;
		margin-bottom: 1rem;
	}

	.empty-title {
		font-size: 1.25rem;
		font-weight: 600;
		margin-bottom: 0.5rem;
	}

	.empty-description {
		color: var(--text-secondary, #6b7280);
		margin-bottom: 1.5rem;
	}

	.empty-cta {
		padding: 0.75rem 1.5rem;
		background: var(--primary, #3b82f6);
		color: white;
		border-radius: 0.5rem;
		text-decoration: none;
		font-weight: 500;
	}

	/* Chat Layout */
	.chat-layout {
		display: grid;
		grid-template-columns: 1fr;
		gap: 1.5rem;
		height: calc(100vh - 12rem);
		min-height: 500px;
	}

	@media (min-width: 1024px) {
		.chat-layout {
			grid-template-columns: 1fr 350px;
		}
	}

	/* Chat Panel */
	.chat-panel {
		display: flex;
		flex-direction: column;
		background: var(--surface, white);
		border-radius: 0.75rem;
		border: 1px solid var(--border, #e5e7eb);
		overflow: hidden;
	}

	.settings-bar {
		display: flex;
		gap: 1.5rem;
		padding: 0.75rem 1rem;
		background: var(--surface-secondary, #f9fafb);
		border-bottom: 1px solid var(--border, #e5e7eb);
	}

	.setting {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.setting label {
		font-size: 0.875rem;
		color: var(--text-secondary, #6b7280);
	}

	.setting input {
		width: 60px;
		padding: 0.25rem 0.5rem;
		border: 1px solid var(--border, #e5e7eb);
		border-radius: 0.375rem;
		font-size: 0.875rem;
	}

	.setting .unit {
		font-size: 0.875rem;
		color: var(--text-secondary, #6b7280);
	}

	/* Messages */
	.messages {
		flex: 1;
		overflow-y: auto;
		padding: 1rem;
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.welcome-message {
		text-align: center;
		padding: 2rem;
	}

	.welcome-message h2 {
		font-size: 1.5rem;
		margin-bottom: 0.5rem;
	}

	.welcome-message p {
		color: var(--text-secondary, #6b7280);
		margin-bottom: 1.5rem;
	}

	.suggestions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		justify-content: center;
	}

	.suggestions button {
		padding: 0.5rem 1rem;
		background: var(--surface-secondary, #f3f4f6);
		border: 1px solid var(--border, #e5e7eb);
		border-radius: 2rem;
		font-size: 0.875rem;
		cursor: pointer;
		transition: all 0.2s;
	}

	.suggestions button:hover {
		background: var(--primary, #3b82f6);
		color: white;
		border-color: var(--primary, #3b82f6);
	}

	.message {
		max-width: 85%;
	}

	.message.user {
		align-self: flex-end;
	}

	.message.assistant {
		align-self: flex-start;
	}

	.message-content {
		padding: 0.75rem 1rem;
		border-radius: 1rem;
		line-height: 1.5;
	}

	.message.user .message-content {
		background: var(--primary, #3b82f6);
		color: white;
		border-bottom-right-radius: 0.25rem;
	}

	.message.assistant .message-content {
		background: var(--surface-secondary, #f3f4f6);
		border-bottom-left-radius: 0.25rem;
	}

	.typing {
		display: flex;
		gap: 0.25rem;
		padding: 1rem;
	}

	.typing span {
		width: 0.5rem;
		height: 0.5rem;
		background: var(--text-secondary, #9ca3af);
		border-radius: 50%;
		animation: typing 1.4s infinite ease-in-out;
	}

	.typing span:nth-child(2) {
		animation-delay: 0.2s;
	}

	.typing span:nth-child(3) {
		animation-delay: 0.4s;
	}

	@keyframes typing {
		0%,
		80%,
		100% {
			transform: scale(0.8);
			opacity: 0.5;
		}
		40% {
			transform: scale(1);
			opacity: 1;
		}
	}

	.recipe-preview {
		margin-top: 0.5rem;
		padding: 0.75rem;
		background: white;
		border: 1px solid var(--border, #e5e7eb);
		border-radius: 0.5rem;
	}

	.recipe-preview-header {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-weight: 600;
		margin-bottom: 0.5rem;
	}

	.recipe-preview-content {
		font-size: 0.875rem;
		color: var(--text-secondary, #6b7280);
	}

	/* Input Area */
	.input-area {
		display: flex;
		gap: 0.5rem;
		padding: 1rem;
		border-top: 1px solid var(--border, #e5e7eb);
	}

	.input-area textarea {
		flex: 1;
		padding: 0.75rem 1rem;
		border: 1px solid var(--border, #e5e7eb);
		border-radius: 0.5rem;
		resize: none;
		font-family: inherit;
		font-size: 1rem;
	}

	.input-area textarea:focus {
		outline: none;
		border-color: var(--primary, #3b82f6);
	}

	.send-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 3rem;
		height: 3rem;
		background: var(--primary, #3b82f6);
		color: white;
		border: none;
		border-radius: 0.5rem;
		cursor: pointer;
		flex-shrink: 0;
	}

	.send-btn:hover:not(:disabled) {
		background: var(--primary-hover, #2563eb);
	}

	.send-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.send-btn svg {
		width: 1.25rem;
		height: 1.25rem;
	}

	/* Recipe Panel */
	.recipe-panel {
		background: var(--surface, white);
		border-radius: 0.75rem;
		border: 1px solid var(--border, #e5e7eb);
		padding: 1.5rem;
		overflow-y: auto;
	}

	.recipe-panel-header {
		margin-bottom: 1.5rem;
	}

	.recipe-panel-header h2 {
		font-size: 1.25rem;
		font-weight: 600;
		margin-bottom: 0.5rem;
	}

	.style-badge {
		display: inline-block;
		padding: 0.25rem 0.75rem;
		background: var(--primary-light, #dbeafe);
		color: var(--primary, #3b82f6);
		border-radius: 2rem;
		font-size: 0.875rem;
	}

	.recipe-stats {
		display: grid;
		grid-template-columns: repeat(5, 1fr);
		gap: 0.5rem;
		margin-bottom: 1.5rem;
	}

	.stat {
		text-align: center;
		padding: 0.75rem 0.5rem;
		background: var(--surface-secondary, #f9fafb);
		border-radius: 0.5rem;
	}

	.stat-label {
		display: block;
		font-size: 0.75rem;
		color: var(--text-secondary, #6b7280);
		margin-bottom: 0.25rem;
	}

	.stat-value {
		font-size: 1rem;
		font-weight: 600;
	}

	.recipe-section {
		margin-bottom: 1.5rem;
	}

	.recipe-section h3 {
		font-size: 0.875rem;
		font-weight: 600;
		text-transform: uppercase;
		color: var(--text-secondary, #6b7280);
		margin-bottom: 0.5rem;
	}

	.recipe-section p {
		margin: 0;
	}

	.recipe-section .small {
		font-size: 0.875rem;
		color: var(--text-secondary, #6b7280);
		margin-top: 0.25rem;
	}

	.notes {
		font-size: 0.875rem;
		line-height: 1.6;
	}

	.recipe-actions {
		margin-top: 1.5rem;
		padding-top: 1.5rem;
		border-top: 1px solid var(--border, #e5e7eb);
	}

	.save-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		width: 100%;
		padding: 0.75rem 1rem;
		background: var(--success, #10b981);
		color: white;
		border: none;
		border-radius: 0.5rem;
		font-weight: 500;
		cursor: pointer;
	}

	.save-btn:hover:not(:disabled) {
		background: var(--success-hover, #059669);
	}

	.save-btn:disabled {
		opacity: 0.7;
		cursor: not-allowed;
	}

	.success-message {
		padding: 0.75rem;
		background: var(--success-light, #d1fae5);
		color: var(--success, #059669);
		border-radius: 0.5rem;
		text-align: center;
		margin-bottom: 0.75rem;
	}

	.error-message {
		padding: 0.75rem;
		background: var(--error-light, #fee2e2);
		color: var(--error, #dc2626);
		border-radius: 0.5rem;
		text-align: center;
		margin-bottom: 0.75rem;
	}
</style>
