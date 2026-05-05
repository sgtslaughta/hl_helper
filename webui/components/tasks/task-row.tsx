'use client';

import { Badge } from '@/components/primitives/badge';
import Link from 'next/link';

interface Task {
	id: string;
	name: string;
	status: 'pending' | 'running' | 'completed' | 'failed';
	hostCount: number;
	createdAt: string;
	completedAt?: string;
}

interface TaskRowProps {
	task: Task;
}

const statusBadgeVariant = {
	pending: 'dim',
	running: 'accent',
	completed: 'ok',
	failed: 'danger',
} as const;

export function TaskRow({ task }: TaskRowProps) {
	return (
		<tr className="border-b border-hairline hover:bg-surface-2 transition-colors">
			<td className="px-4 py-3 text-sm">
				<Link href={`/tasks/${task.id}`} className="text-accent hover:underline">
					{task.name}
				</Link>
			</td>
			<td className="px-4 py-3">
				<Badge variant={statusBadgeVariant[task.status]} size="sm">
					{task.status}
				</Badge>
			</td>
			<td className="px-4 py-3 text-sm text-text-dim">{task.hostCount} hosts</td>
			<td className="px-4 py-3 text-sm text-text-dim">{task.createdAt}</td>
			<td className="px-4 py-3 text-sm text-text-dim">{task.completedAt || '—'}</td>
		</tr>
	);
}
