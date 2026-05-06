'use client';

export const dynamic = 'force-dynamic';

import { EmptyState } from '@/components/empty-states/empty-state';
import { BlueprintSkeleton } from '@/components/skeletons/blueprint-skeleton';
import { TaskRow, type Task } from '@/components/tasks/task-row';
import { apiFetch } from '@/lib/api-client';
import { useQuery } from '@tanstack/react-query';

interface TasksPage {
	items: Task[];
	next_cursor: string | null;
}

export default function TasksPage() {
	const { data, isLoading, isError } = useQuery({
		queryKey: ['tasks'],
		queryFn: () => apiFetch<TasksPage>('/v1/tasks?limit=100'),
		refetchInterval: 15_000,
	});

	const tasks: Task[] = data?.items ?? [];

	if (isLoading) return <BlueprintSkeleton rows={8} />;
	if (isError) return <EmptyState title="Failed to load tasks" description="Please try again" />;
	if (tasks.length === 0)
		return (
			<EmptyState
				title="No tasks yet"
				description="Tasks appear here when you dispatch actions on hosts."
			/>
		);

	return (
		<div className="p-4">
			<div className="mb-6">
				<h1 className="text-h2 font-bold text-text mb-2">Tasks</h1>
				<p className="text-text-dim">All dispatched actions across the fleet</p>
			</div>

			<div className="rounded border border-hairline bg-surface overflow-hidden">
				<table className="w-full text-sm">
					<thead className="border-b border-hairline bg-surface-2">
						<tr>
							<th className="px-4 py-3 text-left font-semibold text-text">Kind</th>
							<th className="px-4 py-3 text-left font-semibold text-text">Detail</th>
							<th className="px-4 py-3 text-left font-semibold text-text">Status</th>
							<th className="px-4 py-3 text-left font-semibold text-text">Risk</th>
							<th className="px-4 py-3 text-left font-semibold text-text">Created</th>
							<th className="px-4 py-3 text-right font-semibold text-text">Actions</th>
						</tr>
					</thead>
					<tbody>
						{tasks.map(task => (
							<TaskRow key={task.id} task={task} />
						))}
					</tbody>
				</table>
			</div>
		</div>
	);
}
