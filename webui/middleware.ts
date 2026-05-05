import { NextResponse } from 'next/server';

export function middleware() {
	const response = NextResponse.next();

	// Add security headers
	const nonce = crypto.randomUUID();
	response.headers.set(
		'Content-Security-Policy',
		[
			"default-src 'self'",
			`script-src 'self' 'nonce-${nonce}'`,
			`style-src 'self' 'nonce-${nonce}'`,
			"img-src 'self' data:",
			"font-src 'self'",
			"connect-src 'self' ws: wss:",
			"frame-ancestors 'self'",
		].join('; '),
	);

	response.headers.set('X-Content-Type-Options', 'nosniff');
	response.headers.set('X-Frame-Options', 'SAMEORIGIN');
	response.headers.set('X-XSS-Protection', '1; mode=block');
	response.headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');

	return response;
}

export const config = {
	matcher: ['/((?!_next/static|_next/image|favicon.ico|public).*)'],
};
