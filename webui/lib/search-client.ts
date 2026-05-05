'use client';

import { useQuery } from '@tanstack/react-query';
import { Meilisearch } from 'meilisearch';
import { getRuntimeConfig } from './runtime-config';

/**
 * Search result type returned from unified search across multiple indices.
 */
export interface SearchResult {
	index: string;
	hit: Record<string, unknown>;
	highlights?: Record<string, string>;
	score?: number;
}

/**
 * Client for MeiliSearch integration.
 * Uses backend proxy route for RBAC enforcement.
 */
export class SearchClient {
	private client: Meilisearch | null = null;

	constructor(
		private host: string,
		private apiKey: string,
	) {}

	/**
	 * Get or create the MeiliSearch client (for direct access, not preferred).
	 * Prefer using the /api/proxy/v1/search backend route instead.
	 */
	private getClient(): Meilisearch {
		if (!this.client) {
			this.client = new Meilisearch({
				host: this.host,
				apiKey: this.apiKey,
			});
		}
		return this.client;
	}

	/**
	 * Search across multiple indices via backend proxy.
	 * Contract: POST /api/proxy/v1/search with {indices, query, filters, limit}
	 * Backend enforces RBAC before querying MeiliSearch.
	 */
	async search(
		indices: string[],
		query: string,
		opts?: { limit?: number; filters?: Record<string, string> },
	): Promise<SearchResult[]> {
		const config = await getRuntimeConfig();
		const limit = opts?.limit ?? 10;

		const response = await fetch(`${config.apiBase}/proxy/v1/search`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			credentials: 'include',
			body: JSON.stringify({
				indices,
				query,
				filters: opts?.filters,
				limit,
			}),
		});

		if (!response.ok) {
			throw new Error(`Search failed: ${response.statusText}`);
		}

		const results = await response.json();
		return results as SearchResult[];
	}

	/**
	 * Direct MeiliSearch access (bypasses RBAC).
	 * Only use for non-sensitive queries or when RBAC is not required.
	 */
	async directSearch(
		index: string,
		query: string,
		opts?: { limit?: number },
	): Promise<SearchResult[]> {
		const client = this.getClient();
		const idx = client.index(index);

		const searchResult = await idx.search(query, {
			limit: opts?.limit ?? 10,
		});

		return searchResult.hits.map((hit: Record<string, unknown>) => ({
			index,
			hit,
			score: (hit as Record<string, number>)._rankingScore,
		}));
	}
}

/**
 * Factory function to get configured MeiliSearch client from runtime config.
 * Returns null if Meilisearch is not configured.
 */
export async function getMeiliClient(): Promise<SearchClient | null> {
	// TODO: Add meiliHost and meiliApiKey to RuntimeConfig when backend exposes them
	const host = process.env.NEXT_PUBLIC_MEILI_HOST || 'http://localhost:7700';
	const apiKey = process.env.NEXT_PUBLIC_MEILI_API_KEY || '';

	if (!host || !apiKey) {
		return null;
	}

	return new SearchClient(host, apiKey);
}

/**
 * React hook for searching via backend proxy route.
 * Returns query results, loading state, and error.
 */
export function useSearch(query: string, indices: string[]) {
	return useQuery({
		queryKey: ['search', { query, indices }],
		queryFn: async () => {
			if (!query.trim()) {
				return [];
			}

			const client = new SearchClient('', ''); // Host/key unused for proxy route
			return client.search(indices, query, { limit: 10 });
		},
		enabled: !!query.trim(),
		staleTime: 5 * 60 * 1000, // 5 minutes
	});
}
