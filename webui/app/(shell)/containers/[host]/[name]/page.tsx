'use client';

import { EmptyState } from '@/components/empty-states/empty-state';
import { Badge } from '@/components/primitives/badge';
import { Tabs, TabsContent } from '@/components/primitives/tabs';
import { BlueprintSkeleton } from '@/components/skeletons/blueprint-skeleton';
import { apiFetch } from '@/lib/api-client';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'next/navigation';

interface Container {
	id: string;
	name: string;
	image: string;
	host: string;
	status: 'running' | 'stopped' | 'paused';
	uptime?: string;
	createdAt?: string;
	ports?: string[];
}

const statusBadgeVariant = {
	running: 'ok',
	stopped: 'dim',
	paused: 'warn',
} as const;

export default function ContainerDetailPage() {
	const params = useParams();
	const host = params.host as string;
	const name = params.name as string;

	const {
		data: container,
		isLoading,
		isError,
	} = useQuery({
		queryKey: ['container', host, name],
		queryFn: () => apiFetch<Container>(`/v1/containers/${host}/${name}`),
	});

	if (isLoading) return <BlueprintSkeleton rows={5} />;
	if (isError || !container) return <EmptyState title="Container not found" />;

	const tabs = [
		{ label: 'Overview', value: 'overview' },
		{ label: 'Logs', value: 'logs' },
		{ label: 'Exec', value: 'exec' },
		{ label: 'ImageInfo', value: 'imageinfo' },
	];

	return (
		<div className="p-4">
			<div className="mb-6">
				<div className="flex items-center gap-4 mb-2">
					<h1 className="text-h2 font-bold text-text">{container.name}</h1>
					<Badge variant={statusBadgeVariant[container.status]} size="sm">
						{container.status}
					</Badge>
				</div>
				<p className="text-text-dim text-sm">{container.image}</p>
			</div>

			<Tabs tabs={tabs}>
				<TabsContent value="overview">
					<div className="rounded border border-hairline bg-surface p-4">
						<h3 className="text-sm font-semibold text-text mb-4">Container Information</h3>
						<div className="grid grid-cols-2 gap-4 text-sm">
							<div>
								<span className="text-xs font-semibold text-text-dim">Host</span>
								<p className="text-text mt-1">{container.host}</p>
							</div>
							<div>
								<span className="text-xs font-semibold text-text-dim">Image</span>
								<p className="text-text mt-1 text-xs font-mono">{container.image}</p>
							</div>
							<div>
								<span className="text-xs font-semibold text-text-dim">Created</span>
								<p className="text-text mt-1">{container.createdAt || '—'}</p>
							</div>
							<div>
								<span className="text-xs font-semibold text-text-dim">Uptime</span>
								<p className="text-text mt-1">{container.uptime || '—'}</p>
							</div>
							{container.ports && (
								<div className="col-span-2">
									<span className="text-xs font-semibold text-text-dim">Ports</span>
									<p className="text-text mt-1">{container.ports.join(', ') || '—'}</p>
								</div>
							)}
						</div>
					</div>
				</TabsContent>

				<TabsContent value="logs">
					<EmptyState title="Logs" description="Wave 3: Container logs loading" />
				</TabsContent>

				<TabsContent value="exec">
					<EmptyState title="Exec" description="Wave 3: Command execution loading" />
				</TabsContent>

				<TabsContent value="imageinfo">
					<EmptyState title="Image Info" description="Wave 3: Image metadata loading" />
				</TabsContent>
			</Tabs>
		</div>
	);
}
