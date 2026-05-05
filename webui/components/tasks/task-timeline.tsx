'use client';

import { Badge } from '@/components/primitives/badge';

interface TimelineEvent {
	hostId: string;
	hostName: string;
	status: 'pending' | 'running' | 'completed' | 'failed';
	startedAt?: string;
	completedAt?: string;
	output?: string;
}

interface TaskTimelineProps {
	events: TimelineEvent[];
}

const statusBadgeVariant = {
	pending: 'dim',
	running: 'accent',
	completed: 'ok',
	failed: 'danger',
} as const;

export function TaskTimeline({ events }: TaskTimelineProps) {
	return (
		<div className="space-y-4">
			{events.length === 0 ? (
				<p className="text-text-dim text-sm">No events yet</p>
			) : (
				events.map(event => (
					<div key={event.hostId} className="flex gap-4 border-l-2 border-hairline pl-4 py-2">
						<div className="flex-shrink-0">
							<div className="w-3 h-3 bg-accent rounded-full relative -left-4" />
						</div>
						<div className="flex-1">
							<div className="flex items-center justify-between mb-2">
								<h4 className="text-sm font-medium text-text">{event.hostName}</h4>
								<Badge variant={statusBadgeVariant[event.status]} size="sm">
									{event.status}
								</Badge>
							</div>
							{event.startedAt && (
								<p className="text-xs text-text-dim mb-1">Started: {event.startedAt}</p>
							)}
							{event.completedAt && (
								<p className="text-xs text-text-dim mb-1">Completed: {event.completedAt}</p>
							)}
							{event.output && (
								<pre className="bg-surface-2 text-text-dim text-xs p-2 rounded overflow-x-auto max-h-32 overflow-y-auto">
									{event.output}
								</pre>
							)}
						</div>
					</div>
				))
			)}
		</div>
	);
}
