'use client';

export const dynamic = 'force-dynamic';

import { EmptyState } from '@/components/empty-states/empty-state';
import { BlueprintSkeleton } from '@/components/skeletons/blueprint-skeleton';
import { ResultOutputDrawer } from '@/components/tasks/result-output-drawer';
import { apiFetch } from '@/lib/api-client';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'next/navigation';
import { useState } from 'react';

interface TaskOut {
	id: string;
	kind: string;
	status: string;
	risk: string;
	created_at: string;
	updated_at: string;
	target_selector: Record<string, unknown>;
	payload: Record<string, unknown>;
	requires_approval: boolean;
	created_by: string | null;
}

interface ResultItem {
	host_id: string;
	status: string;
	last_command_id: string;
	error: string | null;
}

interface ResultsResponse {
	results: ResultItem[];
}

const STATUS_COLORS: Record<string, string> = {
	completed: 'text-green-400',
	running: 'text-blue-400',
	pending: 'text-text-dim',
	failed: 'text-red-400',
	cancelled: 'text-orange-400',
	ok: 'text-green-400',
	error: 'text-red-400',
	rejected: 'text-orange-400',
};

export default function TaskDetailPage() {
	const params = useParams<{ id: string }>();
	const taskId = params.id;
	const [openHostId, setOpenHostId] = useState<string | null>(null);

	const taskQ = useQuery<TaskOut>({
		queryKey: ['task', taskId],
		queryFn: () => apiFetch<TaskOut>(`/v1/tasks/${encodeURIComponent(taskId)}`),
	});

	const resultsQ = useQuery<ResultsResponse>({
		queryKey: ['task', taskId, 'results'],
		queryFn: () => apiFetch<ResultsResponse>(`/v1/tasks/${encodeURIComponent(taskId)}/results`),
		refetchInterval: 5_000,
	});

	if (taskQ.isLoading) return <BlueprintSkeleton rows={6} />;
	if (taskQ.isError || !taskQ.data) return <EmptyState title="Task not found" description="" />;
	const task = taskQ.data;

	const results = resultsQ.data?.results ?? [];

	return (
		<div className="p-4">
			<header className="mb-4">
				<h1 className="text-h2 font-bold text-text">{task.kind}</h1>
				{task.kind === 'shell_exec' && typeof task.payload?.command === 'string' ? (
					<pre className="mt-2 overflow-x-auto rounded border border-hairline bg-surface-2 px-3 py-2 font-mono text-sm text-text">
						$ {task.payload.command as string}
					</pre>
				) : null}
				<p className="text-text-dim text-sm mt-2">
					<span className={STATUS_COLORS[task.status] ?? 'text-text-dim'}>{task.status}</span>{' '}
					· {task.risk} · {task.created_at}
				</p>
			</header>

			<section className="mb-6 rounded border border-hairline bg-surface p-4">
				<h3 className="mb-3 text-h4 font-semibold text-text">Payload</h3>
				<pre className="overflow-auto whitespace-pre-wrap break-all rounded bg-surface-2 p-2 font-mono text-xs text-text-dim">
					{JSON.stringify(task.payload, null, 2)}
				</pre>
			</section>

			<section>
				<h3 className="mb-3 text-h4 font-semibold text-text">Per-host results</h3>
				{results.length === 0 ? (
					<EmptyState
						title="No results yet"
						description="Results appear once at least one host has executed the command."
					/>
				) : (
					<div className="rounded border border-hairline bg-surface overflow-hidden">
						<table className="w-full text-sm">
							<thead className="border-b border-hairline bg-surface-2">
								<tr>
									<th className="px-4 py-2 text-left font-semibold text-text">Host</th>
									<th className="px-4 py-2 text-left font-semibold text-text">Status</th>
									<th className="px-4 py-2 text-left font-semibold text-text">Error</th>
									<th className="px-4 py-2 text-right font-semibold text-text">Output</th>
								</tr>
							</thead>
							<tbody>
								{results.map(r => (
									<tr key={r.host_id} className="border-b border-hairline hover:bg-surface-2">
										<td className="px-4 py-2 text-text font-mono text-xs">{r.host_id}</td>
										<td className={`px-4 py-2 ${STATUS_COLORS[r.status] ?? 'text-text-dim'}`}>
											{r.status}
										</td>
										<td className="px-4 py-2 text-text-dim">{r.error ?? '—'}</td>
										<td className="px-4 py-2 text-right">
											<button
												type="button"
												onClick={() => setOpenHostId(r.host_id)}
												className="rounded border border-hairline px-2 py-1 text-xs text-text hover:bg-surface-2"
											>
												View output
											</button>
										</td>
									</tr>
								))}
							</tbody>
						</table>
					</div>
				)}
			</section>

			{openHostId ? (
				<ResultOutputDrawer
					taskId={taskId}
					hostId={openHostId}
					onClose={() => setOpenHostId(null)}
				/>
			) : null}
		</div>
	);
}
