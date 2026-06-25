/**
 * Calculate brewing water volumes from grain bill and batch size.
 *
 * Defaults are calibrated to Brewfather's water model (validated against a real
 * BF export: 5.85 kg grain / 23 L batch / 25.85 L pre-boil → mash 16.8 L,
 * sparge 12.7 L, total 29.5 L, mash vol 20.72 L). See bead tilt_ui-4pzy.
 *
 * All equipment parameters are overridable so a per-equipment profile (Phase 2)
 * can supply the brewer's real losses instead of these defaults.
 */

export interface WaterEquipment {
	mashRatioLPerKg?: number; // strike water-to-grain ratio
	grainAbsorptionLPerKg?: number; // wort retained by grain after lauter
	mashTunDeadspaceL?: number; // liquid trapped in mash tun / under false bottom
	grainDisplacementLPerKg?: number; // grain volume contribution to mash volume
	boilOffLPerHr?: number; // kettle evaporation rate
	trubChillerLossL?: number; // kettle loss to trub + chiller
}

// Brewfather-calibrated defaults (Generic 19L stainless profile).
const DEFAULTS: Required<WaterEquipment> = {
	mashRatioLPerKg: 2.7,
	grainAbsorptionLPerKg: 0.45,
	mashTunDeadspaceL: 1.0,
	grainDisplacementLPerKg: 0.67,
	boilOffLPerHr: 0.85,
	trubChillerLossL: 1.0,
};

export interface WaterVolumes {
	mashWater: number;
	spargeWater: number;
	totalWater: number;
	mashVolume: number;
	preBoilVolume: number;
}

const round2 = (n: number) => Math.round(n * 100) / 100;

/**
 * Reverse-flow water model (Brewfather / Brewtarget style):
 *   pre-boil  = given boilSize, else batch + boil-off + trub/chiller loss
 *   mashWater = grain·ratio + deadspace
 *   total     = pre-boil + grain·absorption + deadspace
 *   sparge    = total − mashWater   (deadspace cancels; absorption raises sparge)
 */
export function calculateWaterVolumes(
	batchSizeLiters: number,
	totalGrainKg: number,
	boilTimeMinutes?: number | null,
	boilSizeL?: number | null,
	equipment?: WaterEquipment,
): WaterVolumes | null {
	if (batchSizeLiters <= 0 || totalGrainKg <= 0) return null;

	const eq = { ...DEFAULTS, ...equipment };
	const boilTimeHrs = (boilTimeMinutes ?? 60) / 60;

	const preBoilVolume =
		boilSizeL ??
		batchSizeLiters + boilTimeHrs * eq.boilOffLPerHr + eq.trubChillerLossL;

	const grainAbsorption = totalGrainKg * eq.grainAbsorptionLPerKg;
	const mashWater = totalGrainKg * eq.mashRatioLPerKg + eq.mashTunDeadspaceL;
	// Reverse-flow target: water needed to land pre-boil after lauter losses.
	const targetTotal = preBoilVolume + grainAbsorption + eq.mashTunDeadspaceL;
	// Clamp sparge at zero (thick/small mashes can need none), then keep the
	// total consistent with the actual additions: total === mash + sparge always.
	const spargeWater = Math.max(0, targetTotal - mashWater);
	const totalWater = mashWater + spargeWater;
	const mashVolume = mashWater + totalGrainKg * eq.grainDisplacementLPerKg;

	return {
		mashWater: round2(mashWater),
		spargeWater: round2(spargeWater),
		totalWater: round2(totalWater),
		mashVolume: round2(mashVolume),
		preBoilVolume: round2(preBoilVolume),
	};
}
