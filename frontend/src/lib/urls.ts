// Readable URLs: /batches/16-american-pale-ale (tilt_ui-9hg).
// Pages read the leading number with parseInt, so the name is decoration:
// old /batches/16 links keep working and renames never break a link.

export function slugify(name?: string | null): string {
	return (name ?? '')
		.normalize('NFKD')
		.replace(/[̀-ͯ]/g, '') // strip accents
		.toLowerCase()
		.replace(/[^a-z0-9]+/g, '-')
		.replace(/^-+|-+$/g, '')
		.slice(0, 60)
		.replace(/-+$/, '');
}

function withSlug(base: string, id: number, name?: string | null): string {
	const slug = slugify(name);
	return slug ? `${base}/${id}-${slug}` : `${base}/${id}`;
}

export function batchUrl(batch: { id: number; name?: string | null; recipe?: { name?: string | null } | null }): string {
	return withSlug('/batches', batch.id, batch.name || batch.recipe?.name);
}

export function recipeUrl(recipe: { id: number; name?: string | null }): string {
	return withSlug('/recipes', recipe.id, recipe.name);
}
