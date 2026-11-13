import type { HistoricalReading } from '$lib/api';

// Valid range for outlier filtering (matches backend)
const SG_MIN = 0.5;
const SG_MAX = 1.2;
const DAY_MS = 24 * 60 * 60 * 1000;
// "Rate" is the slope over this trailing window: the same 12 h the backend
// stall rule uses, so the UI and the stall alert agree (tilt_ui-3kbr).
const RATE_WINDOW_MS = 12 * 60 * 60 * 1000;
const RATE_MIN_SPAN_MS = 60 * 60 * 1000;
const SG_CHANGE_THRESHOLD = 0.001;

// Percentile helper - filters out noise spikes from High/Low stats
export function percentile(arr: number[], p: number): number {
	const sorted = [...arr].sort((a, b) => a - b);
	const idx = (p / 100) * (sorted.length - 1);
	const lower = Math.floor(idx);
	const upper = Math.ceil(idx);
	if (lower === upper) return sorted[lower];
	return sorted[lower] + (sorted[upper] - sorted[lower]) * (idx - lower);
}

/** Least-squares slope in SG/day, or null when the points do not span an hour. */
function slopePerDay(points: { t: number; sg: number }[]): number | null {
	const n = points.length;
	if (n < 3 || points[n - 1].t - points[0].t < RATE_MIN_SPAN_MS) return null;
	const t0 = points[0].t;
	let sumX = 0, sumY = 0, sumXY = 0, sumX2 = 0;
	for (const p of points) {
		const x = (p.t - t0) / DAY_MS;
		sumX += x;
		sumY += p.sg;
		sumXY += x * p.sg;
		sumX2 += x * x;
	}
	const denom = n * sumX2 - sumX * sumX;
	return denom > 0 ? (n * sumXY - sumX * sumY) / denom : null;
}

/** Gravity-derived stats shared by the full stats panel and Home's trend strip. */
export function analyseSg(readings: HistoricalReading[], originalGravity: number | null) {
	// Filter out invalid readings (flagged by backend) first
	const validReadings = readings.filter((r) => r.status !== 'invalid');
	if (validReadings.length === 0) return null;

	// Readings come newest first, so sort for chronological order
	const sorted = [...validReadings].sort(
		(a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
	);

	// SG with its own timestamp (prefer calibrated, drop outliers). Keeping the
	// pair together matters: indexing `sorted` by a filtered index was wrong
	// as soon as one reading was dropped.
	const points = sorted
		.map((r) => ({ t: new Date(r.timestamp).getTime(), sg: r.sg_calibrated ?? r.sg_raw }))
		.filter((p): p is { t: number; sg: number } => p.sg !== null && p.sg >= SG_MIN && p.sg <= SG_MAX);
	if (points.length === 0) return null;

	const sgValues = points.map((p) => p.sg);
	const currentSg = sgValues[sgValues.length - 1];
	const firstSg = sgValues[0];
	// Use percentiles to filter noise spikes (Tilt can report bad values when bumped)
	const highSg = percentile(sgValues, 95);
	const lowSg = percentile(sgValues, 5);

	const firstTime = points[0].t;
	const lastTime = points[points.length - 1].t;
	const durationDays = (lastTime - firstTime) / DAY_MS;

	// Current fermentation rate (SG/day): slope of the last 12 h. Falls back to
	// the whole-window average when the window is too short to fit.
	const fermRate =
		slopePerDay(points.filter((p) => p.t >= lastTime - RATE_WINDOW_MS)) ??
		(durationDays > 0 ? (currentSg - firstSg) / durationDays : 0);

	// Days at current SG: time since SG last differed by more than 0.001.
	// Never differed = stable for everything we can see.
	let daysAtCurrentSg = durationDays;
	for (let i = points.length - 2; i >= 0; i--) {
		if (Math.abs(points[i].sg - currentSg) > SG_CHANGE_THRESHOLD) {
			daysAtCurrentSg = (lastTime - points[i + 1].t) / DAY_MS;
			break;
		}
	}

	// Use explicit OG if set, otherwise estimate from highSg (95th percentile)
	const og = originalGravity ?? highSg;
	const ogIsEstimated = originalGravity === null;

	return { sorted, currentSg, firstSg, highSg, lowSg, fermRate, durationDays, daysAtCurrentSg, og, ogIsEstimated };
}
