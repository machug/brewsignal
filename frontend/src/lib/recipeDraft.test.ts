import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import { buildDraft, createDraftCalculator } from './recipeDraft';
import type { CalculatedStats, RecipeDraft } from './api';

const stats = (og: number): CalculatedStats => ({
	og, fg: 1.01, abv: 5, ibu: 30, srm: 5, bu_gu: 0.6, calories_per_330ml: 150, color_hex: '#fc0', assumptions: []
});
const draft = (): RecipeDraft => ({ fermentables: [], hops: [], cultures: [] });

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('createDraftCalculator', () => {
	test('keeps last stats when calculate fails', async () => {
		let shown: CalculatedStats | null = null;
		let stale = false;
		const calculate = vi.fn().mockResolvedValueOnce(stats(1.05)).mockRejectedValueOnce(new Error('offline'));
		const calc = createDraftCalculator({
			calculate, onResult: (s) => (shown = s), onStale: (v) => (stale = v)
		});
		calc.request(draft());
		await vi.advanceTimersByTimeAsync(200);
		expect(shown).toMatchObject({ og: 1.05 });
		expect(stale).toBe(false);

		calc.request(draft());
		await vi.advanceTimersByTimeAsync(200);
		expect(shown).toMatchObject({ og: 1.05 });
		expect(stale).toBe(true);
	});

	test('debounces 200 ms and aborts the previous request', async () => {
		const signals: AbortSignal[] = [];
		const calculate = vi.fn((_d: RecipeDraft, s?: AbortSignal) => {
			signals.push(s!);
			return new Promise<CalculatedStats | null>(() => {});
		});
		const results: unknown[] = [];
		const calc = createDraftCalculator({ calculate, onResult: (s) => results.push(s), onStale: () => {} });
		calc.request(draft());
		calc.request(draft());
		await vi.advanceTimersByTimeAsync(199);
		expect(calculate).not.toHaveBeenCalled();
		await vi.advanceTimersByTimeAsync(1);
		expect(calculate).toHaveBeenCalledTimes(1);
		calc.request(draft());
		expect(signals[0].aborted).toBe(true);
	});

	test('a null result (no fermentables) is shown, not treated as failure', async () => {
		let shown: CalculatedStats | null = stats(1.05);
		let stale = true;
		const calc = createDraftCalculator({
			calculate: vi.fn().mockResolvedValue(null), onResult: (s) => (shown = s), onStale: (v) => (stale = v)
		});
		calc.request(draft());
		await vi.advanceTimersByTimeAsync(200);
		expect(shown).toBeNull();
		expect(stale).toBe(false);
	});
});

describe('buildDraft', () => {
	test('maps editor state to the calculate payload', () => {
		const d = buildDraft({
			batchSizeLiters: 20, efficiencyPercent: 72,
			fermentables: [{ name: 'Pale', amount_kg: 4, potential_sg: 1.037, color_srm: 2, type: 'base' }, { name: 'X', amount_kg: 1, potential_sg: 9 }],
			hops: [
				{ name: 'Citra', amount_grams: 30, alpha_acid_percent: 12, boil_time_minutes: 20, use: 'whirlpool', whirlpool_temp_c: 80 },
				{ name: 'Dry', amount_grams: 50, boil_time_minutes: 5760, use: 'dry_hop' },
				{ name: 'Ext', amount_grams: 9, is_extract: true, use: 'dry_hop' }
			],
			yeast: { attenuation_low: 73, attenuation_high: 77 }
		});
		expect(d.fermentables[1].potential_sg).toBeUndefined();
		expect(d.hops[0].timing).toEqual({ use: 'whirlpool', duration: { value: 20, unit: 'min' }, temperature: { value: 80, unit: 'C' } });
		expect(d.hops[1].timing.duration).toBeUndefined();
		expect(d.hops[2]).toMatchObject({ amount_grams: 0, is_extract: true });
		expect(d.cultures).toEqual([{ attenuation_min_percent: 73, attenuation_max_percent: 77 }]);
	});
});
