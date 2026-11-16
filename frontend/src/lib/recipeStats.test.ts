import { describe, expect, test } from 'vitest';
import { batchExpected, effectiveStats, statDiffers } from './recipeStats';
import type { CalculatedStats } from './api';

const calc: CalculatedStats = {
	og: 1.05, fg: 1.01, abv: 5.2, ibu: 37, srm: 6, bu_gu: 0.74,
	calories_per_330ml: 160, color_hex: '#ffcc00', assumptions: ['Assumed 75% brewhouse efficiency']
};

describe('effectiveStats', () => {
	test('calculated wins and carries assumptions', () => {
		const s = effectiveStats({ calculated: calc, target_og: 1.06 });
		expect(s).toMatchObject({ source: 'calculated', og: 1.05, ibu: 37, colorHex: '#ffcc00', buGu: 0.74 });
		expect(s.assumptions).toEqual(['Assumed 75% brewhouse efficiency']);
	});
	test('declared when only targets exist', () => {
		const s = effectiveStats({ calculated: null, target_og: 1.06, target_ibu: 40 });
		expect(s).toMatchObject({ source: 'declared', og: 1.06, ibu: 40 });
		expect(s.fg).toBeUndefined();
	});
	test('empty with no numbers, never invented defaults', () => {
		const s = effectiveStats({});
		expect(s.source).toBe('empty');
		expect(s.og).toBeUndefined();
		expect(s.ibu).toBeUndefined();
	});
});

describe('statDiffers', () => {
	test('gravity threshold is 0.002', () => {
		expect(statDiffers('og', 1.05, 1.052)).toBe(false);
		expect(statDiffers('og', 1.05, 1.053)).toBe(true);
	});
	test('IBU threshold is 2', () => {
		expect(statDiffers('ibu', 37, 39)).toBe(false);
		expect(statDiffers('ibu', 37, 39.5)).toBe(true);
	});
	test('missing values never differ', () => {
		expect(statDiffers('og', undefined, 1.05)).toBe(false);
		expect(statDiffers('og', 1.05, null)).toBe(false);
	});
});

describe('batchExpected', () => {
	const recipe = { calculated: calc };
	test('measured OG wins', () => {
		expect(batchExpected({ measured_og: 1.048, expected_og: 1.05, recipe }).og).toBe(1.048);
	});
	test('snapshot beats live recipe (recipe edited after fermenting started)', () => {
		const b = batchExpected({ expected_og: 1.07, expected_fg: 1.012, expected_abv: 7, recipe });
		expect(b).toMatchObject({ og: 1.07, fg: 1.012, abv: 7 });
	});
	test('planning batch uses live recipe stats', () => {
		expect(batchExpected({ recipe })).toMatchObject({ og: 1.05, fg: 1.01, ibu: 37 });
	});
	test('target view ignores measured OG', () => {
		expect(batchExpected({ measured_og: 1.048, expected_og: 1.05, recipe }, false).og).toBe(1.05);
	});
	test('no recipe and no snapshot gives nothing', () => {
		expect(batchExpected({}).fg).toBeUndefined();
	});
});
