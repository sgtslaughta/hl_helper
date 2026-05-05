'use client';

import { ContainerCard } from '@/components/containers/container-card';
import { EmptyState } from '@/components/empty-states/empty-state';
import { BlueprintSkeleton } from '@/components/skeletons/blueprint-skeleton';
import { apiFetch } from '@/lib/api-client';
import { useQuery } from '@tanstack/react-query';

interface Container {
	id: string;
	name: string;
	image: string;
	host: string;
	status: 'running' | 'stopped' | 'paused';
	uptime?: string;
}

export default function ContainersPage() {
	const { data, isLoading, isError } = useQuery({
		queryKey: ['containers'],
		queryFn: () => apiFetch<Container[]>('/v1/containers'),
	});

	if (isLoading) return <BlueprintSkeleton rows={8} />;
	if (isError || !data) return <EmptyState title="Failed to load containers" />;
	if (data.length === 0) return <EmptyState title="No containers found" />;

	return (
		<div className="p-4">
			<div className="mb-6">
				<h1 className="text-h2 font-bold text-text mb-2">Containers</h1>
				<p className="text-text-dim">Manage container workloads</p>
			</div>

			<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
				{data.map(container => (
					<ContainerCard key={container.id} container={container} />
				))}
			</div>
		</div>
	);
}
