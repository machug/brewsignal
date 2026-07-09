<script lang="ts">
	import { fetchEquipment, type EquipmentResponse } from '$lib/api';
	import { checkBrewability, maxFitBatchLiters } from '$lib/brewing/brewability';

	interface Props {
		batchSizeLiters: number | null | undefined;
		totalGrainKg: number;
		boilTimeMinutes?: number | null;
		boilSizeL?: number | null;
		/** When provided, a "Scale to fit" action appears with the largest fitting batch size. */
		onScaleToFit?: (suggestedBatchLiters: number) => void;
	}

	let { batchSizeLiters, totalGrainKg, boilTimeMinutes, boilSizeL, onScaleToFit }: Props = $props();

	let equipment = $state<EquipmentResponse[] | null>(null);

	$effect(() => {
		// limit 200 = the API's max page size; default (50) could miss the
		// vessel that actually fits and produce false warnings.
		fetchEquipment({ is_active: true, limit: 200 })
			.then((items) => (equipment = items))
			// No equipment registered / endpoint unavailable → stay silent.
			.catch(() => (equipment = null));
	});

	let warnings = $derived.by(() => {
		if (!equipment?.length || !batchSizeLiters) return [];
		return checkBrewability(
			{
				batch_size_liters: batchSizeLiters,
				total_grain_kg: totalGrainKg,
				boil_time_minutes: boilTimeMinutes,
				boil_size_l: boilSizeL,
			},
			equipment,
		);
	});

	let suggestedBatch = $derived.by(() => {
		if (!onScaleToFit || warnings.length === 0 || !equipment?.length || !batchSizeLiters) return null;
		return maxFitBatchLiters(
			{
				batch_size_liters: batchSizeLiters,
				total_grain_kg: totalGrainKg,
				boil_time_minutes: boilTimeMinutes,
				boil_size_l: boilSizeL,
			},
			equipment,
		);
	});
</script>

{#if warnings.length > 0}
	<div class="brewability-banner" role="alert">
		<svg class="banner-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
			<path
				stroke-linecap="round"
				stroke-linejoin="round"
				d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"
			/>
		</svg>
		<div class="banner-body">
			<p class="banner-title">May not be brewable on your equipment</p>
			<ul class="banner-list">
				{#each warnings as warning (warning.code + warning.equipment_name)}
					<li>{warning.message}</li>
				{/each}
			</ul>
			{#if suggestedBatch != null && onScaleToFit}
				<button type="button" class="scale-to-fit" onclick={() => onScaleToFit(suggestedBatch!)}>
					Scale to fit ({suggestedBatch} L)
				</button>
			{/if}
		</div>
	</div>
{/if}

<style>
	.brewability-banner {
		display: flex;
		gap: var(--space-3);
		align-items: flex-start;
		background: var(--warning-muted);
		border: 1px solid var(--warning);
		border-radius: 10px;
		padding: var(--space-4) var(--space-5);
		margin: var(--space-5) 0;
	}

	.banner-icon {
		width: 20px;
		height: 20px;
		flex-shrink: 0;
		color: var(--warning);
		margin-top: 2px;
	}

	.banner-title {
		margin: 0 0 var(--space-1);
		font-weight: 600;
		color: var(--text-primary);
		font-size: 0.9rem;
	}

	.banner-list {
		margin: 0;
		padding-left: var(--space-4);
		color: var(--text-secondary);
		font-size: 0.85rem;
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.scale-to-fit {
		align-self: flex-start;
		margin-top: var(--space-3);
		padding: var(--space-1) var(--space-3);
		background: none;
		border: 1px solid var(--warning);
		border-radius: 8px;
		color: var(--warning);
		font-size: 0.85rem;
		font-weight: 600;
		cursor: pointer;
	}

	.scale-to-fit:hover {
		background: var(--warning-muted);
	}
</style>
