<script lang="ts">
	import type { BatchResponse, TastingNoteResponse, TastingNoteCreate, TastingNoteUpdate } from '$lib/api';
	import { createTastingNote, updateTastingNote, deleteTastingNote } from '$lib/api';

	interface Props {
		batch: BatchResponse;
		onUpdate?: (batch: BatchResponse) => void;
	}

	let { batch, onUpdate }: Props = $props();

	// Local copy of tasting notes for reactivity
	let notes = $state<TastingNoteResponse[]>(batch.tasting_notes ?? []);
	let expanded = $state(true);
	let showForm = $state(false);
	let editingId = $state<number | null>(null);
	let saving = $state(false);

	// Form state for new/edit
	let formData = $state<TastingNoteCreate>({
		appearance_score: undefined,
		appearance_notes: '',
		aroma_score: undefined,
		aroma_notes: '',
		flavor_score: undefined,
		flavor_notes: '',
		mouthfeel_score: undefined,
		mouthfeel_notes: '',
		overall_score: undefined,
		overall_notes: '',
	});

	// Calculate average overall score
	let averageScore = $derived(() => {
		if (notes.length === 0) return null;
		const scores = notes.filter(n => n.overall_score != null).map(n => n.overall_score!);
		if (scores.length === 0) return null;
		return (scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(1);
	});

	function toggleExpanded() {
		expanded = !expanded;
	}

	function resetForm() {
		formData = {
			appearance_score: undefined,
			appearance_notes: '',
			aroma_score: undefined,
			aroma_notes: '',
			flavor_score: undefined,
			flavor_notes: '',
			mouthfeel_score: undefined,
			mouthfeel_notes: '',
			overall_score: undefined,
			overall_notes: '',
		};
		editingId = null;
		showForm = false;
	}

	function startNewNote() {
		resetForm();
		showForm = true;
	}

	function editNote(note: TastingNoteResponse) {
		formData = {
			appearance_score: note.appearance_score ?? undefined,
			appearance_notes: note.appearance_notes ?? '',
			aroma_score: note.aroma_score ?? undefined,
			aroma_notes: note.aroma_notes ?? '',
			flavor_score: note.flavor_score ?? undefined,
			flavor_notes: note.flavor_notes ?? '',
			mouthfeel_score: note.mouthfeel_score ?? undefined,
			mouthfeel_notes: note.mouthfeel_notes ?? '',
			overall_score: note.overall_score ?? undefined,
			overall_notes: note.overall_notes ?? '',
		};
		editingId = note.id;
		showForm = true;
	}

	async function saveNote() {
		if (saving) return;
		saving = true;

		try {
			if (editingId) {
				// Update existing
				const updated = await updateTastingNote(batch.id, editingId, formData as TastingNoteUpdate);
				notes = notes.map(n => n.id === editingId ? updated : n);
			} else {
				// Create new
				const created = await createTastingNote(batch.id, formData);
				notes = [created, ...notes];
			}
			resetForm();
			// Update parent with new notes
			onUpdate?.({ ...batch, tasting_notes: notes });
		} catch (e) {
			console.error('Failed to save tasting note:', e);
		} finally {
			saving = false;
		}
	}

	async function removeNote(noteId: number) {
		if (!confirm('Delete this tasting note?')) return;

		try {
			await deleteTastingNote(batch.id, noteId);
			notes = notes.filter(n => n.id !== noteId);
			onUpdate?.({ ...batch, tasting_notes: notes });
		} catch (e) {
			console.error('Failed to delete tasting note:', e);
		}
	}

	function formatDate(dateStr: string): string {
		return new Date(dateStr).toLocaleDateString('en-AU', {
			day: 'numeric',
			month: 'short',
			year: 'numeric'
		});
	}

	// Score display helper
	function scoreStars(score: number | null | undefined): string {
		if (score == null) return '-';
		return '\u2605'.repeat(score) + '\u2606'.repeat(5 - score);
	}
</script>

<div class="tasting-card">
	<button type="button" class="card-header" onclick={toggleExpanded}>
		<div class="header-content">
			<h3 class="card-title">Tasting Notes</h3>
			{#if notes.length > 0}
				<span class="note-count">{notes.length}</span>
			{/if}
		</div>
		<div class="header-right">
			{#if averageScore()}
				<span class="avg-score">Avg: {averageScore()}/5</span>
			{/if}
			<svg class="chevron" class:expanded fill="none" viewBox="0 0 24 24" stroke="currentColor">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
			</svg>
		</div>
	</button>

	{#if expanded}
		<div class="card-content">
			<!-- Add New Note Button -->
			{#if !showForm}
				<button type="button" class="add-note-btn" onclick={startNewNote}>
					<svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
					</svg>
					Add Tasting Note
				</button>
			{/if}

			<!-- Note Form -->
			{#if showForm}
				<div class="note-form">
					<div class="form-header">
						<h4>{editingId ? 'Edit' : 'New'} Tasting Note</h4>
						<button type="button" class="close-btn" onclick={resetForm}>
							<svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
							</svg>
						</button>
					</div>

					<!-- Score Categories -->
					{#each [
						{ key: 'appearance', label: 'Appearance' },
						{ key: 'aroma', label: 'Aroma' },
						{ key: 'flavor', label: 'Flavor' },
						{ key: 'mouthfeel', label: 'Mouthfeel' },
						{ key: 'overall', label: 'Overall' }
					] as category}
						<div class="score-category">
							<div class="category-header">
								<span class="category-label">{category.label}</span>
								<div class="score-selector">
									{#each [1, 2, 3, 4, 5] as score}
										<button
											type="button"
											class="score-btn"
											class:selected={formData[`${category.key}_score` as keyof typeof formData] === score}
											onclick={() => {
												const key = `${category.key}_score` as keyof typeof formData;
												(formData as any)[key] = score;
											}}
										>
											{score}
										</button>
									{/each}
								</div>
							</div>
							<textarea
								class="category-notes"
								placeholder="Notes on {category.label.toLowerCase()}..."
								rows="2"
								bind:value={formData[`${category.key}_notes` as keyof typeof formData]}
							></textarea>
						</div>
					{/each}

					<div class="form-actions">
						<button type="button" class="cancel-btn" onclick={resetForm}>Cancel</button>
						<button type="button" class="save-btn" onclick={saveNote} disabled={saving}>
							{saving ? 'Saving...' : (editingId ? 'Update' : 'Save')}
						</button>
					</div>
				</div>
			{/if}

			<!-- Existing Notes -->
			{#if notes.length > 0}
				<div class="notes-list">
					{#each notes as note}
						<div class="note-item" class:editing={editingId === note.id}>
							<div class="note-header">
								<span class="note-date">{formatDate(note.tasted_at)}</span>
								<div class="note-actions">
									<button type="button" class="action-btn" onclick={() => editNote(note)} title="Edit">
										<svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
										</svg>
									</button>
									<button type="button" class="action-btn delete" onclick={() => removeNote(note.id)} title="Delete">
										<svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
										</svg>
									</button>
								</div>
							</div>

							<div class="note-scores">
								{#each [
									{ key: 'appearance', label: 'App' },
									{ key: 'aroma', label: 'Aroma' },
									{ key: 'flavor', label: 'Flav' },
									{ key: 'mouthfeel', label: 'Mouth' },
									{ key: 'overall', label: 'Overall' }
								] as cat}
									<div class="score-item" class:overall={cat.key === 'overall'}>
										<span class="score-label">{cat.label}</span>
										<span class="score-value">{scoreStars(note[`${cat.key}_score` as keyof TastingNoteResponse] as number | undefined)}</span>
									</div>
								{/each}
							</div>

							{#if note.overall_notes}
								<p class="note-text">{note.overall_notes}</p>
							{/if}
						</div>
					{/each}
				</div>
			{:else if !showForm}
				<p class="empty-message">No tasting notes yet. Add your first one to track how this batch develops over time.</p>
			{/if}
		</div>
	{/if}
</div>

<style>
	.tasting-card {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.75rem;
		overflow: hidden;
	}

	.card-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		width: 100%;
		padding: 1rem 1.25rem;
		background: transparent;
		border: none;
		cursor: pointer;
		text-align: left;
		transition: background 0.15s ease;
	}

	.card-header:hover {
		background: var(--bg-elevated);
	}

	.header-content {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}

	.header-right {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}

	.card-title {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin: 0;
	}

	.note-count {
		font-size: 0.6875rem;
		font-weight: 600;
		padding: 0.125rem 0.5rem;
		background: var(--primary-bg);
		color: var(--primary);
		border-radius: 1rem;
	}

	.avg-score {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-secondary);
		font-family: var(--font-mono);
	}

	.chevron {
		width: 1rem;
		height: 1rem;
		color: var(--text-muted);
		transition: transform 0.2s ease;
	}

	.chevron.expanded {
		transform: rotate(180deg);
	}

	.card-content {
		padding: 1rem 1.25rem;
		border-top: 1px solid var(--border-subtle);
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.add-note-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		padding: 0.75rem;
		background: var(--bg-elevated);
		border: 1px dashed var(--border-subtle);
		border-radius: 0.5rem;
		color: var(--text-muted);
		font-size: 0.875rem;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.add-note-btn:hover {
		border-color: var(--primary);
		color: var(--primary);
	}

	.add-note-btn svg {
		width: 1rem;
		height: 1rem;
	}

	/* Note Form */
	.note-form {
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
		border-radius: 0.5rem;
		padding: 1rem;
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.form-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.form-header h4 {
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
	}

	.close-btn {
		background: none;
		border: none;
		padding: 0.25rem;
		cursor: pointer;
		color: var(--text-muted);
	}

	.close-btn:hover {
		color: var(--text-primary);
	}

	.close-btn svg {
		width: 1.25rem;
		height: 1.25rem;
	}

	.score-category {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.category-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.category-label {
		font-size: 0.8125rem;
		font-weight: 500;
		color: var(--text-secondary);
	}

	.score-selector {
		display: flex;
		gap: 0.25rem;
	}

	.score-btn {
		width: 2rem;
		height: 2rem;
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--bg-base);
		border: 1px solid var(--border-subtle);
		border-radius: 0.25rem;
		font-size: 0.875rem;
		font-weight: 500;
		color: var(--text-muted);
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.score-btn:hover {
		border-color: var(--primary);
		color: var(--primary);
	}

	.score-btn.selected {
		background: var(--primary);
		border-color: var(--primary);
		color: white;
	}

	.category-notes {
		width: 100%;
		padding: 0.5rem;
		background: var(--bg-base);
		border: 1px solid var(--border-subtle);
		border-radius: 0.375rem;
		font-size: 0.8125rem;
		color: var(--text-primary);
		resize: none;
		font-family: inherit;
	}

	.category-notes:focus {
		outline: none;
		border-color: var(--primary);
	}

	.form-actions {
		display: flex;
		justify-content: flex-end;
		gap: 0.5rem;
		padding-top: 0.5rem;
		border-top: 1px solid var(--border-subtle);
	}

	.cancel-btn,
	.save-btn {
		padding: 0.5rem 1rem;
		border-radius: 0.375rem;
		font-size: 0.8125rem;
		font-weight: 500;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.cancel-btn {
		background: transparent;
		border: 1px solid var(--border-subtle);
		color: var(--text-secondary);
	}

	.cancel-btn:hover {
		border-color: var(--text-muted);
	}

	.save-btn {
		background: var(--primary);
		border: none;
		color: white;
	}

	.save-btn:hover {
		opacity: 0.9;
	}

	.save-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	/* Notes List */
	.notes-list {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.note-item {
		background: var(--bg-base);
		border: 1px solid var(--border-subtle);
		border-radius: 0.5rem;
		padding: 0.75rem;
	}

	.note-item.editing {
		opacity: 0.5;
	}

	.note-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.5rem;
	}

	.note-date {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-muted);
	}

	.note-actions {
		display: flex;
		gap: 0.25rem;
	}

	.action-btn {
		background: none;
		border: none;
		padding: 0.25rem;
		cursor: pointer;
		color: var(--text-muted);
		border-radius: 0.25rem;
		transition: all 0.15s ease;
	}

	.action-btn:hover {
		background: var(--bg-elevated);
		color: var(--text-primary);
	}

	.action-btn.delete:hover {
		color: var(--negative);
	}

	.action-btn svg {
		width: 1rem;
		height: 1rem;
	}

	.note-scores {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin-bottom: 0.5rem;
	}

	.score-item {
		display: flex;
		flex-direction: column;
		align-items: center;
		padding: 0.25rem 0.5rem;
		background: var(--bg-elevated);
		border-radius: 0.25rem;
	}

	.score-item.overall {
		background: var(--primary-bg);
	}

	.score-label {
		font-size: 0.625rem;
		color: var(--text-muted);
		text-transform: uppercase;
	}

	.score-value {
		font-size: 0.75rem;
		color: var(--amber);
	}

	.score-item.overall .score-value {
		color: var(--primary);
	}

	.note-text {
		font-size: 0.8125rem;
		color: var(--text-secondary);
		line-height: 1.4;
		margin: 0;
	}

	.empty-message {
		text-align: center;
		color: var(--text-muted);
		font-size: 0.875rem;
		padding: 1rem;
		margin: 0;
	}
</style>
