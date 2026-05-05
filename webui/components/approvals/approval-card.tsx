'use client';

import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { useState } from 'react';

interface Approval {
	id: string;
	title: string;
	description?: string;
	status: 'pending' | 'approved' | 'rejected';
	requestedBy: string;
	requestedAt: string;
}

interface ApprovalCardProps {
	approval: Approval;
	onApprove?: (id: string, reason: string) => Promise<void>;
	onReject?: (id: string, reason: string) => Promise<void>;
}

const statusBadgeVariant = {
	pending: 'warn',
	approved: 'ok',
	rejected: 'danger',
} as const;

export function ApprovalCard({ approval, onApprove, onReject }: ApprovalCardProps) {
	const [reason, setReason] = useState('');
	const [isLoading, setIsLoading] = useState(false);
	const isPending = approval.status === 'pending';

	const handleApprove = async () => {
		setIsLoading(true);
		try {
			await onApprove?.(approval.id, reason);
		} finally {
			setIsLoading(false);
		}
	};

	const handleReject = async () => {
		setIsLoading(true);
		try {
			await onReject?.(approval.id, reason);
		} finally {
			setIsLoading(false);
		}
	};

	return (
		<div className="rounded border border-hairline bg-surface p-4">
			<div className="flex items-start justify-between mb-3">
				<div>
					<h3 className="text-sm font-semibold text-text">{approval.title}</h3>
					<p className="text-xs text-text-dim mt-1">
						Requested by {approval.requestedBy} on {approval.requestedAt}
					</p>
				</div>
				<Badge variant={statusBadgeVariant[approval.status]} size="sm">
					{approval.status}
				</Badge>
			</div>

			{approval.description && <p className="text-xs text-text-dim mb-4">{approval.description}</p>}

			{isPending && (
				<div className="space-y-3">
					<textarea
						value={reason}
						onChange={e => setReason(e.target.value)}
						placeholder="Add a reason (optional)..."
						className="w-full px-3 py-2 rounded bg-surface-2 border border-hairline text-text text-sm placeholder:text-text-dim focus:outline-none focus:border-accent resize-none"
						rows={3}
					/>
					<div className="flex gap-2">
						<Button
							variant="primary"
							size="sm"
							onClick={handleApprove}
							isLoading={isLoading}
							disabled={isLoading}
							type="button"
						>
							Approve
						</Button>
						<Button
							variant="danger"
							size="sm"
							onClick={handleReject}
							isLoading={isLoading}
							disabled={isLoading}
							type="button"
						>
							Reject
						</Button>
					</div>
				</div>
			)}
		</div>
	);
}
