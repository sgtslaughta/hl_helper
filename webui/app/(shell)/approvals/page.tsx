'use client';

export const dynamic = 'force-dynamic';

import { ApprovalCard } from '@/components/approvals/approval-card';
import { EmptyState } from '@/components/empty-states/empty-state';
import { BlueprintSkeleton } from '@/components/skeletons/blueprint-skeleton';
import { apiFetch } from '@/lib/api-client';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

interface Approval {
	id: string;
	title: string;
	description?: string;
	status: 'pending' | 'approved' | 'rejected';
	requestedBy: string;
	requestedAt: string;
}

export default function ApprovalsPage() {
	const queryClient = useQueryClient();

	const { data, isLoading, isError } = useQuery({
		queryKey: ['approvals'],
		queryFn: async () => {
			const raw = await apiFetch<Approval[] | { items: Approval[] }>('/v1/approvals');
			return Array.isArray(raw) ? raw : (raw?.items ?? []);
		},
	});

	const approveMutation = useMutation({
		mutationFn: async ({ id, reason }: { id: string; reason: string }) => {
			return apiFetch(`/v1/approvals/${id}/approve`, {
				method: 'POST',
				body: JSON.stringify({ reason }),
			});
		},
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ['approvals'] });
		},
	});

	const rejectMutation = useMutation({
		mutationFn: async ({ id, reason }: { id: string; reason: string }) => {
			return apiFetch(`/v1/approvals/${id}/reject`, {
				method: 'POST',
				body: JSON.stringify({ reason }),
			});
		},
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ['approvals'] });
		},
	});

	if (isLoading) return <BlueprintSkeleton rows={5} />;
	if (isError) return <EmptyState title="Failed to load approvals" />;
	const approvals = data ?? [];
	if (approvals.length === 0)
		return <EmptyState title="No pending approvals" description="All caught up!" />;

	return (
		<div className="p-4">
			<div className="mb-6">
				<h1 className="text-h2 font-bold text-text mb-2">Approvals</h1>
				<p className="text-text-dim">Review and approve pending requests</p>
			</div>

			<div className="space-y-4">
				{approvals.map(approval => (
					<ApprovalCard
						key={approval.id}
						approval={approval}
						onApprove={async (id, reason) => {
							await approveMutation.mutateAsync({ id, reason });
						}}
						onReject={async (id, reason) => {
							await rejectMutation.mutateAsync({ id, reason });
						}}
					/>
				))}
			</div>
		</div>
	);
}
