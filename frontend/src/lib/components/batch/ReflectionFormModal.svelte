<script lang="ts">
	import { createBatchReflection, type BatchReflectionCreate } from '$lib/api';
	import type { ReflectionPhase } from '$lib/types/reflection';
	import { PHASE_INFO } from '$lib/types/reflection';

	interface Props {
		open: boolean;
		batchId: number;
		existingPhases: ReflectionPhase[];
		defaultPhase?: ReflectionPhase;
		onClose: () => void;
		onSaved: () => void;
	}

	let { open, batchId, existingPhases, defaultPhase, onClose, onSaved }: Props = $props();

	const ALL_PHASES: ReflectionPhase[] = ['brew_day', 'fermentation', 'packaging', 'conditioning'];

	let phase = $state<ReflectionPhase>(defaultPhase ?? 'brew_day');
	let whatWentWell = $state('');
	let whatWentWrong = $state('');
	let lessonsLearned = $state('');
	let nextTimeChanges = $state('');
	let saving = $state(false);
	let error = $state<string | null>(null);

	// Track click-outside without triggering on selection drags.
	let pointerDownOnOverlay = $state(false);

	let availablePhases = $derived(
		ALL_PHASES.filter((p) => !existingPhases.includes(p) || p === phase)
	);

	$effect(() => {
		if (open) {
			// Reset form state when opening. Pick first available phase if
			// the default is already taken.
			const taken = existingPhases.includes(phase);
			if (taken) {
				const first = ALL_PHASES.find((p) => !existingPhases.includes(p));
				if (first) phase = first;
			}
			whatWentWell = '';
			whatWentWrong = '';
			lessonsLearned = '';
			nextTimeChanges = '';
			error = null;
			saving = false;
		}
	});

	function handleOverlayPointerDown(e: PointerEvent) {
		pointerDownOnOverlay = e.target === e.currentTarget;
	}

	function handleOverlayClick(e: MouseEvent) {
		if (pointerDownOnOverlay && e.target === e.currentTarget) {
			handleClose();
		}
		pointerDownOnOverlay = false;
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') handleClose();
	}

	function handleClose() {
		if (saving) return;
		onClose();
	}

	async function handleSave() {
		if (saving) return;

		const trimmedWell = whatWentWell.trim();
		const trimmedWrong = whatWentWrong.trim();
		const trimmedLessons = lessonsLearned.trim();
		const trimmedNext = nextTimeChanges.trim();

		if (!trimmedWell && !trimmedWrong && !trimmedLessons && !trimmedNext) {
			error = 'Add at least one reflection note before saving.';
			return;
		}

		saving = true;
		error = null;

		const payload: BatchReflectionCreate = {
			phase,
			what_went_well: trimmedWell || undefined,
			what_went_wrong: trimmedWrong || undefined,
			lessons_learned: trimmedLessons || undefined,
			next_time_changes: trimmedNext || undefined
		};

		try {
			await createBatchReflection(batchId, payload);
			onSaved();
			onClose();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to save reflection';
		} finally {
			saving = false;
		}
	}
</script>

