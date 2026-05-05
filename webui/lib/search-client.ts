'use client';

// TODO: MeiliSearch client wrapper
// Wire: POST /api/v1/search with {indices, query, filters, limit}

export interface SearchResult {
	id: string;
	title: string;
	type: string;
	score: number;
}

export async function search(
	query: string,
	indices: string[] = ['hosts', 'tasks', 'docs'],
): Promise<SearchResult[]> {
	// Placeholder
	console.log('Search not yet wired:', query, indices);
	return [];
}
