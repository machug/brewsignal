<script lang="ts">
	export interface WaterAdjustmentInput {
		stage: string;
		volume_liters?: number;
		calcium_sulfate_g?: number;
		calcium_chloride_g?: number;
		magnesium_sulfate_g?: number;
		sodium_bicarbonate_g?: number;
		calcium_carbonate_g?: number;
		calcium_hydroxide_g?: number;
		magnesium_chloride_g?: number;
		sodium_chloride_g?: number;
		acid_type?: string;
		acid_ml?: number;
		acid_concentration_percent?: number;
	}

	interface Props {
		adjustments: WaterAdjustmentInput[];
		onUpdate: (adjustments: WaterAdjustmentInput[]) => void;
	}

	let { adjustments = [], onUpdate }: Props = $props();

	let localAdjustments = $state<WaterAdjustmentInput[]>([]);

	$effect(() => {
		localAdjustments = [...adjustments];
	});

	function addAdjustment() {
		const newAdjustment: WaterAdjustmentInput = {
			stage: 'mash',
			volume_liters: 0,
			calcium_sulfate_g: 0,
			calcium_chloride_g: 0,
			magnesium_sulfate_g: 0,
			sodium_bicarbonate_g: 0,
			sodium_chloride_g: 0
		};
		localAdjustments = [...localAdjustments, newAdjustment];
		onUpdate(localAdjustments);
	}

	function removeAdjustment(index: number) {
		localAdjustments = localAdjustments.filter((_, i) => i !== index);
		onUpdate(localAdjustments);
	}

	function updateAdjustment(index: number, field: keyof WaterAdjustmentInput, value: unknown) {
		localAdjustments[index] = { ...localAdjustments[index], [field]: value };
		onUpdate(localAdjustments);
	}

	function getStageLabel(stage: string): string {
		const labels: Record<string, string> = {
			mash: 'Mash',
			sparge: 'Sparge',
			total: 'Total'
		};
		return labels[stage] || stage;
	}
</script>

