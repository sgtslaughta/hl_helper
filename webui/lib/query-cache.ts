'use client';

import { QueryClient } from '@tanstack/react-query';

export function createQueryClient(): QueryClient {
	return new QueryClient({
		defaultOptions: {
			queries: {
				staleTime: 30 * 1000, // 30s
				gcTime: 5 * 60 * 1000, // 5min
				retry: failureCount => {
					if (failureCount > 3) return false;
					return true;
				},
				retryDelay: attemptIndex => {
					return Math.min(1000 * 2 ** attemptIndex, 30000) + Math.random() * 1000;
				},
				refetchOnWindowFocus: true,
				refetchOnReconnect: true,
			},
			mutations: {
				retry: 1,
				retryDelay: 500,
			},
		},
	});
}

// Helper to pause focus refetch when terminal is focused
export function pauseFocusRefetch(enabled: boolean): void {
	if (typeof document !== 'undefined') {
		if (enabled) {
			document.body.setAttribute('data-terminal-focused', 'true');
		} else {
			document.body.removeAttribute('data-terminal-focused');
		}
	}
}
