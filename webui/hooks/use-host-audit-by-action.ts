'use client';

import { apiFetch } from '@/lib/api-client';
import { useQuery } from '@tanstack/react-query';

export interface AuditEntry {
	sequence: number;
	timestamp: string;
	actor: string;
	action: string;
	subject: string | null;
	payload: Record<string, unknown>;
}

interface AuditPage {
	items: AuditEntry[];
	next_cursor: string | null;
}

export function useHostAuditByAction(hostId: string, action: string, limit = 10) {
	return useQuery<AuditEntry[]>({
		queryKey: ['hosts', hostId, 'audit', action],
		queryFn: async () => {
			const url = `/v1/audit?subject=${encodeURIComponent(hostId)}&action=${encodeURIComponent(action)}&limit=${limit}`;
			const page = await apiFetch<AuditPage>(url);
			return page.items;
		},
		refetchInterval: 30_000,
		enabled: !!hostId,
	});
}
