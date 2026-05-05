'use client';

interface RuntimeConfig {
	apiBase: string;
	wsBase: string;
	basePath: string;
}

let cached: RuntimeConfig | null = null;

export async function getRuntimeConfig(): Promise<RuntimeConfig> {
	if (cached) return cached;

	try {
		const resp = await fetch('/_runtime-config.json');
		if (!resp.ok) throw new Error(`Failed to fetch runtime config: ${resp.status}`);
		cached = await resp.json();
	} catch {
		// Fallback to relative paths
		const basePath =
			typeof window !== 'undefined'
				? window.location.pathname.split('/').slice(0, -1).join('/')
				: '';
		// Route through the runtime proxy handler at /api/proxy/[...path].
		// It reads INTERNAL_API_BASE at request time, so the same image works
		// across compose (server:8000) + AIO (127.0.0.1:8000) without rebuild.
		cached = {
			apiBase: `${basePath}/api/proxy`,
			wsBase: `${typeof window !== 'undefined' ? (window.location.protocol === 'https:' ? 'wss:' : 'ws:') : 'ws:'}//${typeof window !== 'undefined' ? window.location.host : 'localhost'}${basePath}/api/proxy/v1/events`,
			basePath: basePath || '/',
		};
	}

	return cached as RuntimeConfig;
}
