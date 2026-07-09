/**
 * Equipment-aware brewability check (v1 — bead tilt_ui-zzp8).
 *
 * Compares a recipe's computed volumes against the user's registered
 * equipment (inventory Equipment table: capacity only, no brewing profile
 * yet). A category is only checked when the user owns at least one active
 * vessel of that category with a known capacity; if any such vessel fits,
 * the recipe is considered brewable and no warning is raised. When none
 * fits, the warning references the largest candidate.
 *
 * Volume math reuses the Brewfather-calibrated defaults in
 * $lib/utils/water.ts until per-equipment profiles exist (v2).
 */

import type { EquipmentResponse, EquipmentType } from '$lib/api';
import { calculateWaterVolumes, estimatePreBoilVolume, WATER_DEFAULTS } from '$lib/utils/water';

// Fermenters need headroom for krausen; 20% is the common rule of thumb.
const KRAUSEN_HEADSPACE_FACTOR = 1.2;

export type BrewabilityCode =
	| 'mash_overflow'
	| 'grain_over_capacity'
	| 'boil_overflow'
	| 'fermenter_overflow';

export interface BrewabilityWarning {
	code: BrewabilityCode;
	equipment_name: string;
	/** Litres, except kg for grain_over_capacity. */
	required: number;
	available: number;
	message: string;
}

export interface BrewabilityRecipe {
	batch_size_liters: number;
	total_grain_kg: number;
	boil_time_minutes?: number | null;
	boil_size_l?: number | null;
}

const MASH_TYPES: EquipmentType[] = ['all_in_one', 'mash_tun'];
const BOIL_TYPES: EquipmentType[] = ['all_in_one', 'kettle'];

// Kettle additions never enter the mash tun / malt pipe — same set the stat
// calculators use for skipping brewhouse efficiency (calculations.ts).
const KETTLE_FERMENTABLE_TYPES = new Set([
	'sugar',
	'extract',
	'dry extract',
	'liquid extract',
	'honey',
	'fruit',
	'juice',
]);

/**
 * Total weight that actually occupies the mash: grain and other mashed
 * fermentables, excluding kettle additions. Untyped entries count as mashed.
 */
export function totalMashGrainKg(
	fermentables: Array<{ amount_kg?: number | null; type?: string | null }>,
): number {
	return fermentables.reduce(
		(sum, f) =>
			KETTLE_FERMENTABLE_TYPES.has((f.type ?? '').toLowerCase()) ? sum : sum + (f.amount_kg ?? 0),
		0,
	);
}

const round2 = (n: number) => Math.round(n * 100) / 100;

function largestBy(
	equipment: EquipmentResponse[],
	types: EquipmentType[],
	capacity: (e: EquipmentResponse) => number | undefined,
): EquipmentResponse | null {
	let best: EquipmentResponse | null = null;
	for (const e of equipment) {
		if (!e.is_active || !types.includes(e.type)) continue;
		const cap = capacity(e);
		if (cap == null || cap <= 0) continue;
		if (best === null || cap > capacity(best)!) best = e;
	}
	return best;
}

function checkCapacity(
	warnings: BrewabilityWarning[],
	vessel: EquipmentResponse | null,
	capacity: (e: EquipmentResponse) => number | undefined,
	required: number,
	code: BrewabilityCode,
	message: (name: string, required: number, available: number) => string,
): void {
	if (vessel === null || required <= 0) return;
	const available = capacity(vessel)!;
	if (required <= available) return;
	warnings.push({
		code,
		equipment_name: vessel.name,
		required: round2(required),
		available,
		message: message(vessel.name, round2(required), available),
	});
}

/**
 * Largest batch size (litres, floored to 0.5 L) at which the proportionally
 * scaled recipe fits the owned equipment. Everything in the recipe scales
 * with the batch ratio (grain, mash volume minus deadspace, pre-boil minus
 * fixed losses), so each capacity bound inverts to a max ratio directly.
 *
 * Returns null when the recipe already fits, when nothing is judgeable,
 * or when no positive batch size can fit (suggestion would be useless).
 */
