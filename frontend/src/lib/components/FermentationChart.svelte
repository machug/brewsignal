<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import uPlot from 'uplot';
	import {
		fetchBatchReadings,
		fetchBatchPredictions,
		fetchBatchControlEvents,
		fetchAmbientHistory,
		fetchChamberHistory,
		fetchBatch,
		TIME_RANGES,
		type HistoricalReading,
		type AmbientHistoricalReading,
		type ChamberHistoricalReading,
		type ControlEvent
	} from '$lib/api';
	import { configState, fahrenheitToCelsius, formatGravity, getGravityUnit } from '$lib/stores/config.svelte';
	import FermentationStats, { analyseSg, formatRate, formatDuration } from './FermentationStats.svelte';
	import { gravityIncrs } from '$lib/chart/gravityTicks';

	const REFRESH_STORAGE_KEY = 'brewsignal_chart_refresh_minutes';
	const REFRESH_OPTIONS = [
		{ label: 'Off', value: 0 },
		{ label: '1 min', value: 1 },
		{ label: '3 min', value: 3 },
		{ label: '5 min', value: 5 },
		{ label: '10 min', value: 10 }
	];

	// Get smoothing settings from config
	let smoothingEnabled = $derived(configState.config.smoothing_enabled);
	let smoothingSamples = $derived(configState.config.smoothing_samples);

	// System timezone for chart display
	let systemTimezone = $state<string>('UTC');
	let lastLoadTime = $state(0);
	let refreshMinutes = $state<number>(3);

	interface Props {
		batchId: number;
		deviceColor?: string;
		originalGravity?: number | null;
		/** When the automatic diacetyl rest started (ISO, UTC). Draws a marker. */
		restStartedAt?: string | null;
		/** Show the stats block under the chart (off on Home, where readouts sit above). */
		showStats?: boolean;
		/** Compact single-row trend strip (rate, ETA, stable-for, OG est.) under the chart. */
		showTrend?: boolean;
	}

	let { batchId, deviceColor = 'BLACK', originalGravity = null, restStartedAt = null, showStats = true, showTrend = false }: Props = $props();

	// Reactive check for display units
	let useCelsius = $derived(configState.config.temp_units === 'C');
	let gravityUnit = $derived(getGravityUnit());

	let chartContainer: HTMLDivElement;
	let chart: uPlot | null = null;
	let loading = $state(true);
	let error = $state<string | null>(null);
	let selectedRange = $state(24); // hours (0 = all data)
	let readings = $state<HistoricalReading[]>([]);
	let ambientReadings = $state<AmbientHistoricalReading[]>([]);
	let chamberReadings = $state<ChamberHistoricalReading[]>([]);
	let currentTrend = $state<TrendResult | null>(null);
	// Days until fermentation completes, from the backend prediction: the same
	// number the Predictions panel and the assistant show (tilt_ui-3kbr). The
	// chart's own line-to-1.010 estimate is gone.
	let etaDays = $state<number | null>(null);
	// Heater/cooler events for the bands. The chart loads its own, for the
	// selected range, so no page can forget to pass them (tilt_ui-glha).
	let controlEvents = $state<ControlEvent[]>([]);
	let deviceId = $state<string | null>(null); // Store device_id from batch
	let isHistoricalBatch = $state(false); // Track if batch is completed/conditioning

	// Helper to read CSS variable values at runtime (for uPlot which needs actual color values)
	function getCssVar(name: string, fallback: string = ''): string {
		if (typeof document === 'undefined') return fallback;
		return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
	}

	// Chart colors - read from CSS tokens at runtime
	// These are initialized with fallbacks and updated on mount
	let chartColors = $state({
		sg: '',
		sgFill: '',
		temp: '',
		surface: '',
		textMuted: '',
		textSecondary: '',
		grid: '',
		ambient: '',
		chamber: '',
		trend: '',
		anomaly: '',
		battery: '',
		filtered: '',
		filteredTemp: '',
		heatingBand: '',
		coolingBand: '',
		rest: ''
	});


	// Color mapping for tilt accent in chart (reads --tilt-* tokens)
	function getTiltColorMap(): Record<string, string> {
		return {
			RED: getCssVar('--tilt-red'),
			GREEN: getCssVar('--tilt-green'),
			BLACK: getCssVar('--tilt-black'),
			PURPLE: getCssVar('--tilt-purple'),
			ORANGE: getCssVar('--tilt-orange'),
			BLUE: getCssVar('--tilt-blue'),
			YELLOW: getCssVar('--tilt-yellow'),
			PINK: getCssVar('--tilt-pink')
		};
	}

	// Initialize chart colors from CSS tokens
	function initChartColors() {
		chartColors = {
			sg: getCssVar('--chart-sg'),
			sgFill: getCssVar('--chart-sg-fill'),
			temp: getCssVar('--chart-temp'),
			surface: getCssVar('--bg-surface'),
			textMuted: getCssVar('--chart-axis'),
			textSecondary: getCssVar('--ink-secondary'),
			grid: getCssVar('--chart-grid'),
			ambient: getCssVar('--chart-ambient'),
			chamber: getCssVar('--chart-chamber'),
			trend: getCssVar('--chart-trend'),
			anomaly: getCssVar('--chart-anomaly'),
			battery: getCssVar('--chart-battery'),
			filtered: getCssVar('--chart-filtered'),
			filteredTemp: getCssVar('--chart-filtered-temp'),
			heatingBand: getCssVar('--chart-heating-band'),
			coolingBand: getCssVar('--chart-cooling-band'),
			rest: getCssVar('--accent')
		};
	}

	// Trend line visibility state
	const TREND_STORAGE_KEY = 'brewsignal_chart_trend_enabled';
	let showTrendLine = $state(true);

	// Ambient, Chamber, Battery visibility toggles
	const AMBIENT_STORAGE_KEY = 'brewsignal_chart_ambient_enabled';
	const CHAMBER_STORAGE_KEY = 'brewsignal_chart_chamber_enabled';
	const ANOMALY_STORAGE_KEY = 'brewsignal_chart_anomaly_enabled';
	const BATTERY_STORAGE_KEY = 'brewsignal_chart_battery_enabled';
	let showAmbient = $state(true);
	let showChamber = $state(true);
	let showAnomalies = $state(true);
	let showBattery = $state(true);

	// Track if battery data is available
	let hasBatteryData = $state(false);

	// Kalman-filtered SG series (from ML pipeline)
	const FILTERED_STORAGE_KEY = 'brewsignal_chart_filtered_enabled';
	let showFiltered = $state(true);
	let hasFilteredData = $state(false);

	// Kalman-filtered temperature series (from ML pipeline)
	const FILTERED_TEMP_STORAGE_KEY = 'brewsignal_chart_filtered_temp_enabled';
	let showFilteredTemp = $state(true);
	let hasFilteredTempData = $state(false);

	// Anomaly data for tooltip
	interface AnomalyInfo {
		timestamp: number;
		sg: number;
		reasons: string[];
	}
	let anomalyData = $state<AnomalyInfo[]>([]);

	// Control period data for heating/cooling bands
	interface ControlPeriod {
		type: 'heating' | 'cooling';
		startTime: number;
		endTime: number;
	}
	let controlPeriods = $state<ControlPeriod[]>([]);
	const CONTROL_BANDS_STORAGE_KEY = 'brewsignal_chart_control_bands_enabled';
	let showControlBands = $state(true);

	// Linear regression for trend line calculation
	interface TrendResult {
		slope: number;        // SG change per second
		intercept: number;    // Y-intercept
		r2: number;           // Coefficient of determination (0-1)
	}

	function calculateLinearRegression(
		timestamps: number[],
		sgValues: (number | null)[]
	): TrendResult | null {
		// Filter out null values and pair with timestamps
		const validPairs: [number, number][] = [];
		for (let i = 0; i < timestamps.length; i++) {
			if (sgValues[i] !== null) {
				validPairs.push([timestamps[i], sgValues[i]!]);
			}
		}

		// Need at least 10 points for meaningful trend
		if (validPairs.length < 10) return null;

		const n = validPairs.length;
		let sumX = 0, sumY = 0, sumXY = 0, sumX2 = 0;

		for (const [x, y] of validPairs) {
			sumX += x;
			sumY += y;
			sumXY += x * y;
			sumX2 += x * x;
		}

		const denom = n * sumX2 - sumX * sumX;
		if (Math.abs(denom) < 1e-10) return null; // Avoid division by zero

		const slope = (n * sumXY - sumX * sumY) / denom;
		const intercept = (sumY - slope * sumX) / n;

		// Calculate R² (coefficient of determination)
		const yMean = sumY / n;
		let ssRes = 0, ssTot = 0;
		for (const [x, y] of validPairs) {
			const predicted = slope * x + intercept;
			ssRes += (y - predicted) ** 2;
			ssTot += (y - yMean) ** 2;
		}
		const r2 = ssTot > 0 ? 1 - (ssRes / ssTot) : 0;

		return { slope, intercept, r2 };
	}

	function processControlEvents(events: ControlEvent[]): ControlPeriod[] {
		const periods: ControlPeriod[] = [];

		// Track active periods
		let heatingStart: number | null = null;
		let coolingStart: number | null = null;

		for (const event of events) {
			const timestamp = parseUtcTimestamp(event.timestamp);

			if (event.action === 'heat_on') {
				heatingStart = timestamp;
			} else if (event.action === 'heat_off' && heatingStart !== null) {
				periods.push({
					type: 'heating',
					startTime: heatingStart,
					endTime: timestamp
				});
				heatingStart = null;
			} else if (event.action === 'cool_on') {
				coolingStart = timestamp;
			} else if (event.action === 'cool_off' && coolingStart !== null) {
				periods.push({
					type: 'cooling',
					startTime: coolingStart,
					endTime: timestamp
				});
				coolingStart = null;
			}
		}

		// Handle unpaired events - extend to current time
		const now = Date.now() / 1000;
		if (heatingStart !== null) {
			periods.push({
				type: 'heating',
				startTime: heatingStart,
				endTime: now
			});
		}
		if (coolingStart !== null) {
			periods.push({
				type: 'cooling',
				startTime: coolingStart,
				endTime: now
			});
		}

		return periods;
	}

	function generateTrendLine(
		timestamps: number[],
		trend: TrendResult
	): (number | null)[] {
		return timestamps.map(t => trend.slope * t + trend.intercept);
	}

	// Create a date formatter for the target timezone
	function formatTimeInTz(timestamp: number, tz: string, short: boolean): string {
		const date = new Date(timestamp * 1000);
		try {
			if (short) {
				return date.toLocaleTimeString('en-AU', {
					hour: '2-digit',
					minute: '2-digit',
					hour12: false,
					timeZone: tz
				});
			}
			return date.toLocaleDateString('en-AU', {
				month: 'short',
				day: 'numeric',
				timeZone: tz
			});
		} catch (e) {
			// Fallback if timezone is invalid
			console.warn('Invalid timezone:', tz, e);
			if (short) {
				return date.toLocaleTimeString('en-AU', {
					hour: '2-digit',
					minute: '2-digit',
					hour12: false
				});
			}
			return date.toLocaleDateString('en-AU', {
				month: 'short',
				day: 'numeric'
			});
		}
	}

	function getChartOptions(width: number, celsius: boolean, tz: string): uPlot.Options {
		const tiltColors = getTiltColorMap();
		const sgColor = chartColors.sg;
		const tempColor = chartColors.temp;

		return {
			width,
			height: 220,
			padding: [16, 12, 0, 0],
			cursor: {
				show: true,
				x: true,
				y: true,
				drag: { x: false, y: false, setScale: false }
			},
			legend: {
				show: true,
				live: true,
				markers: {
					show: true,
					width: 8,
					stroke: (u, seriesIdx) => u.series[seriesIdx].stroke as string,
					fill: (u, seriesIdx) => u.series[seriesIdx].stroke as string
				}
			},
			hooks: {
				drawClear: [
					(u: uPlot) => {
						if (!showControlBands || controlPeriods.length === 0) return;
						const { ctx } = u;
						const { left, top, width, height } = u.bbox;
						const right = left + width;
						ctx.save();
						for (const period of controlPeriods) {
							let x0 = u.valToPos(period.startTime, 'x', true);
							let x1 = u.valToPos(period.endTime, 'x', true);
							if (x1 < left || x0 > right) continue;
							x0 = Math.max(x0, left);
							x1 = Math.min(x1, right);
							// Keep short relay cycles visible as at least a sliver
							if (x1 - x0 < 1) x1 = x0 + 1;
							ctx.fillStyle =
								period.type === 'heating' ? chartColors.heatingBand : chartColors.coolingBand;
							ctx.fillRect(x0, top, x1 - x0, height);
						}
						ctx.restore();
					}
				],
				draw: [
					// Diacetyl rest marker: a dashed line with a label where the rest started
					(u: uPlot) => {
						if (!restStartedAt) return;
						const { ctx } = u;
						const { left, top, width, height } = u.bbox;
						const x = u.valToPos(parseUtcTimestamp(restStartedAt), 'x', true);
						if (x < left || x > left + width) return;
						const dpr = devicePixelRatio || 1;
						ctx.save();
						ctx.strokeStyle = chartColors.rest;
						ctx.fillStyle = chartColors.rest;
						ctx.lineWidth = dpr;
						ctx.setLineDash([4 * dpr, 3 * dpr]);
						ctx.beginPath();
						ctx.moveTo(x, top);
						ctx.lineTo(x, top + height);
						ctx.stroke();
						ctx.font = `600 ${10 * dpr}px "Archivo", sans-serif`;
						ctx.textBaseline = 'top';
						const label = 'D-REST';
						const flip = x + ctx.measureText(label).width + 8 * dpr > left + width;
						ctx.textAlign = flip ? 'right' : 'left';
						ctx.fillText(label, x + (flip ? -4 : 4) * dpr, top + 4 * dpr);
						ctx.restore();
					}
				],
				setCursor: [
					(u: uPlot) => {
						const idx = u.cursor.idx;
						if (idx === null || idx === undefined) return;

						// Update legend with crosshair values
						const legendEl = u.root.querySelector('.u-legend') as HTMLElement;
						if (!legendEl) return;

						legendEl.style.cssText = `
							position: absolute;
							top: 12px;
							left: 12px;
							background: var(--bg-elevated);
							border: 1px solid var(--rule-strong);
							border-radius: 4px;
							padding: 0.5rem 0.75rem;
							font-family: var(--font-num);
							font-size: 0.6875rem;
							pointer-events: none;
						`;
					}
				]
			},
			scales: {
				x: { time: true },
				sg: {
					auto: true,
					range: (u, min, max) => {
						const padding = (max - min) * 0.1 || 0.005;
						return [min - padding, max + padding];
					}
				},
				temp: {
					auto: true,
					range: (u, min, max) => {
						// Ensure minimum 10-degree range so small fluctuations don't look exaggerated
						const dataRange = max - min;
						const minRange = 10;
						if (dataRange < minRange) {
							const center = (max + min) / 2;
							return [center - minRange / 2, center + minRange / 2];
						}
						const padding = dataRange * 0.1;
						return [min - padding, max + padding];
					}
				},
				battery: {
					auto: false,
					range: [0, 105] // Fixed 0-100% range with padding
				}
			},
			axes: [
				{
					// X axis (time)
					stroke: chartColors.textMuted,
					grid: { stroke: chartColors.grid, width: 1 },
					ticks: { stroke: chartColors.grid, width: 1, size: 4 },
					font: '11px "Chivo Mono", ui-monospace, monospace',
					labelFont: '11px "Chivo Mono", ui-monospace, monospace',
					values: (u, vals) =>
						vals.map((v) => formatTimeInTz(v, tz, selectedRange <= 24))
				},
				{
					// Y axis left (SG/Plato/Brix)
					scale: 'sg',
					stroke: chartColors.textMuted,
					grid: { stroke: chartColors.grid, width: 1 },
					ticks: { stroke: chartColors.grid, width: 1, size: 4 },
					font: '11px "Chivo Mono", ui-monospace, monospace',
					labelFont: '11px "Chivo Mono", ui-monospace, monospace',
					values: (u, vals) => vals.map((v) => formatGravity(v)),
					// Tick steps no finer than the display precision, so labels never repeat.
					// Steps are in SG (the data space), see gravityTicks.ts.
					incrs: gravityIncrs(configState.config.sg_units),
					side: 3 // left
				},
				{
					// Y axis right (Temp)
					scale: 'temp',
					stroke: chartColors.textMuted,
					grid: { show: false },
					ticks: { stroke: chartColors.grid, width: 1, size: 4 },
					font: '11px "Chivo Mono", ui-monospace, monospace',
					labelFont: '11px "Chivo Mono", ui-monospace, monospace',
					values: (u, vals) => vals.map((v) => v.toFixed(0) + '°'),
					side: 1 // right
				}
			],
			series: [
				{
					// x series (timestamps)
					value: (u: uPlot, v: number) => formatTimeInTz(v, tz, false) + ' ' + formatTimeInTz(v, tz, true)
				},
				{
					// Gravity series (SG/Plato/Brix)
					label: gravityUnit === 'SG' ? 'Gravity' : gravityUnit === '°P' ? 'Plato' : 'Brix',
					scale: 'sg',
					stroke: sgColor,
					width: 2,
					value: (u: uPlot, v: number | null) => v !== null ? formatGravity(v) : '--',
					fill: (u: uPlot, idx: number) => {
						const gradient = u.ctx.createLinearGradient(0, u.bbox.top, 0, u.bbox.top + u.bbox.height);
						gradient.addColorStop(0, chartColors.sgFill);
						gradient.addColorStop(1, 'transparent');
						return gradient;
					},
					points: { show: false },
					paths: uPlot.paths.spline?.() // Smooth spline interpolation
				},
				{
					// Wort Temp series
					label: 'Wort',
					scale: 'temp',
					stroke: tempColor,
					width: 1.5,
					dash: [4, 4],
					value: (u: uPlot, v: number | null) => v !== null ? v.toFixed(1) + '°' : '--',
					points: { show: false },
					paths: uPlot.paths.spline?.() // Smooth spline interpolation
				},
				{
					// Ambient Temp series
					label: 'Ambient',
					scale: 'temp',
					stroke: chartColors.ambient,
					width: 1.5,
					dash: [2, 4],
					value: (u: uPlot, v: number | null) => v !== null ? v.toFixed(1) + '°' : '--',
					points: { show: false },
					paths: uPlot.paths.spline?.(), // Smooth spline interpolation
					show: showAmbient
				},
				{
					// Chamber Temp series
					label: 'Chamber',
					scale: 'temp',
					stroke: chartColors.chamber,
					width: 1.5,
					dash: [4, 2],
					value: (u: uPlot, v: number | null) => v !== null ? v.toFixed(1) + '°' : '--',
					points: { show: false },
					paths: uPlot.paths.spline?.(), // Smooth spline interpolation
					show: showChamber
				},
				{
					// SG Trend line series
					label: 'Trend',
					scale: 'sg',
					stroke: chartColors.trend,
					width: 2,
					dash: [8, 4],
					value: (u: uPlot, v: number | null) => v !== null ? formatGravity(v) : '--',
					points: { show: false },
					show: showTrendLine
					// Linear path (no spline for trend line)
				},
				{
					// Anomaly markers series - points only, no connecting line
					label: 'Anomaly',
					scale: 'sg',
					stroke: 'transparent',
					width: 0,
					value: (u: uPlot, v: number | null) => v !== null ? formatGravity(v) + ' ⚠️' : '--',
					points: {
						show: true,
						size: 12,
						space: 0,
						fill: chartColors.anomaly,
						stroke: chartColors.surface,
						width: 2
					},
					show: showAnomalies
				},
				{
					// Battery level series
					label: 'Battery',
					scale: 'battery',
					stroke: chartColors.battery,
					width: 1.5,
					dash: [2, 2],
					value: (u: uPlot, v: number | null) => v !== null ? v.toFixed(0) + '%' : '--',
					points: { show: false },
					paths: uPlot.paths.spline?.(), // Smooth spline interpolation
					show: showBattery
				},
				{
					// Kalman-filtered SG series (ML pipeline output)
					label: 'Filtered',
					scale: 'sg',
					stroke: chartColors.filtered,
					width: 1.5,
					value: (u: uPlot, v: number | null) => v !== null ? formatGravity(v) : '--',
					points: { show: false },
					paths: uPlot.paths.spline?.(),
					show: hasFilteredData && showFiltered
				},
				{
					// Kalman-filtered temperature series (ML pipeline output)
					label: 'Filt Temp',
					scale: 'temp',
					stroke: chartColors.filteredTemp,
					width: 1.5,
					dash: [6, 3],
					value: (u: uPlot, v: number | null) => v !== null ? v.toFixed(1) + '°' : '--',
					points: { show: false },
					paths: uPlot.paths.spline?.(),
					show: hasFilteredTempData && showFilteredTemp
				}
			]
		};
	}

	// Moving average smoothing function
	function smoothData(values: (number | null)[], windowSize: number): (number | null)[] {
		if (windowSize <= 1) return values;

		const result: (number | null)[] = [];
		for (let i = 0; i < values.length; i++) {
			// Collect valid values in the window
			const windowValues: number[] = [];
			const halfWindow = Math.floor(windowSize / 2);

			for (let j = Math.max(0, i - halfWindow); j <= Math.min(values.length - 1, i + halfWindow); j++) {
				const v = values[j];
				if (v !== null) windowValues.push(v);
			}

			if (windowValues.length > 0) {
				result.push(windowValues.reduce((a, b) => a + b, 0) / windowValues.length);
			} else {
				result.push(null);
			}
		}
		return result;
	}

	// Downsample data for longer time ranges to improve performance
	function downsampleData(
		timestamps: number[],
		sgValues: (number | null)[],
		tempValues: (number | null)[],
		ambientValues: (number | null)[],
		chamberValues: (number | null)[],
		batteryValues: (number | null)[],
		filteredValues: (number | null)[],
		filteredTempValues: (number | null)[],
		maxPoints: number
	): [number[], (number | null)[], (number | null)[], (number | null)[], (number | null)[], (number | null)[], (number | null)[], (number | null)[]] {
		if (timestamps.length <= maxPoints) {
			return [timestamps, sgValues, tempValues, ambientValues, chamberValues, batteryValues, filteredValues, filteredTempValues];
		}

		const step = Math.ceil(timestamps.length / maxPoints);
		const newTimestamps: number[] = [];
		const newSg: (number | null)[] = [];
		const newTemp: (number | null)[] = [];
		const newAmbient: (number | null)[] = [];
		const newChamber: (number | null)[] = [];
		const newBattery: (number | null)[] = [];
		const newFiltered: (number | null)[] = [];
		const newFilteredTemp: (number | null)[] = [];

		for (let i = 0; i < timestamps.length; i += step) {
			// Average values in this bucket
			const bucketEnd = Math.min(i + step, timestamps.length);
			let sgSum = 0, sgCount = 0;
			let tempSum = 0, tempCount = 0;
			let ambientSum = 0, ambientCount = 0;
			let chamberSum = 0, chamberCount = 0;
			let batterySum = 0, batteryCount = 0;
			let filteredSum = 0, filteredCount = 0;
			let filteredTempSum = 0, filteredTempCount = 0;

			for (let j = i; j < bucketEnd; j++) {
				if (sgValues[j] !== null) { sgSum += sgValues[j]!; sgCount++; }
				if (tempValues[j] !== null) { tempSum += tempValues[j]!; tempCount++; }
				if (ambientValues[j] !== null) { ambientSum += ambientValues[j]!; ambientCount++; }
				if (chamberValues[j] !== null) { chamberSum += chamberValues[j]!; chamberCount++; }
				if (batteryValues[j] !== null) { batterySum += batteryValues[j]!; batteryCount++; }
				if (filteredValues[j] !== null) { filteredSum += filteredValues[j]!; filteredCount++; }
				if (filteredTempValues[j] !== null) { filteredTempSum += filteredTempValues[j]!; filteredTempCount++; }
			}

			// Use middle timestamp of bucket
			newTimestamps.push(timestamps[Math.floor((i + bucketEnd - 1) / 2)]);
			newSg.push(sgCount > 0 ? sgSum / sgCount : null);
			newTemp.push(tempCount > 0 ? tempSum / tempCount : null);
			newAmbient.push(ambientCount > 0 ? ambientSum / ambientCount : null);
			newChamber.push(chamberCount > 0 ? chamberSum / chamberCount : null);
			newBattery.push(batteryCount > 0 ? batterySum / batteryCount : null);
			newFiltered.push(filteredCount > 0 ? filteredSum / filteredCount : null);
			newFilteredTemp.push(filteredTempCount > 0 ? filteredTempSum / filteredTempCount : null);
		}

		return [newTimestamps, newSg, newTemp, newAmbient, newChamber, newBattery, newFiltered, newFilteredTemp];
	}

	// Parse timestamp string as UTC (backend stores UTC but may omit Z suffix)
	function parseUtcTimestamp(timestamp: string): number {
		// If timestamp doesn't end with Z or timezone offset, treat as UTC
		if (!timestamp.endsWith('Z') && !timestamp.match(/[+-]\d{2}:\d{2}$/)) {
			timestamp = timestamp + 'Z';
		}
		return new Date(timestamp).getTime() / 1000;
	}

	// Interpolate ambient readings to match tilt timestamps
	function interpolateAmbientToTimestamps(
		ambientReadings: AmbientHistoricalReading[],
		targetTimestamps: number[],
		celsius: boolean
	): (number | null)[] {
		if (ambientReadings.length === 0 || targetTimestamps.length === 0) {
			return targetTimestamps.map(() => null);
		}

		// Sort ambient readings by timestamp (oldest first)
		const sortedAmbient = [...ambientReadings].sort(
			(a, b) => parseUtcTimestamp(a.timestamp) - parseUtcTimestamp(b.timestamp)
		);

		// Extract timestamps and temps from ambient readings
		const ambientTimes = sortedAmbient.map(r => parseUtcTimestamp(r.timestamp));
		const ambientTemps = sortedAmbient.map(r => {
			if (r.temperature === null) return null;
			// Ambient is in Celsius from HA, convert to F if needed
			return celsius ? r.temperature : (r.temperature * 9 / 5) + 32;
		});

		// For each target timestamp, find nearest ambient value or interpolate
		return targetTimestamps.map(ts => {
			// Find surrounding ambient readings
			let before: { time: number; temp: number | null } | null = null;
			let after: { time: number; temp: number | null } | null = null;

			for (let i = 0; i < ambientTimes.length; i++) {
				if (ambientTimes[i] <= ts) {
					before = { time: ambientTimes[i], temp: ambientTemps[i] };
				}
				if (ambientTimes[i] >= ts && after === null) {
					after = { time: ambientTimes[i], temp: ambientTemps[i] };
					break;
				}
			}

			// If we have both, interpolate
			if (before && after && before.temp !== null && after.temp !== null) {
				if (before.time === after.time) return before.temp;
				const ratio = (ts - before.time) / (after.time - before.time);
				return before.temp + ratio * (after.temp - before.temp);
			}

			// Use nearest available value
			if (before !== null && before.temp !== null) return before.temp;
			if (after !== null && after.temp !== null) return after.temp;

			return null;
		});
	}

	function processData(
		readings: HistoricalReading[],
		ambient: AmbientHistoricalReading[],
		chamber: ChamberHistoricalReading[],
		celsius: boolean
	): uPlot.AlignedData {
		// Readings come newest first, reverse for chronological order
		const sorted = [...readings].reverse();

		let timestamps: number[] = [];
		let sgValues: (number | null)[] = [];
		let tempValues: (number | null)[] = [];
		let batteryValues: (number | null)[] = [];
		let anomalyValues: (number | null)[] = [];
		let filteredValues: (number | null)[] = [];
		let filteredTempValues: (number | null)[] = [];
		const anomalyInfoList: AnomalyInfo[] = [];
		let foundBatteryData = false;
		let foundFilteredData = false;
		let foundFilteredTempData = false;

		for (const r of sorted) {
			const ts = parseUtcTimestamp(r.timestamp);
			const sg = r.sg_calibrated ?? r.sg_raw;
			timestamps.push(ts);
			sgValues.push(sg);

			// Kalman-filtered SG from the ML pipeline (null before pipeline warm-up)
			const filtered = r.sg_filtered ?? null;
			filteredValues.push(filtered);
			if (filtered !== null) foundFilteredData = true;

			// Track anomaly data - show SG value only for anomaly points
			if (r.is_anomaly && sg !== null) {
				anomalyValues.push(sg);
				// Parse anomaly reasons (stored as comma-separated string or JSON)
				let reasons: string[] = [];
				if (r.anomaly_reasons) {
					try {
						reasons = JSON.parse(r.anomaly_reasons);
					} catch {
						reasons = r.anomaly_reasons.split(',').map(s => s.trim());
					}
				}
				anomalyInfoList.push({ timestamp: ts, sg, reasons });
			} else {
				anomalyValues.push(null);
			}

			// Temperature is already in Celsius from API (since PR #66)
			// Convert to Fahrenheit only if user preference is F
			const temp = r.temp_calibrated ?? r.temp_raw;
			if (temp !== null) {
				tempValues.push(celsius ? temp : (temp * 9 / 5) + 32);
			} else {
				tempValues.push(null);
			}

			// Kalman-filtered temperature from the ML pipeline (Celsius, null before warm-up)
			const filteredTemp = r.temp_filtered ?? null;
			if (filteredTemp !== null) {
				filteredTempValues.push(celsius ? filteredTemp : (filteredTemp * 9 / 5) + 32);
				foundFilteredTempData = true;
			} else {
				filteredTempValues.push(null);
			}

			// Battery level (GravityMon/iSpindel only)
			if (r.battery_percent !== null && r.battery_percent !== undefined) {
				batteryValues.push(r.battery_percent);
				foundBatteryData = true;
			} else {
				batteryValues.push(null);
			}
		}

		// Update whether we have battery data
		hasBatteryData = foundBatteryData;
		hasFilteredData = foundFilteredData;
		hasFilteredTempData = foundFilteredTempData;

		// Store anomaly info for tooltips
		anomalyData = anomalyInfoList;

		// Interpolate ambient and chamber readings to match tilt timestamps
		let ambientValues = interpolateAmbientToTimestamps(ambient, timestamps, celsius);
		let chamberValues = interpolateAmbientToTimestamps(chamber, timestamps, celsius);

		// Apply smoothing if enabled in config (don't smooth anomaly markers or battery)
		if (smoothingEnabled && smoothingSamples > 1) {
			sgValues = smoothData(sgValues, smoothingSamples);
			tempValues = smoothData(tempValues, smoothingSamples);
			ambientValues = smoothData(ambientValues, smoothingSamples);
			chamberValues = smoothData(chamberValues, smoothingSamples);
			// Note: Don't smooth battery values - they should show actual readings
		}

		// Downsample for performance (max 500 points)
		// Note: anomalyValues are handled separately to preserve all anomaly markers
		const maxPoints = 500;
		const originalTimestamps = [...timestamps];
		const originalAnomalyValues = [...anomalyValues];
		[timestamps, sgValues, tempValues, ambientValues, chamberValues, batteryValues, filteredValues, filteredTempValues] = downsampleData(timestamps, sgValues, tempValues, ambientValues, chamberValues, batteryValues, filteredValues, filteredTempValues, maxPoints);

		// Map anomaly values to downsampled timestamps
		// For each downsampled timestamp, check if any original anomaly was near it
		anomalyValues = timestamps.map(ts => {
			// Find the closest original anomaly within a reasonable window
			for (let i = 0; i < originalTimestamps.length; i++) {
				if (originalAnomalyValues[i] !== null) {
					// Check if this anomaly is close to the current downsampled timestamp
					const timeDiff = Math.abs(originalTimestamps[i] - ts);
					const windowSize = (originalTimestamps[originalTimestamps.length - 1] - originalTimestamps[0]) / maxPoints;
					if (timeDiff <= windowSize) {
						return originalAnomalyValues[i];
					}
				}
			}
			return null;
		});

		// Calculate trend line
		const trend = calculateLinearRegression(timestamps, sgValues);
		currentTrend = trend;

		// Generate trend line values (or nulls if no valid trend)
		const trendValues: (number | null)[] = trend
			? generateTrendLine(timestamps, trend)
			: timestamps.map(() => null);

		return [timestamps, sgValues, tempValues, ambientValues, chamberValues, trendValues, anomalyValues, batteryValues, filteredValues, filteredTempValues];
	}

