import type { BatchStatus } from '$lib/api';

/**
 * Centralized status configuration - single source of truth for status colors and labels
 */
export const statusConfig: Record<BatchStatus, { label: string; color: string; bg: string }> = {
	planning: { label: 'Planning', color: 'var(--status-planning)', bg: 'var(--bg-elevated)' },
	brewing: { label: 'Brew Day', color: 'var(--status-brewing)', bg: 'color-mix(in oklch, var(--status-brewing) 14%, transparent)' },
	fermenting: { label: 'Fermenting', color: 'var(--status-fermenting)', bg: 'var(--recipe-accent-muted)' },
	conditioning: { label: 'Conditioning', color: 'var(--status-conditioning)', bg: 'color-mix(in oklch, var(--status-conditioning) 14%, transparent)' },
	completed: { label: 'Completed', color: 'var(--status-completed)', bg: 'var(--positive-muted)' },
	archived: { label: 'Archived', color: 'var(--status-archived)', bg: 'var(--bg-elevated)' }
};
