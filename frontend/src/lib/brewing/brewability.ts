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
import { calculateWaterVolumes } from '$lib/utils/water';

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

export function checkBrewability(
	recipe: BrewabilityRecipe,
	equipment: EquipmentResponse[],
): BrewabilityWarning[] {
	const warnings: BrewabilityWarning[] = [];
	const litres = (e: EquipmentResponse) => e.capacity_liters;
	const kg = (e: EquipmentResponse) => e.capacity_kg;

	const volumes = calculateWaterVolumes(
		recipe.batch_size_liters,
		recipe.total_grain_kg,
		recipe.boil_time_minutes,
		recipe.boil_size_l,
	);

	if (volumes) {
		checkCapacity(
			warnings,
			largestBy(equipment, MASH_TYPES, litres),
			litres,
			volumes.mashVolume,
			'mash_overflow',
			(name, req, avail) => `Mash won't fit: needs ${req} L, ${name} holds ${avail} L`,
		);
		checkCapacity(
			warnings,
			largestBy(equipment, MASH_TYPES, kg),
			kg,
			recipe.total_grain_kg,
			'grain_over_capacity',
			(name, req, avail) => `Grain bill too big: ${req} kg, ${name} takes ${avail} kg`,
		);
	}

	// Boil check works even for extract recipes (no grain → no water model);
	// fall back to the recipe's explicit pre-boil volume.
	const preBoil = volumes?.preBoilVolume ?? recipe.boil_size_l ?? 0;
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
