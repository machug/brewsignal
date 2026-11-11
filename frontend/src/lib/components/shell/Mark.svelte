<script lang="ts">
	// BrewSignal mark "Tilt Meniscus" (tilt_ui-nv1r.7): a tilted hydrometer floating
	// at the wort surface, its weighted bulb below the line in the accent colour.
	// Strokes use currentColor; the bulb uses --accent. Drawn on a 32-unit grid.
	let { size = 20, title }: { size?: number; title?: string } = $props();
</script>

<svg
	viewBox="0 0 32 32"
	width={size}
	height={size}
	fill="none"
	role={title ? 'img' : undefined}
	aria-hidden={title ? undefined : 'true'}
	aria-label={title}
>
	<path d="M4 16H28" stroke="currentColor" stroke-width="2" />
	<path d="M13.2 16L16.2 7.2A2.8 2.8 0 0 1 21.5 9.1L19.1 16" stroke="currentColor" stroke-width="2" />
	<path d="M11.1 19.5H18.8L16.9 25A3.8 3.8 0 0 1 9.7 22.5Z" fill="var(--accent)" />
</svg>
