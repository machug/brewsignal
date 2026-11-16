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

/** True once the batch's expected numbers are a frozen snapshot (fermenting or later). */
export function hasSnapshot(status: BatchResponse['status']): boolean {
	return status !== 'planning' && status !== 'brewing';
}

/**
 * What a batch is expected to reach. OG prefers the measured value (unless
 * `includeMeasured` is false). Otherwise planning and brewing batches read the
 * recipe's live stats and ignore any stored snapshot; from fermenting on the
 * snapshot is all there is, frozen even where a field is null (no mixing).
 */
export function batchExpected(
	batch: Pick<BatchResponse, 'status' | 'measured_og' | 'expected_og' | 'expected_fg' | 'expected_abv' | 'expected_ibu' | 'expected_srm'> & {
		recipe?: RecipeLike | null;
	},
	includeMeasured = true
): StatValues {
	const isLive = !hasSnapshot(batch.status);
	const live = isLive && batch.recipe ? effectiveStats(batch.recipe) : ({} as EffectiveStats);
	return {
		og: (includeMeasured ? batch.measured_og : null) ?? (isLive ? live.og : batch.expected_og ?? undefined),
		fg: isLive ? live.fg : batch.expected_fg ?? undefined,
		abv: isLive ? live.abv : batch.expected_abv ?? undefined,
		ibu: isLive ? live.ibu : batch.expected_ibu ?? undefined,
		srm: isLive ? live.srm : batch.expected_srm ?? undefined
	};
}

const THRESHOLD: Record<keyof StatValues, number> = { og: 0.002, fg: 0.002, abv: 0.2, ibu: 2, srm: 1 };

/** True when a declared target is far enough from the calculated value to show beside it. */
export function statDiffers(stat: keyof StatValues, calc?: number | null, target?: number | null): boolean {
	if (calc == null || target == null) return false;
	return Math.abs(calc - target) > THRESHOLD[stat] + 1e-9;
}


/**
 * Expected numbers for the batch form's preview, based on what saving will do:
 * the stored snapshot is kept only when the batch is already fermenting or later,
 * stays so, and keeps its recipe. Otherwise the backend snapshots (or reads) the
 * live recipe, so that is what is shown.
 */
export function previewExpected(
	batch: Parameters<typeof batchExpected>[0] & { recipe_id?: number | null },
	destinationStatus: BatchResponse['status'],
	selectedRecipe?: (RecipeLike & { id: number }) | null
): StatValues {
	const sameRecipe = !selectedRecipe || selectedRecipe.id === batch.recipe_id;
	if (hasSnapshot(batch.status) && hasSnapshot(destinationStatus) && sameRecipe) return batchExpected(batch, false);
	const recipe = selectedRecipe ?? batch.recipe;
	return recipe ? effectiveStats(recipe) : {};
}
