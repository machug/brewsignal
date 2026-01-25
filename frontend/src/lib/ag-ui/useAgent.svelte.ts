/**
 * AG-UI useAgent Hook for Svelte 5
 * High-level hook for interacting with AG-UI agents
 */

import { createAgentState, createAgentClient, type AgentState, type AgentClient } from './client.svelte';
import type { Message, ToolDefinition, RunConfig } from './types';

export interface UseAgentConfig {
	/** AG-UI endpoint URL */
	url: string;
	/** Optional HTTP headers */
	headers?: Record<string, string>;
	/** Optional thread ID for conversation continuity */
	threadId?: string;
	/** Tool definitions available to the agent */
	tools?: ToolDefinition[];
	/** Initial shared state */
	initialState?: Record<string, unknown>;
	/** Called when agent state changes */
	onStateChange?: (state: Record<string, unknown>) => void;
	/** Called when a tool is invoked */
	onToolCall?: (name: string, args: string) => void;
	/** Called when run completes */
	onComplete?: () => void;
	/** Called on error */
	onError?: (error: string) => void;
}

/**
 * Create an AG-UI agent hook
 * Returns reactive state and methods for interacting with the agent
 */
export function useAgent(config: UseAgentConfig) {
	const agentState = createAgentState();
	const client = createAgentClient({
		url: config.url,
		headers: config.headers
	});

	// Track tools and state from config (non-reactive to avoid loops)
	let tools: ToolDefinition[] = config.tools || [];
	let sharedState: Record<string, unknown> = config.initialState || {};

	// Track current thread ID
	let currentThreadId: string | undefined = config.threadId;

	/**
	 * Send a message to the agent
	 */
	async function send(content: string, threadId?: string): Promise<void> {
		// Add user message to state
		agentState.addUserMessage(content);

		// Use provided threadId or current one
		const effectiveThreadId = threadId || currentThreadId || agentState.threadId;

		// Build run config
		const runConfig: RunConfig = {
			threadId: effectiveThreadId || undefined,
			messages: agentState.messages,
			tools: tools.length > 0 ? tools : undefined,
			state: Object.keys(sharedState).length > 0 ? sharedState : undefined
		};

		// Run the agent
		await client.run(agentState, runConfig);

		// Update current thread ID from response
		if (agentState.threadId) {
			currentThreadId = agentState.threadId;
		}

		// Call completion callback if no error
		if (!agentState.error) {
			config.onComplete?.();
		} else {
			config.onError?.(agentState.error);
		}
	}

	/**
	 * Load messages from a persisted thread
	 */
	function loadMessages(messages: Message[], threadId: string): void {
		// Clear current state
		agentState.clear();

		// Set thread ID
		currentThreadId = threadId;
		agentState._setThreadId(threadId);

		// Add messages to state
		for (const msg of messages) {
			agentState._addMessage(msg);
		}
	}

	/**
	 * Stop the current run
	 */
	function stop(): void {
		client.abort();
	}

	/**
	 * Clear the conversation
	 */
	function clear(): void {
		client.abort();
		agentState.clear();
		currentThreadId = undefined;  // Reset thread ID for new conversation
	}

	/**
	 * Update shared state
	 */
	function setState(newState: Record<string, unknown>): void {
		sharedState = { ...sharedState, ...newState };
	}

	/**
	 * Update tools
	 */
	function setTools(newTools: ToolDefinition[]): void {
		tools = newTools;
	}

	return {
		// State (reactive getters)
		get status() { return agentState.status; },
		get error() { return agentState.error; },
		get messages() { return agentState.allMessages; },
		get isStreaming() { return agentState.isStreaming; },
		get isRunning() { return agentState.isRunning; },
		get threadId() { return agentState.threadId; },
		get currentStep() { return agentState.currentStep; },
		get toolCalls() { return agentState.toolCalls; },
		get sharedState() { return sharedState; },

		// Streaming state for current message
		get streamingContent() { return agentState.streamingContent; },

		// Methods
		send,
		stop,
		clear,
		setState,
		setTools,
		loadMessages,

		// Raw access if needed
		_agentState: agentState,
		_client: client
	};
}

export type UseAgentReturn = ReturnType<typeof useAgent>;
