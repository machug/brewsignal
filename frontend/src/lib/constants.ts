/**
 * Brewing calculation constants
 */

/**
 * Standard ABV calculation multiplier.
 *
 * Formula: ABV% = (OG - FG) × ABV_MULTIPLIER
 *
 * This is the commonly used homebrewing approximation based on the
 * relationship between gravity points and alcohol production during
 * fermentation. More accurate for beers in typical gravity ranges
 * (OG 1.040-1.080). For high-gravity beers (>1.080), the alternate
 * ABV formula may be more accurate but adds complexity.
 *
 * Example: OG 1.050, FG 1.010 → (0.050 - 0.010) × 131.25 = 5.25% ABV
 */
export const ABV_MULTIPLIER = 131.25;
