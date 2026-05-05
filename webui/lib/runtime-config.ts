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
		cached = {
			apiBase: `${basePath}/api`,
			wsBase: `${typeof window !== 'undefined' ? (window.location.protocol === 'https:' ? 'wss:' : 'ws:') : 'ws:'}//${typeof window !== 'undefined' ? window.location.host : 'localhost'}${basePath}/api/v1/events`,
			basePath: basePath || '/',
		};
	}

	return cached as RuntimeConfig;
}
