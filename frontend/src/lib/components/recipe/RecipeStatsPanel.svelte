<script lang="ts">
	import { srmToHex, srmToDescription, calculateBUGU, calculateCalories } from '$lib/brewing';

	interface Props {
		og?: number;
		fg?: number;
		abv?: number;
		ibu?: number;
		colorSrm?: number;
		batchSizeLiters?: number;
	}

	let { og = 1.050, fg = 1.010, abv = 5.0, ibu = 30, colorSrm = 8, batchSizeLiters = 20 }: Props = $props();

	// Derived calculations
	let colorHex = $derived(srmToHex(colorSrm));
	let colorDesc = $derived(srmToDescription(colorSrm));
	let buguRatio = $derived(ibu && og ? calculateBUGU(ibu, og) : 0);
	let calories = $derived(og && fg ? calculateCalories(og, fg) : 0);

	// Balance description based on BU:GU ratio
	let balanceDesc = $derived.by(() => {
		if (buguRatio < 0.3) return 'Very Sweet';
		if (buguRatio < 0.5) return 'Malty';
		if (buguRatio < 0.7) return 'Balanced';
		if (buguRatio < 0.9) return 'Hoppy';
		return 'Very Bitter';
	});
</script>

<div class="stats-panel">
	<div class="beer-hero">
		<div class="beer-preview" aria-hidden="true">
			<div class="beer-glow" style="--beer-color: {colorHex}"></div>
			<div class="beer-glass" style="--beer-color: {colorHex}">
				<div class="beer-foam">
					<div class="foam-bubble"></div>
					<div class="foam-bubble"></div>
					<div class="foam-bubble"></div>
				</div>
				<div class="beer-liquid">
					<div class="carbonation">
						<span class="bubble"></span>
						<span class="bubble"></span>
						<span class="bubble"></span>
						<span class="bubble"></span>
						<span class="bubble"></span>
					</div>
				</div>
				<div class="beer-gloss"></div>
				<div class="condensation"></div>
			</div>
		</div>
		<div class="beer-meta">
			<span class="stat-label">Color</span>
			<span class="stat-value">{colorSrm.toFixed(0)} SRM</span>
			<span class="stat-sub">{colorDesc}</span>
		</div>
	</div>

	<div class="stats-grid">
		<div class="stat-group">
			<div class="stat">
				<span class="stat-label">OG</span>
				<span class="stat-value">{og.toFixed(3)}</span>
			</div>
			<div class="stat">
				<span class="stat-label">FG</span>
				<span class="stat-value">{fg.toFixed(3)}</span>
			</div>
			<div class="stat">
				<span class="stat-label">ABV</span>
				<span class="stat-value">{abv.toFixed(1)}%</span>
			</div>
		</div>

		<div class="stat-group">
			<div class="stat">
				<span class="stat-label">IBU</span>
				<span class="stat-value">{ibu.toFixed(0)}</span>
			</div>
			<div class="stat">
				<span class="stat-label">BU:GU</span>
				<span class="stat-value balance">{buguRatio.toFixed(2)}</span>
				<span class="stat-sub">{balanceDesc}</span>
			</div>
		</div>

		<div class="stat-group">
			<div class="stat">
				<span class="stat-label">Calories</span>
				<span class="stat-value">{calories}</span>
				<span class="stat-sub">per 330ml</span>
			</div>
		</div>
	</div>
</div>

