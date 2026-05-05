import type { MetadataRoute } from 'next';

export default function manifest(): MetadataRoute.Manifest {
	return {
		name: 'hl_helper',
		short_name: 'hlh',
		description: 'Self-hosted fleet manager',
		start_url: '/',
		scope: '/',
		display: 'standalone',
		orientation: 'portrait-primary',
		theme_color: '#0f1216',
		background_color: '#0f1216',
		icons: [
			{
				src: '/icons/icon-192.png',
				sizes: '192x192',
				type: 'image/png',
				purpose: 'any',
			},
			{
				src: '/icons/icon-192-maskable.png',
				sizes: '192x192',
				type: 'image/png',
				purpose: 'maskable',
			},
			{
				src: '/icons/icon-512.png',
				sizes: '512x512',
				type: 'image/png',
				purpose: 'any',
			},
			{
				src: '/icons/icon-512-maskable.png',
				sizes: '512x512',
				type: 'image/png',
				purpose: 'maskable',
			},
		],
		categories: ['productivity', 'utilities'],
		screenshots: [
			{
				src: '/icons/screenshot-1.png',
				sizes: '540x720',
				type: 'image/png',
				form_factor: 'narrow',
			},
			{
				src: '/icons/screenshot-2.png',
				sizes: '1280x720',
				type: 'image/png',
				form_factor: 'wide',
			},
		],
	};
}
