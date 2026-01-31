/**
 * AG-UI Svelte Client
 * A Svelte 5 native client for the Agent-User Interaction Protocol
 */

import type {
	AgentEvent,
	Message,
	ToolCall,
	ToolDefinition,
	RunConfig,
	ConnectionStatus,
	EventType
} from './types';

// Parse Server-Sent Events from a streaming response
function parseSSELine(line: string): AgentEvent | null {
	if (!line.startsWith('data: ')) return null;
	const data = line.slice(6).trim();
	if (data === '[DONE]') return null;
	try {
		return JSON.parse(data) as AgentEvent;
	} catch {
		console.warn('Failed to parse SSE event:', data);
		return null;
	}
}

// Create a unique ID
function createId(): string {
	return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

/**
 * AG-UI Agent State
 * Reactive state for an agent conversation using Svelte 5 runes
 */
export function createAgentState() {
	// Core state using $state rune
	const state = $state({
		// Connection
		status: 'disconnected' as ConnectionStatus,
		error: null as string | null,

		// Thread info
		threadId: null as string | null,
		runId: null as string | null,

		// Messages
		messages: [] as Message[],

		// Current streaming message
		streamingMessageId: null as string | null,
		streamingContent: '',

		// Tool calls - using array for better Svelte reactivity
		toolCallsList: [] as ToolCall[],

		// Agent state (shared state from agent)
		agentState: {} as Record<string, unknown>,

		// Current step
		currentStep: null as string | null
	});

	// Helper to find/update tool calls
	function findToolCall(id: string): ToolCall | undefined {
		return state.toolCallsList.find(tc => tc.id === id);
	}

	function updateToolCall(id: string, updates: Partial<ToolCall>) {
		const idx = state.toolCallsList.findIndex(tc => tc.id === id);
		if (idx >= 0) {
			state.toolCallsList[idx] = { ...state.toolCallsList[idx], ...updates };
		}
	}

	// Derived state
	const isStreaming = $derived(state.streamingMessageId !== null);
	const isConnected = $derived(state.status === 'connected');
	const isRunning = $derived(state.status === 'connecting' || isStreaming);

	// Get all messages including streaming
	const allMessages = $derived(() => {
		const msgs = [...state.messages];
		if (state.streamingMessageId && state.streamingContent) {
			// Check if streaming message already exists
			const existingIdx = msgs.findIndex((m) => m.id === state.streamingMessageId);
			if (existingIdx >= 0) {
				msgs[existingIdx] = {
					...msgs[existingIdx],
					content: state.streamingContent
				};
			} else {
				msgs.push({
					id: state.streamingMessageId,
					role: 'assistant',
					content: state.streamingContent
				});
			}
		}
		return msgs;
	});

	// Event handlers
	function handleEvent(event: AgentEvent) {
		switch (event.type) {
			case 'RUN_STARTED':
				state.status = 'connected';
				state.threadId = event.threadId;
				state.runId = event.runId;
				state.error = null;
				break;

			case 'RUN_FINISHED':
				state.status = 'connected';
				// Finalize any streaming message
				if (state.streamingMessageId && state.streamingContent) {
					const existingIdx = state.messages.findIndex(
						(m) => m.id === state.streamingMessageId
					);
					if (existingIdx >= 0) {
						state.messages[existingIdx].content = state.streamingContent;
					} else {
						state.messages.push({
							id: state.streamingMessageId,
							role: 'assistant',
							content: state.streamingContent
						});
					}
				}
				state.streamingMessageId = null;
				state.streamingContent = '';
				state.currentStep = null;
				break;

			case 'RUN_ERROR':
				state.status = 'error';
				state.error = event.message;
				state.streamingMessageId = null;
				state.streamingContent = '';
				break;

			case 'STEP_STARTED':
				state.currentStep = event.stepName;
				break;

			case 'STEP_FINISHED':
				state.currentStep = null;
				break;

			case 'TEXT_MESSAGE_START':
				state.streamingMessageId = event.messageId;
				state.streamingContent = '';
				break;

			case 'TEXT_MESSAGE_CONTENT':
				if (event.messageId === state.streamingMessageId) {
					state.streamingContent += event.delta;
				}
				break;

			case 'TEXT_MESSAGE_END':
				if (event.messageId === state.streamingMessageId) {
					// Finalize the message
					state.messages.push({
						id: state.streamingMessageId,
						role: 'assistant',
						content: state.streamingContent
					});
					state.streamingMessageId = null;
					state.streamingContent = '';
				}
				break;

			case 'TEXT_MESSAGE_CHUNK':
				// Convenience event - handle as combined start/content/end
				if (!state.streamingMessageId) {
					state.streamingMessageId = event.messageId;
					state.streamingContent = '';
				}
				state.streamingContent += event.content;
				break;

			case 'TOOL_CALL_START':
				// Add new tool call to array (creates new array for reactivity)
				state.toolCallsList = [...state.toolCallsList, {
					id: event.toolCallId,
					// Handle both toolCallName (spec) and toolName (backend variant)
					name: event.toolCallName || (event as any).toolName || 'unknown',
					args: '',
					status: 'running'
				}];
				break;

			case 'TOOL_CALL_ARGS':
				const toolCall = findToolCall(event.toolCallId);
				if (toolCall) {
					updateToolCall(event.toolCallId, { args: toolCall.args + event.delta });
				}
				break;

			case 'TOOL_CALL_END':
				updateToolCall(event.toolCallId, { status: 'completed' });
				break;

			case 'TOOL_CALL_RESULT':
				// Handle both content (spec) and result (backend variant)
				updateToolCall(event.toolCallId, {
					result: event.content || (event as any).result,
					status: 'completed'
				});
				break;

			default:
				// Handle backend variant event types not in AG-UI spec
				if ((event as any).type === 'TOOL_RESULT') {
					updateToolCall((event as any).toolCallId, {
						result: (event as any).content || (event as any).result,
						status: 'completed'
					});
				}
				break;

			case 'STATE_SNAPSHOT':
				state.agentState = event.snapshot;
				break;

			case 'STATE_DELTA':
				// Apply JSON Patch operations
				for (const op of event.delta) {
					const path = op.path.split('/').filter(Boolean);
					if (op.op === 'add' || op.op === 'replace') {
						let obj: Record<string, unknown> = state.agentState;
						for (let i = 0; i < path.length - 1; i++) {
							if (!(path[i] in obj)) {
								obj[path[i]] = {};
							}
							obj = obj[path[i]] as Record<string, unknown>;
						}
						obj[path[path.length - 1]] = op.value;
					} else if (op.op === 'remove') {
						let obj: Record<string, unknown> = state.agentState;
						for (let i = 0; i < path.length - 1; i++) {
							obj = obj[path[i]] as Record<string, unknown>;
						}
						delete obj[path[path.length - 1]];
					}
				}
				break;

			case 'MESSAGES_SNAPSHOT':
				state.messages = event.messages;
				break;

			case 'CUSTOM':
				// Emit custom event - could be handled by subscribers
				console.log('Custom event:', event.name, event.value);
				break;
		}
	}

	// Add a user message
	function addUserMessage(content: string): Message {
		const message: Message = {
			id: createId(),
			role: 'user',
			content,
			createdAt: new Date().toISOString()
		};
		state.messages.push(message);
		return message;
	}

	// Clear conversation
	function clear() {
		state.messages = [];
		state.streamingMessageId = null;
		state.streamingContent = '';
		state.toolCallsList = [];
		state.agentState = {};
		state.threadId = null;
		state.runId = null;
		state.error = null;
		state.currentStep = null;
	}

	// Reset error
	function clearError() {
		state.error = null;
		if (state.status === 'error') {
			state.status = 'disconnected';
		}
	}

	return {
		// State (read-only access)
		get status() { return state.status; },
		get error() { return state.error; },
		get threadId() { return state.threadId; },
		get runId() { return state.runId; },
		get messages() { return state.messages; },
		get streamingMessageId() { return state.streamingMessageId; },
		get streamingContent() { return state.streamingContent; },
		get toolCalls() { return state.toolCallsList; },
		get agentState() { return state.agentState; },
		get currentStep() { return state.currentStep; },

		// Derived
		get isStreaming() { return isStreaming; },
		get isConnected() { return isConnected; },
		get isRunning() { return isRunning; },
		get allMessages() { return allMessages(); },

		// Methods
		handleEvent,
		addUserMessage,
		clear,
		clearError,

		// Internal state mutation (for agent client)
		_setStatus(status: ConnectionStatus) { state.status = status; },
		_setError(error: string | null) { state.error = error; },
		_setThreadId(threadId: string) { state.threadId = threadId; },
		_addMessage(message: Message) { state.messages.push(message); }
	};
}

export type AgentState = ReturnType<typeof createAgentState>;

/**
 * AG-UI HTTP Agent Client
 * Connects to an AG-UI compatible backend via SSE
 */
export function createAgentClient(config: {
	url: string;
	headers?: Record<string, string> | (() => Record<string, string>) | (() => Promise<Record<string, string>>);
}) {
	let abortController: AbortController | null = null;

	/**
	 * Resolve headers - supports static object, sync function, or async function
	 */
	async function resolveHeaders(): Promise<Record<string, string>> {
		if (!config.headers) return {};
		if (typeof config.headers === 'function') {
			return await config.headers();
		}
		return config.headers;
	}

	/**
	 * Run the agent with the given configuration
	 */
	async function run(
		agentState: AgentState,
		runConfig: RunConfig
	): Promise<void> {
		// Abort any existing run
		abort();

		abortController = new AbortController();
		agentState._setStatus('connecting');
		agentState._setError(null);

		try {
			// Resolve headers dynamically (supports async token fetching)
			const headers = await resolveHeaders();

			const response = await fetch(config.url, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					Accept: 'text/event-stream',
					...headers
				},
				body: JSON.stringify(runConfig),
				signal: abortController.signal
			});

			if (!response.ok) {
				const errorText = await response.text();
				throw new Error(`HTTP ${response.status}: ${errorText}`);
			}

			if (!response.body) {
				throw new Error('No response body');
			}

			// Read the SSE stream
			const reader = response.body.getReader();
			const decoder = new TextDecoder();
			let buffer = '';

			while (true) {
				const { done, value } = await reader.read();
				if (done) break;

				buffer += decoder.decode(value, { stream: true });
				const lines = buffer.split('\n');
				buffer = lines.pop() || '';

				for (const line of lines) {
					const event = parseSSELine(line);
					if (event) {
						agentState.handleEvent(event);
					}
				}
			}

			// Process any remaining buffer
			if (buffer.trim()) {
				const event = parseSSELine(buffer);
				if (event) {
					agentState.handleEvent(event);
				}
			}
		} catch (err) {
			if (err instanceof Error && err.name === 'AbortError') {
				// Run was aborted, not an error
				agentState._setStatus('disconnected');
			} else {
				agentState._setStatus('error');
				agentState._setError(err instanceof Error ? err.message : 'Unknown error');
			}
		} finally {
			abortController = null;
		}
	}

	/**
	 * Abort the current run
	 */
	function abort() {
		if (abortController) {
			abortController.abort();
			abortController = null;
		}
	}

	return {
		run,
		abort
	};
}

export type AgentClient = ReturnType<typeof createAgentClient>;
