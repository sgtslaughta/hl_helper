'use client';

export const dynamic = 'force-dynamic';

import { EmptyState } from '@/components/empty-states/empty-state';
import { HostFilters } from '@/components/hosts/host-filters';
import { HostRow } from '@/components/hosts/host-row';
import { BlueprintSkeleton } from '@/components/skeletons/blueprint-skeleton';
import { apiFetch } from '@/lib/api-client';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

interface Host {
	id: string;
	name: string;
	status: 'healthy' | 'warning' | 'critical';
	os: string;
	version: string;
	lastSeen?: string;
}

export default function HostsPage() {
	const [status, setStatus] = useState('all');
	const [search, setSearch] = useState('');

	const { data, isLoading, isError } = useQuery({
		queryKey: ['hosts', status, search],
		queryFn: async () => {
			const params = new URLSearchParams();
			if (status !== 'all') params.append('status', status);
			if (search) params.append('search', search);
			return apiFetch<Host[]>(`/v1/hosts?${params}`);
		},
	});

	if (isLoading) return <BlueprintSkeleton rows={8} />;
	if (isError || !data)
		return <EmptyState title="Failed to load hosts" description="Please try again" />;
	if (data.length === 0)
		return <EmptyState title="No hosts found" description="Get started by connecting a host" />;

	return (
		<div className="p-4">
			<div className="mb-6">
				<h1 className="text-h2 font-bold text-text mb-2">Hosts</h1>
				<p className="text-text-dim">Manage infrastructure endpoints</p>
			</div>

			<HostFilters onStatusChange={setStatus} onSearch={setSearch} />

			<div className="rounded border border-hairline bg-surface overflow-hidden">
				<table className="w-full text-sm">
					<thead className="border-b border-hairline bg-surface-2">
						<tr>
							<th className="px-4 py-3 text-left font-semibold text-text">Name</th>
							<th className="px-4 py-3 text-left font-semibold text-text">OS</th>
							<th className="px-4 py-3 text-left font-semibold text-text">Version</th>
							<th className="px-4 py-3 text-left font-semibold text-text">Status</th>
							<th className="px-4 py-3 text-left font-semibold text-text">Last Seen</th>
						</tr>
					</thead>
					<tbody>
						{data.map(host => (
							<HostRow key={host.id} host={host} />
						))}
					</tbody>
				</table>
			</div>
		</div>
	);
}
