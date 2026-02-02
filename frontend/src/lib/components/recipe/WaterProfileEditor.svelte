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
							class="input-type"
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
							class="input-name"
							value={profile.name || ''}
							placeholder="Profile name"
							onchange={(e) => updateProfile(i, 'name', e.currentTarget.value)}
						/>
						<button type="button" class="btn-remove" onclick={() => removeProfile(i)}>×</button>
					</div>

					<div class="ion-grid">
						<div class="ion-field">
							<label>Ca</label>
							<input
								type="number"
								value={profile.calcium_ppm ?? ''}
								placeholder="0"
								onchange={(e) => updateProfile(i, 'calcium_ppm', parseFloat(e.currentTarget.value) || 0)}
							/>
							<span class="unit">ppm</span>
						</div>
						<div class="ion-field">
							<label>Mg</label>
							<input
								type="number"
								value={profile.magnesium_ppm ?? ''}
								placeholder="0"
								onchange={(e) => updateProfile(i, 'magnesium_ppm', parseFloat(e.currentTarget.value) || 0)}
							/>
							<span class="unit">ppm</span>
						</div>
						<div class="ion-field">
							<label>Na</label>
							<input
								type="number"
								value={profile.sodium_ppm ?? ''}
								placeholder="0"
								onchange={(e) => updateProfile(i, 'sodium_ppm', parseFloat(e.currentTarget.value) || 0)}
							/>
							<span class="unit">ppm</span>
						</div>
						<div class="ion-field">
							<label>Cl</label>
							<input
								type="number"
								value={profile.chloride_ppm ?? ''}
								placeholder="0"
								onchange={(e) => updateProfile(i, 'chloride_ppm', parseFloat(e.currentTarget.value) || 0)}
							/>
							<span class="unit">ppm</span>
						</div>
						<div class="ion-field">
							<label>SO4</label>
							<input
								type="number"
								value={profile.sulfate_ppm ?? ''}
								placeholder="0"
								onchange={(e) => updateProfile(i, 'sulfate_ppm', parseFloat(e.currentTarget.value) || 0)}
							/>
							<span class="unit">ppm</span>
						</div>
						<div class="ion-field">
							<label>HCO3</label>
							<input
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
							<input
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

	.profiles-list {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}

	.profile-card {
		padding: var(--space-4);
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
		border-radius: 8px;
	}

	.profile-card.target {
		border-color: var(--recipe-accent-border);
		background: linear-gradient(135deg, var(--bg-elevated) 0%, rgba(245, 158, 11, 0.03) 100%);
	}

	.profile-header {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		margin-bottom: var(--space-4);
	}

	.input-type {
		width: 100px;
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

	.input-name {
		flex: 1;
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

	.ion-grid {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: var(--space-3);
	}

	.ion-field {
		display: flex;
		align-items: center;
		gap: var(--space-1);
		padding: var(--space-2);
		background: var(--bg-surface);
		border-radius: 4px;
	}

	.ion-field label {
		font-size: 11px;
		font-weight: 600;
		color: var(--text-muted);
		min-width: 28px;
	}

	.ion-field input {
		flex: 1;
		width: 50px;
		padding: var(--space-1);
		background: transparent;
		border: none;
		color: var(--text-primary);
		font-family: var(--font-mono);
		font-size: 12px;
		text-align: right;
	}

	.ion-field input:focus {
		outline: none;
	}

	.ion-field .unit {
		font-size: 10px;
		color: var(--text-muted);
	}

	.profile-footer {
		display: flex;
		gap: var(--space-3);
		margin-top: var(--space-3);
		padding-top: var(--space-3);
		border-top: 1px solid var(--border-subtle);
	}

	.ph-field {
		display: flex;
		align-items: center;
		gap: var(--space-2);
	}

	.ph-field label {
		font-size: 12px;
		font-weight: 500;
		color: var(--text-secondary);
	}

	.ph-field input {
		width: 60px;
		padding: var(--space-2);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 4px;
		color: var(--text-primary);
		font-family: var(--font-mono);
		font-size: 13px;
		text-align: right;
	}

	.ph-field input:focus {
		outline: none;
		border-color: var(--recipe-accent);
	}

	@media (max-width: 640px) {
		.ion-grid {
			grid-template-columns: repeat(2, 1fr);
		}
	}
</style>
