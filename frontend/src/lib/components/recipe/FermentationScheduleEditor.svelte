<script lang="ts">
	export interface FermentationStepInput {
		step_number: number;
		type: string;
		temp_c: number;
		time_days: number;
	}

	interface Props {
		steps: FermentationStepInput[];
		onUpdate: (steps: FermentationStepInput[]) => void;
	}

	let { steps = [], onUpdate }: Props = $props();

	let localSteps = $state<FermentationStepInput[]>([]);

	$effect(() => {
		localSteps = [...steps];
	});

	function addStep() {
		const newStep: FermentationStepInput = {
			step_number: localSteps.length + 1,
			type: 'primary',
			temp_c: 18,
			time_days: 14
		};
		localSteps = [...localSteps, newStep];
		onUpdate(localSteps);
	}

	function removeStep(index: number) {
		localSteps = localSteps.filter((_, i) => i !== index);
		localSteps = localSteps.map((s, i) => ({ ...s, step_number: i + 1 }));
		onUpdate(localSteps);
	}

	function updateStep(index: number, field: keyof FermentationStepInput, value: unknown) {
		localSteps[index] = { ...localSteps[index], [field]: value };
		onUpdate(localSteps);
	}

</script>

<div class="editor-section">
	<div class="section-header">
		<h4>Fermentation Schedule</h4>
		<button type="button" class="btn-add" onclick={addStep}>+ Add Step</button>
	</div>

	{#if localSteps.length === 0}
		<p class="empty-state">No fermentation steps defined. Click "Add Step" to add one.</p>
	{:else}
		<div class="steps-list">
			{#each localSteps as step, i}
				<div class="step-row">
					<span class="step-num">{i + 1}</span>
					<select
						class="input-type"
						aria-label="Step type"
						value={step.type}
						onchange={(e) => updateStep(i, 'type', e.currentTarget.value)}
					>
						<option value="primary">Primary</option>
						<option value="secondary">Secondary</option>
						<option value="conditioning">Conditioning</option>
						<option value="lagering">Lagering</option>
					</select>
					<input
						type="number"
						class="input-temp"
						aria-label="Temperature in °C"
						value={step.temp_c}
						placeholder="Temp"
						onchange={(e) => updateStep(i, 'temp_c', parseFloat(e.currentTarget.value) || 0)}
					/>
					<span class="unit">°C</span>
					<input
						type="number"
						class="input-days"
						aria-label="Duration in days"
						value={step.time_days}
						placeholder="Days"
						onchange={(e) => updateStep(i, 'time_days', parseInt(e.currentTarget.value) || 0)}
					/>
					<span class="unit">days</span>
					<button type="button" class="btn-remove" aria-label="Remove" onclick={() => removeStep(i)}>×</button>
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
		margin: 0;
		padding: var(--space-md);
		border: 1px dashed var(--rule-strong);
		border-radius: 4px;
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

	.unit {
		font-size: var(--text-sm);
		color: var(--ink-muted);
		white-space: nowrap;
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

	.steps-list {
		display: flex;
		flex-direction: column;
	}

	/* Hairline rows: one row per step/item */
	.step-row {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: var(--space-xs);
		padding: var(--space-xs) 0;
		border-bottom: 1px solid var(--rule-hairline);
	}

	.step-num {
		width: 2ch;
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: var(--text-sm);
		color: var(--ink-muted);
		text-align: right;
		flex-shrink: 0;
	}

	.input-type {
		flex: 0 1 140px;
	}

	.input-temp,
	.input-days {
		width: 84px;
		flex: none;
	}

	@media (max-width: 760px) {
		.step-row .btn-remove {
			margin-left: auto;
		}
	}
</style>
