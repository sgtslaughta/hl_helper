'use client';

import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api-client';
import { BlueprintSkeleton } from '@/components/skeletons/blueprint-skeleton';
import { EmptyState } from '@/components/empty-states/empty-state';

interface TaskListItem {
	id: string;
	kind: string;
	status: string;
	created_at: string;
	risk: string;
}
interface TasksPage {
	items: TaskListItem[];
	next_cursor: string | null;
}

const STATUS_COLORS: Record<string, string> = {
	completed: 'text-green-400',
	running: 'text-blue-400',
	pending: 'text-text-dim',
	failed: 'text-red-400',
	cancelled: 'text-orange-400',
};

export function HostTasksPanel({ hostId }: { hostId: string }) {
	const q = useQuery<TasksPage>({
		queryKey: ['hosts', hostId, 'tasks'],
		queryFn: () =>
			apiFetch<TasksPage>(
				`/v1/tasks?host_id=${encodeURIComponent(hostId)}&limit=50`
			),
	});

	if (q.isLoading) return <BlueprintSkeleton rows={5} />;
	if (q.isError)
		return (
			<EmptyState title="Failed to load tasks" description="Try again." />
		);

	const items = q.data?.items ?? [];
	if (items.length === 0)
		return (
			<EmptyState
				title="No tasks yet for this host"
				description="Actions will appear here as they run."
			/>
		);

	return (
		<div className="rounded border border-hairline bg-surface overflow-hidden">
			<table className="w-full text-sm">
				<thead className="border-b border-hairline bg-surface-2">
					<tr>
						<th className="px-4 py-2 text-left font-semibold text-text">
							Kind
						</th>
						<th className="px-4 py-2 text-left font-semibold text-text">
							Status
						</th>
						<th className="px-4 py-2 text-left font-semibold text-text">
							Risk
						</th>
						<th className="px-4 py-2 text-left font-semibold text-text">
							Created
						</th>
					</tr>
				</thead>
				<tbody>
					{items.map(t => (
						<tr
							key={t.id}
							className="border-b border-hairline hover:bg-surface-2"
						>
							<td className="px-4 py-2 text-text">
								<Link
									href={`/tasks/${t.id}`}
									className="hover:underline"
								>
									{t.kind}
								</Link>
							</td>
							<td
								className={`px-4 py-2 ${
									STATUS_COLORS[t.status] ?? 'text-text-dim'
								}`}
							>
								{t.status}
							</td>
							<td className="px-4 py-2 text-text-dim">{t.risk}</td>
							<td className="px-4 py-2 text-text-dim font-mono text-xs">
								{t.created_at}
							</td>
						</tr>
					))}
				</tbody>
			</table>
		</div>
	);
}
