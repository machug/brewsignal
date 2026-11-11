<script lang="ts">
	import type { RecipeResponse } from '$lib/api';
	import { calculateWaterVolumes } from '$lib/utils/water';
	import BatchCard from './BatchCard.svelte';

	interface Props {
		recipe: RecipeResponse;
	}

	let { recipe }: Props = $props();

	let waterVolumes = $derived.by(() => {
		if (!recipe.batch_size_liters || !recipe.fermentables?.length) return null;
		const totalGrainKg = recipe.fermentables.reduce((sum, f) => sum + (f.amount_kg ?? 0), 0);
		return calculateWaterVolumes(recipe.batch_size_liters, totalGrainKg, recipe.boil_time_minutes, recipe.boil_size_l);
	});
</script>

{#if waterVolumes}
	<BatchCard title="Water Volumes" compact>
		<div class="water-grid">
			<div class="water-item">
				<span class="water-value">{waterVolumes.mashWater.toFixed(1)}&thinsp;L</span>
				<span class="water-label">Mash</span>
			</div>
			<div class="water-item">
				<span class="water-value">{waterVolumes.spargeWater.toFixed(1)}&thinsp;L</span>
				<span class="water-label">Sparge</span>
			</div>
			<div class="water-item highlight">
				<span class="water-value">{waterVolumes.totalWater.toFixed(1)}&thinsp;L</span>
				<span class="water-label">Total</span>
			</div>
			<div class="water-item">
				<span class="water-value">{waterVolumes.mashVolume.toFixed(1)}&thinsp;L</span>
				<span class="water-label">Mash Vol</span>
			</div>
		</div>
	</BatchCard>
{/if}

<style>
	.water-grid {
		display: grid;
		grid-template-columns: repeat(4, minmax(0, 1fr));
		border-top: 1px solid var(--rule-hairline);
		border-bottom: 1px solid var(--rule-hairline);
	}
	.water-item {
		display: flex;
		flex-direction: column;
		gap: var(--space-2xs);
		padding: var(--space-xs) var(--space-sm);
	}
	.water-item + .water-item {
		border-left: 1px solid var(--rule-hairline);
	}
	.water-value {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: var(--text-base);
		font-weight: 600;
		color: var(--ink-primary);
	}
	.water-item.highlight .water-value {
		color: var(--accent);
	}
	.water-label {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-muted);
		text-transform: uppercase;
		letter-spacing: 0.07em;
	}
	@media (max-width: 480px) {
		.water-grid {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
		.water-item:nth-child(3) {
			border-left: none;
		}
		.water-item:nth-child(n + 3) {
			border-top: 1px solid var(--rule-hairline);
		}
	}
</style>
