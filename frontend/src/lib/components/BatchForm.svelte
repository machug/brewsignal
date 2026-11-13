<script lang="ts">
	import { onMount } from 'svelte';
	import type { BatchResponse, BatchCreate, BatchUpdate, RecipeResponse, BatchStatus, HeaterEntity, YeastStrainResponse } from '$lib/api';
	import { fetchRecipes, fetchHeaterEntities, fetchCoolerEntities } from '$lib/api';
	import { configState, getTempUnit, fahrenheitToCelsius, celsiusToFahrenheit, formatGravity, getGravityUnit } from '$lib/stores/config.svelte';
	import { fetchAllDevices, type DeviceResponse } from '$lib/api/devices';
	import RecipeSelector from './RecipeSelector.svelte';
	import YeastSelector from './batch/YeastSelector.svelte';

	interface Props {
		batch?: BatchResponse;
		onSubmit: (data: BatchCreate | BatchUpdate) => Promise<void>;
		onCancel: () => void;
		initialRecipeId?: number;
	}

	let { batch, onSubmit, onCancel, initialRecipeId }: Props = $props();

	// Form state
	let name = $state(batch?.name || '');
	let recipeId = $state<number | null>(batch?.recipe_id || null);
	let yeastStrainId = $state<number | null>(batch?.yeast_strain_id || null);
	let deviceId = $state<string | null>(batch?.device_id || null);
	let status = $state<BatchStatus>(batch?.status || 'planning');
	let brewDate = $state(batch?.brew_date ? batch.brew_date.split('T')[0] : '');
	let measuredOg = $state(batch?.measured_og?.toString() || '');
	let measuredFg = $state(batch?.measured_fg?.toString() || '');
	let notes = $state(batch?.notes || '');

	// Temperature control fields
	// Backend stores temps in Celsius (standardized after ML integration)
	let heaterEntityId = $state(batch?.heater_entity_id || '');
	let coolerEntityId = $state(batch?.cooler_entity_id || '');

	// Helper to convert backend C value to display value (F or C based on preference)
	function tempToDisplay(tempC: number | null | undefined): string {
		if (tempC === null || tempC === undefined) return '';
		if (configState.config.temp_units === 'F') {
			return celsiusToFahrenheit(tempC).toFixed(1);
		}
		return tempC.toFixed(1);
	}

	// Helper to convert temperature DELTA (difference) from C to display unit
	// For deltas: ΔF = ΔC × 9/5 (no offset addition)
	function tempDeltaToDisplay(deltaC: number | null | undefined): string {
		if (deltaC === null || deltaC === undefined) return '';
		if (configState.config.temp_units === 'F') {
			return (deltaC * 9 / 5).toFixed(1);
		}
		return deltaC.toFixed(1);
	}

	// Helper to convert display value back to C for backend
	function displayToTempC(displayValue: string): number | undefined {
		if (!displayValue) return undefined;
		const num = parseFloat(displayValue);
		if (isNaN(num)) return undefined;
		if (configState.config.temp_units === 'F') {
			return fahrenheitToCelsius(num);
		}
		return num;
	}

	// Helper to convert display delta back to C delta for backend
	// For deltas: ΔC = ΔF × 5/9 (no offset subtraction)
	function displayToTempDeltaC(displayValue: string): number | undefined {
		if (!displayValue) return undefined;
		const num = parseFloat(displayValue);
		if (isNaN(num)) return undefined;
		if (configState.config.temp_units === 'F') {
			return num * 5 / 9;
		}
		return num;
	}

	let tempTarget = $state(tempToDisplay(batch?.temp_target));
	let tempHysteresis = $state(tempDeltaToDisplay(batch?.temp_hysteresis));

	// Automatic diacetyl rest rule (tilt_ui-ml8e). The controller runs it; this form only sets it.
	let restEnabled = $state(batch?.rest_trigger_percent != null);
	let restPercent = $state((batch?.rest_trigger_percent ?? 75).toString());
	let restTemp = $state(tempToDisplay(batch?.rest_temp_target ?? 21));
	let restHoldHours = $state((batch?.rest_hold_hours ?? 3).toString());
	// What the form showed at open. An untouched rule is not sent back, so display
	// rounding (Fahrenheit, 1 decimal) cannot change it or arm a finished rule again.
	const restShownAtOpen = batch?.rest_trigger_percent != null ? `${restPercent}|${restTemp}` : null;
	let restTempMin = $derived(configState.config.temp_units === 'C' ? 5.5 : 42);

	// Preview only. Same formula as rest_trigger_sg in backend/temp_controller.py, which decides.
	let restTriggerSg = $derived.by(() => {
		const recipe = selectedRecipe ?? batch?.recipe;
		const og = parseFloat(measuredOg) || recipe?.og;
		const fg = recipe?.fg;
		const pct = parseFloat(restPercent);
		if (!og || !fg || isNaN(pct) || og <= fg || og > 1.2) return null;
		return og - ((og - fg) * pct) / 100;
	});

	let recipes = $state<RecipeResponse[]>([]);
	let heaterEntities = $state<HeaterEntity[]>([]);
	let coolerEntities = $state<HeaterEntity[]>([]);
	let availableDevices = $state<DeviceResponse[]>([]);
	let loadingRecipes = $state(true);
	let loadingHeaters = $state(false);
	let loadingCoolers = $state(false);
	let loadingDevices = $state(false);
	let saving = $state(false);

	// Reactive temperature unit and validation ranges
	let tempUnit = $derived(getTempUnit());

	// Temperature validation ranges (depend on unit preference)
	let tempTargetMin = $derived(configState.config.temp_units === 'C' ? 0 : 32);
	let tempTargetMax = $derived(configState.config.temp_units === 'C' ? 38 : 100);
	let tempHysteresisMin = $derived(configState.config.temp_units === 'C' ? 0.3 : 0.5);
	let tempHysteresisMax = $derived(configState.config.temp_units === 'C' ? 5.5 : 10);

	let error = $state<string | null>(null);
	let selectedRecipe = $state<RecipeResponse | null>(null);
	let selectedYeast = $state<YeastStrainResponse | null>(null);

	// Check if HA is enabled
	let haEnabled = $derived(configState.config.ha_enabled);

	const statusOptions: { value: BatchStatus; label: string }[] = [
		{ value: 'planning', label: 'Planning' },
		{ value: 'fermenting', label: 'Fermenting' },
		{ value: 'conditioning', label: 'Conditioning' },
		{ value: 'completed', label: 'Completed' },
		{ value: 'archived', label: 'Archived' }
	];

	let isEditMode = $derived(!!batch);

	async function loadRecipes() {
		loadingRecipes = true;
		try {
			recipes = await fetchRecipes();
		} catch (e) {
			console.error('Failed to load recipes:', e);
		} finally {
			loadingRecipes = false;
		}
	}

	async function loadDevices() {
		loadingDevices = true;
		try {
			// Fetch only paired devices for batch assignment
			availableDevices = await fetchAllDevices(true);
		} catch (e) {
			console.error('Failed to load devices:', e);
		} finally {
			loadingDevices = false;
		}
	}

	async function loadHeaterEntities() {
		if (!haEnabled) return;
		loadingHeaters = true;
		try {
			heaterEntities = await fetchHeaterEntities();
		} catch (e) {
			console.error('Failed to load heater entities:', e);
		} finally {
			loadingHeaters = false;
		}
	}

	async function loadCoolerEntities() {
		if (!haEnabled) return;
		loadingCoolers = true;
		try {
			coolerEntities = await fetchCoolerEntities();
		} catch (e) {
			console.error('Failed to load cooler entities:', e);
		} finally {
			loadingCoolers = false;
		}
	}

	function handleRecipeSelect(recipe: RecipeResponse | null) {
		selectedRecipe = recipe;
		if (recipe) {
			// Auto-fill form from recipe
			name = recipe.name;
			recipeId = recipe.id;
			if (recipe.og) {
				measuredOg = recipe.og.toString();
			}
		} else {
			recipeId = null;
		}
	}

	function handleYeastSelect(yeast: YeastStrainResponse | null) {
		selectedYeast = yeast;
		yeastStrainId = yeast?.id || null;
	}

	async function handleSubmit(e: Event) {
		e.preventDefault();
		if (saving) return;

		saving = true;
		error = null;

		try {
			const data: BatchCreate | BatchUpdate = {
				name: name || undefined,
				status,
				device_id: deviceId || undefined,
				yeast_strain_id: yeastStrainId || undefined,
				brew_date: brewDate ? new Date(brewDate).toISOString() : undefined,
				measured_og: measuredOg ? parseFloat(measuredOg) : undefined,
				notes: notes || undefined,
				// Temperature control - convert display values back to C for backend
				heater_entity_id: heaterEntityId || undefined,
				cooler_entity_id: coolerEntityId || undefined,
				temp_target: displayToTempC(tempTarget),
				temp_hysteresis: displayToTempDeltaC(tempHysteresis)
			};

			// Diacetyl rest rule: null switches it off. The fields only show with a heater
			// or cooler, so without one the stored rule is left as it is.
			if (!restEnabled) {
				if (isEditMode) data.rest_trigger_percent = null;
			} else if (heaterEntityId || coolerEntityId) {
				const hold = parseFloat(restHoldHours);
				data.rest_hold_hours = isNaN(hold) ? null : hold;
				if (`${restPercent}|${restTemp}` !== restShownAtOpen) {
					const pct = parseFloat(restPercent);
					const restC = displayToTempC(restTemp);
					if (isNaN(pct) || restC === undefined) {
						throw new Error('Diacetyl rest needs a start percent and a rest temperature');
					}
					data.rest_trigger_percent = pct;
					data.rest_temp_target = restC;
				}
			}
			if ((heaterEntityId || coolerEntityId) && data.temp_target === undefined) {
				throw new Error('Set a target temperature. Without one the heater and cooler are not controlled.');
			}

			// Set recipe_id for both create and update
			if (!isEditMode) {
				(data as BatchCreate).recipe_id = recipeId || undefined;
			} else {
				(data as BatchUpdate).recipe_id = recipeId || undefined;
			}

			if (isEditMode && measuredFg) {
				(data as BatchUpdate).measured_fg = parseFloat(measuredFg);
			}

			await onSubmit(data);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to save batch';
		} finally {
			saving = false;
		}
	}

	// Auto-fill name from recipe when recipe changes
	$effect(() => {
		if (!isEditMode && recipeId && !name) {
			const recipe = recipes.find((r) => r.id === recipeId);
			if (recipe) {
				name = recipe.name;
			}
		}
	});

	// Load heater entities when HA becomes enabled
	$effect(() => {
		if (haEnabled && heaterEntities.length === 0 && !loadingHeaters) {
			loadHeaterEntities();
		}
	});

	// Load cooler entities when HA becomes enabled
	$effect(() => {
		if (haEnabled && coolerEntities.length === 0 && !loadingCoolers) {
			loadCoolerEntities();
		}
	});

	// Auto-select recipe from query parameter
	$effect(() => {
		if (initialRecipeId && recipes.length > 0 && !selectedRecipe) {
			const recipe = recipes.find((r) => r.id === initialRecipeId);
			if (recipe) {
				handleRecipeSelect(recipe);
			}
		}
	});

	// Initialize selectedRecipe when editing batch with recipe
	$effect(() => {
		if (isEditMode && batch?.recipe && recipes.length > 0 && !selectedRecipe) {
			const recipe = recipes.find((r) => r.id === batch.recipe_id);
			if (recipe) {
				selectedRecipe = recipe;
			}
		}
	});

	// Initialize selectedYeast when editing batch with yeast_strain (once only)
	let yeastInitialized = false;
	$effect(() => {
		if (isEditMode && batch?.yeast_strain && !yeastInitialized) {
			selectedYeast = batch.yeast_strain;
			yeastInitialized = true;
		}
	});

	onMount(() => {
		loadRecipes();
		loadDevices();
		loadHeaterEntities();
		loadCoolerEntities();
	});
