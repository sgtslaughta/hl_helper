import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
	plugins: [react()],
	test: {
		environment: 'jsdom',
		globals: true,
		include: ['tests/unit/**/*.test.{ts,tsx}'],
		setupFiles: ['./tests/unit/setup.ts'],
		coverage: {
			provider: 'v8',
			reporter: ['text', 'json', 'html'],
			exclude: ['node_modules/', 'tests/', '.next/'],
		},
	},
	resolve: {
		alias: {
			'@': '/home/user/code/hl_helper/webui',
		},
	},
});
