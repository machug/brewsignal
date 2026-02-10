<script lang="ts">
	import type { TastingNote, ScoreCategory } from '$lib/types';
	import { SCORE_CATEGORIES, MAX_TOTAL_SCORE, BJCP_MAX_TOTAL, BJCP_CATEGORIES, getBJCPRating } from '$lib/types';
	import BatchCard from './BatchCard.svelte';

	interface Props {
		tastingNotes: TastingNote[];
		onAddTasting?: () => void;
		onViewDetails?: (note: TastingNote) => void;
	}

	let { tastingNotes, onAddTasting, onViewDetails }: Props = $props();
	let expandedNoteId = $state<number | null>(null);

	// Sort notes by date (newest first)
	let sortedNotes = $derived(
		[...tastingNotes].sort(
			(a, b) => new Date(b.tasted_at).getTime() - new Date(a.tasted_at).getTime()
		)
	);

	let hasNotes = $derived(tastingNotes.length > 0);

	function toggleExpanded(noteId: number): void {
		expandedNoteId = expandedNoteId === noteId ? null : noteId;
	}

	function formatDate(dateStr: string): string {
		return new Date(dateStr).toLocaleDateString('en-AU', {
			day: 'numeric',
			month: 'short',
			year: 'numeric'
		});
	}

	function getScoreColor(score: number | undefined): 'excellent' | 'good' | 'poor' | 'none' {
		if (score === undefined || score === null) return 'none';
		if (score > 20) return 'excellent';
		if (score >= 15) return 'good';
		return 'poor';
	}

	function getIndividualScoreColor(score: number | undefined): 'high' | 'medium' | 'low' | 'none' {
		if (score === undefined || score === null) return 'none';
		if (score >= 4) return 'high';
		if (score >= 3) return 'medium';
		return 'low';
	}

	function getScoreValue(note: TastingNote, category: ScoreCategory): number | undefined {
		const key = `${category}_score` as keyof TastingNote;
		return note[key] as number | undefined;
	}

	function getNoteValue(note: TastingNote, category: ScoreCategory): string | undefined {
		const key = `${category}_notes` as keyof TastingNote;
		return note[key] as string | undefined;
	}

	function getBJCPScoreColor(score: number | undefined): 'outstanding' | 'excellent' | 'verygood' | 'good' | 'fair' | 'none' {
		if (score === undefined || score === null) return 'none';
		if (score >= 45) return 'outstanding';
		if (score >= 38) return 'excellent';
		if (score >= 30) return 'verygood';
		if (score >= 21) return 'good';
		return 'fair';
	}

	function getBJCPCategoryTotal(note: TastingNote, category: string): number {
		if (category === 'aroma') return (note.aroma_malt || 0) + (note.aroma_hops || 0) + (note.aroma_fermentation || 0) + (note.aroma_other || 0);
		if (category === 'appearance') return (note.appearance_color || 0) + (note.appearance_clarity || 0) + (note.appearance_head || 0);
		if (category === 'flavor') return (note.flavor_malt || 0) + (note.flavor_hops || 0) + (note.flavor_bitterness || 0) + (note.flavor_fermentation || 0) + (note.flavor_balance || 0) + (note.flavor_finish || 0);
		if (category === 'mouthfeel') return (note.mouthfeel_body || 0) + (note.mouthfeel_carbonation || 0) + (note.mouthfeel_warmth || 0);
		if (category === 'overall') return note.overall_score || 0;
		return 0;
	}

	function hasAnyNotes(note: TastingNote): boolean {
		return (
			!!note.appearance_notes ||
			!!note.aroma_notes ||
			!!note.flavor_notes ||
			!!note.mouthfeel_notes ||
			!!note.overall_notes ||
			!!note.style_deviation_notes ||
			!!note.ai_suggestions
		);
	}
</script>

