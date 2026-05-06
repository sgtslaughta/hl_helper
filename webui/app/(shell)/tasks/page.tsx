'use client';

export const dynamic = 'force-dynamic';

import { EmptyState } from '@/components/empty-states/empty-state';
import { NewTaskModal } from '@/components/tasks/new-task-modal';
import { BlueprintSkeleton } from '@/components/skeletons/blueprint-skeleton';
import { TaskRow, type Task } from '@/components/tasks/task-row';
import { apiFetch } from '@/lib/api-client';
import { useCanPerform } from '@/lib/rbac';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

interface TasksPage {
	items: Task[];
	next_cursor: string | null;
}

export default function TasksPage() {
	const [showNew, setShowNew] = useState(false);
	const cap = useCanPerform('shell-exec');
	const { data, isLoading, isError } = useQuery({
		queryKey: ['tasks'],
		queryFn: () => apiFetch<TasksPage>('/v1/tasks?limit=100'),
		refetchInterval: 15_000,
	});

	const tasks: Task[] = data?.items ?? [];

	const header = (
		<div className="mb-6 flex items-start justify-between gap-4">
			<div>
				<h1 className="text-h2 font-bold text-text mb-2">Tasks</h1>
				<p className="text-text-dim">All dispatched actions across the fleet</p>
			</div>
			<button
				type="button"
				disabled={!cap.allowed}
				title={cap.allowed ? '' : cap.reason}
				onClick={() => setShowNew(true)}
				className="rounded border border-hairline bg-accent px-3 py-1.5 text-sm font-medium text-text hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
			>
				+ New Task
			</button>
		</div>
	);

	if (isLoading) return <div className="p-4">{header}<BlueprintSkeleton rows={8} /></div>;
	if (isError) return <div className="p-4">{header}<EmptyState title="Failed to load tasks" description="Please try again" /></div>;
	if (tasks.length === 0)
		return (
			<div className="p-4">
				{header}
				<EmptyState
					title="No tasks yet"
					description="Click + New Task to dispatch one."
				/>
				{showNew ? <NewTaskModal onClose={() => setShowNew(false)} /> : null}
			</div>
		);

	return (
		<div className="p-4">
			{header}

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
			{showNew ? <NewTaskModal onClose={() => setShowNew(false)} /> : null}
		</div>
	);
}
