import withSerwistInit from '@serwist/next';
import createNextIntlPlugin from 'next-intl/plugin';

const withNextIntl = createNextIntlPlugin('./i18n.ts');

const withSerwist = withSerwistInit({
	swSrc: 'app/sw.ts',
	swDest: 'public/sw.js',
	disable: process.env.NODE_ENV === 'development',
});

/** @type {import('next').NextConfig} */
const basePathEnv = process.env.FLEET_BASE_PATH;
const nextConfig = {
	output: 'standalone',
	basePath: basePathEnv && basePathEnv !== '/' ? basePathEnv : '',
	images: {
		unoptimized: true,
	},
	headers: async () => [
		{
			source: '/(.*)',
			headers: [
				{ key: 'X-Content-Type-Options', value: 'nosniff' },
				{ key: 'X-Frame-Options', value: 'SAMEORIGIN' },
				{ key: 'X-XSS-Protection', value: '1; mode=block' },
				{ key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
			],
		},
	],
	serverExternalPackages: [],
};

export default withSerwist(withNextIntl(nextConfig));
