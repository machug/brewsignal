/** Gravity-axis tick steps, in SG (chart data is always SG; Plato/Brix only convert labels). */
export type GravityUnits = 'sg' | 'plato' | 'brix';

// SG labels have 3 decimals, so steps never go below 0.001.
const SG_INCRS = [0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1];
// Plato/Brix labels have 1 decimal; ~240 deg per SG unit, so 0.0005 SG ~ 0.12 deg (always a new label).
// Roughly 0.12 / 0.25 / 0.5 / 1 / 2.5 / 5 / 10 degrees.
const DEGREE_INCRS = [0.0005, 0.001, 0.002, 0.004, 0.01, 0.02, 0.04];

export function gravityIncrs(units: GravityUnits): number[] {
	return units === 'sg' ? SG_INCRS : DEGREE_INCRS;
}