// Minimum interval between data fetches (30 seconds) to prevent BLE event spam
const MIN_FETCH_INTERVAL_MS = 30000;

async function loadData(userTriggered = false) {
	const now = Date.now();
	const timeSinceLastLoad = now - lastLoadTime;

	// For automatic reloads, respect the minimum fetch interval
	// User-triggered actions (range change, manual refresh) always proceed
	if (!userTriggered && lastLoadTime > 0 && timeSinceLastLoad < MIN_FETCH_INTERVAL_MS) {
		return;
	}

	loading = true;
	error = null;

	try {
		// Fetch batch to get device_id and status if we don't have it yet
		if (!deviceId) {
			const batch = await fetchBatch(batchId);
			deviceId = batch.device_id ?? null;
			// Check if this is a historical/completed batch
			const historicalStatuses = ['completed', 'conditioning', 'archived'];
			isHistoricalBatch = historicalStatuses.includes(batch.status);
			// Default to "All" for historical batches on first load
			if (isHistoricalBatch && selectedRange !== 0) {
				selectedRange = 0; // 0 = all data
			}
		}

		// Fetch batch readings (all readings for batch, regardless of device)
		// This allows viewing historical data even after switching devices mid-ferment
		// Pass hours=undefined when selectedRange is 0 (All) to get all data
		const hoursParam = selectedRange > 0 ? selectedRange : undefined;
		const [batchData, ambientData, chamberData, prediction, events] = await Promise.all([
			fetchBatchReadings(batchId, hoursParam),
			// For ambient/chamber, use 720 hours (30 days) as max when "All" is selected
			fetchAmbientHistory(hoursParam ?? 720).catch(() => []), // Don't fail if ambient unavailable
			fetchChamberHistory(hoursParam ?? 720).catch(() => []), // Don't fail if chamber unavailable
			// No ETA for a batch that is no longer fermenting
			isHistoricalBatch ? null : fetchBatchPredictions(batchId).catch(() => null),
			fetchBatchControlEvents(batchId, hoursParam ?? 720).catch(() => [])
		]);
		controlEvents = events;
		const hours = prediction?.available ? prediction.hours_to_completion : null;
		etaDays = hours != null && hours > 0 ? hours / 24 : null;
		readings = batchData;
		ambientReadings = ambientData;
		chamberReadings = chamberData;
		updateChart();
	} catch (e) {
		error = e instanceof Error ? e.message : 'Failed to load data';
	} finally {
		lastLoadTime = Date.now();
		loading = false;
	}
}

	function updateChart() {
		if (destroyed || !chartContainer || readings.length === 0) return;

		const data = processData(readings, ambientReadings, chamberReadings, useCelsius);
		// Collapsed (display: none) containers measure 0: reuse the last visible width
		if (chartContainer.clientWidth > 0) lastWidth = chartContainer.clientWidth;
		const opts = getChartOptions(lastWidth || 600, useCelsius, systemTimezone);

		if (chart) {
			chart.destroy();
		}

		chart = new uPlot(opts, data, chartContainer);
	}

