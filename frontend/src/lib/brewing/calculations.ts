/**
 * Brewing Calculations Module
 *
 * Standard formulas for calculating beer characteristics from ingredients.
 * All calculations use metric units internally (kg, liters, Celsius).
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
}

export interface Hop {
  name: string;
  amount_grams: number;
  alpha_acid_percent: number;
  boil_time_minutes: number;
  form?: 'pellet' | 'whole' | 'plug';
  use?: 'boil' | 'whirlpool' | 'dry_hop' | 'first_wort' | 'mash';
}

export interface Yeast {
  name: string;
  attenuation_percent: number;  // e.g., 75
  temp_min_c: number;
  temp_max_c: number;
}

export interface RecipeStats {
  og: number;
  fg: number;
  abv: number;
  ibu: number;
  srm: number;
  color_hex: string;
  calories_per_330ml: number;
}

export interface BatchParams {
  batch_size_liters: number;
  efficiency_percent: number;
  boil_time_minutes: number;
  boil_off_liters_per_hour?: number;  // default 4
}

// ============================================================================
// Gravity Calculations
// ============================================================================

/**
 * Calculate Original Gravity from fermentables
 *
 * Formula: OG = 1 + (sum of gravity points / batch volume)
 * Gravity Points = weight_kg * potential_extract * efficiency * 1000 / volume_L
 */
export function calculateOG(
  fermentables: Fermentable[],
  batch: BatchParams
): number {
  const totalPoints = fermentables.reduce((sum, f) => {
    // Convert potential SG to points (e.g., 1.037 -> 37)
    const potentialPoints = (f.potential_sg - 1) * 1000;
    // Apply efficiency and scale to batch size
    const points = (f.amount_kg * potentialPoints * batch.efficiency_percent) /
                   (batch.batch_size_liters / 100);
    return sum + points;
  }, 0);

  return 1 + (totalPoints / 1000);
}

/**
 * Calculate Final Gravity from OG and yeast attenuation
 */
