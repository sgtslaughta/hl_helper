import withSerwistInit from '@serwist/next';

// Service worker disabled across all envs. Serwist's runtimeCaching intercepts
// authenticated navigations and serves stale 307 redirects, breaking login.
// Re-enable with FLEET_PWA=1 once cache strategy filters auth-cookie routes.
const withSerwist = withSerwistInit({
	swSrc: 'app/sw.ts',
	swDest: 'public/sw.js',
	disable: process.env.FLEET_PWA !== '1',
});

/** @type {import('next').NextConfig} */
const basePathEnv = process.env.FLEET_BASE_PATH;
const nextConfig = {
	output: 'standalone',
	basePath: basePathEnv && basePathEnv !== '/' ? basePathEnv : '',
	images: {
		unoptimized: true,
	},
	// Allow LAN-IP access during dev (e.g. http://192.168.1.196:3000) so the
	// dev server serves /_next/* chunks without the "Cross origin request
	// detected" warning escalating into a chunk-load failure.
	allowedDevOrigins: process.env.FLEET_ALLOWED_DEV_ORIGINS
		? process.env.FLEET_ALLOWED_DEV_ORIGINS.split(',').map((s) => s.trim())
		: ['localhost', '127.0.0.1', '0.0.0.0', '*.local', '192.168.0.0/16', '10.0.0.0/8'],
	// Security headers are set in middleware.ts so they vary per-request
	// (HSTS only on HTTPS, CSP nonce, etc.). Keep next.config bare.
	serverExternalPackages: [],
};

export default withSerwist(nextConfig);
