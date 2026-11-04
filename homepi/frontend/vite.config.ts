import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [
		tailwindcss(),
		// Static SPA: FastAPI serves build/ and falls back to index.html.
		sveltekit({ adapter: adapter({ pages: 'build', assets: 'build', fallback: 'index.html' }) })
	],
	server: {
		// `bun run dev` talks to a local backend on :8090.
		proxy: { '/api': { target: 'http://127.0.0.1:8090', ws: true } }
	}
});
