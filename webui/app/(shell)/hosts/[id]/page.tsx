'use client';

import { EmptyState } from '@/components/empty-states/empty-state';
import { TrustPanel } from '@/components/hosts/trust-panel';
import { Badge } from '@/components/primitives/badge';
import { Tabs, TabsContent } from '@/components/primitives/tabs';
import { BlueprintSkeleton } from '@/components/skeletons/blueprint-skeleton';
import { apiFetch } from '@/lib/api-client';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'next/navigation';

interface Host {
	id: string;
	name: string;
	os: string;
	version: string;
	status: 'healthy' | 'warning' | 'critical';
	lastSeen: string;
}

interface TrustInfo {
	trusted: boolean;
	certificateSHA: string;
	issuedAt: string;
	expiresAt: string;
	issuer: string;
}

const statusBadgeVariant = {
	healthy: 'ok',
	warning: 'warn',
	critical: 'danger',
} as const;

export default function HostDetailPage() {
	const params = useParams();
	const hostId = params.id as string;

	const {
		data: host,
		isLoading,
		isError,
	} = useQuery({
		queryKey: ['host', hostId],
		queryFn: () => apiFetch<Host>(`/v1/hosts/${hostId}`),
	});

	const { data: trustInfo } = useQuery({
		queryKey: ['host-trust', hostId],
		queryFn: () => apiFetch<TrustInfo>(`/v1/hosts/${hostId}/trust`),
		enabled: !!host,
	});

	if (isLoading) return <BlueprintSkeleton rows={5} />;
	if (isError || !host) return <EmptyState title="Host not found" />;

	const tabs = [
		{ label: 'Overview', value: 'overview' },
		{ label: 'Packages', value: 'packages' },
		{ label: 'Advisories', value: 'advisories' },
		{ label: 'History', value: 'history' },
		{ label: 'Trust', value: 'trust' },
	];

	return (
		<div className="p-4">
			<div className="mb-6">
				<div className="flex items-center gap-4 mb-2">
					<h1 className="text-h2 font-bold text-text">{host.name}</h1>
					<Badge variant={statusBadgeVariant[host.status]} size="sm">
						{host.status}
					</Badge>
				</div>
				<p className="text-text-dim">
					{host.os} v{host.version}
				</p>
			</div>

			<Tabs tabs={tabs}>
				<TabsContent value="overview">
					<div className="space-y-4">
						<div className="rounded border border-hairline bg-surface p-4">
							<h3 className="text-sm font-semibold text-text mb-4">Host Information</h3>
							<div className="grid grid-cols-2 gap-4 text-sm">
								<div>
									<span className="text-xs font-semibold text-text-dim">Operating System</span>
									<p className="text-text mt-1">{host.os}</p>
								</div>
								<div>
									<span className="text-xs font-semibold text-text-dim">Version</span>
									<p className="text-text mt-1">v{host.version}</p>
								</div>
								<div>
									<span className="text-xs font-semibold text-text-dim">Last Seen</span>
									<p className="text-text mt-1">{host.lastSeen}</p>
								</div>
								<div>
									<span className="text-xs font-semibold text-text-dim">Status</span>
									<p className="text-text mt-1 capitalize">{host.status}</p>
								</div>
							</div>
						</div>
					</div>
				</TabsContent>

				<TabsContent value="packages">
					<EmptyState title="Packages" description="Wave 3: Package inventory loading" />
				</TabsContent>

				<TabsContent value="advisories">
					<EmptyState title="Security Advisories" description="Wave 3: Advisory data loading" />
				</TabsContent>

				<TabsContent value="history">
					<EmptyState title="Task History" description="Wave 3: Historical runs loading" />
				</TabsContent>

				<TabsContent value="trust">
					{trustInfo && <TrustPanel hostId={hostId} trustInfo={trustInfo} />}
				</TabsContent>
			</Tabs>
		</div>
	);
}
