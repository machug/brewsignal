<script lang="ts">
	interface FermentationStep {
		id: number;
		step_number: number;
		type: string;
		temp_c: number;
		time_days: number;
	}

	let { steps }: { steps: FermentationStep[] } = $props();

	// Sort by step number
	let sortedSteps = $derived([...steps].sort((a, b) => a.step_number - b.step_number));

	function formatType(type: string): string {
		const typeMap: Record<string, string> = {
			primary: 'Primary',
			secondary: 'Secondary',
			conditioning: 'Conditioning',
			lagering: 'Lagering',
		};
		return typeMap[type.toLowerCase()] || type.charAt(0).toUpperCase() + type.slice(1);
	}
</script>

{#if steps.length > 0}
	<div class="fermentation-schedule">
		<h3>Fermentation Schedule</h3>
		<div class="table-scroll">
			<table>
				<thead>
					<tr>
						<th class="idx">#</th>
						<th>Stage</th>
						<th class="num">Temp</th>
						<th class="num">Duration</th>
					</tr>
				</thead>
				<tbody>
					{#each sortedSteps as step, i}
						<tr>
							<td class="idx num">{i + 1}</td>
							<td class="name">{formatType(step.type)}</td>
							<td class="num">{step.temp_c.toFixed(0)}&thinsp;°C</td>
							<td class="num">{step.time_days}&thinsp;{step.time_days === 1 ? 'day' : 'days'}</td>
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

	th:first-child,
	td:first-child {
		padding-left: 0;
	}

	th:last-child,
	td:last-child {
		padding-right: 0;
	}

	@media (max-width: 760px) {
		table {
			min-width: 0;
			table-layout: auto;
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
