import { describe, expect, test } from 'vitest';
import { describeBUGU } from './calculations';

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
