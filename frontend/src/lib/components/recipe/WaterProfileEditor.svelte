<script lang="ts">
	export interface WaterProfileInput {
		profile_type: string;
		name?: string;
		calcium_ppm?: number;
		magnesium_ppm?: number;
		sodium_ppm?: number;
		chloride_ppm?: number;
		sulfate_ppm?: number;
		bicarbonate_ppm?: number;
		ph?: number;
		alkalinity?: number;
	}

	interface Props {
		profiles: WaterProfileInput[];
		onUpdate: (profiles: WaterProfileInput[]) => void;
	}

	let { profiles = [], onUpdate }: Props = $props();

	let localProfiles = $state<WaterProfileInput[]>([]);

	$effect(() => {
		localProfiles = [...profiles];
	});

	function addProfile() {
		const newProfile: WaterProfileInput = {
			profile_type: 'source',
			name: 'New Profile',
			calcium_ppm: 0,
			magnesium_ppm: 0,
			sodium_ppm: 0,
			chloride_ppm: 0,
			sulfate_ppm: 0,
			bicarbonate_ppm: 0,
			ph: 7.0
		};
		localProfiles = [...localProfiles, newProfile];
		onUpdate(localProfiles);
	}

	function removeProfile(index: number) {
		localProfiles = localProfiles.filter((_, i) => i !== index);
		onUpdate(localProfiles);
	}

	function updateProfile(index: number, field: keyof WaterProfileInput, value: unknown) {
		localProfiles[index] = { ...localProfiles[index], [field]: value };
		onUpdate(localProfiles);
	}

	function getProfileLabel(type: string): string {
		const labels: Record<string, string> = {
			source: 'Source Water',
			target: 'Target Profile',
			mash: 'Mash Water',
			sparge: 'Sparge Water'
		};
		return labels[type] || type;
	}
</script>

<div class="editor-section">
	<div class="section-header">
		<h4>Water Profiles</h4>
		<button type="button" class="btn-add" onclick={addProfile}>+ Add Profile</button>
	</div>

	{#if localProfiles.length === 0}
		<p class="empty-state">No water profiles defined. Click "Add Profile" to add one.</p>
	{:else}
		<div class="profiles-list">
			{#each localProfiles as profile, i}
				<div class="profile-card" class:target={profile.profile_type === 'target'}>
					<div class="profile-header">
						<select
							class="input-type" aria-label="Profile type"
							value={profile.profile_type}
							onchange={(e) => updateProfile(i, 'profile_type', e.currentTarget.value)}
						>
							<option value="source">Source</option>
							<option value="target">Target</option>
							<option value="mash">Mash</option>
							<option value="sparge">Sparge</option>
						</select>
						<input
							type="text"
							class="input-name" aria-label="Profile name"
							value={profile.name || ''}
							placeholder="Profile name"
							onchange={(e) => updateProfile(i, 'name', e.currentTarget.value)}
						/>
						<button type="button" class="btn-remove" aria-label="Remove" onclick={() => removeProfile(i)}>×</button>
					</div>

					<div class="ion-grid">
						<div class="ion-field">
							<label>Ca</label>
							<input aria-label="Ca"
								type="number"
								value={profile.calcium_ppm ?? ''}
								placeholder="0"
								onchange={(e) => updateProfile(i, 'calcium_ppm', parseFloat(e.currentTarget.value) || 0)}
							/>
							<span class="unit">ppm</span>
						</div>
						<div class="ion-field">
							<label>Mg</label>
							<input aria-label="Mg"
								type="number"
								value={profile.magnesium_ppm ?? ''}
								placeholder="0"
								onchange={(e) => updateProfile(i, 'magnesium_ppm', parseFloat(e.currentTarget.value) || 0)}
							/>
							<span class="unit">ppm</span>
						</div>
						<div class="ion-field">
							<label>Na</label>
							<input aria-label="Na"
								type="number"
								value={profile.sodium_ppm ?? ''}
								placeholder="0"
								onchange={(e) => updateProfile(i, 'sodium_ppm', parseFloat(e.currentTarget.value) || 0)}
							/>
							<span class="unit">ppm</span>
						</div>
						<div class="ion-field">
							<label>Cl</label>
							<input aria-label="Cl"
								type="number"
								value={profile.chloride_ppm ?? ''}
								placeholder="0"
								onchange={(e) => updateProfile(i, 'chloride_ppm', parseFloat(e.currentTarget.value) || 0)}
							/>
							<span class="unit">ppm</span>
						</div>
						<div class="ion-field">
							<label>SO4</label>
							<input aria-label="SO4"
								type="number"
								value={profile.sulfate_ppm ?? ''}
								placeholder="0"
								onchange={(e) => updateProfile(i, 'sulfate_ppm', parseFloat(e.currentTarget.value) || 0)}
							/>
							<span class="unit">ppm</span>
						</div>
						<div class="ion-field">
							<label>HCO3</label>
							<input aria-label="HCO3"
								type="number"
								value={profile.bicarbonate_ppm ?? ''}
								placeholder="0"
								onchange={(e) => updateProfile(i, 'bicarbonate_ppm', parseFloat(e.currentTarget.value) || 0)}
							/>
							<span class="unit">ppm</span>
						</div>
					</div>

					<div class="profile-footer">
						<div class="ph-field">
							<label>pH</label>
							<input aria-label="pH"
								type="number"
								step="0.1"
								value={profile.ph ?? ''}
								placeholder="7.0"
								onchange={(e) => updateProfile(i, 'ph', parseFloat(e.currentTarget.value) || 0)}
							/>
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

	label {
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-muted);
		text-transform: uppercase;
		letter-spacing: 0.08em;
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

	.profiles-list {
		display: flex;
		flex-direction: column;
	}

	/* Hairline rows: one row per step/item */

	.input-name {
		flex: 1 1 160px;
	}

	.input-type {
		flex: 0 1 140px;
	}

	/* Profiles and adjustments: hairline-separated blocks, no cards */
	.profile-card {
		display: flex;
		flex-direction: column;
		gap: var(--space-sm);
		padding: var(--space-md) 0;
		border-bottom: 1px solid var(--rule-hairline);
	}

	.profile-header {
		display: flex;
		align-items: flex-end;
		flex-wrap: wrap;
		gap: var(--space-xs);
	}

	.profile-header .btn-remove {
		margin-left: auto;
	}

	.ion-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(8.5rem, 1fr));
		gap: var(--space-sm);
	}

	.ion-field,
	.ph-field {
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto;
		align-items: center;
		gap: var(--space-2xs) var(--space-xs);
	}

	.ion-field label,
	.ph-field label {
		grid-column: 1 / -1;
	}

	.ph-field {
		max-width: 8.5rem;
	}

	.ph-field input {
		grid-column: 1 / -1;
	}

	.input-type {
		flex: 0 1 140px;
	}

	.input-name {
		flex: 1 1 160px;
	}
</style>