export function calculateFG(og: number, attenuation_percent: number): number {
  const ogPoints = (og - 1) * 1000;
  const fgPoints = ogPoints * (1 - attenuation_percent / 100);
  return 1 + (fgPoints / 1000);
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

// ============================================================================
// ABV Calculations
// ============================================================================

/**
 * Calculate ABV from OG and FG
 *
 * Standard formula: ABV = (OG - FG) * 131.25
 * More accurate formula: ABV = (76.08 * (OG - FG) / (1.775 - OG)) * (FG / 0.794)
 */
export function calculateABV(og: number, fg: number, method: 'simple' | 'accurate' = 'simple'): number {
  if (method === 'simple') {
    return (og - fg) * 131.25;
  }

  // More accurate formula accounting for alcohol's effect on density
  return (76.08 * (og - fg) / (1.775 - og)) * (fg / 0.794);
}

/**
 * Calculate Apparent Attenuation
 */
export function calculateApparentAttenuation(og: number, fg: number): number {
  const ogPoints = (og - 1) * 1000;
  const fgPoints = (fg - 1) * 1000;
  return ((ogPoints - fgPoints) / ogPoints) * 100;
}

// ============================================================================
// IBU Calculations
// ============================================================================

/**
 * Calculate IBU contribution from a single hop addition using Tinseth formula
 *
 * Tinseth is most accurate for high-gravity beers
 */
export function calculateIBU_Tinseth(
  hop: Hop,
  og: number,
  batch_size_liters: number
): number {
  // Skip non-boil additions
  if (hop.use === 'dry_hop' || hop.boil_time_minutes <= 0) {
    return 0;
  }

  // Bigness factor (adjusts for wort gravity)
  const bigness = 1.65 * Math.pow(0.000125, og - 1);

  // Boil time factor (utilization increases with time, max around 60 min)
  const btFactor = (1 - Math.exp(-0.04 * hop.boil_time_minutes)) / 4.15;

  // Combined utilization
  let utilization = bigness * btFactor;

  // Pellet adjustment (10% better utilization)
  if (hop.form === 'pellet') {
    utilization *= 1.10;
  }

  // First wort hopping adjustment (10% more utilization)
  if (hop.use === 'first_wort') {
    utilization *= 1.10;
  }

  // Whirlpool/steep adjustment (reduced utilization)
  if (hop.use === 'whirlpool') {
    utilization *= 0.20;  // ~20% of boil utilization
  }

  // IBU = (alpha * amount_grams * utilization * 1000) / (batch_liters * 10)
  const ibu = (hop.alpha_acid_percent / 100) * hop.amount_grams * utilization * 1000 /
              (batch_size_liters * 10);

  return Math.max(0, ibu);
}

/**
 * Calculate total IBU from all hop additions
 */
export function calculateTotalIBU(
  hops: Hop[],
  og: number,
  batch_size_liters: number
): number {
  return hops.reduce((total, hop) => {
    return total + calculateIBU_Tinseth(hop, og, batch_size_liters);
  }, 0);
}

/**
 * Calculate BU:GU ratio (bitterness balance)
 *
 * < 0.5 = malty/sweet
 * 0.5 - 0.8 = balanced
 * > 0.8 = hoppy/bitter
 */
export function calculateBUGU(ibu: number, og: number): number {
  const ogPoints = (og - 1) * 1000;
  return ogPoints > 0 ? ibu / ogPoints : 0;
}

// ============================================================================
// Color (SRM) Calculations
// ============================================================================

/**
 * Calculate SRM using Morey equation
 *
 * MCU (Malt Color Units) = (weight_lbs * color_lovibond) / volume_gallons
 * SRM = 1.4922 * MCU^0.6859
 */
export function calculateSRM(
  fermentables: Fermentable[],
  batch_size_liters: number
): number {
  // Convert to US units for the formula
  const batch_gallons = batch_size_liters * 0.264172;

  const mcu = fermentables.reduce((sum, f) => {
    const weight_lbs = f.amount_kg * 2.20462;
    // SRM and Lovibond are approximately equal for our purposes
    return sum + (weight_lbs * f.color_srm) / batch_gallons;
  }, 0);

  // Morey equation
  const srm = 1.4922 * Math.pow(mcu, 0.6859);

  // Cap at 40 SRM (anything darker is essentially black)
  return Math.min(40, Math.max(0, srm));
}

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
 * Calculate calories per serving (330ml)
 *
 * Approximation based on alcohol and residual sugars
 */
export function calculateCalories(og: number, fg: number, serving_ml: number = 330): number {
  const abv = calculateABV(og, fg);
  // Alcohol contributes ~7 calories per gram, ~6.9 per mL of pure alcohol
  // Residual carbs contribute ~4 calories per gram

  const alcoholCalories = abv * 0.79 * 7 * (serving_ml / 100);  // 0.79 g/mL density
  const carbCalories = (fg - 1) * 1000 * 0.4 * (serving_ml / 100);  // Rough approximation

  return Math.round(alcoholCalories + carbCalories);
}

/**
 * Calculate all recipe stats at once
 */
export function calculateRecipeStats(
  fermentables: Fermentable[],
  hops: Hop[],
  yeast: Yeast,
  batch: BatchParams
): RecipeStats {
  const og = calculateOG(fermentables, batch);
  const fg = calculateFG(og, yeast.attenuation_percent);
  const abv = calculateABV(og, fg);
  const ibu = calculateTotalIBU(hops, og, batch.batch_size_liters);
  const srm = calculateSRM(fermentables, batch.batch_size_liters);

  return {
    og: Math.round(og * 1000) / 1000,
    fg: Math.round(fg * 1000) / 1000,
    abv: Math.round(abv * 10) / 10,
    ibu: Math.round(ibu),
    srm: Math.round(srm * 10) / 10,
    color_hex: srmToHex(srm),
    calories_per_330ml: calculateCalories(og, fg, 330),
  };
}

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