{#if open}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="modal-overlay"
		onpointerdown={handleOverlayPointerDown}
		onclick={handleOverlayClick}
		onkeydown={handleKeydown}
		role="presentation"
	>
		<div
			class="modal-content"
			role="dialog"
			aria-modal="true"
			aria-labelledby="reflection-modal-title"
			tabindex="-1"
			onkeydown={(e) => e.stopPropagation()}
		>
			<div class="modal-header">
				<h2 id="reflection-modal-title">Add Reflection</h2>
				<button class="modal-close" onclick={handleClose} aria-label="Close">&times;</button>
			</div>

			<div class="modal-body">
				<div class="form-row">
					<label class="form-label" for="reflection-phase">Phase</label>
					<select
						id="reflection-phase"
						class="form-select"
						bind:value={phase}
						disabled={saving}
					>
						{#each availablePhases as p}
							<option value={p}>{PHASE_INFO[p].icon} {PHASE_INFO[p].name}</option>
						{/each}
					</select>
				</div>

				<div class="form-row">
					<label class="form-label" for="reflection-well">What went well?</label>
					<textarea
						id="reflection-well"
						class="form-textarea"
						bind:value={whatWentWell}
						placeholder="Wins, things you nailed, what to repeat..."
						rows="3"
						disabled={saving}
					></textarea>
				</div>

				<div class="form-row">
					<label class="form-label" for="reflection-wrong">What went wrong?</label>
					<textarea
						id="reflection-wrong"
						class="form-textarea"
						bind:value={whatWentWrong}
						placeholder="Mistakes, surprises, off-target results..."
						rows="3"
						disabled={saving}
					></textarea>
				</div>

				<div class="form-row">
					<label class="form-label" for="reflection-lessons">Lessons learned</label>
					<textarea
						id="reflection-lessons"
						class="form-textarea"
						bind:value={lessonsLearned}
						placeholder="Key takeaways from this brew..."
						rows="3"
						disabled={saving}
					></textarea>
				</div>

				<div class="form-row">
					<label class="form-label" for="reflection-next">Next time, change...</label>
					<textarea
						id="reflection-next"
						class="form-textarea"
						bind:value={nextTimeChanges}
						placeholder="Process tweaks, recipe adjustments, gear changes..."
						rows="3"
						disabled={saving}
					></textarea>
				</div>

				{#if error}
					<div class="form-error">{error}</div>
				{/if}
			</div>

			<div class="modal-footer">
				<button
					type="button"
					class="btn-secondary"
					onclick={handleClose}
					disabled={saving}
				>Cancel</button>
				<button
					type="button"
					class="btn-primary"
					onclick={handleSave}
					disabled={saving}
				>
					{#if saving}
						<span class="btn-spinner"></span>
						Saving...
					{:else}
						Save Reflection
					{/if}
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.modal-overlay {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.7);
		backdrop-filter: blur(4px);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
		padding: var(--space-4);
	}

	.modal-content {
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 12px;
		max-width: 600px;
		width: 100%;
		max-height: 90vh;
		display: flex;
		flex-direction: column;
		box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
	}

	.modal-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: var(--space-4) var(--space-5);
		border-bottom: 1px solid var(--border-subtle);
	}

	.modal-header h2 {
		margin: 0;
		font-size: 18px;
		font-weight: 600;
		color: var(--text-primary);
	}

	.modal-close {
		background: none;
		border: none;
		font-size: 24px;
		color: var(--text-secondary);
		cursor: pointer;
		padding: 0;
		line-height: 1;
	}

	.modal-close:hover {
		color: var(--text-primary);
	}

	.modal-body {
		padding: var(--space-5);
		overflow-y: auto;
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}

	.modal-footer {
		display: flex;
		justify-content: flex-end;
		gap: var(--space-2);
		padding: var(--space-3) var(--space-5);
		border-top: 1px solid var(--border-subtle);
	}

	.form-row {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}

	.form-label {
		font-size: 13px;
		font-weight: 500;
		color: var(--text-primary);
	}

	.form-select,
	.form-textarea {
		width: 100%;
		padding: var(--space-2) var(--space-3);
		background: var(--bg-elevated);
		border: 1px solid var(--border-default);
		border-radius: 8px;
		color: var(--text-primary);
		font-size: 14px;
		font-family: inherit;
		resize: vertical;
	}

	.form-select:focus,
	.form-textarea:focus {
		outline: none;
		border-color: var(--accent-primary, #3b82f6);
	}

	.form-select:disabled,
	.form-textarea:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.form-textarea {
		min-height: 70px;
		line-height: 1.5;
	}

	.form-error {
		padding: var(--space-3);
		background: var(--negative-bg, rgba(239, 68, 68, 0.1));
		border: 1px solid var(--negative);
		border-radius: 8px;
		color: var(--negative);
		font-size: 13px;
	}

	.btn-primary,
	.btn-secondary {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		padding: 9px 16px;
		font-size: 13px;
		font-weight: 500;
		border-radius: 8px;
		cursor: pointer;
		transition: all 0.2s ease;
	}

	.btn-primary {
		background: var(--accent-primary, #3b82f6);
		border: 1px solid var(--accent-primary, #3b82f6);
		color: white;
	}

	.btn-primary:hover:not(:disabled) {
		filter: brightness(1.1);
	}

	.btn-secondary {
		background: transparent;
		border: 1px solid var(--border-default);
		color: var(--text-primary);
	}

	.btn-secondary:hover:not(:disabled) {
		background: var(--bg-hover);
	}

	.btn-primary:disabled,
	.btn-secondary:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.btn-spinner {
		width: 14px;
		height: 14px;
		border: 2px solid currentColor;
		border-top-color: transparent;
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
</style>
