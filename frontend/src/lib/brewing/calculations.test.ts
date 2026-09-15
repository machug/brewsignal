import { describe, expect, test } from 'vitest';
import { calculateIBU_Tinseth, describeBUGU, type Hop } from './calculations';

// Whirlpool stand temperature derate (tilt_ui-2mxj). Mirrors
// backend/tests/test_brewing_ibu.py::TestWhirlpoolStandTemperature.
function stand(tempC: number | null): number {
	const hop: Hop = {
		name: 'Nectaron',
		amount_grams: 30,
		alpha_acid_percent: 12,
		boil_time_minutes: 20,
		form: 'pellet',
		use: 'whirlpool',
		whirlpool_temp_c: tempC,
	};
	return calculateIBU_Tinseth(hop, 1.054, 21);
}

describe('whirlpool stand temperature', () => {
	test('80 °C stand is about a quarter of a hot stand', () => {
		expect(stand(80) / stand(null)).toBeCloseTo(0.229, 2);
	});

	test('100 °C stand matches the legacy hot stand', () => {
		expect(stand(100)).toBeCloseTo(stand(null), 6);
	});

	test('55 °C stand is near zero', () => {
		expect(stand(55)).toBeLessThan(1);
	});
});

// BU:GU balance bands (tilt_ui-idp9)
describe('describeBUGU', () => {
	test('in-style American Pale Ale is not Very Bitter', () => {
		// Hugh's Hoppy Pale after the whirlpool fix: 52 IBU at 1.054
		expect(describeBUGU(0.96)).toBe('Hoppy');
		expect(describeBUGU(0.8)).toBe('Hoppy');
	});

	test('band edges', () => {
		expect(describeBUGU(0.29)).toBe('Very Malty');
		expect(describeBUGU(0.3)).toBe('Malty');
		expect(describeBUGU(0.5)).toBe('Balanced');
		expect(describeBUGU(0.7)).toBe('Hoppy');
		expect(describeBUGU(1.0)).toBe('Very Bitter');
	});
});
