import { describe, expect, it } from 'vitest';
import type { HistoricalReading } from '$lib/api';
import { analyseSg } from './sgStats';

const T0 = Date.UTC(2026, 10, 11, 8, 0);
const HOUR = 60 * 60 * 1000;

function reading(hours: number, sg: number | null): HistoricalReading {
	return { timestamp: new Date(T0 + hours * HOUR).toISOString(), sg_calibrated: sg, sg_raw: sg } as HistoricalReading;
}

describe('analyseSg', () => {
	it('rate is the slope of the last 12 h, not the whole-window average', () => {
		// 36 h flat lag phase, then 12 h dropping 1 point per hour
		const readings = [
			...Array.from({ length: 36 }, (_, h) => reading(h, 1.05)),
			...Array.from({ length: 13 }, (_, h) => reading(36 + h, 1.05 - 0.001 * h))
		];
		const stats = analyseSg(readings, 1.05)!;
		expect(stats.fermRate).toBeCloseTo(-0.024, 3); // whole-window average would be -0.006
	});

	it('stable-for uses the right timestamp when a reading is filtered out', () => {
		// The outlier at hour 1 used to shift every later index by one
		const readings = [reading(0, 1.02), reading(1, 9.999), reading(2, 1.02), reading(3, 1.012), reading(9, 1.012)];
		expect(analyseSg(readings, null)!.daysAtCurrentSg).toBeCloseTo(6 / 24, 5);
	});

	it('stable-for is the whole window when gravity never moved', () => {
		const readings = Array.from({ length: 49 }, (_, h) => reading(h, 1.012));
		expect(analyseSg(readings, null)!.daysAtCurrentSg).toBeCloseTo(2, 5);
	});
});
