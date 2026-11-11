<script lang="ts">
	import type { TastingNote, ScoreCategory } from '$lib/types';
	import { SCORE_CATEGORIES, MAX_TOTAL_SCORE, BJCP_MAX_TOTAL, BJCP_CATEGORIES, getBJCPRating } from '$lib/types';

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

<div class="tasting-content">
		<!-- Header with Add button -->
		<div class="tasting-header">
			<span class="notes-count">
				<span class="num">{tastingNotes.length}</span>
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
										<span class="age-badge"><span class="num">{note.days_since_packaging}</span> days aged</span>
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
												<span class="context-label">Serve</span>
												<span class="num">{note.serving_temp_c}&thinsp;&deg;C</span>
											</span>
										{/if}
										{#if note.glassware}
											<span class="context-item">
												<span class="context-label">Glass</span>
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

<style>
	.num {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums lining-nums;
	}

	.tasting-content {
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
	}

	.tasting-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: var(--space-sm);
	}

	.notes-count {
		font-size: var(--text-xs);
		color: var(--ink-muted);
	}

	.add-btn,
	.empty-add-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: var(--space-xs);
		min-height: 44px;
		padding: 0 var(--space-md);
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--accent);
		background: var(--accent-tint);
		border: 1px solid var(--accent-rule);
		border-radius: 4px;
		cursor: pointer;
	}

	.add-btn:hover,
	.empty-add-btn:hover {
		border-color: var(--accent);
	}

	button:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.add-btn svg,
	.empty-add-btn svg {
		width: 0.875rem;
		height: 0.875rem;
	}

	/* Notes ledger */
	.notes-list {
		display: flex;
		flex-direction: column;
		border-bottom: 1px solid var(--rule-hairline);
	}

	.note-item {
		border-top: 1px solid var(--rule-hairline);
	}

	.note-item.expanded {
		background: var(--bg-elevated);
	}

	.note-summary {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: var(--space-sm);
		width: 100%;
		min-height: 48px;
		padding: var(--space-sm) var(--space-xs);
		background: transparent;
		border: none;
		cursor: pointer;
		text-align: left;
	}

	.note-summary:hover {
		background: var(--bg-elevated);
	}

	.note-summary:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: -2px;
	}

	.summary-left {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
		min-width: 0;
	}

	.date-info {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
		flex-wrap: wrap;
	}

	.tasting-date {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: var(--text-sm);
		font-weight: 500;
		color: var(--ink-primary);
	}

	.age-badge {
		font-family: var(--font-display);
		font-size: 0.6875rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--ink-secondary);
		border: 1px solid var(--rule-strong);
		padding: 1px 7px;
		border-radius: 2px;
	}

	/* Legacy 1-5 score cells */
	.score-badges,
	.bjcp-scores {
		display: flex;
		flex-wrap: wrap;
		border: 1px solid var(--rule-hairline);
		border-radius: 4px;
		width: fit-content;
		max-width: 100%;
	}

	.score-badge {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: 0.6875rem;
		font-weight: 600;
		padding: 2px var(--space-xs);
		color: var(--ink-muted);
	}

	.score-badge + .score-badge {
		border-left: 1px solid var(--rule-hairline);
	}

	.score-badge.score-high { color: var(--positive); }
	.score-badge.score-medium { color: var(--warning); }
	.score-badge.score-low { color: var(--negative); }

	/* BJCP summary cells */
	.bjcp-category {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 2px;
		padding: 3px var(--space-xs);
		min-width: 2.75rem;
	}

	.bjcp-category + .bjcp-category {
		border-left: 1px solid var(--rule-hairline);
	}

	.category-label {
		font-family: var(--font-display);
		font-size: 0.5625rem;
		font-weight: 600;
		color: var(--ink-muted);
		text-transform: uppercase;
		letter-spacing: 0.06em;
		line-height: 1;
	}

	.bjcp-category.overall .category-label,
	.bjcp-category.overall .category-score {
		color: var(--accent);
	}

	.category-score {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: 0.6875rem;
		font-weight: 600;
		color: var(--ink-primary);
		line-height: 1.2;
	}

	/* Totals: outlined readout, tone by rating */
	.bjcp-total,
	.total-score {
		display: flex;
		align-items: baseline;
		gap: 2px;
		padding: 3px var(--space-xs);
		border-radius: 4px;
		border: 1px solid var(--rule-strong);
	}

	.bjcp-total.bjcp-outstanding,
	.bjcp-total.bjcp-excellent,
	.total-score.excellent {
		border-color: var(--status-steady);
	}
	.bjcp-total.bjcp-verygood {
		border-color: var(--temp-trace);
	}
	.bjcp-total.bjcp-good,
	.total-score.good {
		border-color: var(--status-warn);
	}
	.bjcp-total.bjcp-fair,
	.total-score.poor {
		border-color: var(--status-danger);
	}

	.total-score-value,
	.score-value {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: var(--text-base);
		font-weight: 600;
		color: var(--ink-primary);
	}

	.bjcp-total.bjcp-outstanding .total-score-value,
	.bjcp-total.bjcp-excellent .total-score-value,
	.total-score.excellent .score-value,
	.bjcp-total.bjcp-outstanding .total-rating,
	.bjcp-total.bjcp-excellent .total-rating {
		color: var(--positive);
	}
	.bjcp-total.bjcp-verygood .total-score-value,
	.bjcp-total.bjcp-verygood .total-rating {
		color: var(--temp-trace);
	}
	.bjcp-total.bjcp-good .total-score-value,
	.total-score.good .score-value,
	.bjcp-total.bjcp-good .total-rating {
		color: var(--warning);
	}
	.bjcp-total.bjcp-fair .total-score-value,
	.total-score.poor .score-value,
	.bjcp-total.bjcp-fair .total-rating {
		color: var(--negative);
	}

	.total-score-max,
	.score-max {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: 0.6875rem;
		color: var(--ink-muted);
	}

	.total-rating {
		font-family: var(--font-display);
		font-size: 0.625rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--ink-secondary);
		margin-left: var(--space-2xs);
	}

	.summary-right {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		flex-shrink: 0;
	}

	.style-indicator {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 1.25rem;
		height: 1.25rem;
		border-radius: 50%;
		border: 1px solid currentColor;
	}

	.style-indicator svg {
		width: 0.75rem;
		height: 0.75rem;
	}

	.style-indicator.to-style { color: var(--positive); }
	.style-indicator.off-style { color: var(--negative); }

	.expand-chevron {
		width: 1rem;
		height: 1rem;
		color: var(--ink-muted);
		transition: transform 0.2s var(--ease-out-quart);
	}

	.expand-chevron.rotated {
		transform: rotate(180deg);
	}

	/* Details */
	.note-details {
		padding: 0 var(--space-xs) var(--space-md);
		border-top: 1px solid var(--rule-hairline);
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
	}

	.context-row {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-md);
		padding-top: var(--space-sm);
	}

	.context-item {
		display: flex;
		align-items: baseline;
		gap: var(--space-xs);
		font-size: var(--text-xs);
		color: var(--ink-secondary);
	}

	.context-label {
		font-family: var(--font-display);
		font-size: 0.6875rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--ink-muted);
	}

	.section-title {
		font-family: var(--font-display);
		font-size: 0.6875rem;
		font-weight: 600;
		color: var(--ink-muted);
		text-transform: uppercase;
		letter-spacing: 0.08em;
		margin: 0 0 var(--space-xs) 0;
	}

	.scores-section,
	.style-section {
		padding-top: var(--space-xs);
	}

	.scores-grid,
	.bjcp-detail-grid {
		display: flex;
		flex-direction: column;
		gap: var(--space-sm);
	}

	.score-item,
	.bjcp-detail-item {
		display: flex;
		flex-direction: column;
		gap: var(--space-2xs);
	}

	.score-header,
	.bjcp-detail-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.score-name,
	.bjcp-detail-name {
		font-size: var(--text-xs);
		font-weight: 700;
		color: var(--ink-secondary);
	}

	.score-display,
	.bjcp-detail-score {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-muted);
	}

	.bjcp-detail-score { color: var(--accent); }
	.score-display.score-high { color: var(--positive); }
	.score-display.score-medium { color: var(--warning); }
	.score-display.score-low { color: var(--negative); }

	.score-bar-container {
		height: 4px;
		background: var(--bg-subtle);
		border-radius: 2px;
		overflow: hidden;
	}

	.score-bar {
		height: 100%;
		border-radius: 2px;
		background: var(--ink-muted);
		transition: width 0.3s var(--ease-out-quart);
	}

	.score-bar.score-high { background: var(--positive); }
	.score-bar.score-medium { background: var(--warning); }
	.score-bar.score-low { background: var(--negative); }
	.score-bar.bjcp-bar { background: var(--accent); }

	.score-notes {
		font-size: var(--text-xs);
		color: var(--ink-secondary);
		line-height: 1.45;
		margin: var(--space-2xs) 0 0 0;
	}

	.bjcp-subcategories {
		display: flex;
		gap: var(--space-2xs);
		flex-wrap: wrap;
	}

	.bjcp-sub-badge {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: 0.625rem;
		padding: 1px 5px;
		border: 1px solid var(--rule-hairline);
		border-radius: 2px;
		color: var(--ink-muted);
	}

	.style-content {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
	}

	.style-badge {
		display: inline-flex;
		align-items: center;
		padding: 2px 7px;
		font-family: var(--font-display);
		font-size: 0.6875rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		border: 1px solid currentColor;
		border-radius: 2px;
		width: fit-content;
	}

	.style-badge.to-style { color: var(--positive); }
	.style-badge.off-style { color: var(--negative); }

	.style-notes {
		font-size: var(--text-xs);
		color: var(--ink-secondary);
		line-height: 1.45;
		margin: 0;
	}

	.ai-section {
		padding-top: var(--space-sm);
		border-top: 1px solid var(--rule-hairline);
	}

	.ai-header {
		margin-bottom: var(--space-xs);
	}

	.ai-badge {
		font-family: var(--font-display);
		font-size: 0.6875rem;
		font-weight: 600;
		color: var(--ink-muted);
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}

	.ai-content {
		font-size: var(--text-xs);
		color: var(--ink-secondary);
		line-height: 1.5;
		margin: 0;
		white-space: pre-wrap;
	}

	.view-details-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-height: 44px;
		padding: 0 var(--space-md);
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-secondary);
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		cursor: pointer;
		align-self: flex-start;
	}

	.view-details-btn:hover {
		color: var(--ink-primary);
		background: var(--bg-subtle);
	}

	.empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: var(--space-xl) var(--space-md);
		text-align: center;
	}

	.empty-text {
		font-size: var(--text-base);
		font-weight: 700;
		color: var(--ink-secondary);
		margin: 0 0 var(--space-2xs) 0;
	}

	.empty-subtext {
		font-size: var(--text-sm);
		color: var(--ink-muted);
		margin: 0 0 var(--space-md) 0;
		max-width: 280px;
	}

	.empty-add-btn {
		color: var(--accent-ink);
		background: var(--accent);
		border-color: var(--accent);
	}

	.empty-add-btn:hover {
		background: var(--accent-hover);
		border-color: var(--accent-hover);
	}

	@media (max-width: 480px) {
		.tasting-header {
			flex-direction: column;
			align-items: flex-start;
		}

		.summary-right {
			gap: var(--space-xs);
		}

		.total-rating {
			display: none;
		}
	}
</style>
