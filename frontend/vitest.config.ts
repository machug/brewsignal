import { defineConfig } from 'vitest/config';
import path from 'node:path';

// Standalone config: pure-TS unit tests only (no Svelte components), so we
// deliberately skip vite.config.ts and its SvelteKit plugin.
export default defineConfig({
	resolve: {
		alias: {
			$lib: path.resolve(__dirname, 'src/lib'),
		},
	},
	test: {
		include: ['src/**/*.test.ts'],
		environment: 'node',
	},
});
