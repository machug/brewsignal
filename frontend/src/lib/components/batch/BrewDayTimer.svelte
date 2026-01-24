<script lang="ts">
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
			// Resuming - update start time to resume from current remaining
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
	}

	function subtractMinute() {
		if (secondsRemaining >= 60) {
			secondsRemaining -= 60;
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

	// Initialize from server state on mount
	$effect(() => {
		// Request notification permission
		if ('Notification' in window && Notification.permission === 'default') {
			Notification.requestPermission();
		}

		// Restore timer state from batch
		if (batch.timer_phase && batch.timer_phase !== 'idle' && batch.timer_phase !== 'complete') {
			timerPhase = batch.timer_phase as 'mash' | 'boil';
			secondsRemaining = calculateRemainingFromServer();
			isPaused = batch.timer_paused_at != null;

			if (!isPaused && secondsRemaining > 0) {
				startTimer();
			}
		}

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
					<button type="button" class="duration-btn" onclick={() => mashDuration = Math.max(1, mashDuration - 5)}>−</button>
					<span class="duration-value">{mashDuration}</span>
					<button type="button" class="duration-btn" onclick={() => mashDuration += 5}>+</button>
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
					<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
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
			<div class="complete-icon">✓</div>
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

			<div class="progress-bar">
				<div class="progress-fill" class:mash={timerPhase === 'mash'} class:boil={timerPhase === 'boil'} style="width: {progress}%"></div>
			</div>

			<div class="timer-controls">
				<button type="button" class="control-btn" onclick={subtractMinute} title="Subtract 1 minute">
					−1m
				</button>
				<button type="button" class="control-btn pause" class:paused={isPaused} onclick={togglePause}>
					{#if isPaused}
						<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
						</svg>
						Resume
					{:else}
						<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
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
								<span class="hop-time">{hop.time}m</span>
								<span class="hop-name">{hop.name}</span>
								<span class="hop-amount">{hop.amount}g</span>
								{#if isDone}
									<span class="hop-check">✓</span>
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
						Mash Done → Start Boil
					</button>
				{/if}
				<button type="button" class="reset-btn" onclick={resetTimer}>Reset</button>
			</div>
		</div>
	{/if}
</div>

<style>
	.timer-card {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.75rem;
		padding: 1.25rem;
	}

	.timer-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 1rem;
	}

	.timer-title {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin: 0;
	}

	.saving-indicator {
		font-size: 0.6875rem;
		color: var(--text-muted);
		font-style: italic;
	}

	.phase-badge {
		font-size: 0.6875rem;
		font-weight: 600;
		padding: 0.25rem 0.5rem;
		border-radius: 9999px;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.phase-badge.mash {
		background: rgba(217, 119, 6, 0.15);
		color: #d97706;
	}

	.phase-badge.boil {
		background: rgba(239, 68, 68, 0.15);
		color: var(--tilt-red);
	}

	/* Idle state */
	.timer-idle {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.timer-option {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.option-label {
		font-size: 0.875rem;
		color: var(--text-secondary);
	}

	.duration-input,
	.duration-display {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.duration-btn {
		width: 2rem;
		height: 2rem;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 1rem;
		font-weight: 600;
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
		border-radius: 0.375rem;
		color: var(--text-primary);
		cursor: pointer;
	}

	.duration-btn:hover {
		background: var(--bg-hover);
	}

	.duration-value {
		font-size: 1.25rem;
		font-weight: 600;
		font-family: var(--font-mono);
		color: var(--text-primary);
		min-width: 2.5rem;
		text-align: center;
	}

	.duration-unit {
		font-size: 0.875rem;
		color: var(--text-muted);
	}

	.timer-actions {
		display: flex;
		gap: 0.75rem;
		margin-top: 0.5rem;
	}

	.start-btn {
		flex: 1;
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		padding: 0.75rem 1rem;
		font-size: 0.875rem;
		font-weight: 600;
		border-radius: 0.5rem;
		cursor: pointer;
		transition: all var(--transition);
	}

	.start-btn.mash {
		background: linear-gradient(135deg, #d97706 0%, #f59e0b 100%);
		border: none;
		color: white;
	}

	.start-btn.mash:hover {
		filter: brightness(1.1);
	}

	.start-btn.boil {
		background: var(--bg-elevated);
		border: 1px solid var(--border-default);
		color: var(--text-secondary);
	}

	.start-btn.boil:hover {
		background: var(--bg-hover);
		color: var(--text-primary);
	}

	.btn-icon {
		width: 1rem;
		height: 1rem;
	}

	/* Active state */
	.timer-active {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.timer-display {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.25rem;
	}

	.time-value {
		font-size: 3rem;
		font-weight: 700;
		font-family: var(--font-mono);
		color: var(--text-primary);
		line-height: 1;
	}

	.time-label {
		font-size: 0.75rem;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.progress-bar {
		height: 6px;
		background: var(--bg-elevated);
		border-radius: 3px;
		overflow: hidden;
	}

	.progress-fill {
		height: 100%;
		border-radius: 3px;
		transition: width 1s linear;
	}

	.progress-fill.mash {
		background: linear-gradient(90deg, #d97706, #f59e0b);
	}

	.progress-fill.boil {
		background: linear-gradient(90deg, var(--tilt-red), #f87171);
	}

	.timer-controls {
		display: flex;
		justify-content: center;
		gap: 0.5rem;
	}

	.control-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.375rem;
		padding: 0.5rem 1rem;
		font-size: 0.8125rem;
		font-weight: 500;
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
		border-radius: 0.375rem;
		color: var(--text-secondary);
		cursor: pointer;
		transition: all var(--transition);
	}

	.control-btn:hover {
		background: var(--bg-hover);
		color: var(--text-primary);
	}

	.control-btn.pause {
		min-width: 100px;
	}

	.control-btn.pause.paused {
		background: var(--positive-muted);
		border-color: var(--positive);
		color: var(--positive);
	}

	/* Hop schedule */
	.hop-schedule {
		margin-top: 0.5rem;
		padding-top: 1rem;
		border-top: 1px solid var(--border-subtle);
	}

	.schedule-title {
		font-size: 0.6875rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin: 0 0 0.75rem 0;
	}

	.hop-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.hop-item {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 0.5rem 0.75rem;
		background: var(--bg-elevated);
		border-radius: 0.375rem;
		font-size: 0.8125rem;
	}

	.hop-item.next {
		background: rgba(249, 115, 22, 0.15);
		border: 1px solid rgba(249, 115, 22, 0.3);
	}

	.hop-item.done {
		opacity: 0.5;
	}

	.hop-time {
		font-weight: 600;
		font-family: var(--font-mono);
		color: var(--text-primary);
		min-width: 2.5rem;
	}

	.hop-name {
		flex: 1;
		color: var(--text-primary);
	}

	.hop-amount {
		font-family: var(--font-mono);
		color: var(--text-secondary);
	}

	.hop-check {
		color: var(--positive);
		font-weight: 600;
	}

	/* Phase actions */
	.phase-actions {
		display: flex;
		gap: 0.5rem;
		margin-top: 0.5rem;
	}

	.next-phase-btn {
		flex: 1;
		padding: 0.625rem 1rem;
		font-size: 0.8125rem;
		font-weight: 600;
		background: linear-gradient(135deg, var(--tilt-red) 0%, #f87171 100%);
		border: none;
		border-radius: 0.375rem;
		color: white;
		cursor: pointer;
		transition: all var(--transition);
	}

	.next-phase-btn:hover {
		filter: brightness(1.1);
	}

	.reset-btn {
		padding: 0.625rem 1rem;
		font-size: 0.8125rem;
		font-weight: 500;
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
		border-radius: 0.375rem;
		color: var(--text-secondary);
		cursor: pointer;
		transition: all var(--transition);
	}

	.reset-btn:hover {
		background: var(--bg-hover);
		color: var(--text-primary);
	}

	/* Complete state */
	.timer-complete {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 1rem;
		padding: 1rem;
	}

	.complete-icon {
		width: 3rem;
		height: 3rem;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 1.5rem;
		background: var(--positive-muted);
		color: var(--positive);
		border-radius: 50%;
	}

	.complete-text {
		font-size: 0.9375rem;
		color: var(--text-secondary);
		margin: 0;
		text-align: center;
	}
</style>
