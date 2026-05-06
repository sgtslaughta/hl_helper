'use client';

import { EmptyState } from '@/components/empty-states/empty-state';

export function HostTasksPanel({ hostId: _hostId }: { hostId: string }) {
	return (
		<EmptyState
			title="Tasks backend not yet wired"
			description="Per-host tasks endpoint pending implementation."
		/>
	);
}
