/**
 * Convert Fahrenheit to Celsius
 */
export function fahrenheitToCelsius(f: number): number {
  return (f - 32) * (5 / 9);
}

/**
 * Convert Celsius to Fahrenheit
 */
export function celsiusToFahrenheit(c: number): number {
  return (c * 9 / 5) + 32;
}

/**
 * Convert calibration point to Celsius for backend storage
 * @param raw Raw value in user's preferred unit
 * @param actual Actual value in user's preferred unit
 * @param useCelsius Whether user preference is Celsius
 * @returns [raw, actual] in Celsius
 */
export function convertTempPointToCelsius(
  raw: number,
  actual: number,
  useCelsius: boolean
): [number, number] {
  if (useCelsius) {
    return [raw, actual];
  }
  return [fahrenheitToCelsius(raw), fahrenheitToCelsius(actual)];
}

/**
 * Convert calibration point from Celsius storage to user's preferred unit
 * @param raw Raw value in Celsius (from backend)
 * @param actual Actual value in Celsius (from backend)
 * @param useCelsius Whether user preference is Celsius
 * @returns [raw, actual] in user's preferred unit
 */
export function convertTempPointFromCelsius(
  raw: number,
  actual: number,
  useCelsius: boolean
): [number, number] {
  if (useCelsius) {
    return [raw, actual];
  }
  return [celsiusToFahrenheit(raw), celsiusToFahrenheit(actual)];
}
