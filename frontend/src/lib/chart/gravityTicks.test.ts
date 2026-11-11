import { describe, it, expect } from 'vitest';
import { gravityIncrs, type GravityUnits } from './gravityTicks';
// Same polynomial as sgToPlato in config.svelte.ts (a rune module cannot load in vitest); Brix = Plato there.
const sgToPlato = (sg: number) => -616.868 + 1111.14 * sg - 630.272 * sg ** 2 + 135.997 * sg ** 3;
const sgToBrix = sgToPlato;

const label: Record<GravityUnits, (sg: number) => string> = {
	sg: (sg) => sg.toFixed(3),
	plato: (sg) => sgToPlato(sg).toFixed(1),
	brix: (sg) => sgToBrix(sg).toFixed(1)
};

describe('gravityIncrs', () => {
	for (const units of ['sg', 'plato', 'brix'] as const) {
		it(`${units}: tick labels never repeat across 1.010-1.060`, () => {
			for (const inc of gravityIncrs(units)) {
				const labels: string[] = [];
				for (let i = Math.ceil(1.01 / inc); i * inc <= 1.06 + 1e-9; i++) labels.push(label[units](i * inc));
				expect(new Set(labels).size, `${units} step ${inc}`).toBe(labels.length);
			}
		});
	}
});
