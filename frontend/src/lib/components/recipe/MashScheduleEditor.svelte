<script lang="ts">
	export interface MashStepInput {
		step_number: number;
		name: string;
		type: string;
		temp_c: number;
		time_minutes: number;
		infusion_amount_liters?: number;
		infusion_temp_c?: number;
		ramp_time_minutes?: number;
	}

	interface Props {
		steps: MashStepInput[];
		onUpdate: (steps: MashStepInput[]) => void;
	}

	let { steps = [], onUpdate }: Props = $props();

	let localSteps = $state<MashStepInput[]>([]);

	$effect(() => {
		localSteps = [...steps];
	});

	function addStep() {
		const newStep: MashStepInput = {
			step_number: localSteps.length + 1,
			name: `Step ${localSteps.length + 1}`,
			type: 'infusion',
			temp_c: 67,
			time_minutes: 60
		};
		localSteps = [...localSteps, newStep];
		onUpdate(localSteps);
	}

	function removeStep(index: number) {
		localSteps = localSteps.filter((_, i) => i !== index);
		localSteps = localSteps.map((s, i) => ({ ...s, step_number: i + 1 }));
		onUpdate(localSteps);
	}

	function updateStep(index: number, field: keyof MashStepInput, value: unknown) {
		localSteps[index] = { ...localSteps[index], [field]: value };
		onUpdate(localSteps);
	}
</script>

<div class="editor-section">
	<div class="section-header">
		<h4>Mash Schedule</h4>
		<button type="button" class="btn-add" onclick={addStep}>+ Add Step</button>
	</div>

	{#if localSteps.length === 0}
		<p class="empty-state">No mash steps defined. Click "Add Step" to add one.</p>
	{:else}
		<div class="steps-list">
			{#each localSteps as step, i}
				<div class="step-row">
					<span class="step-num">{i + 1}</span>
					<input
						type="text"
						class="input-name"
						value={step.name}
						placeholder="Step name"
						onchange={(e) => updateStep(i, 'name', e.currentTarget.value)}
					/>
					<select
						class="input-type"
						value={step.type}
						onchange={(e) => updateStep(i, 'type', e.currentTarget.value)}
					>
						<option value="infusion">Infusion</option>
						<option value="temperature">Temperature</option>
						<option value="decoction">Decoction</option>
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
						class="input-time"
						value={step.time_minutes}
						placeholder="Time"
						onchange={(e) => updateStep(i, 'time_minutes', parseInt(e.currentTarget.value) || 0)}
					/>
					<span class="unit">min</span>
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

	.step-num {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 24px;
		height: 24px;
		background: var(--recipe-accent);
		color: var(--gray-950);
		border-radius: 50%;
		font-size: 12px;
		font-weight: 600;
		flex-shrink: 0;
	}

	.input-name {
		flex: 1;
		min-width: 100px;
		padding: var(--space-2);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 4px;
		color: var(--text-primary);
		font-size: 13px;
	}

	.input-name:focus {
		outline: none;
		border-color: var(--recipe-accent);
	}

	.input-type {
		width: 120px;
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
	.input-time {
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
	.input-time:focus {
		outline: none;
		border-color: var(--recipe-accent);
	}

	.unit {
		font-size: 12px;
		color: var(--text-muted);
		min-width: 24px;
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

		.input-name {
			order: 1;
			flex-basis: calc(100% - 60px);
		}

		.step-num {
			order: 0;
		}

		.btn-remove {
			order: 2;
		}

		.input-type {
			order: 3;
			flex: 1;
		}

		.input-temp,
		.input-time {
			order: 4;
			width: 60px;
		}
	}
</style>