// Set once the component is destroyed; async init and timers check it so nothing is
// installed (or left running) after teardown.
let destroyed = false;
let lastWidth = 0;
let resizeObserver: ResizeObserver | null = null;
let themeObserver: MutationObserver | null = null;

function handleResize() {
	// A hidden (collapsed) container measures 0; keep the last size until it is shown again
	if (chart && chartContainer && chartContainer.clientWidth > 0) {
		chart.setSize({ width: chartContainer.clientWidth, height: 220 });
	}
}

let refreshInterval: ReturnType<typeof setInterval> | null = null;

function resetRefreshInterval() {
	if (refreshInterval) {
		clearInterval(refreshInterval);
		refreshInterval = null;
	}

	if (refreshMinutes > 0 && !destroyed) {
		const intervalMs = refreshMinutes * 60 * 1000;
		refreshInterval = setInterval(() => {
			if (!loading) {
				// Automatic refresh - NOT user triggered, subject to throttling
				loadData(false);
			}
		}, intervalMs);
	}
}

onMount(async () => {
	// Initialize chart colors from CSS tokens
	initChartColors();

	// uPlot paints on canvas with colours resolved once: re-resolve and rebuild on theme switch
	themeObserver = new MutationObserver(() => {
		if (destroyed) return;
		initChartColors();
		updateChart();
	});
	themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

	// Load preferred refresh interval from localStorage
	const storedRefresh = localStorage.getItem(REFRESH_STORAGE_KEY);
	if (storedRefresh !== null) {
		const parsed = parseInt(storedRefresh, 10);
		if (!Number.isNaN(parsed)) {
			refreshMinutes = parsed;
		}
	}

	// Load preferences from localStorage
	const storedTrend = localStorage.getItem(TREND_STORAGE_KEY);
	if (storedTrend !== null) {
		showTrendLine = storedTrend === 'true';
	}
	const storedAmbient = localStorage.getItem(AMBIENT_STORAGE_KEY);
	if (storedAmbient !== null) {
		showAmbient = storedAmbient === 'true';
	}
	const storedChamber = localStorage.getItem(CHAMBER_STORAGE_KEY);
	if (storedChamber !== null) {
		showChamber = storedChamber === 'true';
	}
	const storedAnomaly = localStorage.getItem(ANOMALY_STORAGE_KEY);
	if (storedAnomaly !== null) {
		showAnomalies = storedAnomaly === 'true';
	}
	const storedBattery = localStorage.getItem(BATTERY_STORAGE_KEY);
	if (storedBattery !== null) {
		showBattery = storedBattery === 'true';
	}
	const storedControlBands = localStorage.getItem(CONTROL_BANDS_STORAGE_KEY);
	if (storedControlBands !== null) {
		showControlBands = storedControlBands === 'true';
	}
	const storedFiltered = localStorage.getItem(FILTERED_STORAGE_KEY);
	if (storedFiltered !== null) {
		showFiltered = storedFiltered === 'true';
	}

	const storedFilteredTemp = localStorage.getItem(FILTERED_TEMP_STORAGE_KEY);
	if (storedFilteredTemp !== null) {
		showFilteredTemp = storedFilteredTemp === 'true';
	}

	// Fetch system timezone for chart display
	try {
		const response = await fetch('/api/system/timezone');
		if (response.ok) {
			const data = await response.json();
			systemTimezone = data.timezone || 'UTC';
		}
	} catch (e) {
		console.warn('Failed to fetch system timezone, using UTC');
	}

	// Initial load is user-triggered (mounting the component)
	await loadData(true);
	// Destroyed while the async init was in flight: install nothing
	if (destroyed) return;
	// Observe the container (also tracks width changes while collapsed/expanded)
	if (chartContainer) {
		resizeObserver = new ResizeObserver(handleResize);
		resizeObserver.observe(chartContainer);
	}
	resetRefreshInterval();
});

	onDestroy(() => {
		destroyed = true;
		chart?.destroy();
		chart = null;
		resizeObserver?.disconnect();
		resizeObserver = null;
		themeObserver?.disconnect();
		themeObserver = null;
		if (refreshInterval) {
			clearInterval(refreshInterval);
			refreshInterval = null;
		}
	});

	let trendStats = $derived(showTrend && readings.length > 0 ? analyseSg(readings, originalGravity) : null);

	// Process control events into periods when they change
	$effect(() => {
		if (controlEvents && controlEvents.length > 0) {
			controlPeriods = processControlEvents(controlEvents);
		} else {
			controlPeriods = [];
		}
		// Bands are painted in the drawClear hook, which only runs on redraw
		chart?.redraw();
	});

	// The rest marker is painted in the draw hook: redraw when it appears
	$effect(() => {
		restStartedAt;
		chart?.redraw();
	});

	// Re-render chart when temp units or smoothing settings change
	$effect(() => {
		if (useCelsius !== undefined && readings.length > 0 && chartContainer) {
			updateChart();
		}
	});

	// Re-render chart when smoothing settings change
	$effect(() => {
		// Track smoothing changes
		const _ = [smoothingEnabled, smoothingSamples];
		if (readings.length > 0 && chartContainer) {
			updateChart();
		}
	});

	function handleRefreshChange(event: Event) {
		const minutes = Number((event.target as HTMLSelectElement).value);
		refreshMinutes = minutes;
		localStorage.setItem(REFRESH_STORAGE_KEY, String(minutes));
		resetRefreshInterval();
		// User changed refresh setting - trigger immediate reload
		loadData(true);
	}

	function toggleTrendLine() {
		showTrendLine = !showTrendLine;
		localStorage.setItem(TREND_STORAGE_KEY, String(showTrendLine));
		// Update the series visibility in the existing chart
		if (chart) {
			chart.setSeries(5, { show: showTrendLine });
		}
	}

	function toggleAmbient() {
		showAmbient = !showAmbient;
		localStorage.setItem(AMBIENT_STORAGE_KEY, String(showAmbient));
		// Update the series visibility in the existing chart
		if (chart) {
			chart.setSeries(3, { show: showAmbient });
		}
	}

	function toggleChamber() {
		showChamber = !showChamber;
		localStorage.setItem(CHAMBER_STORAGE_KEY, String(showChamber));
		// Update the series visibility in the existing chart
		if (chart) {
			chart.setSeries(4, { show: showChamber });
		}
	}

	function toggleAnomalies() {
		showAnomalies = !showAnomalies;
		localStorage.setItem(ANOMALY_STORAGE_KEY, String(showAnomalies));
		// Update the series visibility in the existing chart
		if (chart) {
			chart.setSeries(6, { show: showAnomalies });
		}
	}

	function toggleFiltered() {
		showFiltered = !showFiltered;
		localStorage.setItem(FILTERED_STORAGE_KEY, String(showFiltered));
		// Update the series visibility in the existing chart
		if (chart) {
			chart.setSeries(8, { show: showFiltered });
		}
	}

	function toggleFilteredTemp() {
		showFilteredTemp = !showFilteredTemp;
		localStorage.setItem(FILTERED_TEMP_STORAGE_KEY, String(showFilteredTemp));
		// Update the series visibility in the existing chart
		if (chart) {
			chart.setSeries(9, { show: showFilteredTemp });
		}
	}

	function toggleControlBands() {
		showControlBands = !showControlBands;
		localStorage.setItem(CONTROL_BANDS_STORAGE_KEY, String(showControlBands));
		chart?.redraw();
	}

	function toggleBattery() {
		showBattery = !showBattery;
		localStorage.setItem(BATTERY_STORAGE_KEY, String(showBattery));
		// Update the series visibility in the existing chart
		if (chart) {
			chart.setSeries(7, { show: showBattery });
		}
	}
