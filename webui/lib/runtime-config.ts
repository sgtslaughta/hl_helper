'use client';

interface RuntimeConfig {
	apiBase: string;
	wsBase: string;
	basePath: string;
}

let cached: RuntimeConfig | null = null;

/**
 * Resolve runtime config. We deliberately skip a network round-trip and compute
 * relative URLs from window.location so the same image works across compose
 * (server:8000), AIO (127.0.0.1:8000), and reverse-proxy deployments without
 * rebuild. The Next.js proxy handler at /api/proxy/[...path] reads
 * INTERNAL_API_BASE at request time and forwards.
 */
export async function getRuntimeConfig(): Promise<RuntimeConfig> {
	if (cached) return cached;

	const basePath =
		typeof window !== 'undefined' && window.location.pathname.startsWith('/hl_helper')
			? '/hl_helper'
			: '';

	const protocol = typeof window !== 'undefined' ? window.location.protocol : 'http:';
	const host = typeof window !== 'undefined' ? window.location.host : 'localhost:3000';
	const wsProtocol = protocol === 'https:' ? 'wss:' : 'ws:';

	cached = {
		apiBase: `${basePath}/api/proxy`,
		// Origin only (no path). Callers append their own ws path, e.g.
		// `${wsBase}/api/proxy/v1/agents/<id>/terminal`.
		wsBase: `${wsProtocol}//${host}${basePath}`,
		basePath: basePath || '/',
	};
	return cached;
}
