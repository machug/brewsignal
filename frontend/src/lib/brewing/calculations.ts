/**
 * Brewing helpers: unit conversions, labels, water and carbonation maths.
 * Recipe stats (OG, FG, ABV, IBU, SRM, calories, BU:GU) are calculated only by
 * the backend (services/brewing.py); see $lib/recipeStats for reading them.
 * Metric units internally (kg, liters, Celsius).
 */

// ============================================================================
// Types
// ============================================================================

export interface Fermentable {
  name: string;
  amount_kg: number;
  potential_sg: number;  // e.g., 1.037 for base malt
  color_srm: number;
  yield_percent?: number;  // Alternative to potential_sg (e.g., 80%)
  type?: string;  // BeerJSON type: grain, sugar, extract, dry extract, honey...
}

/**
 * Calculate gravity points for display (e.g., 1.052 -> 52)
 */
export function gravityToPoints(sg: number): number {
  return Math.round((sg - 1) * 1000);
}

/**
 * Convert gravity points back to SG
 */
export function pointsToGravity(points: number): number {
  return 1 + (points / 1000);
}

/**
 * Calculate Apparent Attenuation
 */
export function calculateApparentAttenuation(og: number, fg: number): number {
  const ogPoints = (og - 1) * 1000;
  const fgPoints = (fg - 1) * 1000;
  return ((ogPoints - fgPoints) / ogPoints) * 100;
}

/**
 * Balance label for a BU:GU ratio. 'Very Bitter' starts at 1.0, roughly
 * where IPA bitterness begins; BJCP American Pale Ale spans about 0.5-1.1,
 * so the old 0.9 cut-off called in-style pales Very Bitter (tilt_ui-idp9).
 */
export function describeBUGU(ratio: number): string {
  if (ratio < 0.3) return 'Very Malty';
  if (ratio < 0.5) return 'Malty';
  if (ratio < 0.7) return 'Balanced';
  if (ratio < 1.0) return 'Hoppy';
  return 'Very Bitter';
}

// ============================================================================
// Color (SRM) display
// ============================================================================

/**
 * Convert SRM to approximate hex color for display
 */
export function srmToHex(srm: number): string {
  // Clamp SRM to reasonable range
  const clampedSrm = Math.max(1, Math.min(40, srm));

  // SRM to RGB approximation based on BJCP color chart
  const srmColors: { [key: number]: string } = {
    1: '#FFE699',   // Pale straw
    2: '#FFD878',   // Straw
    3: '#FFCA5A',   // Pale gold
    4: '#FFBF42',   // Deep gold
    5: '#FBB123',   // Pale amber
    6: '#F8A600',   // Medium amber
    7: '#F39C00',   // Deep amber
    8: '#EA8F00',   // Amber-brown
    9: '#E58500',   // Brown
    10: '#DE7C00',  // Light brown
    11: '#D77200',  // Medium brown
    12: '#CF6900',  // Brown
    13: '#CB6200',  // Ruby brown
    14: '#C35900',  // Deep brown
    15: '#BB5100',  // Dark brown
    16: '#B54C00',  // Porter
    17: '#B04500',  // Dark porter
    18: '#A63E00',  // Stout
    19: '#A13700',  // Dark stout
    20: '#9B3200',  // Black
    25: '#7C2900',  // Black
    30: '#5E1E00',  // Black
    35: '#401500',  // Black
    40: '#261000',  // Black
  };

  // Find closest SRM value
  const srmKeys = Object.keys(srmColors).map(Number).sort((a, b) => a - b);
  let closestSrm = srmKeys[0];

  for (const key of srmKeys) {
    if (key <= clampedSrm) {
      closestSrm = key;
    } else {
      break;
    }
  }

  return srmColors[closestSrm] || '#261000';
}

/**
 * Get SRM description
 */
export function srmToDescription(srm: number): string {
  if (srm < 2) return 'Pale Straw';
  if (srm < 3) return 'Straw';
  if (srm < 4) return 'Pale Gold';
  if (srm < 6) return 'Deep Gold';
  if (srm < 9) return 'Amber';
  if (srm < 12) return 'Copper';
  if (srm < 15) return 'Light Brown';
  if (srm < 18) return 'Brown';
  if (srm < 20) return 'Dark Brown';
  if (srm < 24) return 'Very Dark';
  if (srm < 30) return 'Black';
  return 'Opaque Black';
}

// ============================================================================
// Mash Calculations
// ============================================================================

