// BJCP style-range checks. A value is outside only when it is strictly below
// min or above max; equal to a bound is inside. The comparison uses the same
// rounding as the displayed value, so "5 SRM" never reads as outside "5 - 10".

export interface StyleRanges {
	og_min?: number;
	og_max?: number;
	fg_min?: number;
	fg_max?: number;
	abv_min?: number;
	abv_max?: number;
	ibu_min?: number;
	ibu_max?: number;
	srm_min?: number;
	srm_max?: number;
}

export interface StyleStats {
	og: number;
	fg: number;
	abv: number;
	ibu: number;
	srm: number;
}

export interface StyleWarning {
	stat: string;
	value: string;
	range: string;
	unit: string;
	severity: 'warning' | 'error';
}

const THIN = ' ';

function round(v: number, digits: number): number {
	return Number(v.toFixed(digits));
}

function outside(value: number, min: number, max: number, digits: number): boolean {
	const v = round(value, digits);
	return v < round(min, digits) || v > round(max, digits);
}

export function computeStyleWarnings(style: StyleRanges | null | undefined, stats: StyleStats): StyleWarning[] {
	if (!style) return [];
	const out: StyleWarning[] = [];
	const has = (a?: number, b?: number): a is number => a !== undefined && b !== undefined;

	if (has(style.og_min, style.og_max) && outside(stats.og, style.og_min, style.og_max!, 3)) {
		out.push({ stat: 'OG', value: stats.og.toFixed(3), range: `${style.og_min.toFixed(3)} – ${style.og_max!.toFixed(3)}`, unit: '', severity: 'warning' });
	}
	if (has(style.fg_min, style.fg_max) && outside(stats.fg, style.fg_min, style.fg_max!, 3)) {
		out.push({ stat: 'FG', value: stats.fg.toFixed(3), range: `${style.fg_min.toFixed(3)} – ${style.fg_max!.toFixed(3)}`, unit: '', severity: 'warning' });
	}
	if (has(style.abv_min, style.abv_max) && outside(stats.abv, style.abv_min, style.abv_max!, 1)) {
		out.push({ stat: 'ABV', value: `${stats.abv.toFixed(1)}%`, range: `${style.abv_min.toFixed(1)}% – ${style.abv_max!.toFixed(1)}%`, unit: '%', severity: 'warning' });
	}
	if (has(style.ibu_min, style.ibu_max) && outside(stats.ibu, style.ibu_min, style.ibu_max!, 0)) {
		out.push({ stat: 'IBU', value: stats.ibu.toFixed(0), range: `${style.ibu_min} – ${style.ibu_max}`, unit: '', severity: 'warning' });
	}
	if (has(style.srm_min, style.srm_max) && outside(stats.srm, style.srm_min, style.srm_max!, 0)) {
		out.push({ stat: 'Color', value: `${stats.srm.toFixed(0)}${THIN}SRM`, range: `${style.srm_min} – ${style.srm_max}${THIN}SRM`, unit: 'SRM', severity: 'warning' });
	}
	return out;
}
