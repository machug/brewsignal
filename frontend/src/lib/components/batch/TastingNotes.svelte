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
		return `${score}/5`;
	}
</script>

<div class="tasting-card">
	<button type="button" class="card-header" onclick={toggleExpanded}>
		<div class="header-content">
			<h3 class="card-title">Tasting Notes</h3>
			{#if notes.length > 0}
				<span class="note-count num">{notes.length}</span>
			{/if}
		</div>
		<div class="header-right">
			{#if averageScore()}
				<span class="avg-score">Avg {averageScore()}/5</span>
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
	.num {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums lining-nums;
	}

	.tasting-card {
		background: var(--bg-surface);
		border: 1px solid var(--rule-hairline);
		border-radius: 6px;
		overflow: hidden;
	}

	.card-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		width: 100%;
		min-height: 48px;
		padding: var(--space-sm) var(--space-md);
		background: transparent;
		border: none;
		cursor: pointer;
		text-align: left;
	}

	.card-header:hover {
		background: var(--bg-elevated);
	}

	button:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.header-content,
	.header-right {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
	}

	.card-title {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-muted);
		text-transform: uppercase;
		letter-spacing: 0.08em;
		margin: 0;
	}

	.note-count {
		font-size: 0.6875rem;
		font-weight: 600;
		padding: 1px 7px;
		border: 1px solid var(--rule-strong);
		border-radius: 2px;
		color: var(--ink-secondary);
	}

	.avg-score {
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-secondary);
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
	}

	.chevron {
		width: 1rem;
		height: 1rem;
		color: var(--ink-muted);
		transition: transform 0.2s var(--ease-out-quart);
	}

	.chevron.expanded {
		transform: rotate(180deg);
	}

	.card-content {
		padding: var(--space-md);
		border-top: 1px solid var(--rule-hairline);
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
	}

	.add-note-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: var(--space-xs);
		min-height: 44px;
		background: var(--accent-tint);
		border: 1px solid var(--accent-rule);
		border-radius: 4px;
		color: var(--accent);
		font-size: var(--text-sm);
		font-weight: 600;
		cursor: pointer;
	}

	.add-note-btn:hover {
		border-color: var(--accent);
	}

	.add-note-btn svg {
		width: 1rem;
		height: 1rem;
	}

	/* Note form: hairline-separated, not nested card */
	.note-form {
		border-top: 1px solid var(--rule-hairline);
		padding-top: var(--space-md);
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
	}

	.form-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.form-header h4 {
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--ink-primary);
		margin: 0;
	}

	.close-btn {
		background: none;
		border: none;
		min-width: 44px;
		min-height: 44px;
		display: flex;
		align-items: center;
		justify-content: center;
		cursor: pointer;
		color: var(--ink-muted);
	}

	.close-btn:hover {
		color: var(--ink-primary);
	}

	.close-btn svg {
		width: 1.25rem;
		height: 1.25rem;
	}

	.score-category {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
	}

	.category-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: var(--space-sm);
	}

	.category-label {
		font-size: var(--text-sm);
		font-weight: 700;
		color: var(--ink-secondary);
	}

	.score-selector {
		display: flex;
		gap: var(--space-2xs);
	}

	.score-btn {
		width: 44px;
		height: 44px;
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: var(--text-sm);
		font-weight: 500;
		color: var(--ink-secondary);
		cursor: pointer;
	}

	.score-btn:hover {
		border-color: var(--accent);
		color: var(--accent);
	}

	.score-btn.selected {
		background: var(--accent);
		border-color: var(--accent);
		color: var(--accent-ink);
	}

	.category-notes {
		width: 100%;
		padding: var(--space-xs) var(--space-sm);
		background: var(--bg-canvas);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		font-size: var(--text-sm);
		color: var(--ink-primary);
		resize: none;
		font-family: var(--font-body);
	}

	.category-notes:focus {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
		border-color: var(--accent);
	}

	.form-actions {
		display: flex;
		justify-content: flex-end;
		gap: var(--space-xs);
		padding-top: var(--space-sm);
		border-top: 1px solid var(--rule-hairline);
	}

	.cancel-btn,
	.save-btn {
		min-height: 44px;
		padding: 0 var(--space-md);
		border-radius: 4px;
		font-size: var(--text-sm);
		font-weight: 600;
		cursor: pointer;
	}

	.cancel-btn {
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		color: var(--ink-secondary);
	}

	.cancel-btn:hover {
		background: var(--bg-subtle);
		color: var(--ink-primary);
	}

	.save-btn {
		background: var(--accent);
		border: 1px solid var(--accent);
		color: var(--accent-ink);
	}

	.save-btn:hover {
		background: var(--accent-hover);
	}

	.save-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	/* Notes list: hairline ledger */
	.notes-list {
		display: flex;
		flex-direction: column;
	}

	.note-item {
		padding: var(--space-sm) 0;
		border-top: 1px solid var(--rule-hairline);
	}

	.note-item.editing {
		opacity: 0.5;
	}

	.note-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: var(--space-xs);
	}

	.note-date {
		font-family: var(--font-num);
		font-size: var(--text-xs);
		color: var(--ink-muted);
	}

	.note-actions {
		display: flex;
		gap: var(--space-2xs);
	}

	.action-btn {
		background: none;
		border: none;
		min-width: 44px;
		min-height: 44px;
		display: flex;
		align-items: center;
		justify-content: center;
		cursor: pointer;
		color: var(--ink-muted);
		border-radius: 4px;
	}

	.action-btn:hover {
		background: var(--bg-elevated);
		color: var(--ink-primary);
	}

	.action-btn.delete:hover {
		color: var(--negative);
	}

	.action-btn svg {
		width: 1rem;
		height: 1rem;
	}

	.note-scores {
		display: grid;
		grid-template-columns: repeat(5, 1fr);
		border: 1px solid var(--rule-hairline);
		border-radius: 4px;
		margin-bottom: var(--space-xs);
	}

	.score-item {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 2px;
		padding: var(--space-xs);
		min-width: 0;
	}

	.score-item + .score-item {
		border-left: 1px solid var(--rule-hairline);
	}

	.score-label {
		font-family: var(--font-display);
		font-size: 0.625rem;
		font-weight: 600;
		color: var(--ink-muted);
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}

	.score-value {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: var(--text-sm);
		color: var(--ink-primary);
	}

	.score-item.overall .score-value {
		color: var(--accent);
	}

	.note-text {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		line-height: 1.45;
		margin: 0;
	}

	.empty-message {
		text-align: center;
		color: var(--ink-muted);
		font-size: var(--text-sm);
		padding: var(--space-md);
		margin: 0;
	}
</style>
