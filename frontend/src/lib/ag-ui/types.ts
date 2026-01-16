/**
 * AG-UI Protocol Types for Svelte
 * Based on the Agent-User Interaction Protocol specification
 */

// Event type discriminators
export type EventType =
	// Lifecycle
	| 'RUN_STARTED'
	| 'RUN_FINISHED'
	| 'RUN_ERROR'
	| 'STEP_STARTED'
	| 'STEP_FINISHED'
	// Text messages
	| 'TEXT_MESSAGE_START'
	| 'TEXT_MESSAGE_CONTENT'
	| 'TEXT_MESSAGE_END'
	| 'TEXT_MESSAGE_CHUNK'
	// Tool calls
	| 'TOOL_CALL_START'
	| 'TOOL_CALL_ARGS'
	| 'TOOL_CALL_END'
	| 'TOOL_CALL_RESULT'
	| 'TOOL_RESULT' // Backend variant
	| 'TOOL_CALL_CHUNK'
	// State management
	| 'STATE_SNAPSHOT'
	| 'STATE_DELTA'
	| 'MESSAGES_SNAPSHOT'
	// Activity
	| 'ACTIVITY_SNAPSHOT'
	| 'ACTIVITY_DELTA'
	// Special
	| 'RAW'
	| 'CUSTOM';

// Base event interface
export interface BaseEvent {
	type: EventType;
	timestamp?: string;
	rawEvent?: unknown;
}

// Lifecycle events
export interface RunStartedEvent extends BaseEvent {
	type: 'RUN_STARTED';
	threadId: string;
	runId: string;
	parentRunId?: string;
	input?: unknown;
}

export interface RunFinishedEvent extends BaseEvent {
	type: 'RUN_FINISHED';
	threadId: string;
	runId: string;
	result?: unknown;
}

export interface RunErrorEvent extends BaseEvent {
	type: 'RUN_ERROR';
	message: string;
	code?: string;
}

export interface StepStartedEvent extends BaseEvent {
	type: 'STEP_STARTED';
	stepName: string;
}

export interface StepFinishedEvent extends BaseEvent {
	type: 'STEP_FINISHED';
	stepName: string;
}

// Text message events
export interface TextMessageStartEvent extends BaseEvent {
	type: 'TEXT_MESSAGE_START';
	messageId: string;
	role: 'assistant' | 'user' | 'system';
}

export interface TextMessageContentEvent extends BaseEvent {
	type: 'TEXT_MESSAGE_CONTENT';
	messageId: string;
	delta: string;
}

export interface TextMessageEndEvent extends BaseEvent {
	type: 'TEXT_MESSAGE_END';
	messageId: string;
}

export interface TextMessageChunkEvent extends BaseEvent {
	type: 'TEXT_MESSAGE_CHUNK';
	messageId: string;
	role: 'assistant' | 'user' | 'system';
	content: string;
}

// Tool call events
export interface ToolCallStartEvent extends BaseEvent {
	type: 'TOOL_CALL_START';
	toolCallId: string;
	toolCallName: string;
	parentMessageId?: string;
}

export interface ToolCallArgsEvent extends BaseEvent {
	type: 'TOOL_CALL_ARGS';
	toolCallId: string;
	delta: string;
}

export interface ToolCallEndEvent extends BaseEvent {
	type: 'TOOL_CALL_END';
	toolCallId: string;
}

export interface ToolCallResultEvent extends BaseEvent {
	type: 'TOOL_CALL_RESULT';
	toolCallId: string;
	messageId: string;
	content: string;
}

export interface ToolCallChunkEvent extends BaseEvent {
	type: 'TOOL_CALL_CHUNK';
	toolCallId: string;
	toolCallName: string;
	args?: string;
	result?: string;
}

// State management events
export interface StateSnapshotEvent extends BaseEvent {
	type: 'STATE_SNAPSHOT';
	snapshot: Record<string, unknown>;
}

export interface StateDeltaEvent extends BaseEvent {
	type: 'STATE_DELTA';
	delta: Array<{
		op: 'add' | 'remove' | 'replace';
		path: string;
		value?: unknown;
	}>;
}

export interface MessagesSnapshotEvent extends BaseEvent {
	type: 'MESSAGES_SNAPSHOT';
	messages: Message[];
}

// Activity events
export interface ActivitySnapshotEvent extends BaseEvent {
	type: 'ACTIVITY_SNAPSHOT';
	messageId: string;
	activityType: string;
	content: unknown;
}

export interface ActivityDeltaEvent extends BaseEvent {
	type: 'ACTIVITY_DELTA';
	messageId: string;
	delta: Array<{
		op: 'add' | 'remove' | 'replace';
		path: string;
		value?: unknown;
	}>;
}

// Special events
export interface RawEvent extends BaseEvent {
	type: 'RAW';
	event: unknown;
	source?: string;
}

export interface CustomEvent extends BaseEvent {
	type: 'CUSTOM';
	name: string;
	value: unknown;
}

// Union type for all events
export type AgentEvent =
	| RunStartedEvent
	| RunFinishedEvent
	| RunErrorEvent
	| StepStartedEvent
	| StepFinishedEvent
	| TextMessageStartEvent
	| TextMessageContentEvent
	| TextMessageEndEvent
	| TextMessageChunkEvent
	| ToolCallStartEvent
	| ToolCallArgsEvent
	| ToolCallEndEvent
	| ToolCallResultEvent
	| ToolCallChunkEvent
	| StateSnapshotEvent
	| StateDeltaEvent
	| MessagesSnapshotEvent
	| ActivitySnapshotEvent
	| ActivityDeltaEvent
	| RawEvent
	| CustomEvent;

// Message types for chat
export interface Message {
	id: string;
	role: 'user' | 'assistant' | 'system';
	content: string;
	toolCalls?: ToolCall[];
	createdAt?: string;
}

export interface ToolCall {
	id: string;
	name: string;
	args: string;
	result?: string;
	status: 'pending' | 'running' | 'completed' | 'error';
}

// Tool definition for agent capabilities
export interface ToolDefinition {
	name: string;
	description: string;
	parameters: {
		type: 'object';
		properties: Record<string, {
			type: string;
			description?: string;
			enum?: string[];
		}>;
		required?: string[];
	};
}

// Agent run configuration
export interface RunConfig {
	threadId?: string;
	messages: Message[];
	tools?: ToolDefinition[];
	state?: Record<string, unknown>;
	metadata?: Record<string, unknown>;
}

// Agent run result
export interface RunResult {
	threadId: string;
	runId: string;
	messages: Message[];
	state?: Record<string, unknown>;
	error?: string;
}

// Connection status
export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error';
