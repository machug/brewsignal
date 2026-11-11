import { describe, it, expect } from 'vitest';
import { batchWarnings } from './batchWarnings';

describe('batchWarnings', () => {
	it('is empty when healthy or no reading', () => {
		expect(batchWarnings({})).toEqual([]);
		expect(batchWarnings({ reading: { paired: true }, tempStatus: 'in_range' })).toEqual([]);
	});
	it('collects anomaly, unpaired and temperature', () => {
		expect(
			batchWarnings({ reading: { is_anomaly: true, anomaly_reasons: ['jump'], paired: false }, tempStatus: 'too_hot' })
		).toEqual(['Anomaly', 'Not logging', 'Above yeast range']);
		expect(batchWarnings({ tempStatus: 'too_cold' })).toEqual(['Below yeast range']);
	});
});
