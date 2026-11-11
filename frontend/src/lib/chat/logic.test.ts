import { describe, expect, it } from 'vitest';
import { activitySummary, applyOutcome, buildChatRequest, segmentParts, toolLabel, type ToolPart } from './logic';

describe('buildChatRequest', () => {
	it('sends only id, newest message, trigger and context', () => {
		const body = buildChatRequest({ id: 'c1', messages: [{ id: 'a' }, { id: 'b' }], trigger: 'submit-message' });
		expect(body).toEqual({ id: 'c1', message: { id: 'b' }, trigger: 'submit-message', context: null });
		const withCtx = buildChatRequest({ id: 'c1', messages: [{ id: 'a' }], trigger: 'regenerate-message', context: { batch_id: 14 } });
		expect(withCtx.context).toEqual({ batch_id: 14 });
	});
});

describe('toolLabel', () => {
	it('maps known tools by state and humanizes unknown ones', () => {
		expect(toolLabel('get_recipe', 'output-available')).toBe('Loaded recipe');
		expect(toolLabel('get_recipe', 'input-available')).toBe('Loading recipe');
		expect(toolLabel('calc_water_profile', 'output-available')).toBe('Calc water profile');
	});
});

describe('applyOutcome', () => {
	const base = { type: 'tool-apply_hop_inventory' } as const;
	it('applied only when applied === true and no error', () => {
		expect(applyOutcome({ ...base, state: 'output-available', output: { applied: true } }).phase).toBe('applied');
		expect(applyOutcome({ ...base, state: 'output-available', output: { applied: true, error: 'x' } }).phase).toBe('failed');
		expect(applyOutcome({ ...base, state: 'output-available', output: { applied: false } }).phase).toBe('failed');
		expect(applyOutcome({ ...base, state: 'output-available', output: 'ok' }).phase).toBe('failed');
		expect(applyOutcome({ ...base, state: 'output-available', output: null }).phase).toBe('failed');
	});
	it('surfaces the error message', () => {
		const r = applyOutcome({ ...base, state: 'output-available', output: { error: 'Stock changed' } } as ToolPart);
		expect(r).toEqual({ phase: 'failed', message: 'Stock changed' });
		expect(applyOutcome({ ...base, state: 'output-error' }).phase).toBe('failed');
	});
	it('maps pending and denied states', () => {
		expect(applyOutcome({ ...base, state: 'approval-requested' }).phase).toBe('proposed');
		expect(applyOutcome({ ...base, state: 'output-denied' }).phase).toBe('denied');
	});
});

describe('segmentParts', () => {
	it('merges reasoning and read-only tools into one leading group', () => {
		const segs = segmentParts([
			{ type: 'reasoning', text: 'hm', state: 'done' },
			{ type: 'tool-get_recipe', state: 'output-available' },
			{ type: 'text', text: 'hi' },
			{ type: 'tool-preview_hop_inventory', state: 'output-available' },
			{ type: 'tool-apply_hop_inventory', state: 'approval-requested' }
		]);
		expect(segs.map((s) => s.kind)).toEqual(['activity', 'text', 'apply']);
		expect(segs[0].kind === 'activity' && segs[0].parts.length).toBe(3);
	});
	it('drops empty reasoning', () => {
		expect(segmentParts([{ type: 'reasoning', text: '  ', state: 'done' }])).toEqual([]);
	});
});

describe('activitySummary', () => {
	it('shows the running label while a tool runs, then the done labels', () => {
		const running = activitySummary([{ type: 'tool-get_recipe', state: 'input-available' }]);
		expect(running).toMatchObject({ text: 'Loading recipe…', running: true });
		const done = activitySummary([
			{ type: 'tool-search_inventory_hops', state: 'output-available' },
			{ type: 'tool-get_recipe', state: 'output-available' }
		]);
		expect(done).toMatchObject({ text: 'Checked hop stock, Loaded recipe', running: false, steps: 2 });
	});
});
