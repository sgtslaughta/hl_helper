import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

const PUBLIC_PATHS = new Set([
	'/login',
	'/onboarding',
	'/forgot-password',
	'/reset-password',
]);

function isAuthExempt(pathname: string): boolean {
	if (PUBLIC_PATHS.has(pathname)) return true;
	for (const p of PUBLIC_PATHS) {
		if (pathname.startsWith(`${p}/`)) return true;
	}
	return false;
}

const TOMBSTONE_SW = `// SW tombstone: unregister and clear caches, then surrender control.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => {
	e.waitUntil((async () => {
		const keys = await caches.keys();
		await Promise.all(keys.map((k) => caches.delete(k)));
		await self.registration.unregister();
		const cs = await self.clients.matchAll({ type: 'window' });
		for (const c of cs) { try { c.navigate(c.url); } catch {} }
	})());
});
self.addEventListener('fetch', () => {});
`;

export function middleware(request: NextRequest) {
	const { pathname } = request.nextUrl;

	// 0. Tombstone any previously installed Serwist SW. Old builds shipped a
	//    Workbox-style precache that intercepted authenticated navigations and
	//    served stale 307 redirects. Serve a self-unregistering stub so existing
	//    clients self-heal on next page load.
	if (pathname === '/sw.js') {
		return new NextResponse(TOMBSTONE_SW, {
			status: 200,
			headers: {
				'Content-Type': 'application/javascript; charset=utf-8',
				'Service-Worker-Allowed': '/',
				'Cache-Control': 'no-store',
			},
		});
	}

	// 1. Auth gate: shell routes require hls_session cookie. Redirect to /login otherwise.
	//    RSC payload + prefetch requests (`RSC: 1` / `Next-Router-Prefetch: 1`) must
	//    NOT be redirected — Next.js can't parse a 307 cross-origin opaque-redirect
	//    as a flight payload, surfacing a NetworkError to the user. Pass them
	//    through; the underlying API calls return 401 which api-client converts
	//    into a hard redirect to /login.
	const isRSC = request.headers.get('rsc') === '1' || request.headers.get('next-router-prefetch') === '1';
	const sessionCookie = request.cookies.get('hls_session');
	if (!sessionCookie && !isAuthExempt(pathname) && pathname !== '/api' && !isRSC) {
		const loginUrl = request.nextUrl.clone();
		loginUrl.pathname = '/login';
		if (pathname !== '/') loginUrl.searchParams.set('next', pathname);
		return NextResponse.redirect(loginUrl);
	}

	// 2. Security headers. CSP is permissive by design so Next 15 inline boot
	//    scripts run. Hostile injection is mitigated by HttpOnly session cookies,
	//    SameSite=lax, X-Frame-Options, and frame-ancestors. Production should
	//    front the app with HTTPS via reverse proxy (caddy/nginx/traefik) which
	//    sets HSTS and tightens further.
	const csp = [
		"default-src 'self'",
		"script-src 'self' 'unsafe-inline' 'unsafe-eval'",
		"style-src 'self' 'unsafe-inline'",
		"img-src 'self' data: blob:",
		"font-src 'self' data:",
		"connect-src 'self' ws: wss: http: https:",
		"frame-ancestors 'none'",
		"frame-src 'none'",
		"base-uri 'self'",
		"form-action 'self'",
		"object-src 'none'",
	].join('; ');

	const response = NextResponse.next();
	response.headers.set('Content-Security-Policy', csp);
	response.headers.set('X-Content-Type-Options', 'nosniff');
	response.headers.set('X-Frame-Options', 'DENY');
	response.headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');
	response.headers.set('Permissions-Policy', 'geolocation=(), microphone=(), camera=()');
	// Cache-Control intentionally not set here. Firefox aborts RSC stream parsing
	// ("TypeError: Error in input stream") when no-store collides with Next's
	// x-nextjs-cache: HIT prerender semantics, and browser detection of RSC vs
	// HTML at the middleware layer is unreliable (Next strips/normalizes the
	// rsc header in some flight modes). Let Next own caching; the SW tombstone
	// + storage clear is the migration path for stale precaches.

	// HSTS only when client identifies HTTPS (reverse proxy adds X-Forwarded-Proto)
	const forwardedProto = request.headers.get('x-forwarded-proto');
	if (forwardedProto === 'https' || request.nextUrl.protocol === 'https:') {
		response.headers.set('Strict-Transport-Security', 'max-age=63072000; includeSubDomains; preload');
	}

	return response;
}

export const config = {
	matcher: [
		'/sw.js',
		'/((?!api|_next/static|_next/image|favicon.ico|icons|manifest.webmanifest|robots.txt).*)',
	],
};
