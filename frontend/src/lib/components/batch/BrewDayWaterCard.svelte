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
				<span class="water-value">{waterVolumes.mashWater.toFixed(1)} L</span>
				<span class="water-label">Mash</span>
			</div>
			<div class="water-item">
				<span class="water-value">{waterVolumes.spargeWater.toFixed(1)} L</span>
				<span class="water-label">Sparge</span>
			</div>
			<div class="water-item highlight">
				<span class="water-value">{waterVolumes.totalWater.toFixed(1)} L</span>
				<span class="water-label">Total</span>
			</div>
			<div class="water-item">
				<span class="water-value">{waterVolumes.mashVolume.toFixed(1)} L</span>
				<span class="water-label">Mash Vol</span>
			</div>
		</div>
	</BatchCard>
{/if}

<style>
	.water-grid {
		display: flex;
		gap: 1.5rem;
		flex-wrap: wrap;
	}

	.water-item {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
	}

	.water-value {
		font-family: var(--font-mono);
		font-size: 0.9375rem;
		font-weight: 500;
		color: var(--text-secondary);
	}

	.water-item.highlight .water-value {
		color: var(--tilt-blue);
		font-weight: 600;
	}

	.water-label {
		font-size: 0.625rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
	}
</style>
