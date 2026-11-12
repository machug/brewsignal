import { describe, expect, it } from 'vitest';
import { batchUrl, recipeUrl, slugify } from './urls';

describe('readable URLs (tilt_ui-9hg)', () => {
	it('slugifies names', () => {
		expect(slugify('American Pale Ale')).toBe('american-pale-ale');
		expect(slugify('Galactic Dry Stout (Guinness Clone)')).toBe('galactic-dry-stout-guinness-clone');
		expect(slugify('Märzen № 2!')).toBe('marzen-no-2');
		expect(slugify('  ')).toBe('');
		expect(slugify(null)).toBe('');
	});

	it('builds batch and recipe paths that still start with the id', () => {
		expect(batchUrl({ id: 16, name: 'American Pale Ale' })).toBe('/batches/16-american-pale-ale');
		expect(batchUrl({ id: 4, name: null, recipe: { name: 'Hazy IPA' } })).toBe('/batches/4-hazy-ipa');
		expect(batchUrl({ id: 7 })).toBe('/batches/7');
		expect(recipeUrl({ id: 25, name: 'West Coast IPA' })).toBe('/recipes/25-west-coast-ipa');
		expect(parseInt(batchUrl({ id: 16, name: '2024 Lager' }).split('/')[2], 10)).toBe(16);
	});

	it('caps long names', () => {
		expect(slugify('a'.repeat(100)).length).toBe(60);
	});
});
