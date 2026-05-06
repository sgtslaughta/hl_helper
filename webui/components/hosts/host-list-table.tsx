'use client';

import { EmptyState } from '@/components/empty-states/empty-state';
import { ActiveHostRow } from '@/components/hosts/active-host-row';
import { PendingHostRow } from '@/components/hosts/pending-host-row';
import { BlueprintSkeleton } from '@/components/skeletons/blueprint-skeleton';
import { type PendingToken, listPendingTokens } from '@/lib/api/enrollment';
import { type Host, listHosts } from '@/lib/api/hosts';
import { useQuery } from '@tanstack/react-query';

interface Props {
	status: string;
	search: string;
	onEnroll: () => void;
}

export function HostListTable({ status, search, onEnroll }: Props) {
	const hostsQ = useQuery<Host[]>({
		queryKey: ['hosts', status, search],
		queryFn: () => listHosts({ status, search }),
	});
	const pendingQ = useQuery<PendingToken[]>({
		queryKey: ['enrollment-tokens'],
		queryFn: listPendingTokens,
		refetchInterval: 30_000,
	});

	if (hostsQ.isLoading || pendingQ.isLoading) return <BlueprintSkeleton rows={8} />;
	if (hostsQ.isError)
		return <EmptyState title="Failed to load hosts" description="Please try again" />;

	const hosts = hostsQ.data ?? [];
	const pending = pendingQ.data ?? [];

	if (hosts.length === 0 && pending.length === 0) {
		return (
			<EmptyState
				title="No hosts yet"
				description="Get started by enrolling your first host"
				action={{ label: 'Enroll host', onClick: onEnroll }}
			/>
		);
	}

	return (
		<div className="rounded border border-hairline bg-surface overflow-hidden">
			<table className="w-full text-sm">
				<thead className="border-b border-hairline bg-surface-2">
					<tr>
						<th className="px-4 py-3 text-left font-semibold text-text">Name</th>
						<th className="px-4 py-3 text-left font-semibold text-text">OS</th>
						<th className="px-4 py-3 text-left font-semibold text-text">Version</th>
						<th className="px-4 py-3 text-left font-semibold text-text">Status</th>
						<th className="px-4 py-3 text-left font-semibold text-text">Last seen</th>
						<th className="px-4 py-3 text-right font-semibold text-text">Actions</th>
					</tr>
				</thead>
				<tbody>
					{pending.map(t => (
						<PendingHostRow key={t.id} token={t} />
					))}
					{hosts.map(h => (
						<ActiveHostRow key={h.id} host={h} />
					))}
				</tbody>
			</table>
		</div>
	);
}