/**
 * Calculate strike water temperature
 *
 * Formula: Tw = (0.2/R)(T2-T1) + T2
 * Where:
 *   Tw = strike water temperature
 *   R = ratio of water to grain (liters per kg)
 *   T1 = initial grain temperature
 *   T2 = target mash temperature
 */
export function calculateStrikeTemp(
  grain_kg: number,
  water_liters: number,
  target_temp_c: number,
  grain_temp_c: number = 20  // Room temperature default
): number {
  const ratio = water_liters / grain_kg;
  const strikeTemp = (0.2 / ratio) * (target_temp_c - grain_temp_c) + target_temp_c;
  return Math.round(strikeTemp * 10) / 10;
}

/**
 * Calculate water volume for mash
 *
 * Typical ratio: 2.5-3.5 L/kg (thinner = more fermentable, thicker = more body)
 */
export function calculateMashWater(
  grain_kg: number,
  ratio_liters_per_kg: number = 3.0
): number {
  return grain_kg * ratio_liters_per_kg;
}

/**
 * Calculate sparge water volume
 */
export function calculateSpargeWater(
  batch_size_liters: number,
  mash_water_liters: number,
  grain_kg: number,
  boil_time_minutes: number,
  boil_off_liters_per_hour: number = 4,
  grain_absorption_liters_per_kg: number = 1.0,
  equipment_loss_liters: number = 2
): number {
  const preboilVolume = batch_size_liters +
                        (boil_off_liters_per_hour * boil_time_minutes / 60) +
                        equipment_loss_liters;
  const grainAbsorption = grain_kg * grain_absorption_liters_per_kg;
  const spargeWater = preboilVolume - mash_water_liters + grainAbsorption;
  return Math.max(0, spargeWater);
}

// ============================================================================
// Carbonation Calculations
// ============================================================================

/**
 * Calculate priming sugar amount for bottle conditioning
 *
 * @param volume_liters - Volume of beer to carbonate
 * @param target_volumes_co2 - Target carbonation (typically 2.0-3.0)
 * @param beer_temp_c - Temperature of beer (affects residual CO2)
 * @param sugar_type - Type of priming sugar
 */
export function calculatePrimingSugar(
  volume_liters: number,
  target_volumes_co2: number,
  beer_temp_c: number,
  sugar_type: 'corn_sugar' | 'table_sugar' | 'dme' | 'honey' = 'corn_sugar'
): number {
  // Residual CO2 volumes based on temperature (approximately)
  const residualCO2 = 3.0378 - (0.050062 * beer_temp_c) + (0.00026555 * beer_temp_c * beer_temp_c);

  // CO2 volumes needed
  const co2Needed = Math.max(0, target_volumes_co2 - residualCO2);

  // Grams of sugar per liter for 1 volume CO2
  const sugarFactor: { [key: string]: number } = {
    corn_sugar: 4.0,      // Dextrose
    table_sugar: 3.8,     // Sucrose (more fermentable)
    dme: 5.3,             // Dry malt extract
    honey: 4.5,           // Honey (varies)
  };

  const factor = sugarFactor[sugar_type] || 4.0;
  return volume_liters * co2Needed * factor;
}

/**
 * Calculate forced carbonation PSI
 *
 * @param target_volumes_co2 - Target carbonation
 * @param temp_c - Temperature of keg
 */
export function calculateForcedCarbonationPSI(
  target_volumes_co2: number,
  temp_c: number
): number {
  // Formula: PSI = -16.6999 - 0.0101059*T + 0.00116512*T^2 + 0.173354*V + 4.24267*V^2 - 0.0684226*T*V
  // Where T = temp in Fahrenheit, V = volumes CO2
  const tempF = (temp_c * 9/5) + 32;
  const V = target_volumes_co2;

  const psi = -16.6999 - 0.0101059 * tempF + 0.00116512 * tempF * tempF +
              0.173354 * V + 4.24267 * V * V - 0.0684226 * tempF * V;

  return Math.max(0, Math.round(psi * 10) / 10);
}

// ============================================================================
// Utility Functions
// ============================================================================



/**
 * Format gravity for display (e.g., 1.052)
 */
export function formatGravity(sg: number): string {
  return sg.toFixed(3);
}

/**
 * Format ABV for display (e.g., "5.2%")
 */
export function formatABV(abv: number): string {
  return `${abv.toFixed(1)}%`;
}

/**
 * Format IBU for display
 */
export function formatIBU(ibu: number): string {
  return Math.round(ibu).toString();
}
