/**
 * Shared hop types + constants used by both HopSelector and RecipeBuilder.
 *
 * Originally these lived in RecipeBuilder.svelte's `<script module>` block,
 * but HopSelector also needed them. Importing them from one Svelte component
 * into another created an ESM cycle (RecipeBuilder imports HopSelector for
 * rendering; HopSelector imported these symbols from RecipeBuilder) which
 * risked a TDZ crash at module-init time in production builds.
 *
 * Plain .ts module breaks the cycle.
 */

/**
 * Cold-side hop-use values allowed for Abstrax Quantum-style extracts.
 * Mirrors the backend allowlist (see backend/services/serializers/recipe_serializer.py
 * _EXTRACT_COLD_SIDE_USES). These long-form keys are preserved verbatim
 * — NOT normalised to the short HopUse form — because the extract editor
 * surfaces them directly in the use dropdown.
 */
export const EXTRACT_USE_ALLOWLIST = [
	'dry_hop',
	'add_to_fermentation',
	'add_to_package',
	'package',
	'keg',
	'brite',
] as const;

export type ExtractHopUse = (typeof EXTRACT_USE_ALLOWLIST)[number];

/**
 * Hop use covers traditional hot-side additions (boil/whirlpool/dry_hop etc.)
 * plus Abstrax Quantum-style cold-side extract additions.
 */
export type HopUse =
	| 'boil'
	| 'whirlpool'
	| 'dry_hop'
	| 'first_wort'
	| 'mash'
	| 'add_to_fermentation'
	| 'add_to_package'
	| 'package'
	| 'keg'
	| 'brite';

export type HopForm = 'pellet' | 'whole' | 'plug';

export const EXTRACT_USE_SET: ReadonlySet<string> = new Set(EXTRACT_USE_ALLOWLIST);

export function isColdSideExtractUse(use: string | undefined | null): boolean {
	return !!use && EXTRACT_USE_SET.has(use);
}
