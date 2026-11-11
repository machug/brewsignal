<script lang="ts">
	interface MashStep {
		id: number;
		step_number: number;
		name: string;
		type: string;
		temp_c: number;
		time_minutes: number;
		ramp_time_minutes?: number;
	}

	let { steps }: { steps: MashStep[] } = $props();

	// Sort by step number
	let sortedSteps = $derived([...steps].sort((a, b) => a.step_number - b.step_number));

	function formatType(type: string): string {
		const typeMap: Record<string, string> = {
			temperature: 'Temperature',
			infusion: 'Infusion',
			decoction: 'Decoction',
		};
		return typeMap[type.toLowerCase()] || type;
	}
</script>

{#if steps.length > 0}
	<div class="mash-schedule">
		<h3>Mash Schedule</h3>
		<div class="table-scroll">
			<table>
				<thead>
					<tr>
						<th class="idx col-sec">#</th>
						<th>Step</th>
						<th class="col-sec">Type</th>
						<th class="num">Temp</th>
						<th class="num">Time</th>
						<th class="num">Ramp</th>
					</tr>
				</thead>
				<tbody>
					{#each sortedSteps as step, i}
						<tr>
							<td class="idx num col-sec">{i + 1}</td>
							<td class="name">{step.name}<div class="sec-inline">{formatType(step.type)}</div></td>
							<td class="type col-sec">{formatType(step.type)}</td>
							<td class="num">{step.temp_c.toFixed(0)}&thinsp;°C</td>
							<td class="num">{step.time_minutes}&thinsp;min</td>
							<td class="num">{step.ramp_time_minutes ? `${step.ramp_time_minutes}\u2009min` : '--'}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	</div>
{/if}

<style>
	h3 {
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-secondary);
		text-transform: uppercase;
		letter-spacing: 0.1em;
		margin: 0 0 var(--space-sm) 0;
	}

	.table-scroll {
		overflow-x: auto;
	}

	table {
		width: 100%;
		min-width: 360px;
		border-collapse: collapse;
	}

	th {
		text-align: left;
		padding: var(--space-xs) var(--space-sm);
		border-bottom: 1px solid var(--rule-strong);
		font-size: var(--text-xs);
		color: var(--ink-muted);
		text-transform: uppercase;
		letter-spacing: 0.08em;
		font-weight: 600;
		white-space: nowrap;
	}

	td {
		padding: var(--space-xs) var(--space-sm);
		border-bottom: 1px solid var(--rule-hairline);
		font-size: var(--text-sm);
		color: var(--ink-primary);
	}

	.num {
		text-align: right;
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		white-space: nowrap;
	}

	th.num {
		font-family: var(--font-body);
	}

	.idx {
		width: 2.5rem;
		color: var(--ink-muted);
	}

	.name {
		font-weight: 600;
	}

	.type {
		color: var(--ink-secondary);
		text-transform: capitalize;
	}

	th:first-child,
	td:first-child {
		padding-left: 0;
	}

	th:last-child,
	td:last-child {
		padding-right: 0;
	}

	.sec-inline {
		display: none;
		color: var(--ink-muted);
		font-size: var(--text-xs);
		font-weight: 400;
		margin-top: 2px;
		text-transform: capitalize;
	}

	@media (max-width: 760px) {
		table {
			min-width: 0;
			table-layout: auto;
		}

		.col-sec {
			display: none;
		}

		.sec-inline {
			display: block;
		}

		th,
		td {
			padding-inline: var(--space-xs);
		}

		th:first-child,
		td:first-child {
			padding-left: 0;
		}

		th:last-child,
		td:last-child {
			padding-right: 0;
		}
	}
</style>
