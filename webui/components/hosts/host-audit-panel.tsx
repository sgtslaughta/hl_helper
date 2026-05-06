'use client';

import { EmptyState } from '@/components/empty-states/empty-state';

export function HostAuditPanel({ hostId: _hostId }: { hostId: string }) {
	return (
		<EmptyState
			title="Audit backend not yet wired"
			description="Per-host audit filtering endpoint pending implementation."
		/>
	);
}