export function maxFitBatchLiters(
	recipe: BrewabilityRecipe,
	equipment: EquipmentResponse[],
): number | null {
	if (recipe.batch_size_liters <= 0) return null;
	if (checkBrewability(recipe, equipment).length === 0) return null;

	const pos = (n: number | null | undefined) => (n != null && n > 0 ? n : undefined);
	const active = equipment.filter((e) => e.is_active);
	const { mashRatioLPerKg, grainDisplacementLPerKg, mashTunDeadspaceL, boilOffLPerHr, trubChillerLossL } =
		WATER_DEFAULTS;
	const boilTimeHrs = (recipe.boil_time_minutes ?? 60) / 60;
	const fixedBoilLosses = boilTimeHrs * boilOffLPerHr + trubChillerLossL;
	const grain = recipe.total_grain_kg;
	const mashVolumePerKg = mashRatioLPerKg + grainDisplacementLPerKg;

	const categoryMaxima: number[] = [];

	const mashVessels = active.filter(
		(e) => MASH_TYPES.includes(e.type) && (pos(e.capacity_liters) != null || pos(e.capacity_kg) != null),
	);
	if (grain > 0 && mashVessels.length > 0) {
		const perVessel = mashVessels.map((e) => {
			const capL = pos(e.capacity_liters);
			const capKg = pos(e.capacity_kg);
			const byVolume = capL != null ? (capL - mashTunDeadspaceL) / (grain * mashVolumePerKg) : Infinity;
			const byGrain = capKg != null ? capKg / grain : Infinity;
			return Math.min(byVolume, byGrain);
		});
		categoryMaxima.push(Math.max(...perVessel));
	}

	const boilVessels = active.filter((e) => BOIL_TYPES.includes(e.type) && pos(e.capacity_liters) != null);
	if (boilVessels.length > 0) {
		const perVessel = boilVessels.map((e) => {
			const capL = pos(e.capacity_liters)!;
			// Explicit boil_size_l scales with the ratio; the derived pre-boil
			// carries fixed (non-scaling) boil-off + trub losses.
			return recipe.boil_size_l != null && recipe.boil_size_l > 0
				? capL / recipe.boil_size_l
				: (capL - fixedBoilLosses) / recipe.batch_size_liters;
		});
		categoryMaxima.push(Math.max(...perVessel));
	}

	const fermenters = active.filter((e) => e.type === 'fermenter' && pos(e.capacity_liters) != null);
	if (fermenters.length > 0) {
		const perVessel = fermenters.map(
			(e) => pos(e.capacity_liters)! / (recipe.batch_size_liters * KRAUSEN_HEADSPACE_FACTOR),
		);
		categoryMaxima.push(Math.max(...perVessel));
	}

	if (categoryMaxima.length === 0) return null;
	const maxRatio = Math.min(...categoryMaxima);
	const suggested = Math.floor((recipe.batch_size_liters * maxRatio) / 0.5) * 0.5;
	return suggested > 0 ? suggested : null;
}

export function checkBrewability(
	recipe: BrewabilityRecipe,
	equipment: EquipmentResponse[],
): BrewabilityWarning[] {
	const warnings: BrewabilityWarning[] = [];
	// Zero/negative capacities are "don't know" (the API accepts them) —
	// treat like missing so they never become a crash or a false warning.
	const pos = (n: number | null | undefined) => (n != null && n > 0 ? n : undefined);
	const litres = (e: EquipmentResponse) => pos(e.capacity_liters);
	const kg = (e: EquipmentResponse) => pos(e.capacity_kg);

	const volumes = calculateWaterVolumes(
		recipe.batch_size_liters,
		recipe.total_grain_kg,
		recipe.boil_time_minutes,
		recipe.boil_size_l,
	);

	if (volumes) {
		// A mash vessel must satisfy BOTH constraints at once — checking volume
		// and grain weight against different vessels would pass recipes no
		// single vessel can actually handle. Unknown capacity = can't judge,
		// so it counts as fitting that constraint.
		const mashVessels = equipment.filter(
			(e) => e.is_active && MASH_TYPES.includes(e.type) && (litres(e) != null || kg(e) != null),
		);
		const fitsMash = (e: EquipmentResponse) =>
			(litres(e) == null || volumes.mashVolume <= litres(e)!) &&
			(kg(e) == null || recipe.total_grain_kg <= kg(e)!);
		if (mashVessels.length > 0 && !mashVessels.some(fitsMash)) {
			// Report against the roomiest candidate; it fails at least one
			// constraint (or no vessel would have failed the joint check).
			const best = largestBy(mashVessels, MASH_TYPES, litres) ?? largestBy(mashVessels, MASH_TYPES, kg)!;
			const bestL = litres(best);
			const bestKg = kg(best);
			if (bestL != null && volumes.mashVolume > bestL) {
				warnings.push({
					code: 'mash_overflow',
					equipment_name: best.name,
					required: round2(volumes.mashVolume),
					available: bestL,
					message: `Mash won't fit: needs ${round2(volumes.mashVolume)} L, ${best.name} holds ${bestL} L`,
				});
			}
			if (bestKg != null && recipe.total_grain_kg > bestKg) {
				warnings.push({
					code: 'grain_over_capacity',
					equipment_name: best.name,
					required: round2(recipe.total_grain_kg),
					available: bestKg,
					message: `Grain bill too big: ${round2(recipe.total_grain_kg)} kg, ${best.name} takes ${bestKg} kg`,
				});
			}
		}
	}

	// Boil check works even for extract recipes (no grain → no water model);
	// use the explicit pre-boil volume or estimate it from batch size + boil-off.
	const preBoil =
		volumes?.preBoilVolume ??
		recipe.boil_size_l ??
		(recipe.batch_size_liters > 0
			? estimatePreBoilVolume(recipe.batch_size_liters, recipe.boil_time_minutes)
			: 0);
	checkCapacity(
		warnings,
		largestBy(equipment, BOIL_TYPES, litres),
		litres,
		preBoil,
		'boil_overflow',
		(name, req, avail) => `Pre-boil volume ${req} L exceeds ${name} (${avail} L)`,
	);

	checkCapacity(
		warnings,
		largestBy(equipment, ['fermenter'], litres),
		litres,
		recipe.batch_size_liters * KRAUSEN_HEADSPACE_FACTOR,
		'fermenter_overflow',
		(name, req, avail) =>
			`Fermenter too small: batch needs ~${req} L with krausen headspace, ${name} holds ${avail} L`,
	);

	return warnings;
}
