import adapterAuto from '@sveltejs/adapter-auto';
import adapterStatic from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

// Use static adapter for Pi builds, auto adapter for Vercel
const useStaticAdapter = process.env.BUILD_TARGET === 'pi';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),

	kit: {
		adapter: useStaticAdapter
			? adapterStatic({
					pages: '../backend/static',
					assets: '../backend/static',
					fallback: 'index.html'
				})
			: adapterAuto()
	}
};

export default config;
