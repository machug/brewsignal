// Editor side of POST /recipes/calculate: turn editor state into a draft and
// keep the numbers fresh without ever inventing them.
import { calculateRecipeDraft, type CalculatedStats, type RecipeDraft } from '$lib/api';

interface DraftFermentable {
	name: string;
	amount_kg: number;
	potential_sg?: number | null;
	color_srm?: number | null;
	type?: string | null;
}

interface DraftHop {
	name: string;
	amount_grams: number;
	alpha_acid_percent?: number | null;
	boil_time_minutes?: number | null;
	use?: string | null;
	form?: string | null;
	is_extract?: boolean;
	whirlpool_temp_c?: number | null;
}

interface DraftYeast {
	attenuation_low?: number | null;
	attenuation_high?: number | null;
}

// Dry hop duration is a day count stored as minutes, never a boil time. Mash hops
// send theirs: the backend counts them like boil hops, as a saved recipe does.
const NO_DURATION_USES = new Set(['dry_hop']);

export function buildDraft(input: {
	batchSizeLiters: number;
	efficiencyPercent: number;
	fermentables: DraftFermentable[];
	hops: DraftHop[];
	yeast: DraftYeast | null;
	yeastAttenuation?: number | null;
}): RecipeDraft {
	const { yeast } = input;
	const hasRange = yeast?.attenuation_low != null && yeast?.attenuation_high != null;
	return {
		batch_size_liters: input.batchSizeLiters,
		efficiency_percent: input.efficiencyPercent,
		yeast_attenuation: input.yeastAttenuation ?? undefined,
		fermentables: input.fermentables.map((f) => ({
			name: f.name,
			amount_kg: f.amount_kg,
			// the server rejects values outside 1.0 to 1.2
			potential_sg: f.potential_sg != null && f.potential_sg >= 1 && f.potential_sg <= 1.2 ? f.potential_sg : undefined,
			color_srm: f.color_srm ?? undefined,
			type: f.type ?? undefined
		})),
		hops: input.hops.map((h) => {
			const use = h.use ?? 'boil';
			const withDuration = !h.is_extract && !NO_DURATION_USES.has(use) && h.boil_time_minutes != null;
			const temp = h.whirlpool_temp_c;
			return {
				name: h.name,
				amount_grams: h.is_extract ? 0 : h.amount_grams,
				alpha_acid_percent: h.is_extract ? undefined : (h.alpha_acid_percent ?? undefined),
				form: h.form ?? undefined,
				is_extract: Boolean(h.is_extract),
				timing: {
					use,
					duration: withDuration ? { value: h.boil_time_minutes!, unit: 'min' } : undefined,
					temperature: temp != null && temp >= 0 && temp <= 100 ? { value: temp, unit: 'C' } : undefined
				}
			};
		}),
		cultures: hasRange
			? [{ attenuation_min_percent: yeast!.attenuation_low!, attenuation_max_percent: yeast!.attenuation_high! }]
			: []
	};
}

export interface DraftCalculator {
	request(draft: RecipeDraft): void;
	cancel(): void;
	/**
	 * Resolves true when the newest requested draft has been calculated
	 * successfully. Runs a waiting debounce immediately; false on failure.
	 */
	settled(): Promise<boolean>;
}

/**
 * Debounces draft calculations and drops superseded ones. On failure the last
 * good stats stay in place (onStale(true)); they are never replaced with guesses.
 */
export function createDraftCalculator(opts: {
	onResult: (stats: CalculatedStats | null) => void;
	onStale: (stale: boolean) => void;
	calculate?: typeof calculateRecipeDraft;
	delayMs?: number;
}): DraftCalculator {
	const calculate = opts.calculate ?? calculateRecipeDraft;
	const delay = opts.delayMs ?? 200;
	let timer: ReturnType<typeof setTimeout> | null = null;
	let controller: AbortController | null = null;
	let pendingDraft: RecipeDraft | null = null;
	let inflight: Promise<boolean> | null = null;
	let lastOk = false;

	function cancel() {
		if (timer) clearTimeout(timer);
		timer = null;
		controller?.abort();
		controller = null;
	}

	function start() {
		timer = null;
		const draft = pendingDraft!;
		const mine = (controller = new AbortController());
		return (inflight = (async () => {
			try {
				const stats = await calculate(draft, mine.signal);
				if (mine.signal.aborted) return false;
				opts.onResult(stats);
				opts.onStale(false);
				return (lastOk = true);
			} catch {
				if (mine.signal.aborted) return false;
				opts.onStale(true);
				return false;
			}
		})());
	}

	return {
		cancel,
		request(draft) {
			cancel();
			pendingDraft = draft;
			lastOk = false;
			timer = setTimeout(start, delay);
		},
		async settled() {
			for (;;) {
				if (timer) {
					clearTimeout(timer);
					start();
				}
				const p = inflight;
				if (!p) return lastOk;
				if (await p) return true;
				// false: failed, or superseded by a newer request (then go again)
				if (p === inflight && !timer) return false;
			}
		}
	};
}
