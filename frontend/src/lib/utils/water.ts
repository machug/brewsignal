/**
 * Calculate brewing water volumes from grain bill and batch size.
 * Equipment defaults are estimates — actual values depend on your system.
 */

const GRAIN_ABSORPTION = 0.96; // L/kg absorbed by grain
const MASH_RATIO = 2.43; // L/kg water-to-grain ratio
const BOIL_OFF_RATE = 4.0; // L/hr evaporation
const TRUB_LOSS = 0.5; // L lost to trub/hops in kettle
const GRAIN_DISPLACEMENT = 0.67; // L/kg grain volume in mash

export interface WaterVolumes {
	mashWater: number;
	spargeWater: number;
	totalWater: number;
	mashVolume: number;
}

export function calculateWaterVolumes(
	batchSizeLiters: number,
	totalGrainKg: number,
	boilTimeMinutes?: number | null,
	boilSizeL?: number | null,
): WaterVolumes | null {
	if (batchSizeLiters <= 0 || totalGrainKg <= 0) return null;

	const boilTimeHrs = (boilTimeMinutes ?? 60) / 60;
	const mashWater = totalGrainKg * MASH_RATIO;
	const grainAbsorption = totalGrainKg * GRAIN_ABSORPTION;
	const preboilVolume = boilSizeL ?? (batchSizeLiters + boilTimeHrs * BOIL_OFF_RATE + TRUB_LOSS);
	const spargeWater = Math.max(0, preboilVolume - mashWater + grainAbsorption);
	const totalWater = mashWater + spargeWater;
	const mashVolume = mashWater + totalGrainKg * GRAIN_DISPLACEMENT;

	return { mashWater, spargeWater, totalWater, mashVolume };
}