<BatchCard title="Tasting Notes" icon="&#127866;">
	<div class="tasting-content">
		<!-- Header with Add button -->
		<div class="tasting-header">
			<span class="notes-count">
				{tastingNotes.length}
				{tastingNotes.length === 1 ? 'tasting' : 'tastings'} recorded
			</span>
			{#if onAddTasting}
				<button type="button" class="add-btn" onclick={onAddTasting}>
					<svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M12 4v16m8-8H4"
						/>
					</svg>
					Add Tasting
				</button>
			{/if}
		</div>

		{#if hasNotes}
			<div class="notes-list">
				{#each sortedNotes as note (note.id)}
					{@const isExpanded = expandedNoteId === note.id}
					{@const scoreColor = note.scoring_version === 2 ? getBJCPScoreColor(note.total_score) : getScoreColor(note.total_score)}

					<div class="note-item" class:expanded={isExpanded}>
						<!-- Note Summary Row -->
						<button
							type="button"
							class="note-summary"
							onclick={() => toggleExpanded(note.id)}
							aria-expanded={isExpanded}
						>
							<div class="summary-left">
								<div class="date-info">
									<span class="tasting-date">{formatDate(note.tasted_at)}</span>
									{#if note.days_since_packaging !== undefined && note.days_since_packaging !== null}
										<span class="age-badge">{note.days_since_packaging} days aged</span>
									{/if}
								</div>

								<!-- Score badges row -->
								{#if note.scoring_version === 2}
									<div class="bjcp-scores">
										<div class="bjcp-category">
											<span class="category-label">Aroma</span>
											<span class="category-score">{getBJCPCategoryTotal(note, 'aroma')}/12</span>
										</div>
										<div class="bjcp-category">
											<span class="category-label">Appear</span>
											<span class="category-score">{getBJCPCategoryTotal(note, 'appearance')}/3</span>
										</div>
										<div class="bjcp-category">
											<span class="category-label">Flavor</span>
											<span class="category-score">{getBJCPCategoryTotal(note, 'flavor')}/20</span>
										</div>
										<div class="bjcp-category">
											<span class="category-label">Mouth</span>
											<span class="category-score">{getBJCPCategoryTotal(note, 'mouthfeel')}/5</span>
										</div>
										<div class="bjcp-category overall">
											<span class="category-label">Overall</span>
											<span class="category-score">{note.overall_score || 0}/10</span>
										</div>
									</div>
								{:else}
									<div class="score-badges">
										{#each Object.entries(SCORE_CATEGORIES) as [category, info]}
											{@const score = getScoreValue(note, category as ScoreCategory)}
											<span
												class="score-badge"
												class:score-high={getIndividualScoreColor(score) === 'high'}
												class:score-medium={getIndividualScoreColor(score) === 'medium'}
												class:score-low={getIndividualScoreColor(score) === 'low'}
												class:score-none={getIndividualScoreColor(score) === 'none'}
											>
												{info.abbrev}:{score ?? '-'}
											</span>
										{/each}
									</div>
								{/if}
							</div>

							<div class="summary-right">
								<!-- To style indicator -->
								{#if note.to_style !== undefined && note.to_style !== null}
									<span
										class="style-indicator"
										class:to-style={note.to_style}
										class:off-style={!note.to_style}
										title={note.to_style ? 'To style' : 'Off style'}
									>
										{#if note.to_style}
											<svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													stroke-width="2.5"
													d="M5 13l4 4L19 7"
												/>
											</svg>
										{:else}
											<svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													stroke-width="2.5"
													d="M6 18L18 6M6 6l12 12"
												/>
											</svg>
										{/if}
									</span>
								{/if}

								<!-- Total score -->
								{#if note.scoring_version === 2}
									<div class="bjcp-total" class:bjcp-outstanding={scoreColor === 'outstanding'} class:bjcp-excellent={scoreColor === 'excellent'} class:bjcp-verygood={scoreColor === 'verygood'} class:bjcp-good={scoreColor === 'good'} class:bjcp-fair={scoreColor === 'fair'}>
										<span class="total-score-value">{note.total_score || 0}</span>
										<span class="total-score-max">/{BJCP_MAX_TOTAL}</span>
										<span class="total-rating">{getBJCPRating(note.total_score || 0)}</span>
									</div>
								{:else}
									<div class="total-score" class:excellent={scoreColor === 'excellent'} class:good={scoreColor === 'good'} class:poor={scoreColor === 'poor'}>
										<span class="score-value">{note.total_score ?? '-'}</span>
										<span class="score-max">/{MAX_TOTAL_SCORE}</span>
									</div>
								{/if}

								<!-- Expand chevron -->
								<svg
									class="expand-chevron"
									class:rotated={isExpanded}
									fill="none"
									viewBox="0 0 24 24"
									stroke="currentColor"
								>
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										stroke-width="2"
										d="M19 9l-7 7-7-7"
									/>
								</svg>
							</div>
						</button>

						<!-- Expanded Details -->
						{#if isExpanded}
							<div class="note-details">
								<!-- Context info -->
								{#if note.serving_temp_c || note.glassware}
									<div class="context-row">
										{#if note.serving_temp_c}
											<span class="context-item">
												<span class="context-icon">&#127777;&#65039;</span>
												{note.serving_temp_c}&deg;C
											</span>
										{/if}
										{#if note.glassware}
											<span class="context-item">
												<span class="context-icon">&#127866;</span>
												{note.glassware}
											</span>
										{/if}
									</div>
								{/if}

								<!-- Score breakdown with notes -->
								{#if note.scoring_version === 2}
									<div class="scores-section">
										<h4 class="section-title">BJCP Scores</h4>
										<div class="bjcp-detail-grid">
											{#each BJCP_CATEGORIES as cat}
												{@const catTotal = getBJCPCategoryTotal(note, cat.key)}
												{@const catNotes = getNoteValue(note, cat.key as ScoreCategory)}
												<div class="bjcp-detail-item">
													<div class="bjcp-detail-header">
														<span class="bjcp-detail-name">{cat.name}</span>
														<span class="bjcp-detail-score">{catTotal}/{cat.maxScore}</span>
													</div>
													<div class="score-bar-container">
														<div
															class="score-bar bjcp-bar"
															style="width: {cat.maxScore > 0 ? (catTotal / cat.maxScore) * 100 : 0}%"
														></div>
													</div>
													{#if cat.subcategories.length > 0}
														<div class="bjcp-subcategories">
															{#each cat.subcategories as sub}
																{@const subVal = (note[sub.key as keyof TastingNote] as number) || 0}
																<span class="bjcp-sub-badge">
																	{sub.name}: {subVal}/{sub.maxScore}
																</span>
															{/each}
														</div>
													{/if}
													{#if catNotes}
														<p class="score-notes">{catNotes}</p>
													{/if}
												</div>
											{/each}
										</div>
									</div>
								{:else}
									<div class="scores-section">
										<h4 class="section-title">Scores</h4>
										<div class="scores-grid">
											{#each Object.entries(SCORE_CATEGORIES) as [category, info]}
												{@const score = getScoreValue(note, category as ScoreCategory)}
												{@const notes = getNoteValue(note, category as ScoreCategory)}
												<div class="score-item">
													<div class="score-header">
														<span class="score-name">{info.name}</span>
														<span
															class="score-display"
															class:score-high={getIndividualScoreColor(score) === 'high'}
															class:score-medium={getIndividualScoreColor(score) === 'medium'}
															class:score-low={getIndividualScoreColor(score) === 'low'}
														>
															{score ?? '-'}/{info.maxScore}
														</span>
													</div>
													<!-- Score bar visualization -->
													<div class="score-bar-container">
														<div
															class="score-bar"
															class:score-high={getIndividualScoreColor(score) === 'high'}
															class:score-medium={getIndividualScoreColor(score) === 'medium'}
															class:score-low={getIndividualScoreColor(score) === 'low'}
															style="width: {score ? (score / info.maxScore) * 100 : 0}%"
														></div>
													</div>
													{#if notes}
														<p class="score-notes">{notes}</p>
													{/if}
												</div>
											{/each}
										</div>
									</div>
								{/if}

								<!-- Style conformance section -->
								{#if note.to_style !== undefined || note.style_deviation_notes}
									<div class="style-section">
										<h4 class="section-title">Style Conformance</h4>
										<div class="style-content">
											{#if note.to_style !== undefined && note.to_style !== null}
												<span
													class="style-badge"
													class:to-style={note.to_style}
													class:off-style={!note.to_style}
												>
													{note.to_style ? 'To Style' : 'Off Style'}
												</span>
											{/if}
											{#if note.style_deviation_notes}
												<p class="style-notes">{note.style_deviation_notes}</p>
											{/if}
										</div>
									</div>
								{/if}

								<!-- AI Suggestions -->
								{#if note.ai_suggestions}
									<div class="ai-section">
										<div class="ai-header">
											<span class="ai-badge">AI Suggestions</span>
										</div>
										<p class="ai-content">{note.ai_suggestions}</p>
									</div>
								{/if}

								<!-- View details button -->
								{#if onViewDetails}
									<button
										type="button"
										class="view-details-btn"
										onclick={() => onViewDetails(note)}
									>
										View Full Details
									</button>
								{/if}
							</div>
						{/if}
					</div>
				{/each}
			</div>
		{:else}
			<!-- Empty state -->
			<div class="empty-state">
				<div class="empty-icon">&#127866;</div>
				<p class="empty-text">No tasting notes yet</p>
				<p class="empty-subtext">Record your first tasting to track how your beer develops over time.</p>
				{#if onAddTasting}
					<button type="button" class="empty-add-btn" onclick={onAddTasting}>
						<svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M12 4v16m8-8H4"
							/>
						</svg>
						Add First Tasting
					</button>
				{/if}
			</div>
		{/if}
	</div>
</BatchCard>

<style>
	.tasting-content {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	/* Header */
	.tasting-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.notes-count {
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	.add-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		padding: 0.5rem 0.75rem;
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--primary);
		background: transparent;
		border: 1px solid var(--primary);
		border-radius: 0.375rem;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.add-btn:hover {
		background: var(--primary);
		color: white;
	}

	.add-btn svg {
		width: 0.875rem;
		height: 0.875rem;
	}

	/* Notes list */
	.notes-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	/* Note item */
	.note-item {
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
		border-radius: 0.5rem;
		overflow: hidden;
		transition: border-color 0.15s ease;
	}

	.note-item:hover {
		border-color: var(--border-default);
	}

	.note-item.expanded {
		border-color: var(--primary);
	}

	/* Note summary */
	.note-summary {
		display: flex;
		justify-content: space-between;
		align-items: center;
		width: 100%;
		padding: 0.75rem;
		background: transparent;
		border: none;
		cursor: pointer;
		text-align: left;
	}

	.summary-left {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.date-info {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		flex-wrap: wrap;
	}

	.tasting-date {
		font-size: 0.875rem;
		font-weight: 500;
		color: var(--text-primary);
	}

	.age-badge {
		font-size: 0.6875rem;
		font-weight: 500;
		color: var(--text-muted);
		background: var(--bg-surface);
		padding: 0.125rem 0.5rem;
		border-radius: 9999px;
	}

	/* Legacy score badges */
	.score-badges {
		display: flex;
		gap: 0.25rem;
		flex-wrap: wrap;
	}

	.score-badge {
		font-family: var(--font-mono);
		font-size: 0.625rem;
		font-weight: 600;
		padding: 0.125rem 0.375rem;
		border-radius: 0.25rem;
		background: var(--bg-surface);
		color: var(--text-muted);
	}

	.score-badge.score-high {
		background: rgba(34, 197, 94, 0.15);
		color: var(--positive);
	}

	.score-badge.score-medium {
		background: rgba(245, 158, 11, 0.15);
		color: var(--recipe-accent);
	}

	.score-badge.score-low {
		background: rgba(239, 68, 68, 0.15);
		color: var(--negative);
	}

	/* BJCP summary scores (compact badges in summary row) */
	.bjcp-scores {
		display: flex;
		gap: 0.25rem;
		flex-wrap: wrap;
	}

	.bjcp-category {
		display: flex;
		flex-direction: column;
		align-items: center;
		padding: 0.125rem 0.375rem;
		border-radius: 0.25rem;
		background: var(--bg-surface);
		min-width: 2.5rem;
	}

	.bjcp-category.overall {
		background: rgba(99, 102, 241, 0.12);
	}

	.category-label {
		font-size: 0.5625rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.03em;
		line-height: 1;
	}

	.bjcp-category.overall .category-label {
		color: var(--accent);
	}

	.category-score {
		font-family: var(--font-mono);
		font-size: 0.625rem;
		font-weight: 700;
		color: var(--text-primary);
		line-height: 1.2;
	}

	.bjcp-category.overall .category-score {
		color: var(--accent);
	}

	/* BJCP total score (in summary-right) */
	.bjcp-total {
		display: flex;
		align-items: baseline;
		gap: 0.125rem;
		padding: 0.25rem 0.5rem;
		border-radius: 0.375rem;
		background: var(--bg-surface);
	}

	.bjcp-total.bjcp-outstanding {
		background: rgba(234, 179, 8, 0.15);
	}

	.bjcp-total.bjcp-excellent {
		background: rgba(34, 197, 94, 0.15);
	}

	.bjcp-total.bjcp-verygood {
		background: rgba(59, 130, 246, 0.15);
	}

	.bjcp-total.bjcp-good {
		background: rgba(245, 158, 11, 0.15);
	}

	.bjcp-total.bjcp-fair {
		background: rgba(239, 68, 68, 0.15);
	}

	.total-score-value {
		font-family: var(--font-mono);
		font-size: 1rem;
		font-weight: 700;
		color: var(--text-primary);
	}

	.bjcp-total.bjcp-outstanding .total-score-value {
		color: rgb(202, 138, 4);
	}

	.bjcp-total.bjcp-excellent .total-score-value {
		color: var(--positive);
	}

	.bjcp-total.bjcp-verygood .total-score-value {
		color: rgb(59, 130, 246);
	}

	.bjcp-total.bjcp-good .total-score-value {
		color: var(--recipe-accent);
	}

	.bjcp-total.bjcp-fair .total-score-value {
		color: var(--negative);
	}

	.total-score-max {
		font-family: var(--font-mono);
		font-size: 0.6875rem;
		color: var(--text-muted);
	}

	.total-rating {
		font-size: 0.625rem;
		font-weight: 600;
		color: var(--text-secondary);
		margin-left: 0.25rem;
	}

	.bjcp-total.bjcp-outstanding .total-rating {
		color: rgb(202, 138, 4);
	}

	.bjcp-total.bjcp-excellent .total-rating {
		color: var(--positive);
	}

	.bjcp-total.bjcp-verygood .total-rating {
		color: rgb(59, 130, 246);
	}

	.bjcp-total.bjcp-good .total-rating {
		color: var(--recipe-accent);
	}

	.bjcp-total.bjcp-fair .total-rating {
		color: var(--negative);
	}

	.summary-right {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}

	/* Style indicator */
	.style-indicator {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 1.25rem;
		height: 1.25rem;
		border-radius: 50%;
	}

	.style-indicator svg {
		width: 0.75rem;
		height: 0.75rem;
	}

	.style-indicator.to-style {
		background: rgba(34, 197, 94, 0.15);
		color: var(--positive);
	}

	.style-indicator.off-style {
		background: rgba(239, 68, 68, 0.15);
		color: var(--negative);
	}

	/* Legacy total score */
	.total-score {
		display: flex;
		align-items: baseline;
		gap: 0.125rem;
		padding: 0.25rem 0.5rem;
		border-radius: 0.375rem;
		background: var(--bg-surface);
	}

	.total-score.excellent {
		background: rgba(34, 197, 94, 0.15);
	}

	.total-score.good {
		background: rgba(245, 158, 11, 0.15);
	}

	.total-score.poor {
		background: rgba(239, 68, 68, 0.15);
	}

	.score-value {
		font-family: var(--font-mono);
		font-size: 1rem;
		font-weight: 700;
		color: var(--text-primary);
	}

	.total-score.excellent .score-value {
		color: var(--positive);
	}

	.total-score.good .score-value {
		color: var(--recipe-accent);
	}

	.total-score.poor .score-value {
		color: var(--negative);
	}

	.score-max {
		font-family: var(--font-mono);
		font-size: 0.6875rem;
		color: var(--text-muted);
	}

	/* Expand chevron */
	.expand-chevron {
		width: 1rem;
		height: 1rem;
		color: var(--text-muted);
		transition: transform 0.2s ease;
	}

	.expand-chevron.rotated {
		transform: rotate(180deg);
	}

	/* Note details */
	.note-details {
		padding: 0 0.75rem 0.75rem;
		border-top: 1px solid var(--border-subtle);
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	/* Context row */
	.context-row {
		display: flex;
		gap: 1rem;
		padding-top: 0.75rem;
	}

	.context-item {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		font-size: 0.75rem;
		color: var(--text-secondary);
	}

	.context-icon {
		font-size: 0.875rem;
	}

	/* Sections */
	.section-title {
		font-size: 0.6875rem;
		font-weight: 600;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin: 0 0 0.5rem 0;
	}

	/* Legacy scores section */
	.scores-section {
		padding-top: 0.5rem;
	}

	.scores-grid {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.score-item {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.score-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.score-name {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-secondary);
	}

	.score-display {
		font-family: var(--font-mono);
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--text-muted);
	}

	.score-display.score-high {
		color: var(--positive);
	}

	.score-display.score-medium {
		color: var(--recipe-accent);
	}

	.score-display.score-low {
		color: var(--negative);
	}

	/* Score bar */
	.score-bar-container {
		height: 4px;
		background: var(--bg-surface);
		border-radius: 2px;
		overflow: hidden;
	}

	.score-bar {
		height: 100%;
		border-radius: 2px;
		background: var(--text-muted);
		transition: width 0.3s ease;
	}

	.score-bar.score-high {
		background: var(--positive);
	}

	.score-bar.score-medium {
		background: var(--recipe-accent);
	}

	.score-bar.score-low {
		background: var(--negative);
	}

	.score-bar.bjcp-bar {
		background: var(--accent);
	}

	.score-notes {
		font-size: 0.75rem;
		color: var(--text-secondary);
		line-height: 1.4;
		margin: 0.25rem 0 0 0;
		padding-left: 0.5rem;
		border-left: 2px solid var(--border-subtle);
	}

	/* BJCP expanded detail grid */
	.bjcp-detail-grid {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.bjcp-detail-item {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.bjcp-detail-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.bjcp-detail-name {
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--text-secondary);
	}

	.bjcp-detail-score {
		font-family: var(--font-mono);
		font-size: 0.75rem;
		font-weight: 700;
		color: var(--accent);
	}

	.bjcp-subcategories {
		display: flex;
		gap: 0.25rem;
		flex-wrap: wrap;
		margin-top: 0.125rem;
	}

	.bjcp-sub-badge {
		font-family: var(--font-mono);
		font-size: 0.5625rem;
		font-weight: 500;
		padding: 0.0625rem 0.25rem;
		border-radius: 0.1875rem;
		background: var(--bg-surface);
		color: var(--text-muted);
	}

	/* Style section */
	.style-section {
		padding-top: 0.5rem;
	}

	.style-content {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.style-badge {
		display: inline-flex;
		align-items: center;
		padding: 0.25rem 0.625rem;
		font-size: 0.6875rem;
		font-weight: 600;
		border-radius: 9999px;
		width: fit-content;
	}

	.style-badge.to-style {
		background: rgba(34, 197, 94, 0.15);
		color: var(--positive);
	}

	.style-badge.off-style {
		background: rgba(239, 68, 68, 0.15);
		color: var(--negative);
	}

	.style-notes {
		font-size: 0.75rem;
		color: var(--text-secondary);
		line-height: 1.4;
		margin: 0;
	}

	/* AI section */
	.ai-section {
		padding: 0.75rem;
		background: linear-gradient(
			135deg,
			rgba(99, 102, 241, 0.08) 0%,
			rgba(139, 92, 246, 0.05) 100%
		);
		border: 1px solid rgba(99, 102, 241, 0.2);
		border-radius: 0.5rem;
	}

	.ai-header {
		margin-bottom: 0.5rem;
	}

	.ai-badge {
		font-size: 0.6875rem;
		font-weight: 600;
		color: var(--accent);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.ai-content {
		font-size: 0.75rem;
		color: var(--text-secondary);
		line-height: 1.5;
		margin: 0;
		white-space: pre-wrap;
	}

	/* View details button */
	.view-details-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		padding: 0.5rem 1rem;
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-secondary);
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.375rem;
		cursor: pointer;
		transition: all 0.15s ease;
		align-self: flex-start;
	}

	.view-details-btn:hover {
		color: var(--text-primary);
		border-color: var(--border-default);
	}

	/* Empty state */
	.empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 2rem 1rem;
		text-align: center;
	}

	.empty-icon {
		font-size: 2.5rem;
		margin-bottom: 0.75rem;
		opacity: 0.5;
	}

	.empty-text {
		font-size: 0.9375rem;
		font-weight: 500;
		color: var(--text-secondary);
		margin: 0 0 0.25rem 0;
	}

	.empty-subtext {
		font-size: 0.8125rem;
		color: var(--text-muted);
		margin: 0 0 1rem 0;
		max-width: 280px;
	}

	.empty-add-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.625rem 1rem;
		font-size: 0.8125rem;
		font-weight: 500;
		color: white;
		background: var(--primary);
		border: none;
		border-radius: 0.5rem;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.empty-add-btn:hover {
		background: var(--primary-hover);
	}

	.empty-add-btn svg {
		width: 1rem;
		height: 1rem;
	}

	/* Responsive */
	@media (max-width: 480px) {
		.tasting-header {
			flex-direction: column;
			align-items: flex-start;
			gap: 0.5rem;
		}

		.summary-right {
			gap: 0.5rem;
		}

		.total-score {
			padding: 0.25rem 0.375rem;
		}

		.bjcp-total {
			padding: 0.25rem 0.375rem;
		}

		.score-value {
			font-size: 0.875rem;
		}

		.total-score-value {
			font-size: 0.875rem;
		}

		.total-rating {
			display: none;
		}
	}
</style>
