<script lang="ts">
	import { recipeUrl } from '$lib/urls';
	import { goto } from '$app/navigation';
	import { importRecipe } from '$lib/api';

	const MAX_FILE_SIZE = 1_000_000; // 1MB in bytes

	let uploading = $state(false);
	let error = $state<string | null>(null);
	let dragActive = $state(false);

	async function handleFileUpload(file: File) {
		error = null;

		// Validate file extension
		const filename = file.name.toLowerCase();
		const allowed = ['.xml', '.json', '.brewsignal'];
		if (!allowed.some((ext) => filename.endsWith(ext))) {
			error = 'Please upload a .xml, .json, or .brewsignal recipe file';
			return;
		}

		if (file.size > MAX_FILE_SIZE) {
			error = 'File must be smaller than 1MB';
			return;
		}

		uploading = true;

		try {
			const recipes = await importRecipe(file);
			// Redirect to first imported recipe or back to list
			if (recipes.length === 1) {
				goto(recipeUrl(recipes[0]));
			} else {
				goto('/recipes');
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to import recipe';
		} finally {
			uploading = false;
		}
	}

	function handleDrop(e: DragEvent) {
		e.preventDefault();
		dragActive = false;

		const file = e.dataTransfer?.files[0];
		if (file) {
			handleFileUpload(file);
		}
	}

	function handleDragOver(e: DragEvent) {
		e.preventDefault();
		dragActive = true;
	}

	function handleDragLeave() {
		dragActive = false;
	}

	function handleFileInput(e: Event) {
		const input = e.target as HTMLInputElement;
		const file = input.files?.[0];
		if (file) {
			handleFileUpload(file);
		}
	}

	function handleKeyDown(e: KeyboardEvent) {
		if (e.key === 'Enter' || e.key === ' ') {
			e.preventDefault();
			const fileInput = document.querySelector('.file-input') as HTMLInputElement;
			if (fileInput) {
				fileInput.click();
			}
		}
	}
</script>

<svelte:head>
	<title>Import Recipe | BrewSignal</title>
</svelte:head>

<div class="page-container">
	<div class="back-link">
		<a href="/recipes" class="back-btn">
			<svg class="back-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
			</svg>
			Back to Recipes
		</a>
	</div>

	<div class="import-container">
		<h1 class="page-title">Import Recipe</h1>
		<p class="page-description">
			Upload recipe files from Brewfather, BeerSmith, Brewer's Friend, or any brewing software
		</p>

		<div
			class="drop-zone"
			class:active={dragActive}
			class:uploading
			ondrop={handleDrop}
			ondragover={handleDragOver}
			ondragleave={handleDragLeave}
			onkeydown={handleKeyDown}
			role="button"
			tabindex="0"
			aria-label="Upload recipe file by dropping or clicking"
		>
			{#if uploading}
				<div class="spinner"></div>
				<p class="drop-text">Importing recipe...</p>
			{:else}
				<svg class="upload-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
					<path stroke-linecap="round" stroke-linejoin="round" d="M12 16V4m0 0L8 8m4-4l4 4M4 16v3a1 1 0 001 1h14a1 1 0 001-1v-3" />
				</svg>
				<p class="drop-text">Drop recipe file here</p>
				<p class="drop-subtext">or click to browse</p>
				<input
					type="file"
					accept=".xml,.json,.brewsignal"
					onchange={handleFileInput}
					class="file-input"
					disabled={uploading}
				/>
			{/if}
		</div>

		<div class="file-info">
			<p class="info-text">Supported: BeerXML (.xml), BeerJSON (.json), Brewfather JSON (.json), BrewSignal (.brewsignal) - max 1MB</p>
		</div>

		{#if error}
			<div class="error-box">
				<svg class="error-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
					/>
				</svg>
				<p class="error-text">{error}</p>
			</div>
		{/if}
	</div>
</div>

<style>
	.page-container {
		max-width: 640px;
		margin: 0 auto;
		padding: var(--space-lg);
	}

	.back-link {
		margin-bottom: var(--space-lg);
	}

	.back-btn {
		display: inline-flex;
		align-items: center;
		gap: var(--space-xs);
		min-height: 44px;
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--ink-secondary);
		text-decoration: none;
		transition: color var(--transition);
	}

	.back-btn:hover {
		color: var(--ink-primary);
	}

	.back-btn:focus-visible,
	.drop-zone:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.back-icon {
		width: 16px;
		height: 16px;
	}

	.import-container {
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
	}

	.page-title {
		font-family: var(--font-display);
		font-size: var(--text-xl);
		font-weight: 600;
		letter-spacing: -0.01em;
		line-height: 1.2;
		margin: 0;
		color: var(--ink-primary);
	}

	.page-description {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		margin: 0;
	}

	.drop-zone {
		position: relative;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: var(--space-xs);
		min-height: 220px;
		padding: var(--space-2xl) var(--space-lg);
		background: var(--bg-surface);
		border: 1px dashed var(--rule-strong);
		border-radius: 4px;
		cursor: pointer;
		text-align: center;
		transition: border-color var(--transition), background var(--transition);
	}

	.drop-zone:hover:not(.uploading) {
		border-color: var(--accent-rule);
		background: var(--bg-elevated);
	}

	.drop-zone.active {
		border-style: solid;
		border-color: var(--accent);
		background: var(--accent-tint);
	}

	.drop-zone.uploading {
		cursor: wait;
		opacity: 0.7;
	}

	.upload-icon {
		width: 40px;
		height: 40px;
		color: var(--ink-muted);
	}

	.drop-text {
		font-family: var(--font-display);
		font-size: var(--text-base);
		font-weight: 600;
		color: var(--ink-primary);
		margin: 0;
	}

	.drop-subtext {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		margin: 0;
	}

	.file-input {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		opacity: 0;
		cursor: pointer;
	}

	.file-input:disabled {
		cursor: wait;
	}

	.file-info {
		display: flex;
	}

	.info-text {
		font-size: var(--text-xs);
		color: var(--ink-muted);
		margin: 0;
		font-family: var(--font-num);
		line-height: 1.6;
	}

	.spinner {
		width: 28px;
		height: 28px;
		border: 2px solid var(--rule-strong);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.spinner {
			animation-duration: 2.4s;
		}
	}

	.error-box {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		padding: var(--space-sm) var(--space-md);
		background: var(--bg-surface);
		border: 1px solid var(--status-danger);
		border-radius: 4px;
	}

	.error-icon {
		width: 20px;
		height: 20px;
		color: var(--status-danger);
		flex-shrink: 0;
	}

	.error-text {
		font-size: var(--text-sm);
		color: var(--status-danger);
		margin: 0;
		overflow-wrap: anywhere;
	}

	@media (max-width: 760px) {
		.page-container {
			padding: var(--space-md);
		}
	}
</style>
