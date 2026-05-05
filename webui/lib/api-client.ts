'use client';

import { ApiError, type ProblemDetail } from './error';
import { getRuntimeConfig } from './runtime-config';

interface FetchOptions extends RequestInit {
	idempotencyKey?: string;
}

function generateIdempotencyKey(): string {
	if (typeof globalThis !== 'undefined' && globalThis.crypto?.randomUUID) {
		return globalThis.crypto.randomUUID();
	}
	// Fallback: simple random string
	return Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
}

export async function apiFetch<T>(path: string, options: FetchOptions = {}): Promise<T> {
	const config = await getRuntimeConfig();
	const url = `${config.apiBase}${path}`;

	const headers: Record<string, string> = {
		'Content-Type': 'application/json',
		...(options.headers as Record<string, string> | undefined),
	};

	// Add idempotency key for POST/PATCH
	if ((options.method === 'POST' || options.method === 'PATCH') && !headers['Idempotency-Key']) {
		headers['Idempotency-Key'] = options.idempotencyKey || generateIdempotencyKey();
	}

	const resp = await fetch(url, {
		...options,
		headers,
		credentials: 'include', // Pass auth cookies
	});

	if (!resp.ok) {
		let problem: ProblemDetail | undefined;
		const contentType = resp.headers.get('content-type');

		try {
			if (
				contentType?.includes('application/json') ||
				contentType?.includes('application/problem+json')
			) {
				problem = await resp.json();
			} else {
				const text = await resp.text();
				problem = { title: text, status: resp.status };
			}
		} catch {
			problem = { title: 'Unknown error', status: resp.status };
		}

		throw new ApiError(
			resp.status,
			problem?.type || 'api_error',
			problem?.detail || problem?.title || `HTTP ${resp.status}`,
			problem,
		);
	}

	const contentType = resp.headers.get('content-type');
	if (contentType?.includes('application/json')) {
		return await resp.json();
	}

	return (await resp.text()) as T;
}
