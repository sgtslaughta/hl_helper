'use client';

import Link from 'next/link';

export interface Task {
	id: string;
	kind: string;
	status: string;
	created_at: string;
	risk: string;
	summary?: string;
}

const STATUS_COLORS: Record<string, string> = {
	completed: 'text-green-400',
	running: 'text-blue-400',
	pending: 'text-text-dim',
	failed: 'text-red-400',
	cancelled: 'text-orange-400',
};

export function TaskRow({ task }: { task: Task }) {
	return (
		<tr className="border-b border-hairline hover:bg-surface-2">
			<td className="px-4 py-2 text-text">
				<Link href={`/tasks/${task.id}`} className="hover:underline">
					{task.kind}
				</Link>
			</td>
			<td className="px-4 py-2 text-text-dim font-mono text-xs max-w-[420px] truncate" title={task.summary ?? ''}>
				{task.summary ?? ''}
			</td>
			<td className={`px-4 py-2 ${STATUS_COLORS[task.status] ?? 'text-text-dim'}`}>
				{task.status}
			</td>
			<td className="px-4 py-2 text-text-dim">{task.risk}</td>
			<td className="px-4 py-2 text-text-dim font-mono text-xs">{task.created_at}</td>
			<td className="px-4 py-2 text-right">
				<Link
					href={`/tasks/${task.id}`}
					className="inline-block rounded border border-hairline px-2 py-1 text-xs text-text hover:bg-surface-2"
				>
					Open
				</Link>
			</td>
		</tr>
	);
}