</script>

<div class="chart-wrapper" role="region" aria-label="Fermentation Chart">
	<!-- Time range selector -->
	<div class="chart-controls">
		<div class="range-group">
			{#each TIME_RANGES as range}
				<button
					type="button"
					class="range-btn"
					class:active={selectedRange === range.hours}
					onclick={() => {
						if (selectedRange !== range.hours) {
							selectedRange = range.hours;
							loadData(true);
						}
					}}
				>
					{range.label}
				</button>
			{/each}
		</div>
		<div class="controls-right">
			<div class="refresh-control">
				<label for="refresh-{batchId}">Refresh</label>
				<select id="refresh-{batchId}" class="refresh-select" value={refreshMinutes} onchange={handleRefreshChange}>
					{#each REFRESH_OPTIONS as option}
						<option value={option.value}>{option.label}</option>
					{/each}
				</select>
			</div>
			<div class="chart-legend">
				<span class="legend-item">
					<span class="legend-dot legend-dot-sg"></span>
					<span>SG</span>
				</span>
				<span class="legend-item">
					<span
						class="legend-line"
						style="background: var(--chart-temp);"
					></span>
					<span>Wort</span>
				</span>
				<button
					type="button"
					class="legend-item legend-toggle"
					class:legend-disabled={!showAmbient}
					onclick={toggleAmbient}
					title={showAmbient ? 'Hide ambient temp' : 'Show ambient temp'}
				>
					<span class="legend-line legend-line-ambient"></span>
					<span>Ambient</span>
				</button>
				<button
					type="button"
					class="legend-item legend-toggle"
					class:legend-disabled={!showChamber}
					onclick={toggleChamber}
					title={showChamber ? 'Hide chamber temp' : 'Show chamber temp'}
				>
					<span class="legend-line legend-line-chamber"></span>
					<span>Chamber</span>
				</button>
				<button
					type="button"
					class="legend-item legend-toggle"
					class:legend-disabled={!showTrendLine}
					onclick={toggleTrendLine}
					title={showTrendLine ? 'Hide trend line' : 'Show trend line'}
				>
					<span class="legend-line legend-line-trend"></span>
					<span>Trend</span>
				</button>
				{#if anomalyData.length > 0}
					<button
						type="button"
						class="legend-item legend-toggle anomaly-toggle"
						class:legend-disabled={!showAnomalies}
						onclick={toggleAnomalies}
						title={showAnomalies ? 'Hide anomaly markers' : 'Show anomaly markers'}
					>
						<span class="legend-dot legend-dot-anomaly"></span>
						<span>Anomalies ({anomalyData.length})</span>
					</button>
				{/if}
				{#if hasFilteredData}
					<button
						type="button"
						class="legend-item legend-toggle"
						class:legend-disabled={!showFiltered}
						onclick={toggleFiltered}
						title={showFiltered ? 'Hide Kalman-filtered SG' : 'Show Kalman-filtered SG'}
					>
						<span class="legend-line legend-line-filtered"></span>
						<span>Filtered</span>
					</button>
				{/if}
				{#if hasFilteredTempData}
					<button
						type="button"
						class="legend-item legend-toggle"
						class:legend-disabled={!showFilteredTemp}
						onclick={toggleFilteredTemp}
						title={showFilteredTemp ? 'Hide Kalman-filtered temperature' : 'Show Kalman-filtered temperature'}
					>
						<span class="legend-line legend-line-filtered-temp"></span>
						<span>Filt Temp</span>
					</button>
				{/if}
				{#if controlPeriods.length > 0}
					<button
						type="button"
						class="legend-item legend-toggle"
						class:legend-disabled={!showControlBands}
						onclick={toggleControlBands}
						title={showControlBands ? 'Hide heating/cooling bands' : 'Show heating/cooling bands'}
					>
						<span class="legend-band legend-band-heating"></span>
						<span class="legend-band legend-band-cooling"></span>
						<span>Heat/Cool</span>
					</button>
				{/if}
				{#if hasBatteryData}
					<button
						type="button"
						class="legend-item legend-toggle"
						class:legend-disabled={!showBattery}
						onclick={toggleBattery}
						title={showBattery ? 'Hide battery level' : 'Show battery level'}
					>
						<span class="legend-line legend-line-battery"></span>
						<span>Battery</span>
					</button>
				{/if}
			</div>
		</div>
	</div>

	<!-- Chart container -->
	<div
		class="chart-container"
		bind:this={chartContainer}
		role="img"
		aria-label="Fermentation progress chart showing gravity and temperature over time"
	>
		<span class="sr-only">
			Interactive chart displaying fermentation data.
			{#if readings.length > 0}
				Showing {readings.length} data points.
			{:else}
				No data available yet.
			{/if}
		</span>
		{#if loading}
			<div class="loading-overlay">
				<div class="loading-spinner"></div>
			</div>
		{/if}
		{#if error}
			<div class="chart-error">
				<span>Failed to load chart</span>
				<button type="button" class="retry-btn" onclick={() => loadData(true)}>Retry</button>
			</div>
		{:else if readings.length === 0}
			<div class="chart-empty">
				<span>No historical data yet</span>
				<span class="text-xs opacity-60">Data will appear as readings are logged</span>
			</div>
		{/if}
	</div>

	{#if showTrend && trendStats}
		<dl class="trend" aria-label="Fermentation trend">
			<div class="trend-item">
				<dt>Rate</dt>
				<dd>{formatRate(trendStats.fermRate)}<span class="trend-unit">&thinsp;SG/day</span></dd>
			</div>
			{#if etaDays != null}
				<div class="trend-item" title="Estimated time until fermentation completes (same prediction as the Predictions panel)">
					<dt>ETA to FG</dt>
					<dd>{formatDuration(etaDays)}</dd>
				</div>
			{/if}
			<div class="trend-item">
				<dt>Stable for</dt>
				<dd>{formatDuration(trendStats.daysAtCurrentSg)}</dd>
			</div>
			{#if trendStats.ogIsEstimated}
				<div class="trend-item" title="Estimated from the highest readings; no measured OG">
					<dt>OG est.</dt>
					<dd>{formatGravity(trendStats.og)}</dd>
				</div>
			{/if}
		</dl>
	{/if}

	<!-- Anomaly Details -->
	{#if showAnomalies && anomalyData.length > 0}
		<div class="anomaly-details">
			{#each anomalyData as anomaly}
				<div class="anomaly-item">
					<span class="anomaly-dot"></span>
					<span class="anomaly-time">{formatTimeInTz(anomaly.timestamp, systemTimezone, false)} {formatTimeInTz(anomaly.timestamp, systemTimezone, true)}</span>
					<span class="anomaly-sg">{formatGravity(anomaly.sg)}</span>
					{#if anomaly.reasons.length > 0}
						<span class="anomaly-reasons">{anomaly.reasons.join(', ')}</span>
					{:else}
						<span class="anomaly-reasons">Unknown reason</span>
					{/if}
				</div>
			{/each}
		</div>
	{/if}

	<!-- Fermentation Stats -->
	{#if showStats && readings.length > 0}
		<FermentationStats
			{readings}
			{originalGravity}
			{etaDays}
		/>
	{/if}
</div>

<style>
	/* One bordered panel: header bar (ranges, refresh, legend) over the plot */
	.chart-wrapper {
		border: 1px solid var(--rule-hairline);
		border-radius: 4px;
		background: var(--bg-surface);
		overflow: hidden;
	}

	.chart-controls {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px 16px;
		flex-wrap: wrap;
		padding: 8px 12px;
		border-bottom: 1px solid var(--rule-hairline);
	}

	.range-group {
		display: flex;
		align-items: center;
		gap: 4px;
		flex-wrap: wrap;
	}

	.controls-right {
		display: flex;
		align-items: center;
		gap: 8px 16px;
		flex-wrap: wrap;
		justify-content: flex-end;
	}

	.chart-wrapper > :global(.stats-panel) {
		margin: 0;
	}

	.trend {
		display: flex;
		flex-wrap: wrap;
		gap: 4px 24px;
		margin: 0;
		padding: 10px 12px;
		border-top: 1px solid var(--rule-hairline);
		font-family: var(--font-num);
		font-size: var(--text-xs);
		font-variant-numeric: tabular-nums lining-nums;
	}

	.trend-item {
		display: flex;
		align-items: baseline;
		gap: 8px;
	}

	.trend dt {
		color: var(--ink-secondary);
		text-transform: uppercase;
		letter-spacing: 0.06em;
		white-space: nowrap;
	}

	.trend dd {
		margin: 0;
		color: var(--ink-primary);
		font-weight: 500;
	}

	.trend-unit {
		color: var(--ink-secondary);
		font-weight: 400;
	}

	.refresh-control {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.6875rem;
		font-family: var(--font-num);
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	.refresh-control label {
		color: var(--text-muted);
	}

	.refresh-select {
		padding: 0.25rem 0.5rem;
		font-size: 0.6875rem;
		font-family: var(--font-num);
		border-radius: 3px;
		border: 1px solid var(--rule-strong);
		background: var(--bg-surface);
		color: var(--text-primary);
		cursor: pointer;
		transition: border-color 0.15s ease, box-shadow 0.15s ease;
	}

	.refresh-select:focus {
		outline: none;
		border-color: var(--accent);
		box-shadow: 0 0 0 1px var(--accent-muted);
	}

	.range-btn {
		min-height: 28px;
		padding: 0 0.625rem;
		font-size: 0.6875rem;
		font-family: var(--font-num);
		font-weight: 500;
		border-radius: 3px;
		color: var(--ink-primary);
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		transition: background-color 140ms var(--ease-out-quart), border-color 140ms var(--ease-out-quart);
		cursor: pointer;
	}

	.range-btn:hover {
		background: var(--bg-elevated);
	}

	.range-btn.active {
		background: var(--accent-tint);
		color: var(--accent);
		border-color: var(--accent-rule);
	}

	.chart-legend {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 4px 16px;
	}

	.legend-item {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		font-size: 0.625rem;
		font-family: var(--font-num);
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.legend-dot {
		width: 0.5rem;
		height: 0.5rem;
		border-radius: 50%;
	}

	.legend-dot-sg {
		background: var(--chart-sg);
	}

	.legend-dot-anomaly {
		background: var(--chart-anomaly);
		
	}

	.legend-line {
		width: 0.75rem;
		height: 2px;
		border-radius: 1px;
	}

	.legend-line-ambient {
		background: linear-gradient(90deg, var(--chart-ambient) 2px, transparent 2px);
		background-size: 4px 2px;
	}

	.legend-line-chamber {
		background: linear-gradient(90deg, var(--chart-chamber) 4px, transparent 4px);
		background-size: 6px 2px;
	}

	.legend-line-trend {
		background: linear-gradient(90deg, var(--chart-trend) 6px, transparent 6px);
		background-size: 10px 2px;
	}

	.legend-line-battery {
		background: linear-gradient(90deg, var(--chart-battery) 2px, transparent 2px);
		background-size: 4px 2px;
	}

	.legend-line-filtered {
		background: var(--chart-filtered);
	}

	.legend-line-filtered-temp {
		background: linear-gradient(90deg, var(--chart-filtered-temp) 6px, transparent 6px);
		background-size: 9px 2px;
	}

	.legend-band {
		width: 0.5rem;
		height: 0.625rem;
		border-radius: 1px;
	}

	.legend-band-heating {
		background: var(--chart-heating-band);
		margin-right: -0.25rem;
	}

	.legend-band-cooling {
		background: var(--chart-cooling-band);
	}

	.legend-toggle {
		background: none;
		border: none;
		padding: 0.25rem 0.375rem;
		margin: -0.25rem -0.375rem;
		border-radius: 0.25rem;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.legend-toggle:hover {
		background: var(--bg-hover);
	}

	.legend-disabled {
		opacity: 0.4;
	}

	.legend-disabled .legend-line-ambient,
	.legend-disabled .legend-line-chamber,
	.legend-disabled .legend-line-trend,
	.legend-disabled .legend-line-filtered,
	.legend-disabled .legend-line-filtered-temp,
	.legend-disabled .legend-line-battery {
		background: linear-gradient(90deg, var(--text-muted) 4px, transparent 4px);
	}

	.legend-disabled .legend-dot-anomaly {
		background: var(--text-muted);
		box-shadow: none;
	}

	.legend-disabled .legend-band {
		background: var(--text-muted);
	}

	.anomaly-toggle {
		color: var(--text-secondary);
	}

	.anomaly-toggle:not(.legend-disabled) {
		color: var(--chart-anomaly);
	}

	.chart-container {
		position: relative;
		width: 100%;
		min-height: 220px;
		background: transparent;
		overflow: hidden;
	}

	.loading-overlay {
		position: absolute;
		inset: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		background: color-mix(in oklch, var(--bg-surface) 70%, transparent);
		backdrop-filter: blur(2px);
		z-index: 10;
	}

	.loading-spinner {
		width: 1.5rem;
		height: 1.5rem;
		border: 2px solid var(--border-subtle);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	.chart-container :global(.u-wrap) {
		background: transparent !important;
	}

	.chart-container :global(.u-legend) {
		color: var(--text-primary);
		line-height: 1.6;
	}

	.chart-container :global(.u-legend .u-series) {
		display: flex;
		align-items: baseline;
		gap: 0.5rem;
		margin-bottom: 0.25rem;
	}

	.chart-container :global(.u-legend .u-label) {
		color: var(--text-muted);
		min-width: 4.5rem;
	}

	.chart-container :global(.u-legend .u-value) {
		color: var(--text-primary);
		font-weight: 500;
		text-align: right;
		flex: 1;
	}

	.chart-error,
	.chart-empty {
		position: absolute;
		inset: 0;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 0.75rem;
		color: var(--text-muted);
		font-size: 0.75rem;
	}

	.retry-btn {
		padding: 0.375rem 0.75rem;
		font-size: 0.6875rem;
		font-weight: 500;
		color: var(--accent);
		background: var(--accent-tint);
		border: 1px solid var(--accent-rule);
		border-radius: 3px;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.retry-btn:hover {
		background: var(--accent-hover);
		color: var(--accent-ink);
	}

	.chart-empty {
		text-align: center;
	}

	/* Anomaly details strip */
	.anomaly-details {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		padding: 0.5rem 0.75rem;
		background: color-mix(in oklch, var(--status-danger) 8%, transparent);
		border: 1px solid color-mix(in oklch, var(--status-danger) 25%, transparent);
		border-radius: 3px;
		margin: 8px 12px 12px;
	}

	.anomaly-item {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.75rem;
		flex-wrap: wrap;
	}

	.anomaly-dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: var(--chart-anomaly);
		flex-shrink: 0;
	}

	.anomaly-time {
		color: var(--text-secondary);
		font-family: var(--font-mono);
		white-space: nowrap;
	}

	.anomaly-sg {
		color: var(--text-secondary);
		font-family: var(--font-mono);
		font-weight: 600;
	}

	.anomaly-reasons {
		color: var(--text-muted);
		font-style: italic;
	}

	/* Screen reader only - visually hidden but accessible */
	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		padding: 0;
		margin: -1px;
		overflow: hidden;
		clip: rect(0, 0, 0, 0);
		white-space: nowrap;
		border: 0;
	}
</style>
