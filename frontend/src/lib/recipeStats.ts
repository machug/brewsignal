// Display rules for recipe and batch stats. The numbers come from the server
// (`calculated`, `target_*`, `expected_*`); nothing here does brewing maths.
import type { BatchResponse, CalculatedStats } from '$lib/api';

export type StatSource = 'calculated' | 'declared' | 'empty';

export interface StatValues {
	og?: number;
	fg?: number;
	abv?: number;
	ibu?: number;
	srm?: number;
}

export interface EffectiveStats extends StatValues {
	source: StatSource;
	assumptions: string[];
	// Only set from a calculation.
	colorHex?: string;
	buGu?: number;
	caloriesPer330ml?: number;
}

type RecipeLike = {
	calculated?: CalculatedStats | null;
	target_og?: number | null;
	target_fg?: number | null;
	target_abv?: number | null;
	target_ibu?: number | null;
	target_srm?: number | null;
};

const FIELDS = ['og', 'fg', 'abv', 'ibu', 'srm'] as const;

/** Per field: the calculated value, else the declared target, else nothing. */
export function effectiveStats(recipe: RecipeLike): EffectiveStats {
	const calc = recipe.calculated ?? null;
	const out: EffectiveStats = { source: 'empty', assumptions: calc?.assumptions ?? [] };
	let anyCalculated = false;
	let anyDeclared = false;
	for (const f of FIELDS) {
		const value = calc?.[f];
		const target = recipe[`target_${f}` as const];
		if (value != null) {
			out[f] = value;
			anyCalculated = true;
		} else if (target != null) {
			out[f] = target;
			anyDeclared = true;
		}
	}
	if (calc) {
		out.colorHex = calc.color_hex;
		out.buGu = calc.bu_gu;
		out.caloriesPer330ml = calc.calories_per_330ml;
	}
	out.source = anyCalculated ? 'calculated' : anyDeclared ? 'declared' : 'empty';
	return out;
}

/**
 * What a batch is expected to reach. OG prefers the measured value (unless
 * `includeMeasured` is false), then the snapshot taken when fermenting began.
 * Only planning and brewing batches have no snapshot and read the recipe's live
 * stats; from fermenting on the snapshot is frozen, even where a field is null.
 */
/** True once the batch's expected numbers are a frozen snapshot (fermenting or later). */
export function hasSnapshot(status: BatchResponse['status']): boolean {
	return status !== 'planning' && status !== 'brewing';
}

export function batchExpected(
	batch: Pick<BatchResponse, 'status' | 'measured_og' | 'expected_og' | 'expected_fg' | 'expected_abv' | 'expected_ibu' | 'expected_srm'> & {
		recipe?: RecipeLike | null;
	},
	includeMeasured = true
): StatValues {
	const isLive = !hasSnapshot(batch.status);
	const live = isLive && batch.recipe ? effectiveStats(batch.recipe) : ({} as EffectiveStats);
	return {
		og: (includeMeasured ? batch.measured_og : null) ?? batch.expected_og ?? live.og,
		fg: batch.expected_fg ?? live.fg,
		abv: batch.expected_abv ?? live.abv,
		ibu: batch.expected_ibu ?? live.ibu,
		srm: batch.expected_srm ?? live.srm
	};
}

const THRESHOLD: Record<keyof StatValues, number> = { og: 0.002, fg: 0.002, abv: 0.2, ibu: 2, srm: 1 };

/** True when a declared target is far enough from the calculated value to show beside it. */
export function statDiffers(stat: keyof StatValues, calc?: number | null, target?: number | null): boolean {
	if (calc == null || target == null) return false;
	return Math.abs(calc - target) > THRESHOLD[stat] + 1e-9;
}

