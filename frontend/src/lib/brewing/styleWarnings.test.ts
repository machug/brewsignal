import { describe, it, expect } from 'vitest';
import { computeStyleWarnings } from './styleWarnings';

const style = { og_min: 1.045, og_max: 1.06, fg_min: 1.01, fg_max: 1.015, abv_min: 4.5, abv_max: 6.2, ibu_min: 30, ibu_max: 50, srm_min: 5, srm_max: 10 };
const inside = { og: 1.05, fg: 1.012, abv: 5, ibu: 40, srm: 7 };

describe('computeStyleWarnings', () => {
	it('no warnings inside the range', () => {
		expect(computeStyleWarnings(style, inside)).toEqual([]);
	});
	it('bounds are inclusive', () => {
		expect(computeStyleWarnings(style, { ...inside, srm: 5 })).toEqual([]);
		expect(computeStyleWarnings(style, { ...inside, srm: 10 })).toEqual([]);
		expect(computeStyleWarnings(style, { og: 1.045, fg: 1.015, abv: 6.2, ibu: 30, srm: 5 })).toEqual([]);
	});
	it('compares at displayed precision', () => {
		// 4.6 displays as "5 SRM" so it is inside 5-10
		expect(computeStyleWarnings(style, { ...inside, srm: 4.6 })).toEqual([]);
		expect(computeStyleWarnings(style, { ...inside, srm: 10.4 })).toEqual([]);
		expect(computeStyleWarnings(style, { ...inside, ibu: 29.6 })).toEqual([]);
	});
	it('flags values beyond the rounded bounds', () => {
		expect(computeStyleWarnings(style, { ...inside, srm: 4 })[0].stat).toBe('Color');
		expect(computeStyleWarnings(style, { ...inside, srm: 11 })[0].stat).toBe('Color');
		expect(computeStyleWarnings(style, { ...inside, og: 1.07 })[0].stat).toBe('OG');
	});
	it('no style gives none', () => {
		expect(computeStyleWarnings(null, inside)).toEqual([]);
	});
});
