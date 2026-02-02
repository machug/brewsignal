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

	function getTypeColor(type: string): string {
		const colorMap: Record<string, string> = {
			primary: 'var(--positive)',
			secondary: 'var(--info)',
			conditioning: 'var(--warning)',
			lagering: 'var(--info)'
		};
		return colorMap[type.toLowerCase()] || 'var(--text-muted)';
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
					<div class="step-marker" style="background: {getTypeColor(step.type)}"></div>
					<span class="step-num">{i + 1}</span>
					<select
						class="input-type"
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
						value={step.temp_c}
						placeholder="Temp"
						onchange={(e) => updateStep(i, 'temp_c', parseFloat(e.currentTarget.value) || 0)}
					/>
					<span class="unit">°C</span>
					<input
						type="number"
						class="input-days"
						value={step.time_days}
						placeholder="Days"
						onchange={(e) => updateStep(i, 'time_days', parseInt(e.currentTarget.value) || 0)}
					/>
					<span class="unit">days</span>
					<button type="button" class="btn-remove" onclick={() => removeStep(i)}>×</button>
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

	.steps-list {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	.step-row {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-3);
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
		border-radius: 6px;
	}

	.step-marker {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		flex-shrink: 0;
	}

	.step-num {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 24px;
		height: 24px;
		background: var(--bg-surface);
		color: var(--text-secondary);
		border-radius: 50%;
		font-size: 12px;
		font-weight: 600;
		flex-shrink: 0;
	}

	.input-type {
		width: 130px;
		padding: var(--space-2);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 4px;
		color: var(--text-primary);
		font-size: 13px;
		cursor: pointer;
	}

	.input-type:focus {
		outline: none;
		border-color: var(--recipe-accent);
	}

	.input-temp,
	.input-days {
		width: 70px;
		padding: var(--space-2);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 4px;
		color: var(--text-primary);
		font-size: 13px;
		text-align: right;
	}

	.input-temp:focus,
	.input-days:focus {
		outline: none;
		border-color: var(--recipe-accent);
	}

	.unit {
		font-size: 12px;
		color: var(--text-muted);
		min-width: 30px;
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

	@media (max-width: 640px) {
		.step-row {
			flex-wrap: wrap;
		}

		.input-type {
			flex: 1;
			min-width: 100px;
		}

		.input-temp,
		.input-days {
			width: 60px;
		}
	}
</style>
