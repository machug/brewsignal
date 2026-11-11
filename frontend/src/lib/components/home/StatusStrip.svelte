<script module lang="ts">
	export interface ChamberIdleStatus {
		enabled: boolean;
		active: boolean;
		chamber_temp: number | null;
		target_temp: number | null;
		hysteresis: number | null;
		heater_state: string | null;
		cooler_state: string | null;
	}
</script>

<script lang="ts">
	import { onMount } from 'svelte';
	import { weatherState } from '$lib/stores/weather.svelte';
	import { formatTemp, getTempUnit } from '$lib/stores/config.svelte';

	interface Props {
		chamberIdle: ChamberIdleStatus | null;
		/** Short labels for active batches whose wort temp is out of the yeast range, e.g. "Batch #7 too hot". */
		outOfRange: string[];
		activeCount: number;
	}

	let { chamberIdle, outOfRange, activeCount }: Props = $props();

	const DISMISS_KEY = 'brewsignal_alerts_dismissed';
	const DISMISS_TIME_KEY = 'brewsignal_alerts_dismissed_time';
	const RESTORE_AFTER_MS = 6 * 60 * 60 * 1000;

	let dismissed = $state(false);
	let expanded = $state(false);

	onMount(() => {
		const flag = localStorage.getItem(DISMISS_KEY);
		const time = localStorage.getItem(DISMISS_TIME_KEY);
		// Auto-restore alerts after 6 hours
		if (flag === 'true' && time && Date.now() - parseInt(time, 10) < RESTORE_AFTER_MS) {
			dismissed = true;
		}
	});

	function dismiss() {
		dismissed = true;
		localStorage.setItem(DISMISS_KEY, 'true');
		localStorage.setItem(DISMISS_TIME_KEY, Date.now().toString());
	}

	let alerts = $derived(weatherState.alerts);
	let showAlerts = $derived(alerts.length > 0 && !dismissed);
	let critical = $derived(alerts.some((a) => a.level === 'critical'));
	let idleState = $derived(
		chamberIdle?.heater_state === 'on' ? 'Heating' : chamberIdle?.cooler_state === 'on' ? 'Cooling' : 'Holding'
	);

	type Tone = 'steady' | 'warn' | 'danger' | 'quiet';
	let view = $derived.by((): { tone: Tone; tag: string; message: string } => {
		if (showAlerts) {
			return {
				tone: critical ? 'danger' : 'warn',
				tag: critical ? 'Weather critical' : 'Weather alert',
				message: `${alerts[0].day}: ${alerts[0].message}`
			};
		}
		if (outOfRange.length > 0) {
			return { tone: 'warn', tag: 'Temperature', message: outOfRange.join(' · ') };
		}
		if (chamberIdle?.active && activeCount === 0) {
			return { tone: 'quiet', tag: 'Chamber idle', message: 'No batch fermenting; chamber held at idle target.' };
		}
		if (activeCount > 0) {
			return { tone: 'steady', tag: 'Steady', message: 'All active batches steady' };
		}
		return { tone: 'quiet', tag: 'Idle', message: 'No active batches' };
	});
</script>

<section class="strip" aria-label="Status">
	<div class="row">
		<div class="main">
			<span class="tag {view.tone}">{view.tag}</span>
			<p class="message">{view.message}</p>
		</div>
		<div class="meta">
			{#if chamberIdle?.active}
				<span class="idle">
					{#if view.tag !== 'Chamber idle'}Chamber idle{/if}
					{#if chamberIdle.chamber_temp != null}
						<span class="num">{formatTemp(chamberIdle.chamber_temp)}</span>
					{/if}
					{#if chamberIdle.target_temp != null}
						<span aria-hidden="true">&rarr;</span>
						<span class="num">{formatTemp(chamberIdle.target_temp)}&thinsp;{getTempUnit()}</span>
					{/if}
					&middot; {idleState}
				</span>
			{/if}
			{#if showAlerts}
				{#if alerts.length > 1}
					<button type="button" class="link" aria-expanded={expanded} onclick={() => (expanded = !expanded)}>
						{expanded ? 'Hide' : `All ${alerts.length} alerts`}
					</button>
				{/if}
				<button type="button" class="link" onclick={dismiss} aria-label="Dismiss weather alerts">Dismiss</button>
			{/if}
		</div>
	</div>
	{#if showAlerts && expanded}
		<ul class="alert-list">
			{#each alerts as alert}
				<li class:danger={alert.level === 'critical'}>
					<span class="alert-day">{alert.day}</span>
					<span>{alert.message}</span>
				</li>
			{/each}
		</ul>
	{/if}
</section>

<style>
	.strip {
		border-bottom: 1px solid var(--rule-hairline);
		background-color: var(--bg-surface);
		padding: var(--space-sm) var(--space-xl);
	}
	.row {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-xs) var(--space-lg);
	}
	.main {
		display: flex;
		align-items: baseline;
		flex-wrap: wrap;
		gap: var(--space-xs) var(--space-sm);
		font-size: var(--text-sm);
		min-width: 0;
	}
	.message {
		color: var(--ink-primary);
	}
	.tag {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		font-family: var(--font-num);
		font-size: var(--text-xs);
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		padding: 2px 7px;
		border-radius: 2px;
		color: var(--tone);
		border: 1px solid color-mix(in oklch, var(--tone) 38%, transparent);
		background-color: color-mix(in oklch, var(--tone) 10%, transparent);
	}
	.tag::before {
		content: '';
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background-color: currentColor;
	}
	.tag.steady {
		--tone: var(--status-steady);
	}
	.tag.warn {
		--tone: var(--status-warn);
	}
	.tag.danger {
		--tone: var(--status-danger);
	}
	.tag.quiet {
		--tone: var(--ink-secondary);
	}
	.meta {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: var(--space-xs) var(--space-md);
		font-family: var(--font-num);
		font-size: var(--text-xs);
		color: var(--ink-muted);
	}
	.idle {
		display: inline-flex;
		align-items: baseline;
		gap: var(--space-2xs);
	}
	.link {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-secondary);
		padding: var(--space-2xs) 0;
		min-height: 28px;
		border-bottom: 1px solid transparent;
		cursor: pointer;
	}
	.link:hover {
		color: var(--ink-primary);
		border-bottom-color: var(--accent);
	}
	.alert-list {
		list-style: none;
		margin-top: var(--space-sm);
		border-top: 1px solid var(--rule-hairline);
	}
	.alert-list li {
		display: flex;
		gap: var(--space-sm);
		padding: var(--space-xs) 0;
		border-bottom: 1px solid var(--rule-hairline);
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}
	.alert-list li.danger {
		color: var(--ink-primary);
	}
	.alert-day {
		font-family: var(--font-num);
		font-size: var(--text-xs);
		color: var(--ink-primary);
		min-width: 5ch;
	}
	@media (max-width: 760px) {
		.strip {
			padding: var(--space-xs) var(--space-md);
		}
	}
</style>
