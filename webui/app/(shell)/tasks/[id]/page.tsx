'use client';

import { EmptyState } from '@/components/empty-states/empty-state';
import { Badge } from '@/components/primitives/badge';
import { Tabs, TabsContent } from '@/components/primitives/tabs';
import { BlueprintSkeleton } from '@/components/skeletons/blueprint-skeleton';
import { TaskTimeline } from '@/components/tasks/task-timeline';
import { apiFetch } from '@/lib/api-client';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'next/navigation';

interface Task {
	id: string;
	name: string;
	status: 'pending' | 'running' | 'completed' | 'failed';
	createdAt: string;
	completedAt?: string;
}

interface TimelineEvent {
	hostId: string;
	hostName: string;
	status: 'pending' | 'running' | 'completed' | 'failed';
	startedAt?: string;
	completedAt?: string;
	output?: string;
}

const statusBadgeVariant = {
	pending: 'dim',
	running: 'accent',
	completed: 'ok',
	failed: 'danger',
} as const;

export default function TaskDetailPage() {
	const params = useParams();
	const taskId = params.id as string;

	const {
		data: task,
		isLoading,
		isError,
	} = useQuery({
		queryKey: ['task', taskId],
		queryFn: () => apiFetch<Task>(`/v1/tasks/${taskId}`),
	});

	const { data: events } = useQuery({
		queryKey: ['task-events', taskId],
		queryFn: () => apiFetch<TimelineEvent[]>(`/v1/tasks/${taskId}/events`),
		enabled: !!task,
	});

	if (isLoading) return <BlueprintSkeleton rows={5} />;
	if (isError || !task) return <EmptyState title="Task not found" />;

	const tabs = [
		{ label: 'Timeline', value: 'timeline' },
		{ label: 'Details', value: 'details' },
	];

	return (
		<div className="p-4">
			<div className="mb-6">
				<div className="flex items-center gap-4 mb-2">
					<h1 className="text-h2 font-bold text-text">{task.name}</h1>
					<Badge variant={statusBadgeVariant[task.status]} size="sm">
						{task.status}
					</Badge>
				</div>
			</div>

			<Tabs tabs={tabs}>
				<TabsContent value="timeline">{events && <TaskTimeline events={events} />}</TabsContent>

				<TabsContent value="details">
					<div className="rounded border border-hairline bg-surface p-4">
						<h3 className="text-sm font-semibold text-text mb-4">Task Information</h3>
						<div className="grid grid-cols-2 gap-4 text-sm">
							<div>
								<span className="text-xs font-semibold text-text-dim">Created</span>
								<p className="text-text mt-1">{task.createdAt}</p>
							</div>
							<div>
								<span className="text-xs font-semibold text-text-dim">Completed</span>
								<p className="text-text mt-1">{task.completedAt || '—'}</p>
							</div>
						</div>
					</div>
				</TabsContent>
			</Tabs>
		</div>
	);
}
