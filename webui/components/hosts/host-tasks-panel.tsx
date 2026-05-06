'use client';

import { EmptyState } from '@/components/empty-states/empty-state';
import { BlueprintSkeleton } from '@/components/skeletons/blueprint-skeleton';
import { NewTaskModal } from '@/components/tasks/new-task-modal';
import { apiFetch } from '@/lib/api-client';
import { useCanPerform } from '@/lib/rbac';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { useState } from 'react';

interface TaskListItem {
	id: string;
	kind: string;
	status: string;
	created_at: string;
	risk: string;
	summary?: string;
}
interface TasksPage {
	items: TaskListItem[];
	next_cursor: string | null;
}

const STATUS_COLORS: Record<string, string> = {
	completed: 'text-green-400',
	succeeded: 'text-green-400',
	running: 'text-blue-400',
	pending: 'text-text-dim',
	failed: 'text-red-400',
	partial: 'text-orange-400',
	cancelled: 'text-orange-400',
};

export function HostTasksPanel({ hostId }: { hostId: string }) {
	const [showNew, setShowNew] = useState(false);
	const cap = useCanPerform('shell-exec');
	const q = useQuery<TasksPage>({
		queryKey: ['hosts', hostId, 'tasks'],
		queryFn: () => apiFetch<TasksPage>(`/v1/tasks?host_id=${encodeURIComponent(hostId)}&limit=50`),
		refetchInterval: 5_000,
	});

	const items = q.data?.items ?? [];

	const headerBar = (
		<div className="mb-3 flex items-center justify-between">
			<h3 className="text-sm font-semibold text-text">Tasks</h3>
			<button
				type="button"
				disabled={!cap.allowed}
				title={cap.allowed ? '' : cap.reason}
				onClick={() => setShowNew(true)}
				className="rounded border border-hairline bg-accent px-2 py-1 text-xs font-medium text-text hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
			>
				+ New Task
			</button>
		</div>
	);

	const modal = showNew ? (
		<NewTaskModal
			defaultHostId={hostId}
			lockHost
			onClose={() => setShowNew(false)}
		/>
	) : null;

	if (q.isLoading) return <div>{headerBar}<BlueprintSkeleton rows={5} />{modal}</div>;
	if (q.isError) return <div>{headerBar}<EmptyState title="Failed to load tasks" description="Try again." />{modal}</div>;

	if (items.length === 0)
		return (
			<div>
				{headerBar}
				<EmptyState
					title="No tasks yet for this host"
					description="Click + New Task to dispatch one."
				/>
				{modal}
			</div>
		);

	return (
		<div>
			{headerBar}
			<div className="rounded border border-hairline bg-surface overflow-hidden">
				<table className="w-full text-sm">
					<thead className="border-b border-hairline bg-surface-2">
						<tr>
							<th className="px-4 py-2 text-left font-semibold text-text">Kind</th>
							<th className="px-4 py-2 text-left font-semibold text-text">Detail</th>
							<th className="px-4 py-2 text-left font-semibold text-text">Status</th>
							<th className="px-4 py-2 text-left font-semibold text-text">Risk</th>
							<th className="px-4 py-2 text-left font-semibold text-text">Created</th>
						</tr>
					</thead>
					<tbody>
						{items.map(t => (
							<tr key={t.id} className="border-b border-hairline hover:bg-surface-2">
								<td className="px-4 py-2 text-text">
									<Link href={`/tasks/${t.id}`} className="hover:underline">
										{t.kind}
									</Link>
								</td>
								<td className="px-4 py-2 text-text-dim font-mono text-xs max-w-[320px] truncate" title={t.summary ?? ''}>
									{t.summary ?? ''}
								</td>
								<td className={`px-4 py-2 ${STATUS_COLORS[t.status] ?? 'text-text-dim'}`}>
									{t.status}
								</td>
								<td className="px-4 py-2 text-text-dim">{t.risk}</td>
								<td className="px-4 py-2 text-text-dim font-mono text-xs">{t.created_at}</td>
							</tr>
						))}
					</tbody>
				</table>
			</div>
			{modal}
		</div>
	);
}
