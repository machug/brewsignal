<script lang="ts">
	import { untrack } from 'svelte';
	import type { RecipeResponse, BatchResponse, BatchUpdate } from '$lib/api';
	import { updateBatch } from '$lib/api';

	interface Props {
		batch: BatchResponse;
		recipe: RecipeResponse;
		onComplete?: () => void;
	}

	let { batch, recipe, onComplete }: Props = $props();

	// Timer state - synced with backend
	let timerPhase = $state<'idle' | 'mash' | 'boil' | 'complete'>(
		(batch.timer_phase as 'idle' | 'mash' | 'boil' | 'complete') || 'idle'
	);
	let secondsRemaining = $state(0);
	let timerInterval: ReturnType<typeof setInterval> | null = null;
	let isPaused = $state(batch.timer_paused_at != null);
	let saving = $state(false);

	// Hop alerts that have fired (local only - resets on page refresh)
	let firedAlerts = $state<Set<number>>(new Set());

	// Default times (can be overridden)
	let mashDuration = $state(60); // Default 60 minutes mash
	let boilDuration = $derived(recipe.boil_time_minutes || 60);

	// Get hop additions sorted by time (descending - added at minutes from end)
	let hopAdditions = $derived.by(() => {
		if (!recipe.hops) return [];
		return recipe.hops
			.filter(h => h.timing?.use === 'add_to_boil' || !h.timing?.use)
			.map(h => ({
				name: h.name,
				amount: h.amount_grams,
				time: h.timing?.duration?.value || 0,
				unit: h.timing?.duration?.unit || 'min'
			}))
			.sort((a, b) => b.time - a.time);
	});

	// Calculate remaining time in MM:SS format
	let timeDisplay = $derived.by(() => {
		const mins = Math.floor(secondsRemaining / 60);
		const secs = secondsRemaining % 60;
		return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
	});

	// Calculate progress percentage
	let progress = $derived.by(() => {
		if (timerPhase === 'mash') {
			return ((mashDuration * 60 - secondsRemaining) / (mashDuration * 60)) * 100;
		} else if (timerPhase === 'boil') {
			return ((boilDuration * 60 - secondsRemaining) / (boilDuration * 60)) * 100;
		}
		return 0;
	});

	// Current phase display
	let phaseDisplay = $derived.by(() => {
		switch (timerPhase) {
			case 'mash': return 'Mash';
			case 'boil': return 'Boil';
			case 'complete': return 'Complete!';
			default: return 'Ready';
		}
	});

	// Calculate remaining time from server state
	function calculateRemainingFromServer(): number {
		if (!batch.timer_started_at || !batch.timer_duration_seconds) return 0;

		const startedAt = new Date(batch.timer_started_at).getTime();
		const duration = batch.timer_duration_seconds * 1000;
		const now = Date.now();

		if (batch.timer_paused_at) {
			// Timer is paused - calculate based on pause time
			const pausedAt = new Date(batch.timer_paused_at).getTime();
			const elapsed = pausedAt - startedAt;
			return Math.max(0, Math.floor((duration - elapsed) / 1000));
		} else {
			// Timer is running
			const elapsed = now - startedAt;
			return Math.max(0, Math.floor((duration - elapsed) / 1000));
		}
	}

	// Save timer state to backend
	async function saveTimerState(phase: string, durationSeconds: number, paused: boolean = false) {
		saving = true;
		try {
			const update: Record<string, unknown> = {
				timer_phase: phase,
				timer_duration_seconds: durationSeconds,
			};

			if (phase === 'idle' || phase === 'complete') {
				update.timer_started_at = null;
				update.timer_paused_at = null;
			} else if (paused) {
				update.timer_paused_at = new Date().toISOString();
			} else {
				// Starting or resuming - set start time
				update.timer_started_at = new Date().toISOString();
				update.timer_paused_at = null;
			}

			await updateBatch(batch.id, update as BatchUpdate);
		} catch (e) {
			console.error('Failed to save timer state:', e);
		} finally {
			saving = false;
		}
	}

	async function startMash() {
		timerPhase = 'mash';
		secondsRemaining = mashDuration * 60;
		firedAlerts = new Set();
		isPaused = false;
		await saveTimerState('mash', mashDuration * 60);
		startTimer();
	}

	async function startBoil() {
		timerPhase = 'boil';
		secondsRemaining = boilDuration * 60;
		firedAlerts = new Set();
		isPaused = false;
		await saveTimerState('boil', boilDuration * 60);
		startTimer();
	}

	function startTimer() {
		if (timerInterval) clearInterval(timerInterval);

		timerInterval = setInterval(() => {
			if (!isPaused && secondsRemaining > 0) {
				secondsRemaining--;

				// Check for hop alerts (boil phase only)
				if (timerPhase === 'boil') {
					const minutesRemaining = Math.floor(secondsRemaining / 60);
					for (const hop of hopAdditions) {
						const hopTime = hop.time;
						if (minutesRemaining === hopTime && !firedAlerts.has(hopTime)) {
							firedAlerts.add(hopTime);
							playAlert();
							showNotification(`Add ${hop.name}`, `${hop.amount}g at ${hopTime} minutes`);
						}
					}
				}

				// Timer complete
				if (secondsRemaining === 0) {
					clearInterval(timerInterval!);
					timerInterval = null;
					playAlert();

					if (timerPhase === 'mash') {
						showNotification('Mash Complete', 'Time to sparge and start the boil!');
					} else if (timerPhase === 'boil') {
						timerPhase = 'complete';
						saveTimerState('complete', 0);
						showNotification('Boil Complete', 'Time to chill the wort!');
						onComplete?.();
					}
				}
			}
		}, 1000);
	}

	async function togglePause() {
		isPaused = !isPaused;

		if (isPaused) {
			// Pausing - save current state with pause timestamp
			await saveTimerState(timerPhase, secondsRemaining, true);
		} else {
			// Resuming - ensure interval is running and save updated start time
			startTimer();
			await saveTimerState(timerPhase, secondsRemaining, false);
		}
	}

	async function resetTimer() {
		if (timerInterval) {
			clearInterval(timerInterval);
			timerInterval = null;
		}
		timerPhase = 'idle';
		secondsRemaining = 0;
		isPaused = false;
		firedAlerts = new Set();
		await saveTimerState('idle', 0);
	}

	function addMinute() {
		secondsRemaining += 60;
		saveTimerState(timerPhase, secondsRemaining, isPaused);
	}

	function subtractMinute() {
		if (secondsRemaining >= 60) {
			secondsRemaining -= 60;
			saveTimerState(timerPhase, secondsRemaining, isPaused);
		}
	}

	function playAlert() {
		// Create a simple beep using Web Audio API
		try {
			const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
			const oscillator = audioContext.createOscillator();
			const gainNode = audioContext.createGain();

			oscillator.connect(gainNode);
			gainNode.connect(audioContext.destination);

			oscillator.frequency.value = 880; // A5 note
			oscillator.type = 'sine';
			gainNode.gain.value = 0.3;

			oscillator.start();

			// Beep pattern: 3 short beeps
			setTimeout(() => gainNode.gain.value = 0, 150);
			setTimeout(() => gainNode.gain.value = 0.3, 250);
			setTimeout(() => gainNode.gain.value = 0, 400);
			setTimeout(() => gainNode.gain.value = 0.3, 500);
			setTimeout(() => gainNode.gain.value = 0, 650);
			setTimeout(() => {
				oscillator.stop();
				audioContext.close();
			}, 700);
		} catch (e) {
			console.warn('Audio notification not available:', e);
		}
	}

	function showNotification(title: string, body: string) {
		if ('Notification' in window && Notification.permission === 'granted') {
			new Notification(title, { body, icon: '/favicon.png' });
		}
	}

	// Initialize from server state on mount (untrack prevents re-runs from batch prop changes)
	$effect(() => {
		// Request notification permission
		if ('Notification' in window && Notification.permission === 'default') {
			Notification.requestPermission();
		}

		untrack(() => {
			// Restore timer state from batch
			if (batch.timer_phase && batch.timer_phase !== 'idle' && batch.timer_phase !== 'complete') {
				timerPhase = batch.timer_phase as 'mash' | 'boil';
				secondsRemaining = calculateRemainingFromServer();
				isPaused = batch.timer_paused_at != null;

				if (secondsRemaining > 0) {
					startTimer();
				}
			}
		});

		// Cleanup on unmount
		return () => {
			if (timerInterval) {
				clearInterval(timerInterval);
			}
		};
	});
