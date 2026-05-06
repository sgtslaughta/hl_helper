'use client';

export const dynamic = 'force-dynamic';

import { EmptyState } from '@/components/empty-states/empty-state';
import { HostActionButtons } from '@/components/hosts/host-action-buttons';
import { HostAuditPanel } from '@/components/hosts/host-audit-panel';
import { HostOverviewCard } from '@/components/hosts/host-overview-card';
import { HostPosturePanel } from '@/components/hosts/host-posture-panel';
import { HostTabs } from '@/components/hosts/host-tabs';
import { HostTasksPanel } from '@/components/hosts/host-tasks-panel';
import { HostTerminalPanel } from '@/components/hosts/host-terminal-panel';
import { BlueprintSkeleton } from '@/components/skeletons/blueprint-skeleton';
import { type Host, getHost } from '@/lib/api/hosts';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'next/navigation';

export default function HostDetailPage() {
	const params = useParams<{ id: string }>();
	const id = params.id;
	const q = useQuery<Host>({ queryKey: ['hosts', id], queryFn: () => getHost(id) });

	if (q.isLoading) return <BlueprintSkeleton rows={6} />;
	if (q.isError || !q.data)
		return (
			<EmptyState title="Host not found" description="It may have been revoked or never existed." />
		);
	const host = q.data;

	const isCriticalOrOffline = host.status === 'critical' || host.status === 'offline';

	const overviewPanel = (
		<div className="space-y-4">
			{isCriticalOrOffline ? (
				<div className="rounded border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-300">
					Host is {host.status}. Recent issues likely require investigation. Last seen{' '}
					{host.last_seen_at ?? 'never'}.
				</div>
			) : null}
			<HostOverviewCard host={host} />
			<div>
				<h3 className="mb-2 text-h4 font-semibold text-text">Actions</h3>
				<HostActionButtons host={host} />
			</div>
		</div>
	);

	return (
		<div className="p-4">
			<header className="mb-4">
				<h1 className="text-h2 font-bold text-text">{host.display_name ?? host.hostname}</h1>
				<p className="text-text-dim text-sm">
					{host.hostname} · {host.status}
				</p>
			</header>
			<HostTabs
				panels={{
					overview: () => overviewPanel,
					tasks: () => <HostTasksPanel hostId={id} />,
					posture: () => <HostPosturePanel hostId={id} />,
					terminal: () => <HostTerminalPanel hostId={id} />,
					audit: () => <HostAuditPanel hostId={id} />,
				}}
			/>
		</div>
	);
}