<div class="editor-section">
	<div class="section-header">
		<h4>Water Adjustments</h4>
		<button type="button" class="btn-add" onclick={addAdjustment}>+ Add Adjustment</button>
	</div>

	{#if localAdjustments.length === 0}
		<div class="empty-state">
			<p>No water adjustments defined. Add one to get started.</p>
			<button type="button" class="btn-add" onclick={addAdjustment}>+ Add Adjustment</button>
		</div>
	{:else}
		<div class="adjustments-list">
			{#each localAdjustments as adjustment, i}
				<div class="adjustment-card">
					<div class="adjustment-header">
						<select
							class="input-stage" aria-label="Stage"
							value={adjustment.stage}
							onchange={(e) => updateAdjustment(i, 'stage', e.currentTarget.value)}
						>
							<option value="mash">Mash</option>
							<option value="sparge">Sparge</option>
							<option value="total">Total</option>
						</select>
						<div class="volume-field">
							<label>Volume</label>
							<span class="field-unit"><input aria-label="Volume"
								type="number"
								step="0.1"
								value={adjustment.volume_liters ?? ''}
								placeholder="0"
								onchange={(e) => updateAdjustment(i, 'volume_liters', parseFloat(e.currentTarget.value) || 0)}
							/><span class="unit" aria-hidden="true">L</span></span>
						</div>
						<button type="button" class="btn-remove" aria-label="Remove" onclick={() => removeAdjustment(i)}>×</button>
					</div>

					<div class="salts-section">
						<h5 class="subsection-title">Salts</h5>
						<div class="salt-grid">
							<div class="salt-field">
								<label>Gypsum (CaSO4)</label>
								<span class="field-unit"><input aria-label="Gypsum (CaSO4)"
									type="number"
									step="0.01"
									value={adjustment.calcium_sulfate_g ?? ''}
									placeholder="0"
									onchange={(e) => updateAdjustment(i, 'calcium_sulfate_g', parseFloat(e.currentTarget.value) || 0)}
								/><span class="unit" aria-hidden="true">g</span></span>
							</div>
							<div class="salt-field">
								<label>Calcium Chloride</label>
								<span class="field-unit"><input aria-label="Calcium Chloride"
									type="number"
									step="0.01"
									value={adjustment.calcium_chloride_g ?? ''}
									placeholder="0"
									onchange={(e) => updateAdjustment(i, 'calcium_chloride_g', parseFloat(e.currentTarget.value) || 0)}
								/><span class="unit" aria-hidden="true">g</span></span>
							</div>
							<div class="salt-field">
								<label>Epsom Salt (MgSO4)</label>
								<span class="field-unit"><input aria-label="Epsom Salt (MgSO4)"
									type="number"
									step="0.01"
									value={adjustment.magnesium_sulfate_g ?? ''}
									placeholder="0"
									onchange={(e) => updateAdjustment(i, 'magnesium_sulfate_g', parseFloat(e.currentTarget.value) || 0)}
								/><span class="unit" aria-hidden="true">g</span></span>
							</div>
							<div class="salt-field">
								<label>Baking Soda</label>
								<span class="field-unit"><input aria-label="Baking Soda"
									type="number"
									step="0.01"
									value={adjustment.sodium_bicarbonate_g ?? ''}
									placeholder="0"
									onchange={(e) => updateAdjustment(i, 'sodium_bicarbonate_g', parseFloat(e.currentTarget.value) || 0)}
								/><span class="unit" aria-hidden="true">g</span></span>
							</div>
							<div class="salt-field">
								<label>Table Salt (NaCl)</label>
								<span class="field-unit"><input aria-label="Table Salt (NaCl)"
									type="number"
									step="0.01"
									value={adjustment.sodium_chloride_g ?? ''}
									placeholder="0"
									onchange={(e) => updateAdjustment(i, 'sodium_chloride_g', parseFloat(e.currentTarget.value) || 0)}
								/><span class="unit" aria-hidden="true">g</span></span>
							</div>
							<div class="salt-field">
								<label>Chalk (CaCO3)</label>
								<span class="field-unit"><input aria-label="Chalk (CaCO3)"
									type="number"
									step="0.01"
									value={adjustment.calcium_carbonate_g ?? ''}
									placeholder="0"
									onchange={(e) => updateAdjustment(i, 'calcium_carbonate_g', parseFloat(e.currentTarget.value) || 0)}
								/><span class="unit" aria-hidden="true">g</span></span>
							</div>
						</div>
					</div>

					<div class="acid-section">
						<h5 class="subsection-title">Acid Addition</h5>
						<div class="acid-grid">
							<div class="acid-field">
								<label>Acid Type</label>
								<select aria-label="Acid Type"
									value={adjustment.acid_type || ''}
									onchange={(e) => updateAdjustment(i, 'acid_type', e.currentTarget.value || undefined)}
								>
									<option value="">None</option>
									<option value="lactic">Lactic</option>
									<option value="phosphoric">Phosphoric</option>
									<option value="citric">Citric</option>
									<option value="hydrochloric">Hydrochloric</option>
								</select>
							</div>
							<div class="acid-field">
								<label>Amount</label>
								<span class="field-unit"><input aria-label="Amount"
									type="number"
									step="0.1"
									value={adjustment.acid_ml ?? ''}
									placeholder="0"
									onchange={(e) => updateAdjustment(i, 'acid_ml', parseFloat(e.currentTarget.value) || 0)}
								/><span class="unit" aria-hidden="true">ml</span></span>
							</div>
							<div class="acid-field">
								<label>Concentration</label>
								<span class="field-unit"><input aria-label="Concentration"
									type="number"
									step="1"
									value={adjustment.acid_concentration_percent ?? ''}
									placeholder="88"
									onchange={(e) => updateAdjustment(i, 'acid_concentration_percent', parseFloat(e.currentTarget.value) || 0)}
								/><span class="unit" aria-hidden="true">%</span></span>
							</div>
						</div>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.editor-section {
		display: flex;
		flex-direction: column;
		gap: var(--space-sm);
	}

	.section-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		flex-wrap: wrap;
		gap: var(--space-sm);
		padding-bottom: var(--space-xs);
		border-bottom: 1px solid var(--rule-strong);
	}

	h4 {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--ink-secondary);
		margin: 0;
	}

	.subsection-title {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--ink-muted);
		margin: 0 0 var(--space-xs) 0;
	}

	.btn-add {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-height: 44px;
		padding: var(--space-xs) var(--space-md);
		background: transparent;
		color: var(--ink-secondary);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		white-space: nowrap;
		cursor: pointer;
		transition: border-color var(--transition), color var(--transition);
	}

	.btn-add:hover {
		border-color: var(--ink-secondary);
		color: var(--ink-primary);
	}

	.btn-add:focus-visible,
	.btn-remove:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.empty-state {
		display: flex;
		align-items: center;
		justify-content: space-between;
		flex-wrap: wrap;
		gap: var(--space-sm);
		padding: var(--space-md);
		background: var(--bg-surface);
		border-top: 1px solid var(--rule-hairline);
		border-bottom: 1px solid var(--rule-hairline);
	}

	.empty-state p {
		flex: 1 1 14rem;
		margin: 0;
		color: var(--ink-secondary);
		font-size: var(--text-sm);
	}

	/* Fields: 44px, 1px strong rule, visible accent focus ring */
	input,
	select {
		min-height: 44px;
		padding: var(--space-xs) var(--space-sm);
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		color: var(--ink-primary);
		font-family: var(--font-body);
		font-size: var(--text-sm);
		box-sizing: border-box;
		min-width: 0;
	}

	input[type='number'] {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		text-align: right;
	}

	input::placeholder {
		color: var(--ink-muted);
	}

	input:focus-visible,
	select:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
		border-color: var(--accent);
	}

	label {
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-muted);
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}

	.field-unit {
		position: relative;
		display: block;
		min-width: 0;
	}

	.field-unit input {
		width: 100%;
		padding-right: 2.25rem;
	}

	.unit {
		position: absolute;
		right: 10px;
		top: 50%;
		transform: translateY(-50%);
		font-family: var(--font-num);
		font-size: var(--text-xs);
		color: var(--ink-muted);
		pointer-events: none;
	}

	.btn-remove {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 44px;
		height: 44px;
		padding: 0;
		background: transparent;
		color: var(--ink-muted);
		border: 1px solid transparent;
		border-radius: 4px;
		font-size: 20px;
		line-height: 1;
		cursor: pointer;
		flex-shrink: 0;
		transition: border-color var(--transition), color var(--transition);
	}

	.btn-remove:hover {
		border-color: var(--status-danger);
		color: var(--status-danger);
	}

	.adjustments-list {
		display: flex;
		flex-direction: column;
	}

	/* Hairline rows: one row per step/item */

	.input-stage {
		flex: 0 1 140px;
	}

	/* Profiles and adjustments: hairline-separated blocks, no cards */
	.adjustment-card {
		display: flex;
		flex-direction: column;
		gap: var(--space-sm);
		padding: var(--space-md) 0;
		border-bottom: 1px solid var(--rule-hairline);
	}

	.adjustment-header {
		display: flex;
		align-items: flex-end;
		flex-wrap: wrap;
		gap: var(--space-xs);
	}

	.adjustment-header .btn-remove {
		margin-left: auto;
	}

	.salt-grid,
	.acid-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(8.5rem, 1fr));
		gap: var(--space-sm);
	}

	.salt-grid {
		grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr));
	}

	.salt-field,
	.acid-field,
	.volume-field {
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto;
		align-items: center;
		gap: var(--space-2xs) var(--space-xs);
	}

	.salt-field label,
	.acid-field label {
		grid-column: 1 / -1;
	}

	.volume-field {
		grid-template-columns: auto minmax(0, 1fr) auto;
		grid-auto-flow: column;
	}

	.volume-field label {
		grid-column: auto;
	}

	.volume-field input {
		width: 96px;
	}

	.acid-field select {
		grid-column: 1 / -1;
	}

	.input-stage {
		flex: 0 1 140px;
	}


	.salt-field .field-unit,
	.acid-field .field-unit {
		grid-column: 1 / -1;
	}

	.volume-field {
		grid-template-columns: auto minmax(0, 1fr);
	}

	.volume-field .field-unit {
		grid-column: auto;
		width: 112px;
	}
</style>
