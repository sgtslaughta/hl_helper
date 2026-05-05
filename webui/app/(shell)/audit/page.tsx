'use client';

export const dynamic = 'force-dynamic';

import { AuditChainBadge } from '@/components/audit/audit-chain-badge';
import { AuditEntry } from '@/components/audit/audit-entry';
import { EmptyState } from '@/components/empty-states/empty-state';
import { Input } from '@/components/primitives/input';
import { apiFetch } from '@/lib/api-client';
import { useCan } from '@/lib/rbac-helpers';
import { useMutation, useQuery } from '@tanstack/react-query';
import { ScrollText } from 'lucide-react';
import { useQueryState } from 'nuqs';
import { useState } from 'react';

interface AuditEntryOut {
	sequence: number;
	timestamp: string;
	actor: string;
	action: string;
	subject: string | null;
	payload: Record<string, unknown>;
	prev_hash: string;
	entry_hash: string;
}

interface AuditPage {
	items: AuditEntryOut[];
	next_cursor: string | null;
}

interface VerifyResult {
	ok: boolean;
	break_at_seq: number | null;
	total_entries: number;
}

export default function AuditPage() {
	const [actor, setActor] = useQueryState('actor');
	const [action, setAction] = useQueryState('action');
	const [subject, setSubject] = useQueryState('subject');
	const [verifyResult, setVerifyResult] = useState<VerifyResult | null>(null);
	const canView = useCan('audit:read');

	const { data, isLoading } = useQuery<AuditPage>({
		queryKey: ['audit', { actor, action, subject }],
		queryFn: async () => {
			const params = new URLSearchParams();
			if (actor) params.append('actor', actor);
			if (action) params.append('action', action);
			if (subject) params.append('subject', subject);
			return await apiFetch(`/v1/audit?${params.toString()}`);
		},
		enabled: canView,
	});

	const verifyMutation = useMutation({
		mutationFn: async () => {
			return await apiFetch<VerifyResult>('/v1/audit/actions/verify', {
				method: 'POST',
				body: JSON.stringify({}),
			});
		},
		onSuccess: result => {
			setVerifyResult(result);
		},
	});

	if (!canView) {
		return (
			<EmptyState
				title="Access Denied"
				description="You don't have permission to view audit logs"
				icon="🔒"
			/>
		);
	}

	const entries = data?.items || [];

	return (
		<div className="flex flex-col gap-6 p-6">
			<div>
				<h1 className="text-h1 text-text">Audit Log</h1>
				<p className="mt-2 text-text-dim">Immutable record of all system actions</p>
			</div>

			{verifyResult && (
				<AuditChainBadge
					ok={verifyResult.ok}
					breakAtSeq={verifyResult.break_at_seq}
					totalEntries={verifyResult.total_entries}
				/>
			)}

			<button
				type="button"
				onClick={() => verifyMutation.mutate()}
				disabled={verifyMutation.isPending}
				className="w-fit rounded bg-accent px-4 py-2 font-semibold text-canvas hover:bg-accent-dim disabled:opacity-50"
			>
				{verifyMutation.isPending ? 'Verifying...' : 'Verify Chain'}
			</button>

			<div className="flex flex-col gap-3 sm:flex-row">
				<Input
					placeholder="Filter by actor..."
					value={actor || ''}
					onChange={e => setActor(e.target.value || null)}
				/>
				<Input
					placeholder="Filter by action..."
					value={action || ''}
					onChange={e => setAction(e.target.value || null)}
				/>
				<Input
					placeholder="Filter by subject..."
					value={subject || ''}
					onChange={e => setSubject(e.target.value || null)}
				/>
			</div>

			{isLoading ? (
				<div className="text-center text-text-dim">Loading audit entries...</div>
			) : entries.length === 0 ? (
				<EmptyState
					title="No entries"
					description="No audit entries match your filters"
					icon={<ScrollText className="h-8 w-8 text-text-dim" />}
				/>
			) : (
				<div className="space-y-0 rounded border border-hairline overflow-hidden">
					{entries.map(entry => (
						<AuditEntry
							key={entry.sequence}
							sequence={entry.sequence}
							timestamp={entry.timestamp}
							actor={entry.actor}
							action={entry.action}
							subject={entry.subject}
							payload={entry.payload}
						/>
					))}
				</div>
			)}
		</div>
	);
}