</script>

<div class="timer-card">
	<div class="timer-header">
		<h3 class="timer-title">Brew Day Timer</h3>
		{#if saving}
			<span class="saving-indicator">Syncing...</span>
		{:else if timerPhase !== 'idle' && timerPhase !== 'complete'}
			<span class="phase-badge" class:mash={timerPhase === 'mash'} class:boil={timerPhase === 'boil'}>
				{phaseDisplay}
			</span>
		{/if}
	</div>

	{#if timerPhase === 'idle'}
		<!-- Timer not started -->
		<div class="timer-idle">
			<div class="timer-option">
				<label class="option-label">Mash Duration</label>
				<div class="duration-input">
					<button type="button" class="duration-btn" onclick={() => mashDuration = Math.max(1, mashDuration - 5)} aria-label="Decrease mash duration">&minus;</button>
					<span class="duration-value">{mashDuration}</span>
					<button type="button" class="duration-btn" onclick={() => mashDuration += 5} aria-label="Increase mash duration">+</button>
					<span class="duration-unit">min</span>
				</div>
			</div>

			<div class="timer-option">
				<label class="option-label">Boil Duration</label>
				<div class="duration-display">
					<span class="duration-value">{boilDuration}</span>
					<span class="duration-unit">min</span>
				</div>
			</div>

			<div class="timer-actions">
				<button type="button" class="start-btn mash" onclick={startMash}>
					<svg class="btn-icon" aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
					</svg>
					Start Mash
				</button>
				<button type="button" class="start-btn boil" onclick={startBoil}>
					Skip to Boil
				</button>
			</div>
		</div>

	{:else if timerPhase === 'complete'}
		<!-- Timer complete -->
		<div class="timer-complete">
						<p class="complete-text">Boil complete! Time to chill the wort.</p>
			<button type="button" class="reset-btn" onclick={resetTimer}>Reset Timer</button>
		</div>

	{:else}
		<!-- Timer running -->
		<div class="timer-active">
			<div class="timer-display">
				<span class="time-value">{timeDisplay}</span>
				<span class="time-label">remaining</span>
			</div>

			<div class="progress-bar" role="progressbar" aria-valuenow={Math.round(progress)} aria-valuemin="0" aria-valuemax="100" aria-label="Timer progress">
				<div class="progress-fill" class:mash={timerPhase === 'mash'} class:boil={timerPhase === 'boil'} style="width: {progress}%"></div>
			</div>

			<div class="timer-controls">
				<button type="button" class="control-btn" onclick={subtractMinute} title="Subtract 1 minute">
					&minus;1m
				</button>
				<button type="button" class="control-btn pause" class:paused={isPaused} onclick={togglePause}>
					{#if isPaused}
						<svg class="btn-icon" aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
						</svg>
						Resume
					{:else}
						<svg class="btn-icon" aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M10 9v6m4-6v6" />
						</svg>
						Pause
					{/if}
				</button>
				<button type="button" class="control-btn" onclick={addMinute} title="Add 1 minute">
					+1m
				</button>
			</div>

			<!-- Hop additions (boil only) -->
			{#if timerPhase === 'boil' && hopAdditions.length > 0}
				<div class="hop-schedule">
					<h4 class="schedule-title">Hop Additions</h4>
					<div class="hop-list">
						{#each hopAdditions as hop}
							{@const minutesRemaining = Math.floor(secondsRemaining / 60)}
							{@const isNext = hop.time <= minutesRemaining && !firedAlerts.has(hop.time)}
							{@const isDone = firedAlerts.has(hop.time) || hop.time > minutesRemaining}
							<div class="hop-item" class:next={isNext} class:done={isDone}>
								<span class="hop-time">{hop.time}&thinsp;m</span>
								<span class="hop-name">{hop.name}</span>
								<span class="hop-amount">{hop.amount}&thinsp;g</span>
								{#if isDone}
									<span class="hop-check" aria-label="done"><svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3.5 8.5l3 3 6-6" /></svg></span>
								{/if}
							</div>
						{/each}
					</div>
				</div>
			{/if}

			<!-- Phase transition buttons -->
			<div class="phase-actions">
				{#if timerPhase === 'mash'}
					<button type="button" class="next-phase-btn" onclick={startBoil}>
						Mash Done &rarr; Start Boil
					</button>
				{/if}
				<button type="button" class="reset-btn" onclick={resetTimer}>Reset</button>
			</div>
		</div>
	{/if}
</div>

<style>
	.timer-card {
		border-top: 1px solid var(--rule-strong);
		padding-top: var(--space-sm);
		min-width: 0;
	}
	.timer-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: var(--space-sm);
	}
	.timer-title {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-muted);
		text-transform: uppercase;
		letter-spacing: 0.08em;
		margin: 0;
	}
	.saving-indicator {
		font-family: var(--font-num);
		font-size: var(--text-xs);
		color: var(--ink-muted);
	}
	.phase-badge {
		font-family: var(--font-display);
		font-size: 0.6875rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		padding: 2px 7px;
		border-radius: 2px;
		border: 1px solid var(--accent-rule);
		color: var(--accent);
	}
	.phase-badge.boil {
		border-color: color-mix(in oklch, var(--status-warn) 55%, transparent);
		color: var(--status-warn);
	}

	/* Idle */
	.timer-idle {
		display: flex;
		flex-direction: column;
		gap: var(--space-sm);
	}
	.timer-option {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-sm);
		padding-bottom: var(--space-xs);
		border-bottom: 1px solid var(--rule-hairline);
	}
	.option-label {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}
	.duration-input,
	.duration-display {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
	}
	.duration-btn {
		width: 44px;
		height: 44px;
		font-size: var(--text-lg);
		line-height: 1;
		color: var(--ink-primary);
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		cursor: pointer;
	}
	.duration-btn:hover {
		background: var(--bg-subtle);
	}
	.duration-value {
		min-width: 2.5rem;
		text-align: center;
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: var(--text-lg);
		font-weight: 600;
		color: var(--ink-primary);
	}
	.duration-unit {
		font-size: var(--text-sm);
		color: var(--ink-muted);
	}
	.timer-actions {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-xs);
	}
	.start-btn,
	.control-btn,
	.next-phase-btn,
	.reset-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: var(--space-xs);
		min-height: 44px;
		padding: 0 var(--space-md);
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		border-radius: 4px;
		cursor: pointer;
		color: var(--ink-primary);
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		transition: background-color 140ms var(--ease-out-quart);
	}
	.start-btn:hover,
	.control-btn:hover,
	.reset-btn:hover {
		background: var(--bg-subtle);
	}
	.start-btn.mash {
		flex: 1;
		color: var(--accent-ink);
		background: var(--accent);
		border-color: var(--accent);
	}
	.start-btn.mash:hover {
		background: var(--accent-hover);
	}
	.btn-icon {
		width: 1rem;
		height: 1rem;
	}

	/* Running */
	.timer-active {
		display: flex;
		flex-direction: column;
		gap: var(--space-sm);
	}
	.timer-display {
		display: flex;
		align-items: baseline;
		gap: var(--space-sm);
	}
	.time-value {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums lining-nums;
		font-size: 3rem;
		font-weight: 600;
		line-height: 1;
		letter-spacing: -0.03em;
		color: var(--ink-primary);
	}
	.time-label {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--ink-muted);
	}
	.progress-bar {
		height: 4px;
		background: var(--rule-hairline);
	}
	.progress-fill {
		height: 100%;
		background: var(--accent);
		transition: width 1s linear;
	}
	.progress-fill.boil {
		background: var(--status-warn);
	}
	.timer-controls {
		display: grid;
		grid-template-columns: 1fr 1.4fr 1fr;
		gap: var(--space-xs);
	}
	.control-btn.pause.paused {
		color: var(--accent);
		background: var(--accent-tint);
		border-color: var(--accent-rule);
	}

	/* Hop schedule */
	.hop-schedule {
		border-top: 1px solid var(--rule-hairline);
		padding-top: var(--space-xs);
	}
	.schedule-title {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--ink-muted);
		margin-bottom: var(--space-xs);
	}
	.hop-list {
		display: flex;
		flex-direction: column;
	}
	.hop-item {
		display: grid;
		grid-template-columns: 3.5rem minmax(0, 1fr) auto 1.25rem;
		align-items: center;
		gap: var(--space-sm);
		min-height: 36px;
		border-bottom: 1px solid var(--rule-hairline);
		font-size: var(--text-sm);
		color: var(--ink-primary);
	}
	.hop-item.next {
		color: var(--accent);
	}
	.hop-item.done {
		color: var(--ink-muted);
	}
	.hop-time,
	.hop-amount {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: var(--text-xs);
	}
	.hop-name {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.hop-check {
		display: inline-flex;
		color: var(--status-steady);
	}
	.phase-actions {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-xs);
	}
	.next-phase-btn {
		flex: 1;
		color: var(--accent);
		background: var(--accent-tint);
		border-color: var(--accent-rule);
	}
	.next-phase-btn:hover {
		border-color: var(--accent);
	}

	/* Complete */
	.timer-complete {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: var(--space-sm);
	}
	.complete-text {
		font-size: var(--text-base);
		color: var(--ink-primary);
	}
	@media (prefers-reduced-motion: reduce) {
		.progress-fill {
			transition: none;
		}
	}
</style>
