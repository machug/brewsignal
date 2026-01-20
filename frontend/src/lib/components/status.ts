import type { BatchStatus } from '$lib/api';

/**
 * Centralized status configuration - single source of truth for status colors and labels
 */
export const statusConfig: Record<BatchStatus, { label: string; color: string; bg: string }> = {
	planning: { label: 'Planning', color: 'var(--status-planning)', bg: 'var(--bg-elevated)' },
	fermenting: { label: 'Fermenting', color: 'var(--status-fermenting)', bg: 'var(--recipe-accent-muted)' },
	conditioning: { label: 'Conditioning', color: 'var(--status-conditioning)', bg: 'rgba(167, 139, 250, 0.15)' },
	completed: { label: 'Completed', color: 'var(--status-completed)', bg: 'var(--positive-muted)' },
	archived: { label: 'Archived', color: 'var(--status-archived)', bg: 'var(--bg-elevated)' }
};