</script>

<form class="batch-form" onsubmit={handleSubmit}>
	<div class="form-header">
		<h2 class="form-title">{isEditMode ? 'Edit Batch' : 'New Batch'}</h2>
		<p class="form-description">
			{isEditMode ? 'Update batch details and measurements' : 'Create a new fermentation batch'}
		</p>
	</div>

	{#if error}
		<div class="error-banner" role="alert">
			{error}
		</div>
	{/if}

	<div class="form-body">
		<!-- Recipe Selection -->
		<RecipeSelector
			selectedRecipeId={selectedRecipe?.id}
			onSelect={handleRecipeSelect}
		/>

			{#if selectedRecipe}
				<div class="recipe-reference">
					<p class="reference-label">From Recipe:</p>
					{#if selectedRecipe.yeast_name}
						<p class="reference-text">
							Yeast: {selectedRecipe.yeast_name}
							{#if selectedRecipe.yeast_temp_min && selectedRecipe.yeast_temp_max}
								({selectedRecipe.yeast_temp_min.toFixed(0)}&ndash;{selectedRecipe.yeast_temp_max.toFixed(
									0
								)}&thinsp;°C)
							{/if}
						</p>
					{/if}
				</div>
			{/if}

		<!-- Yeast Strain Selection -->
		<YeastSelector
			selectedYeastId={selectedYeast?.id}
			onSelect={handleYeastSelect}
			label="Override Yeast Strain (Optional)"
		/>

		<!-- Batch Name -->
		<div class="form-group">
			<label class="form-label" for="name">Batch Name</label>
			<input
				type="text"
				id="name"
				class="form-input"
				bind:value={name}
				placeholder="e.g., Summer IPA #3"
				maxlength="200"
			/>
			<span class="form-hint">Optional - defaults to recipe name</span>
		</div>

		<div class="field-grid">
		<!-- Status -->
		<div class="form-group">
			<label class="form-label" for="status">Status</label>
			<select id="status" class="form-select" bind:value={status}>
				{#each statusOptions as option}
					<option value={option.value}>{option.label}</option>
				{/each}
			</select>
		</div>

		<!-- Device -->
		<div class="form-group">
			<label class="form-label" for="device">Tracking Device</label>
			{#if loadingDevices}
				<span class="form-hint">Loading devices...</span>
			{:else if availableDevices.length === 0}
				<div class="warning-message">
					<p>No paired devices available. Please <a href="/devices">pair a device</a> before creating a batch.</p>
				</div>
			{:else}
				<select id="device" class="form-select" bind:value={deviceId}>
					<option value={null}>No device assigned</option>
					{#each availableDevices as device}
						<option value={device.id}>
							{#if device.device_type === 'tilt'}
								{device.color} Tilt
							{:else if device.device_type === 'ispindel'}
								iSpindel {device.display_name || device.name}
							{:else if device.device_type === 'gravitymon'}
								GravityMon {device.display_name || device.name}
							{:else}
								{device.display_name || device.name}
							{/if}
							{#if device.beer_name && device.beer_name !== 'Untitled'}
								- {device.beer_name}
							{/if}
						</option>
					{/each}
				</select>
				<span class="form-hint">Link a device to track live gravity and temperature</span>
			{/if}
		</div>

		<!-- Brew Date -->
		<div class="form-group">
			<label class="form-label" for="brewDate">Brew Date</label>
			<input
				type="date"
				id="brewDate"
				class="form-input date-input"
				bind:value={brewDate}
			/>
		</div>

		<!-- Gravity Measurements -->
			<div class="form-group">
				<label class="form-label" for="og">Measured OG</label>
				<input
					type="number"
					id="og"
					class="form-input"
					bind:value={measuredOg}
					placeholder="1.050"
					step="0.001"
					min="0.990"
					max="1.200"
				/>
			</div>
			{#if isEditMode}
				<div class="form-group">
					<label class="form-label" for="fg">Measured FG</label>
					<input
						type="number"
						id="fg"
						class="form-input"
						bind:value={measuredFg}
						placeholder="1.010"
						step="0.001"
						min="0.990"
						max="1.100"
					/>
				</div>
			{/if}
		</div>

		<!-- Temperature Control (only if HA is enabled) -->
		{#if haEnabled}
			<div class="form-section">
				<h3 class="section-title">Temperature Control</h3>
				<span class="section-hint">Link heater and/or cooler switches from Home Assistant to control fermentation temperature</span>
			</div>

			<div class="form-group">
				<label class="form-label" for="heaterEntity">Heater Switch</label>
				<select
					id="heaterEntity"
					class="form-select"
					bind:value={heaterEntityId}
					disabled={loadingHeaters}
				>
					<option value="">No heater assigned</option>
					{#each heaterEntities as entity}
						<option value={entity.entity_id}>
							{entity.friendly_name} ({entity.state})
						</option>
					{/each}
				</select>
				{#if loadingHeaters}
					<span class="form-hint">Loading available switches from Home Assistant...</span>
				{:else if heaterEntities.length === 0}
					<span class="form-hint">No switches found in Home Assistant</span>
				{:else}
					<span class="form-hint">Select a switch or input_boolean entity to control the heater</span>
				{/if}
			</div>

			<div class="form-group">
				<label class="form-label" for="coolerEntity">Cooler Switch</label>
				<select
					id="coolerEntity"
					class="form-select"
					bind:value={coolerEntityId}
					disabled={loadingCoolers}
				>
					<option value="">No cooler assigned</option>
					{#each coolerEntities as entity}
						<option value={entity.entity_id}>
							{entity.friendly_name} ({entity.state})
						</option>
					{/each}
				</select>
				{#if loadingCoolers}
					<span class="form-hint">Loading available switches from Home Assistant...</span>
				{:else if coolerEntities.length === 0}
					<span class="form-hint">No switches found in Home Assistant</span>
				{:else}
					<span class="form-hint">Select a switch or input_boolean entity to control the cooler</span>
				{/if}
			</div>

			{#if heaterEntityId || coolerEntityId}
				<div class="form-row">
					<div class="form-group">
						<label class="form-label" for="tempTarget">Target Temperature ({tempUnit})</label>
						<input
							type="number"
							id="tempTarget"
							class="form-input"
							bind:value={tempTarget}
							placeholder="68"
							step="0.5"
							min={tempTargetMin}
							max={tempTargetMax}
							required
						/>
						<span class="form-hint">Needed. Without a target the heater and cooler are not controlled.</span>
					</div>
					<div class="form-group">
						<label class="form-label" for="tempHysteresis">Hysteresis ({tempUnit})</label>
						<input
							type="number"
							id="tempHysteresis"
							class="form-input"
							bind:value={tempHysteresis}
							placeholder="1.0"
							step="0.5"
							min={tempHysteresisMin}
							max={tempHysteresisMax}
						/>
						<span class="form-hint">Leave empty to use global setting</span>
					</div>
				</div>

				<div class="form-group">
					<label class="rest-toggle" for="restEnabled">
						<input type="checkbox" id="restEnabled" bind:checked={restEnabled} />
						Automatic diacetyl rest
					</label>
					<span class="form-hint">
						Raises the target temperature one time, when gravity gets near final gravity. Works while the batch is fermenting.
					</span>
				</div>

				{#if restEnabled}
					<div class="form-row">
						<div class="form-group">
							<label class="form-label" for="restPercent">Start at (% of the way to FG)</label>
							<input type="number" id="restPercent" class="form-input" bind:value={restPercent} step="1" min="10" max="95" />
						</div>
						<div class="form-group">
							<label class="form-label" for="restTemp">Rest Temperature ({tempUnit})</label>
							<input type="number" id="restTemp" class="form-input" bind:value={restTemp} step="0.1" min={restTempMin} max={tempTargetMax} />
						</div>
					</div>
					<div class="form-group">
						<label class="form-label" for="restHoldHours">Gravity must hold for (hours)</label>
						<input type="number" id="restHoldHours" class="form-input" bind:value={restHoldHours} step="0.5" min="0" max="48" />
						<span class="form-hint">
							{#if batch?.rest_fired_at}
								Rest started {new Date(batch.rest_fired_at).toLocaleString()}. The rule is finished. Change the percent or rest temperature to arm it again.
							{:else if restTriggerSg !== null}
								Starts when gravity stays at or below {formatGravity(restTriggerSg)} {getGravityUnit()} for this long. A noisy reading or an outage restarts the wait. The rule only raises the target, and it waits while the target is below 5 °C.
							{:else}
								Needs a recipe with OG and FG. Without them the rule does not start.
							{/if}
						</span>
					</div>
				{/if}
			{/if}
		{/if}

		<!-- Notes -->
		<div class="form-group">
			<label class="form-label" for="notes">Notes</label>
			<textarea
				id="notes"
				class="form-textarea"
				bind:value={notes}
				placeholder="Brewing notes, observations, etc."
				rows="3"
			></textarea>
		</div>
	</div>

	<div class="form-footer">
		<button type="button" class="btn-cancel" onclick={onCancel} disabled={saving}>
			Cancel
		</button>
		<button type="submit" class="btn-submit" disabled={saving}>
			{#if saving}
				<span class="spinner" aria-hidden="true"></span>
				Saving...
			{:else}
				{isEditMode ? 'Save Changes' : 'Create Batch'}
			{/if}
		</button>
	</div>
</form>

<style>
	.batch-form {
		border-top: 1px solid var(--rule-strong);
	}
	.form-header {
		padding: var(--space-md) 0 var(--space-sm);
	}
	.form-title {
		font-family: var(--font-display);
		font-size: var(--text-xl);
		font-weight: 700;
		letter-spacing: -0.02em;
		line-height: 1.15;
		color: var(--ink-primary);
	}
	.form-description {
		margin-top: var(--space-2xs);
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}
	.form-body {
		padding: var(--space-sm) 0 var(--space-lg);
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
	}
	.form-section {
		display: flex;
		flex-direction: column;
		gap: var(--space-2xs);
		padding-top: var(--space-md);
		border-top: 1px solid var(--rule-hairline);
		margin-top: var(--space-xs);
	}
	.section-title {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--ink-muted);
	}
	.section-hint,
	.form-hint {
		font-size: var(--text-xs);
		color: var(--ink-muted);
	}
	.form-group {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
	}
	.rest-toggle {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
		font-size: var(--text-sm);
		color: var(--ink-primary);
		cursor: pointer;
	}
	.form-row {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: var(--space-md);
	}
	.field-grid {
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		gap: var(--space-md);
	}
	@media (min-width: 1041px) {
		.field-grid {
			grid-template-columns: repeat(2, minmax(0, 1fr));
			gap: var(--space-md) var(--space-lg);
		}
	}
	.form-label {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--ink-secondary);
	}
	.form-input,
	.form-select,
	.form-textarea {
		min-height: 44px;
		padding: 0 var(--space-sm);
		font-size: var(--text-base);
		color: var(--ink-primary);
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		outline: none;
		transition: border-color 140ms var(--ease-out-quart);
	}
	.form-input[type='number'],
	.form-input[type='date'] {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
	}
	.form-input:focus,
	.form-select:focus,
	.form-textarea:focus {
		border-color: var(--accent);
	}
	.form-input::placeholder,
	.form-textarea::placeholder {
		color: var(--ink-muted);
	}
	.form-select {
		cursor: pointer;
	}
	.form-textarea {
		padding: var(--space-sm);
		resize: vertical;
		min-height: 80px;
	}
	.form-footer {
		display: flex;
		justify-content: flex-end;
		gap: var(--space-sm);
		padding: var(--space-md) 0;
		border-top: 1px solid var(--rule-hairline);
	}
	.btn-cancel,
	.btn-submit {
		min-height: 44px;
		padding: 0 var(--space-lg);
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		border-radius: 4px;
		cursor: pointer;
		transition: background-color 140ms var(--ease-out-quart);
	}
	.btn-cancel {
		color: var(--ink-primary);
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
	}
	.btn-cancel:hover:not(:disabled) {
		background: var(--bg-subtle);
	}
	.btn-submit {
		display: inline-flex;
		align-items: center;
		gap: var(--space-xs);
		color: var(--accent-ink);
		background: var(--accent);
	}
	.btn-submit:hover:not(:disabled) {
		background: var(--accent-hover);
	}
	.btn-cancel:disabled,
	.btn-submit:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
	.error-banner {
		margin-top: var(--space-sm);
		padding: var(--space-xs) var(--space-sm);
		font-size: var(--text-sm);
		color: var(--status-danger);
		border: 1px solid color-mix(in oklch, var(--status-danger) 55%, transparent);
		background: var(--negative-muted);
	}
	.spinner {
		width: 1rem;
		height: 1rem;
		border: 2px solid color-mix(in oklch, var(--accent-ink) 30%, transparent);
		border-top-color: var(--accent-ink);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
	.recipe-reference {
		padding: var(--space-xs) 0;
	}
	.reference-label {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--accent);
		margin-bottom: var(--space-2xs);
		text-transform: uppercase;
		letter-spacing: 0.07em;
	}
	.reference-text {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		font-family: var(--font-num);
	}
	.warning-message {
		padding: var(--space-xs) var(--space-sm);
		background: var(--warning-muted);
		border: 1px solid color-mix(in oklch, var(--status-warn) 50%, transparent);
		border-radius: 4px;
	}
	.warning-message p {
		font-size: var(--text-sm);
		color: var(--status-warn);
	}
	.warning-message a {
		color: var(--accent);
		font-weight: 700;
		text-decoration: underline;
	}
	.warning-message a:hover {
		color: var(--accent-hover);
	}
	@media (max-width: 480px) {
		.form-row {
			grid-template-columns: minmax(0, 1fr);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.spinner {
			animation: none;
		}
	}
</style>
