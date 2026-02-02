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
		<p class="empty-state">No water adjustments defined. Click "Add Adjustment" to add one.</p>
	{:else}
		<div class="adjustments-list">
			{#each localAdjustments as adjustment, i}
				<div class="adjustment-card">
					<div class="adjustment-header">
						<select
							class="input-stage"
							value={adjustment.stage}
							onchange={(e) => updateAdjustment(i, 'stage', e.currentTarget.value)}
						>
							<option value="mash">Mash</option>
							<option value="sparge">Sparge</option>
							<option value="total">Total</option>
						</select>
						<div class="volume-field">
							<label>Volume</label>
							<input
								type="number"
								step="0.1"
								value={adjustment.volume_liters ?? ''}
								placeholder="0"
								onchange={(e) => updateAdjustment(i, 'volume_liters', parseFloat(e.currentTarget.value) || 0)}
							/>
							<span class="unit">L</span>
						</div>
						<button type="button" class="btn-remove" onclick={() => removeAdjustment(i)}>×</button>
					</div>

					<div class="salts-section">
						<h5 class="subsection-title">Salts</h5>
						<div class="salt-grid">
							<div class="salt-field">
								<label>Gypsum (CaSO4)</label>
								<input
									type="number"
									step="0.01"
									value={adjustment.calcium_sulfate_g ?? ''}
									placeholder="0"
									onchange={(e) => updateAdjustment(i, 'calcium_sulfate_g', parseFloat(e.currentTarget.value) || 0)}
								/>
								<span class="unit">g</span>
							</div>
							<div class="salt-field">
								<label>Calcium Chloride</label>
								<input
									type="number"
									step="0.01"
									value={adjustment.calcium_chloride_g ?? ''}
									placeholder="0"
									onchange={(e) => updateAdjustment(i, 'calcium_chloride_g', parseFloat(e.currentTarget.value) || 0)}
								/>
								<span class="unit">g</span>
							</div>
							<div class="salt-field">
								<label>Epsom Salt (MgSO4)</label>
								<input
									type="number"
									step="0.01"
									value={adjustment.magnesium_sulfate_g ?? ''}
									placeholder="0"
									onchange={(e) => updateAdjustment(i, 'magnesium_sulfate_g', parseFloat(e.currentTarget.value) || 0)}
								/>
								<span class="unit">g</span>
							</div>
							<div class="salt-field">
								<label>Baking Soda</label>
								<input
									type="number"
									step="0.01"
									value={adjustment.sodium_bicarbonate_g ?? ''}
									placeholder="0"
									onchange={(e) => updateAdjustment(i, 'sodium_bicarbonate_g', parseFloat(e.currentTarget.value) || 0)}
								/>
								<span class="unit">g</span>
							</div>
							<div class="salt-field">
								<label>Table Salt (NaCl)</label>
								<input
									type="number"
									step="0.01"
									value={adjustment.sodium_chloride_g ?? ''}
									placeholder="0"
									onchange={(e) => updateAdjustment(i, 'sodium_chloride_g', parseFloat(e.currentTarget.value) || 0)}
								/>
								<span class="unit">g</span>
							</div>
							<div class="salt-field">
								<label>Chalk (CaCO3)</label>
								<input
									type="number"
									step="0.01"
									value={adjustment.calcium_carbonate_g ?? ''}
									placeholder="0"
									onchange={(e) => updateAdjustment(i, 'calcium_carbonate_g', parseFloat(e.currentTarget.value) || 0)}
								/>
								<span class="unit">g</span>
							</div>
						</div>
					</div>

					<div class="acid-section">
						<h5 class="subsection-title">Acid Addition</h5>
						<div class="acid-grid">
							<div class="acid-field">
								<label>Acid Type</label>
								<select
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
								<input
									type="number"
									step="0.1"
									value={adjustment.acid_ml ?? ''}
									placeholder="0"
									onchange={(e) => updateAdjustment(i, 'acid_ml', parseFloat(e.currentTarget.value) || 0)}
								/>
								<span class="unit">ml</span>
							</div>
							<div class="acid-field">
								<label>Concentration</label>
								<input
									type="number"
									step="1"
									value={adjustment.acid_concentration_percent ?? ''}
									placeholder="88"
									onchange={(e) => updateAdjustment(i, 'acid_concentration_percent', parseFloat(e.currentTarget.value) || 0)}
								/>
								<span class="unit">%</span>
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
		gap: var(--space-4);
	}

	.section-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.section-header h4 {
		margin: 0;
		font-size: 14px;
		font-weight: 600;
		color: var(--text-primary);
	}

	.btn-add {
		padding: var(--space-2) var(--space-3);
		background: var(--recipe-accent);
		color: var(--gray-950);
		border: none;
		border-radius: 6px;
		font-size: 13px;
		font-weight: 500;
		cursor: pointer;
		transition: background var(--transition), transform var(--transition);
	}

	.btn-add:hover {
		filter: brightness(1.1);
		transform: translateY(-1px);
	}

	.empty-state {
		color: var(--text-muted);
		font-size: 14px;
		text-align: center;
		padding: var(--space-6);
		background: var(--bg-surface);
		border: 1px dashed var(--border-subtle);
		border-radius: 6px;
		margin: 0;
	}

	.adjustments-list {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}

	.adjustment-card {
		padding: var(--space-4);
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
		border-radius: 8px;
	}

	.adjustment-header {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		margin-bottom: var(--space-4);
		padding-bottom: var(--space-3);
		border-bottom: 1px solid var(--border-subtle);
	}

	.input-stage {
		width: 100px;
		padding: var(--space-2);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 4px;
		color: var(--text-primary);
		font-size: 13px;
		font-weight: 500;
		cursor: pointer;
	}

	.input-stage:focus {
		outline: none;
		border-color: var(--recipe-accent);
	}

	.volume-field {
		display: flex;
		align-items: center;
		gap: var(--space-2);
	}

	.volume-field label {
		font-size: 12px;
		color: var(--text-secondary);
	}

	.volume-field input {
		width: 70px;
		padding: var(--space-2);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 4px;
		color: var(--text-primary);
		font-family: var(--font-mono);
		font-size: 13px;
		text-align: right;
	}

	.volume-field input:focus {
		outline: none;
		border-color: var(--recipe-accent);
	}

	.volume-field .unit {
		font-size: 12px;
		color: var(--text-muted);
	}

	.btn-remove {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 28px;
		height: 28px;
		padding: 0;
		background: transparent;
		border: 1px solid var(--border-subtle);
		border-radius: 4px;
		color: var(--text-muted);
		font-size: 18px;
		cursor: pointer;
		transition: all var(--transition);
		flex-shrink: 0;
		margin-left: auto;
	}

	.btn-remove:hover {
		background: var(--negative-muted);
		border-color: var(--negative);
		color: var(--negative);
	}

	.salts-section,
	.acid-section {
		margin-bottom: var(--space-4);
	}

	.acid-section {
		margin-bottom: 0;
	}

	.subsection-title {
		margin: 0 0 var(--space-3) 0;
		font-size: 11px;
		font-weight: 600;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.salt-grid {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: var(--space-2);
	}

	.salt-field {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		padding: var(--space-2);
		background: var(--bg-surface);
		border-radius: 4px;
	}

	.salt-field label {
		font-size: 11px;
		color: var(--text-muted);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.salt-field input {
		width: 100%;
		padding: var(--space-1);
		background: transparent;
		border: none;
		border-bottom: 1px solid var(--border-subtle);
		color: var(--text-primary);
		font-family: var(--font-mono);
		font-size: 13px;
		text-align: right;
	}

	.salt-field input:focus {
		outline: none;
		border-bottom-color: var(--recipe-accent);
	}

	.salt-field .unit {
		font-size: 10px;
		color: var(--text-muted);
		text-align: right;
	}

	.acid-grid {
		display: grid;
		grid-template-columns: 1fr 1fr 1fr;
		gap: var(--space-3);
	}

	.acid-field {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.acid-field label {
		font-size: 11px;
		color: var(--text-muted);
	}

	.acid-field select,
	.acid-field input {
		padding: var(--space-2);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 4px;
		color: var(--text-primary);
		font-size: 13px;
	}

	.acid-field select {
		cursor: pointer;
	}

	.acid-field input {
		font-family: var(--font-mono);
		text-align: right;
	}

	.acid-field select:focus,
	.acid-field input:focus {
		outline: none;
		border-color: var(--recipe-accent);
	}

	.acid-field .unit {
		font-size: 10px;
		color: var(--text-muted);
		text-align: right;
		margin-top: var(--space-1);
	}

	@media (max-width: 640px) {
		.salt-grid {
			grid-template-columns: repeat(2, 1fr);
		}

		.acid-grid {
			grid-template-columns: 1fr;
		}

		.adjustment-header {
			flex-wrap: wrap;
		}

		.volume-field {
			flex: 1;
		}
	}
</style>