<style>
	.stats-panel {
		display: grid;
		grid-template-columns: auto 1fr;
		align-items: center;
		gap: var(--space-4);
		padding: var(--space-4) var(--space-5);
		background: var(--bg-elevated);
		background-image:
			linear-gradient(135deg, rgba(245, 158, 11, 0.12), rgba(24, 24, 27, 0) 65%),
			var(--recipe-grain-texture);
		background-size: cover, 8px 8px;
		border: 1px solid var(--border-subtle);
		border-radius: 12px;
		box-shadow: 0 8px 20px rgba(0, 0, 0, 0.4);
		overflow: hidden;
	}

	.stats-grid {
		display: flex;
		flex-wrap: nowrap;
		gap: var(--space-2);
		align-items: center;
	}

	.beer-hero {
		display: flex;
		align-items: center;
		gap: var(--space-3);
	}

	.beer-preview {
		position: relative;
		display: flex;
		align-items: flex-end;
		justify-content: center;
		min-width: 80px;
		padding: 8px;
	}

	.beer-glow {
		position: absolute;
		inset: 0;
		background: radial-gradient(ellipse at center bottom, var(--beer-color), transparent 70%);
		opacity: 0.35;
		filter: blur(20px);
		pointer-events: none;
		transition: opacity 0.4s ease;
	}

	.beer-glass {
		position: relative;
		width: 60px;
		height: 90px;
		border-radius: 12px 12px 8px 8px;
		border: 1.5px solid var(--recipe-glass-border);
		background: linear-gradient(135deg, rgba(255, 255, 255, 0.08) 0%, var(--recipe-glass) 50%, rgba(0, 0, 0, 0.15) 100%);
		box-shadow:
			inset 0 2px 0 rgba(255, 255, 255, 0.25),
			inset 0 -4px 12px rgba(0, 0, 0, 0.3),
			0 16px 32px rgba(0, 0, 0, 0.45),
			0 4px 8px rgba(0, 0, 0, 0.25);
		overflow: hidden;
		transition: transform 0.3s ease, box-shadow 0.3s ease;
	}

	.beer-glass:hover {
		transform: translateY(-2px);
		box-shadow:
			inset 0 2px 0 rgba(255, 255, 255, 0.3),
			inset 0 -4px 12px rgba(0, 0, 0, 0.3),
			0 20px 40px rgba(0, 0, 0, 0.5),
			0 6px 12px rgba(0, 0, 0, 0.3);
	}

	.beer-liquid {
		position: absolute;
		bottom: 0;
		left: 0;
		right: 0;
		height: 74%;
		background:
			linear-gradient(180deg, rgba(255, 255, 255, 0.2) 0%, transparent 20%, rgba(0, 0, 0, 0.25) 100%),
			var(--beer-color);
		transition: background 0.5s ease;
	}

	.carbonation {
		position: absolute;
		bottom: 0;
		left: 0;
		right: 0;
		height: 100%;
		pointer-events: none;
	}

	.carbonation .bubble {
		position: absolute;
		bottom: 0;
		width: 3px;
		height: 3px;
		background: rgba(255, 255, 255, 0.5);
		border-radius: 50%;
		animation: rise 3s ease-in infinite;
	}

	.carbonation .bubble:nth-child(1) { left: 20%; animation-delay: 0s; animation-duration: 2.5s; }
	.carbonation .bubble:nth-child(2) { left: 40%; animation-delay: 0.5s; animation-duration: 3s; }
	.carbonation .bubble:nth-child(3) { left: 55%; animation-delay: 1s; animation-duration: 2.8s; }
	.carbonation .bubble:nth-child(4) { left: 70%; animation-delay: 1.5s; animation-duration: 3.2s; }
	.carbonation .bubble:nth-child(5) { left: 30%; animation-delay: 2s; animation-duration: 2.6s; }

	@keyframes rise {
		0% {
			transform: translateY(0) scale(1);
			opacity: 0;
		}
		10% {
			opacity: 0.6;
		}
		90% {
			opacity: 0.3;
		}
		100% {
			transform: translateY(-70px) scale(0.5);
			opacity: 0;
		}
	}

	.beer-foam {
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
		height: 22%;
		background:
			radial-gradient(ellipse at 30% 60%, rgba(255, 255, 255, 0.95) 0%, transparent 60%),
			radial-gradient(ellipse at 70% 40%, rgba(255, 255, 255, 0.9) 0%, transparent 50%),
			var(--recipe-foam);
		box-shadow:
			inset 0 -3px 8px var(--recipe-foam-shadow),
			inset 0 2px 4px rgba(255, 255, 255, 0.4);
		border-bottom: 1px solid rgba(139, 90, 43, 0.3);
	}

	.foam-bubble {
		position: absolute;
		background: rgba(255, 255, 255, 0.7);
		border-radius: 50%;
		box-shadow: inset 0 -1px 2px rgba(0, 0, 0, 0.1);
	}

	.foam-bubble:nth-child(1) { width: 8px; height: 6px; top: 40%; left: 15%; }
	.foam-bubble:nth-child(2) { width: 10px; height: 7px; top: 50%; left: 55%; }
	.foam-bubble:nth-child(3) { width: 6px; height: 5px; top: 35%; left: 75%; }

	.beer-gloss {
		position: absolute;
		top: 10%;
		left: 10%;
		width: 30%;
		height: 75%;
		border-radius: 14px;
		background: linear-gradient(180deg, rgba(255, 255, 255, 0.6) 0%, rgba(255, 255, 255, 0.1) 40%, transparent 100%);
		opacity: 0.65;
		pointer-events: none;
	}

	.condensation {
		position: absolute;
		inset: 0;
		pointer-events: none;
	}

	.condensation::before,
	.condensation::after {
		content: '';
		position: absolute;
		background: rgba(255, 255, 255, 0.5);
		border-radius: 50%;
		box-shadow: 0 1px 1px rgba(0, 0, 0, 0.15);
	}

	.condensation::before {
		width: 4px;
		height: 6px;
		top: 45%;
		right: 12%;
	}

	.condensation::after {
		width: 3px;
		height: 4px;
		top: 62%;
		right: 18%;
	}

	.beer-meta {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.stat-group {
		display: flex;
		gap: var(--space-3);
		padding: 0 var(--space-2);
		border-right: 1px solid rgba(255, 255, 255, 0.06);
	}

	.stat-group:last-child {
		border-right: none;
	}

	.stat {
		display: flex;
		flex-direction: column;
		align-items: center;
		min-width: 48px;
		padding: var(--space-1) var(--space-2);
		border-radius: 8px;
		transition: background 0.2s ease;
	}

	.stat:hover {
		background: rgba(255, 255, 255, 0.04);
	}

	.stat-label {
		font-size: 9px;
		font-weight: 700;
		color: var(--text-tertiary);
		text-transform: uppercase;
		letter-spacing: 0.8px;
		margin-bottom: 2px;
	}

	.stat-value {
		font-size: 18px;
		font-weight: 700;
		color: var(--text-primary);
		font-family: var(--font-mono);
		text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
	}

	.stat-value.balance {
		color: var(--positive);
		text-shadow: 0 0 12px rgba(34, 197, 94, 0.4);
	}

	.stat-sub {
		font-size: 10px;
		color: var(--text-tertiary);
		font-weight: 500;
	}

	/* Responsive */
	@media (max-width: 768px) {
		.stats-panel {
			grid-template-columns: 1fr;
			gap: var(--space-3);
			padding: var(--space-3);
		}

		.beer-hero {
			justify-content: center;
		}

		.beer-preview {
			min-width: 70px;
			padding: 6px;
		}

		.beer-glass {
			width: 50px;
			height: 75px;
		}

		.stats-grid {
			justify-content: center;
			flex-wrap: wrap;
		}

		.stat-group {
			padding: 0 var(--space-2);
			gap: var(--space-2);
		}

		.stat {
			min-width: 42px;
		}

		.stat-value {
			font-size: 14px;
		}
	}
</style>
