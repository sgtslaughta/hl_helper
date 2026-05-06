'use client';

import { EmptyState } from '@/components/empty-states/empty-state';

export function HostPosturePanel({ hostId: _hostId }: { hostId: string }) {
	return (
		<EmptyState
			title="Posture backend not yet wired"
			description="Per-host posture endpoint pending implementation."
		/>
	);
}
