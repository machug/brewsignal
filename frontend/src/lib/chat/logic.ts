// Pure helpers for the assistant chat UI (request body, tool labels, part grouping, apply outcome).

export interface ToolPart {
	type: string;
	state:
		| 'input-streaming'
		| 'input-available'
		| 'approval-requested'
		| 'approval-responded'
		| 'output-available'
		| 'output-error'
		| 'output-denied';
	toolCallId?: string;
	input?: any;
	output?: any;
	errorText?: string;
	approval?: { id: string; approved?: boolean; reason?: string };
}

interface AnyPart {
	type: string;
	[k: string]: any;
}

export const isToolPart = (p: { type: string }) => p.type.startsWith('tool-');
export const toolName = (p: { type: string }) => p.type.slice(5);
export const APPLY_TOOL = 'apply_hop_inventory';
/** Tools that write after the user approves a card (tilt_ui-eevz.1). */
export const APPROVAL_TOOLS = new Set([APPLY_TOOL, 'save_recipe', 'update_recipe']);

/** Body the backend expects (contract): only the newest message, never history. */
export function buildChatRequest(opts: {
	id: string;
	messages: unknown[];
	trigger: string;
	context?: { batch_id: number } | null;
}) {
	return {
		id: opts.id,
		message: opts.messages.at(-1),
		trigger: opts.trigger,
		context: opts.context ?? null
	};
}

// [running label, done label]
const LABELS: Record<string, [string, string]> = {
	get_recipe: ['Loading recipe', 'Loaded recipe'],
	preview_recipe: ['Checking recipe', 'Checked recipe'],
	list_recipes: ['Listing recipes', 'Listed recipes'],
	search_recipes: ['Searching recipes', 'Searched recipes'],
	search_inventory_hops: ['Checking hop stock', 'Checked hop stock'],
	list_hop_inventory: ['Checking hop stock', 'Checked hop stock'],
	preview_hop_inventory: ['Drafting stock update', 'Drafted stock update'],
	get_batch: ['Loading batch', 'Loaded batch'],
	list_batches: ['Listing batches', 'Listed batches'],
	get_equipment: ['Loading equipment', 'Loaded equipment'],
	list_yeast_inventory: ['Checking yeast stock', 'Checked yeast stock'],
	list_fermentables_inventory: ['Checking grain stock', 'Checked grain stock']
};

const humanize = (n: string) => {
	const s = n.replaceAll('_', ' ').trim();
	return s.charAt(0).toUpperCase() + s.slice(1);
};

const isRunning = (t: ToolPart) => t.state === 'input-streaming' || t.state === 'input-available' || t.state === 'approval-responded';

/** Friendly label for a tool call. Unknown tools fall back to the humanized name. */
export function toolLabel(name: string, state: ToolPart['state']): string {
	const l = LABELS[name];
	if (!l) return humanize(name);
	return isRunning({ state } as ToolPart) ? l[0] : l[1];
}

export type Segment =
	| { kind: 'activity'; parts: AnyPart[] }
	| { kind: 'text'; part: AnyPart }
	| { kind: 'apply'; part: AnyPart };

/**
 * One activity group per turn (reasoning + read-only tools, incl. the
 * preview tool whose output the approval card supersedes), placed first;
 * text and apply cards keep their order after it.
 */
export function segmentParts(parts: AnyPart[]): Segment[] {
	const activity: AnyPart[] = [];
	const rest: Segment[] = [];
	for (const p of parts) {
		if (p.type === 'reasoning') {
			if (p.text?.trim() || p.state === 'streaming') activity.push(p);
		} else if (p.type === 'text') {
			rest.push({ kind: 'text', part: p });
		} else if (isToolPart(p)) {
			if (APPROVAL_TOOLS.has(toolName(p))) rest.push({ kind: 'apply', part: p });
			else activity.push(p);
		}
	}
	return activity.length ? [{ kind: 'activity', parts: activity }, ...rest] : rest;
}

/** Collapsed-row summary, e.g. "Checked hop stock, Loaded recipe". */
export function activitySummary(parts: AnyPart[]): { text: string; running: boolean; steps: number } {
	const tools = parts.filter(isToolPart) as unknown as ToolPart[];
	const running = tools.some(isRunning) || parts.some((p) => p.type === 'reasoning' && p.state === 'streaming');
	const labels: string[] = [];
	for (const t of tools) {
		const l = toolLabel(toolName(t), t.state);
		if (!labels.includes(l)) labels.push(l);
	}
	const live = tools.findLast(isRunning);
	const text = live ? `${toolLabel(toolName(live), live.state)}…` : labels.join(', ') || (running ? 'Thinking…' : 'Thought it through');
	return { text, running, steps: parts.length };
}

export type ApplyOutcome =
	| { phase: 'proposed' }
	| { phase: 'running' }
	| { phase: 'applied'; plan: any }
	| { phase: 'failed'; message: string }
	| { phase: 'denied' }
	| { phase: 'pending' };

/** Applied only when the tool output says applied === true; any error key or other shape is a failure. */
export function applyOutcome(t: ToolPart): ApplyOutcome {
	switch (t.state) {
		case 'approval-requested':
			return { phase: 'proposed' };
		case 'approval-responded':
		case 'input-available':
			return { phase: 'running' };
		case 'output-denied':
			return { phase: 'denied' };
		case 'output-error':
			return { phase: 'failed', message: t.errorText || 'The update could not be applied.' };
		case 'output-available': {
			const o = t.output;
			if (o && typeof o === 'object' && !o.error && o.applied === true) return { phase: 'applied', plan: o };
			const msg = o && typeof o === 'object' && typeof o.error === 'string' ? o.error : 'The update could not be applied.';
			return { phase: 'failed', message: msg };
		}
		default:
			return { phase: 'pending' };
	}
}

/** Group threads for the drawer by recency. */
export function relativeTime(iso: string, now = Date.now()): string {
	const d = new Date(iso.endsWith('Z') || /[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + 'Z').getTime();
	const mins = Math.floor((now - d) / 60000);
	if (mins < 1) return 'just now';
	if (mins < 60) return `${mins}m ago`;
	if (mins < 1440) return `${Math.floor(mins / 60)}h ago`;
	if (mins < 10080) return `${Math.floor(mins / 1440)}d ago`;
	return new Date(d).toLocaleDateString();
}

// Thin space between number and unit: a full mono space reads as a double space.
export const formatGrams = (n: number) => `${Math.round(n * 10) / 10}\u2009g`;

/** Short readable summary of a tool input, e.g. "recipe id 32". Objects and arrays are skipped. */
export function summarizeInput(input: unknown): string {
	if (!input || typeof input !== 'object') return '';
	return Object.entries(input as Record<string, unknown>)
		.filter(([, v]) => ['string', 'number', 'boolean'].includes(typeof v))
		.slice(0, 3)
		.map(([k, v]) => `${k.replaceAll('_', ' ')} ${String(v).slice(0, 40)}`)
		.join(', ');
}

/** UUID v4 that also works on plain-HTTP origins (the Pi on the LAN), where
 *  crypto.randomUUID is undefined because it needs a secure context. */
export function newChatId(): string {
	const b = crypto.getRandomValues(new Uint8Array(16));
	b[6] = (b[6] & 0x0f) | 0x40;
	b[8] = (b[8] & 0x3f) | 0x80;
	const h = [...b].map((x) => x.toString(16).padStart(2, '0')).join('');
	return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}
