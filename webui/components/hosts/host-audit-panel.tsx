'use client';

import { EmptyState } from '@/components/empty-states/empty-state';
import { BlueprintSkeleton } from '@/components/skeletons/blueprint-skeleton';
import { apiFetch } from '@/lib/api-client';
import { useQuery } from '@tanstack/react-query';

interface AuditEntryOut {
	sequence: number;
	timestamp: string;
	actor: string;
	action: string;
	subject: string | null;
	payload: Record<string, unknown>;
	prev_hash: string;
	entry_hash: string;
}

interface AuditPageResponse {
	items: AuditEntryOut[];
	next_cursor: string | null;
}

export function HostAuditPanel({ hostId }: { hostId: string }) {
	const q = useQuery<AuditPageResponse>({
		queryKey: ['hosts', hostId, 'audit'],
		queryFn: () =>
			apiFetch<AuditPageResponse>(`/v1/audit?subject=${encodeURIComponent(hostId)}&limit=50`),
	});

	if (q.isLoading) return <BlueprintSkeleton rows={6} />;
	if (q.isError) return <EmptyState title="Failed to load audit" description="Try again." />;
	if (!q.data?.items || q.data.items.length === 0)
		return (
			<EmptyState title="No audit entries" description="Actions on this host will appear here." />
		);

	return (
		<div className="rounded border border-hairline bg-surface overflow-hidden">
			<table className="w-full text-sm">
				<thead className="border-b border-hairline bg-surface-2">
					<tr>
						<th className="px-4 py-2 text-left font-semibold text-text">Time</th>
						<th className="px-4 py-2 text-left font-semibold text-text">Actor</th>
						<th className="px-4 py-2 text-left font-semibold text-text">Action</th>
						<th className="px-4 py-2 text-left font-semibold text-text">Subject</th>
					</tr>
				</thead>
				<tbody>
					{q.data.items.map(entry => (
						<tr key={entry.sequence} className="border-b border-hairline">
							<td className="px-4 py-2 text-text-dim font-mono text-xs">
								{new Date(entry.timestamp).toLocaleString()}
							</td>
							<td className="px-4 py-2 text-text">{entry.actor}</td>
							<td className="px-4 py-2 text-text">{entry.action}</td>
							<td className="px-4 py-2 text-text-dim">{entry.subject || '—'}</td>
						</tr>
					))}
				</tbody>
			</table>
		</div>
	);
}
