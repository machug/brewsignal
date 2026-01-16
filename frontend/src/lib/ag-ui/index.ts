/**
 * AG-UI Svelte Client
 * A Svelte 5 native implementation of the Agent-User Interaction Protocol
 *
 * @example
 * ```svelte
 * <script lang="ts">
 *   import { useAgent } from '$lib/ag-ui';
 *
 *   const agent = useAgent({
 *     url: '/api/assistant/stream',
 *     tools: [{ name: 'lookup_yeast', ... }],
 *     onStateChange: (state) => console.log('State:', state)
 *   });
 * </script>
 *
 * <button onclick={() => agent.send('Create an IPA recipe')}>
 *   Send
 * </button>
 *
 * {#each agent.messages as message}
 *   <div>{message.content}</div>
 * {/each}
 *
 * {#if agent.isStreaming}
 *   <div>{agent.streamingContent}</div>
 * {/if}
 * ```
 */

// Types
export type {
	EventType,
	BaseEvent,
	AgentEvent,
	RunStartedEvent,
	RunFinishedEvent,
	RunErrorEvent,
	StepStartedEvent,
	StepFinishedEvent,
	TextMessageStartEvent,
	TextMessageContentEvent,
	TextMessageEndEvent,
	TextMessageChunkEvent,
	ToolCallStartEvent,
	ToolCallArgsEvent,
	ToolCallEndEvent,
	ToolCallResultEvent,
	ToolCallChunkEvent,
	StateSnapshotEvent,
	StateDeltaEvent,
	MessagesSnapshotEvent,
	ActivitySnapshotEvent,
	ActivityDeltaEvent,
	RawEvent,
	CustomEvent,
	Message,
	ToolCall,
	ToolDefinition,
	RunConfig,
	RunResult,
	ConnectionStatus
} from './types';

// Client
export {
	createAgentState,
	createAgentClient,
	type AgentState,
	type AgentClient
} from './client.svelte';

// Hook
export {
	useAgent,
	type UseAgentConfig,
	type UseAgentReturn
} from './useAgent.svelte';
