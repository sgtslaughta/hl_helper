import { type NextRequest, NextResponse } from 'next/server';

const FASTAPI_BASE = process.env.INTERNAL_API_BASE || 'http://127.0.0.1:8000';

async function handler(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
	const params = await ctx.params;
	const path = (params.path || []).join('/');
	const url = new URL(req.url);
	const query = url.search;

	const targetUrl = `${FASTAPI_BASE}/${path}${query}`;

	const headers = new Headers(req.headers);
	headers.delete('host');
	headers.delete('x-forwarded-host');
	headers.delete('x-forwarded-proto');
	headers.delete('x-forwarded-for');
	headers.delete('x-forwarded-prefix');

	// Preserve cookies and auth
	const cookie = req.headers.get('cookie');
	if (cookie) headers.set('cookie', cookie);

	const auth = req.headers.get('authorization');
	if (auth) headers.set('authorization', auth);

	// Forward X-Forwarded-* if trusted
	const xForwardedHost = req.headers.get('x-forwarded-host');
	const xForwardedProto = req.headers.get('x-forwarded-proto');
	const xForwardedFor = req.headers.get('x-forwarded-for');

	if (xForwardedHost) headers.set('x-forwarded-host', xForwardedHost);
	if (xForwardedProto) headers.set('x-forwarded-proto', xForwardedProto);
	if (xForwardedFor) headers.set('x-forwarded-for', xForwardedFor);

	try {
		const response = await fetch(targetUrl, {
			method: req.method,
			headers,
			body: req.method !== 'GET' && req.method !== 'HEAD' ? req.body : undefined,
		});

		const clonedResponse = response.clone();
		return new NextResponse(clonedResponse.body, {
			status: response.status,
			statusText: response.statusText,
			headers: response.headers,
		});
	} catch (error) {
		return NextResponse.json(
			{
				error: 'Failed to proxy request',
				detail: error instanceof Error ? error.message : 'Unknown error',
			},
			{ status: 502 },
		);
	}
}

export const GET = handler;
export const POST = handler;
export const PATCH = handler;
export const PUT = handler;
export const DELETE = handler;
export const HEAD = handler;
export const OPTIONS = handler;
