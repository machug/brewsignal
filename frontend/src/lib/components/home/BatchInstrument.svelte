<script lang="ts">
	import { onMount } from 'svelte';
	import {
		formatTemp,
		getTempUnit,
		formatGravity,
		getGravityUnit,
		sgToPlato,
		sgToBrix,
		configState
	} from '$lib/stores/config.svelte';
	import {
		updateBatch,
		fetchBatchControlEvents,
		fetchBatchControlStatus,
		fetchRecipe,
		type BatchResponse,
		type BatchProgressResponse,
		type BatchControlStatus,
		type ControlEvent,
		type HopResponse
	} from '$lib/api';
	import { tiltsState } from '$lib/stores/tilts.svelte';
	import FermentationChart from '../FermentationChart.svelte';

	interface Props {
		batch: BatchResponse;
		progress?: BatchProgressResponse;
		expanded?: boolean;
		onToggleExpand?: () => void;
		onBatchUpdated?: () => Promise<void>;
	}

	let { batch, progress, expanded = false, onToggleExpand, onBatchUpdated }: Props = $props();

	const tiltColors: Record<string, string> = {
		RED: 'var(--tilt-red)',
		GREEN: 'var(--tilt-green)',
		BLACK: 'var(--tilt-black)',
		PURPLE: 'var(--tilt-purple)',
		ORANGE: 'var(--tilt-orange)',
		BLUE: 'var(--tilt-blue)',
		YELLOW: 'var(--tilt-yellow)',
		PINK: 'var(--tilt-pink)'
	};

	// Live device reading (WebSocket), looked up directly by device_id
	let reading = $derived(batch.device_id ? (tiltsState.tilts.get(batch.device_id) ?? null) : null);
	let displayName = $derived(batch.name || batch.recipe?.name || `Batch #${batch.batch_number}`);
	let deviceColor = $derived(reading?.color ?? 'BLACK');
	let deviceType = $derived(reading?.device_type ?? null);
	let isBle = $derived(deviceType === 'tilt' || deviceType === null);
	let deviceLabel = $derived(
		!reading
			? 'No signal'
			: isBle
				? `Tilt ${reading.color.charAt(0)}${reading.color.slice(1).toLowerCase()}`
				: `${deviceType} ${reading.color.toLowerCase()}`
	);

	let og = $derived(progress?.measured?.og ?? batch.measured_og ?? null);
	let sg = $derived(progress?.measured?.current_sg ?? batch.measured_og ?? null);
	let temp = $derived(progress?.temperature?.current ?? null);

	// Live figures from current SG and OG; fall back to the server values
	let attenuation = $derived(
		og && sg && og > 1 ? ((og - sg) / (og - 1)) * 100 : (progress?.measured?.attenuation ?? null)
	);
	let abv = $derived(og && sg ? Math.max(0, (og - sg) * 131.25) : (progress?.measured?.abv ?? null));
	let tempStatus = $derived(progress?.temperature?.status ?? 'unknown');

	let gravityUnit = $derived(getGravityUnit());
	let tempUnit = $derived(getTempUnit());

	function gravityDelta(from: number, to: number): string {
		const u = configState.config.sg_units;
		const d = u === 'plato' ? sgToPlato(to) - sgToPlato(from) : u === 'brix' ? sgToBrix(to) - sgToBrix(from) : to - from;
		const digits = u === 'sg' ? 3 : 1;
		const sign = d < 0 ? '−' : '+';
		return sign + Math.abs(d).toFixed(digits);
	}

	// Day count since the current phase started
	let phaseStart = $derived(
		batch.status === 'conditioning'
			? (batch.conditioning_started_at ?? batch.fermenting_started_at)
			: (batch.fermenting_started_at ?? batch.start_time)
	);
	let day = $derived(phaseStart ? Math.max(1, Math.floor((Date.now() - new Date(phaseStart).getTime()) / 86400000) + 1) : null);
	let statusLabel = $derived(batch.status === 'conditioning' ? 'Conditioning' : 'Fermenting');
	let dayText = $derived(day ? `${statusLabel} \u00b7 Day ${day}` : statusLabel);

	// Temperature control (heater/cooler) and target
	let control = $state<BatchControlStatus | null>(null);
	let primaryStepTemp = $state<number | null>(null);
	let targetTemp = $derived(control?.target_temp ?? batch.temp_target ?? primaryStepTemp);
	let controlState = $derived(
		control?.heater_state === 'on'
			? 'Heating'
			: control?.cooler_state === 'on'
				? 'Cooling'
				: control?.enabled
					? 'Holding'
					: null
	);

	async function loadControl() {
		if (!batch.heater_entity_id && !batch.cooler_entity_id) return;
		try {
			control = await fetchBatchControlStatus(batch.id);
		} catch {
			// not critical
		}
	}

	// Next step: recipe dry-hop additions (BeerJSON "add_to_fermentation")
	let dryHops = $state<HopResponse[]>([]);
	async function loadRecipe() {
		if (!batch.recipe_id) return;
		try {
			const recipe = await fetchRecipe(batch.recipe_id);
			dryHops = (recipe.hops ?? []).filter((h) => h.timing?.use === 'add_to_fermentation');
			primaryStepTemp = recipe.fermentation_steps?.find((s) => s.type === 'primary')?.temp_c ?? null;
		} catch {
			// next step omitted when the recipe cannot be read
		}
	}
	let nextStep = $derived.by(() => {
		if (batch.status !== 'fermenting' || dryHops.length === 0) return null;
		const d = dryHops[0].timing?.duration;
		const t = dryHops[0].timing?.time;
		return {
			detail: dryHops.map((h) => ({ name: h.name, grams: h.amount_grams })),
			contact: d?.value != null ? `${d.value} ${d.unit ?? 'day'}${d.value === 1 ? '' : 's'} contact` : null,
			at: t?.value != null ? `Day ${t.value}` : null
		};
	});

	onMount(() => {
		loadControl();
		loadRecipe();
		const id = setInterval(loadControl, 30000);
		return () => clearInterval(id);
	});

	// Chart is mounted on first expand, then kept (CSS hide) so it is not destroyed
	let chartMounted = $state(false);
	let controlEvents = $state<ControlEvent[]>([]);
	$effect(() => {
		if (expanded && !chartMounted) {
			chartMounted = true;
			fetchBatchControlEvents(batch.id, 168)
				.then((e) => (controlEvents = e))
				.catch(() => (controlEvents = []));
		}
	});

	// Inline rename
	let isEditing = $state(false);
	let editValue = $state('');
	let inputRef = $state<HTMLInputElement | null>(null);
	let saving = $state(false);
	let saveError = $state<string | null>(null);

	function startEditing() {
		editValue = displayName;
		isEditing = true;
		saveError = null;
		setTimeout(() => inputRef?.focus(), 0);
	}
	async function saveEdit() {
		if (saving) return;
		const trimmed = editValue.trim();
		if (!trimmed || trimmed === displayName) {
			isEditing = false;
			saveError = null;
			return;
		}
		saving = true;
		saveError = null;
		try {
			await updateBatch(batch.id, { name: trimmed });
			isEditing = false;
			if (onBatchUpdated) await onBatchUpdated();
		} catch (e) {
			saveError = e instanceof Error ? e.message : 'Failed to save batch name';
		} finally {
			saving = false;
		}
	}
	function onEditKey(e: KeyboardEvent) {
		if (e.key === 'Enter') saveEdit();
		else if (e.key === 'Escape') isEditing = false;
	}

	function timeSince(iso: string): string {
		const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
		if (s < 10) return 'just now';
		if (s < 60) return `${s}s ago`;
		const m = Math.floor(s / 60);
		if (m < 60) return `${m}m ago`;
		const h = Math.floor(m / 60);
		if (h < 24) return `${h}h ago`;
		return `${Math.floor(h / 24)}d ago`;
	}

	let styleText = $derived.by(() => {
		const st = batch.recipe?.style;
		if (!st) return null;
		return st.category_number ? `${st.name} (BJCP ${st.category_number}${st.style_letter ?? ''})` : st.name;
	});
	let rawDiffers = $derived(
		!!reading && (reading.sg_raw !== reading.sg || reading.temp_raw !== reading.temp)
	);
	let confidenceLabel = $derived(
		reading?.confidence == null ? null : reading.confidence >= 0.8 ? 'High' : reading.confidence >= 0.5 ? 'Medium' : 'Low'
	);
</script>

{#if !expanded}
	<div class="collapsed">
		<span class="swatch" style="background-color: {tiltColors[deviceColor] ?? 'var(--ink-muted)'}" aria-hidden="true"></span>
		<span class="code">#{batch.batch_number ?? batch.id}</span>
		<span class="c-name">{displayName}</span>
		<span class="c-fig num">
			{sg != null ? formatGravity(sg) : '--'}
			<span class="c-sep" aria-hidden="true">&middot;</span>
			{temp != null ? formatTemp(temp) : '--'}<span class="unit">&thinsp;{tempUnit}</span>
		</span>
		<span class="c-day num">{dayText}</span>
		<button type="button" class="expand" onclick={onToggleExpand} aria-expanded="false" aria-label="Expand {displayName}">
			<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M4 6l4 4 4-4" /></svg>
		</button>
	</div>
{:else}
	<article class="instrument" aria-label="Batch {batch.batch_number ?? batch.id}">
		<header class="head">
			<div class="id">
				<div class="id-row">
					<span class="code">BATCH #{batch.batch_number ?? batch.id}</span>
					{#if styleText}
						<span class="sep" aria-hidden="true">&middot;</span>
						<span class="style">{styleText}</span>
					{/if}
				</div>
				{#if isEditing}
					<input
						type="text"
						class="title-input"
						bind:this={inputRef}
						bind:value={editValue}
						onblur={saveEdit}
						onkeydown={onEditKey}
						disabled={saving}
						maxlength="100"
						aria-label="Batch name"
					/>
					{#if saveError}<span class="err">{saveError}</span>{/if}
				{:else}
					<button type="button" class="title-btn" onclick={startEditing} title="Click to rename">
						<h2 class="title">{displayName}</h2>
					</button>
				{/if}
			</div>
			<div class="sensor">
				{#if batch.device_id}
					<div class="chip">
						<span class="swatch" style="background-color: {tiltColors[deviceColor] ?? 'var(--ink-muted)'}" aria-hidden="true"></span>
						<span>{deviceLabel}</span>
						{#if reading}
							{#if isBle && reading.rssi != null}
								<span class="num chip-meta">{reading.rssi}&thinsp;dBm</span>
							{:else if reading.battery_percent != null}
								<span class="num chip-meta">{reading.battery_percent}%</span>
							{/if}
						{/if}
					</div>
					{#if reading && !reading.paired}
						<span class="flag">Unpaired &middot; not logging</span>
					{/if}
				{/if}
				<span class="day num">{dayText}{reading ? ` \u00b7 ${timeSince(reading.last_seen)}` : ''}</span>
			</div>
		</header>

		{#if reading?.is_anomaly && (reading.anomaly_reasons?.length ?? 0) > 0}
			<div class="anomaly" role="status">
				<span class="a-tag">Anomaly</span>
				<span>{reading.anomaly_reasons?.join(' · ')}</span>
			</div>
		{/if}

		<div class="matrix">
			<div class="cell">
				<div class="label">
					<span>Current {gravityUnit === 'SG' ? 'SG' : gravityUnit === '°P' ? 'Plato' : 'Brix'}</span>
					{#if og && sg}<span class="delta num">{gravityDelta(og, sg)}</span>{/if}
				</div>
				<div class="primary num">{sg != null ? formatGravity(sg) : '--'}{#if gravityUnit !== 'SG'}<span class="unit">&thinsp;{gravityUnit}</span>{/if}</div>
				<div class="sub">
					{#if og}<span>OG <span class="num">{formatGravity(og)}</span></span>{/if}
					{#if confidenceLabel}<span>Confidence {confidenceLabel.toLowerCase()}</span>{/if}
				</div>
			</div>
			<div class="cell">
				<div class="label"><span>Attenuation</span></div>
				<div class="primary num">{attenuation != null ? attenuation.toFixed(0) : '--'}<span class="unit">&thinsp;%</span></div>
				<div class="sub">
					<span>apparent</span>
					{#if progress?.targets?.attenuation != null}<span>target <span class="num">{progress.targets.attenuation.toFixed(0)}&thinsp;%</span></span>{/if}
				</div>
			</div>
			<div class="cell">
				<div class="label"><span>Est. ABV</span></div>
				<div class="primary num">{abv != null ? abv.toFixed(1) : '--'}<span class="unit">&thinsp;%</span></div>
				<div class="sub">
					{#if progress?.targets?.abv != null}<span>target <span class="num">{progress.targets.abv.toFixed(1)}&thinsp;%</span></span>{/if}
				</div>
			</div>
			<div class="cell">
				<div class="label"><span>Wort Temp</span></div>
				<div class="primary num">{temp != null ? formatTemp(temp) : '--'}<span class="unit">&thinsp;{tempUnit}</span></div>
				<div class="sub">
					{#if targetTemp != null}<span>target <span class="num">{formatTemp(targetTemp)}&thinsp;{tempUnit}</span></span>{/if}
					{#if controlState}<span class="chamber">{controlState}</span>{/if}
					{#if tempStatus === 'too_hot' || tempStatus === 'too_cold'}
						<span class="warn">{tempStatus === 'too_hot' ? 'Above' : 'Below'} yeast range</span>
					{/if}
				</div>
			</div>
		</div>

		{#if rawDiffers && reading}
			<p class="raw num">
				Raw {formatGravity(reading.sg_raw)} &middot; {formatTemp(reading.temp_raw)}&thinsp;{tempUnit}
			</p>
		{/if}

		<div class="telemetry">
			{#if chartMounted}
				{#key batch.id}
					<FermentationChart batchId={batch.id} {deviceColor} originalGravity={batch.measured_og} {controlEvents} showStats={false} />
				{/key}
			{/if}
		</div>

		{#if nextStep}
			<div class="next">
				<div class="next-left">
					<span class="kicker">Next step</span>
					<span class="next-detail">
						Dry hop &middot; {nextStep.detail.map((h) => (h.grams != null ? `${h.name} ${h.grams}\u2009g` : h.name)).join(', ')}
					</span>
					{#if nextStep.at || nextStep.contact}
						<span class="next-timing num">{[nextStep.at, nextStep.contact].filter(Boolean).join(' · ')}</span>
					{/if}
				</div>
				{#if batch.recipe_id}
					<a class="link" href="/recipes/{batch.recipe_id}">Recipe</a>
				{/if}
			</div>
		{/if}

		<footer class="foot">
			<a class="link" href="/batches/{batch.id}">View batch details &rarr;</a>
			<button type="button" class="link" onclick={onToggleExpand} aria-expanded="true">Collapse</button>
		</footer>
	</article>
{/if}

<style>
	.num {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums lining-nums;
		letter-spacing: -0.02em;
	}
	.unit {
		font-family: var(--font-body);
		font-size: 0.78em;
		font-weight: 400;
		color: var(--ink-muted);
		letter-spacing: 0;
	}
	.swatch {
		display: inline-block;
		width: 8px;
		height: 8px;
		border-radius: 1px;
		flex-shrink: 0;
	}
	.code {
		font-family: var(--font-num);
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--accent);
		letter-spacing: 0.04em;
	}

	/* Collapsed one-line row */
	.collapsed {
		display: grid;
		grid-template-columns: auto auto minmax(0, 1fr) auto auto auto;
		align-items: center;
		gap: var(--space-sm);
		padding: var(--space-sm) var(--space-xl);
		border-bottom: 1px solid var(--rule-hairline);
		font-size: var(--text-sm);
	}
	.c-name {
		font-family: var(--font-display);
		font-weight: 600;
		color: var(--ink-primary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.c-fig {
		font-size: var(--text-sm);
		color: var(--ink-primary);
	}
	.c-sep {
		color: var(--rule-strong);
		margin: 0 var(--space-2xs);
	}
	.c-day {
		font-size: var(--text-xs);
		color: var(--ink-secondary);
	}
	.expand {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 36px;
		height: 36px;
		border: 1px solid var(--rule-hairline);
		border-radius: 3px;
		color: var(--ink-secondary);
		cursor: pointer;
	}
	.expand:hover {
		color: var(--ink-primary);
		border-color: var(--rule-strong);
	}

	/* Open instrument */
	.instrument {
		padding: var(--space-xl) var(--space-xl) var(--space-lg);
		border-bottom: 1px solid var(--rule-hairline);
		container-type: inline-size;
	}
	.head {
		display: flex;
		flex-wrap: wrap;
		justify-content: space-between;
		align-items: flex-start;
		gap: var(--space-md);
		margin-bottom: var(--space-lg);
	}
	.id {
		min-width: 0;
	}
	.id-row {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: var(--space-xs);
		margin-bottom: 6px;
	}
	.sep {
		color: var(--rule-strong);
	}
	.style {
		font-size: var(--text-xs);
		color: var(--ink-secondary);
		letter-spacing: 0.02em;
	}
	.title-btn {
		text-align: left;
		cursor: text;
		color: inherit;
	}
	.title {
		font-family: var(--font-display);
		font-size: clamp(1.5rem, 2.4vw, 2rem);
		font-weight: 700;
		line-height: 1.15;
		letter-spacing: -0.02em;
		color: var(--ink-primary);
	}
	.title-input {
		font-family: var(--font-display);
		font-size: var(--text-xl);
		font-weight: 700;
		width: min(100%, 32rem);
		color: var(--ink-primary);
		background-color: var(--bg-surface);
		border: 1px solid var(--accent);
		border-radius: 3px;
		padding: var(--space-2xs) var(--space-xs);
	}
	.err {
		display: block;
		font-size: var(--text-xs);
		color: var(--status-danger);
	}
	.sensor {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: var(--space-2xs);
	}
	.chip {
		display: inline-flex;
		align-items: center;
		gap: 7px;
		padding: 4px 10px;
		border: 1px solid var(--rule-hairline);
		border-radius: 2px;
		background-color: var(--bg-surface);
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
	}
	.chip-meta {
		color: var(--ink-muted);
		font-weight: 400;
	}
	.flag {
		font-family: var(--font-num);
		font-size: var(--text-xs);
		color: var(--status-warn);
	}
	.day {
		font-size: var(--text-xs);
		color: var(--ink-secondary);
	}
	.anomaly {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-xs) var(--space-sm);
		align-items: baseline;
		margin-bottom: var(--space-md);
		padding: var(--space-xs) var(--space-sm);
		border: 1px solid color-mix(in oklch, var(--status-warn) 45%, transparent);
		background-color: color-mix(in oklch, var(--status-warn) 8%, transparent);
		font-size: var(--text-sm);
		color: var(--ink-primary);
	}
	.a-tag {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--status-warn);
	}

	/* Readout grid */
	.matrix {
		display: grid;
		grid-template-columns: 1.35fr 1fr 1fr 1.25fr;
		border-top: 1px solid var(--rule-strong);
		border-bottom: 1px solid var(--rule-hairline);
		background-color: var(--bg-surface);
	}
	.cell {
		padding: var(--space-md);
		border-right: 1px solid var(--rule-hairline);
		display: flex;
		flex-direction: column;
		justify-content: space-between;
		gap: var(--space-xs);
		min-width: 0;
	}
	.cell:last-child {
		border-right: none;
	}
	.label {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-xs);
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--ink-muted);
	}
	.delta {
		font-size: 0.7rem;
		text-transform: none;
		letter-spacing: 0;
		color: var(--accent);
	}
	.primary {
		font-size: var(--text-inst);
		font-weight: 600;
		line-height: 1.05;
		color: var(--ink-primary);
	}
	.sub {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: var(--space-2xs) var(--space-xs);
		font-size: var(--text-xs);
		color: var(--ink-secondary);
		min-height: 1.5em;
	}
	.chamber {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		font-family: var(--font-num);
		font-size: 0.72rem;
		color: var(--temp-trace);
	}
	.chamber::before {
		content: '';
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background-color: var(--temp-trace);
	}
	.warn {
		color: var(--status-warn);
	}
	.raw {
		margin-top: var(--space-xs);
		font-size: var(--text-xs);
		color: var(--ink-muted);
	}
	@container (max-width: 680px) {
		.matrix {
			grid-template-columns: 1fr 1fr;
		}
		.cell:nth-child(2) {
			border-right: none;
		}
		.cell:nth-child(1),
		.cell:nth-child(2) {
			border-bottom: 1px solid var(--rule-hairline);
		}
		.primary {
			font-size: 1.75rem;
		}
	}

	.telemetry {
		padding-top: var(--space-lg);
	}

	.next {
		margin-top: var(--space-md);
		padding: var(--space-sm) var(--space-md);
		border: 1px solid var(--rule-hairline);
		background-color: var(--bg-elevated);
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-sm);
	}
	.next-left {
		display: flex;
		align-items: baseline;
		flex-wrap: wrap;
		gap: var(--space-xs) var(--space-sm);
	}
	.kicker {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--accent);
	}
	.next-detail {
		font-size: var(--text-sm);
		color: var(--ink-primary);
	}
	.next-timing {
		font-size: var(--text-xs);
		color: var(--ink-secondary);
	}
	.foot {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: var(--space-md);
		margin-top: var(--space-md);
	}
	.link {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-secondary);
		border-bottom: 1px solid transparent;
		padding-bottom: 1px;
		min-height: 28px;
		display: inline-flex;
		align-items: center;
		cursor: pointer;
	}
	.link:hover {
		color: var(--ink-primary);
		border-bottom-color: var(--accent);
	}

	@media (max-width: 760px) {
		.instrument {
			padding: var(--space-lg) var(--space-md);
		}
		.collapsed {
			padding: var(--space-sm) var(--space-md);
			grid-template-columns: auto auto minmax(0, 1fr) auto;
		}
		.c-fig,
		.c-day {
			display: none;
		}
	}
</style>
