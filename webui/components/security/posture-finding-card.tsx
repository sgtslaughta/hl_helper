'use client';

import { apiFetch } from '@/lib/api-client';
import { useCan } from '@/lib/rbac-helpers';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { AlertCircle, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { useState } from 'react';

const SEVERITY_COLORS: Record<string, { bg: string; icon: typeof AlertCircle }> = {
	critical: { bg: 'bg-danger', icon: AlertCircle },
	high: { bg: 'bg-warn', icon: AlertTriangle },
	medium: { bg: 'bg-warn/50', icon: AlertTriangle },
	low: { bg: 'bg-ok/30', icon: CheckCircle2 },
	suppressed: { bg: 'bg-surface-2', icon: CheckCircle2 },
};

interface PostureCardProps {
	id: string;
	severity: string;
	title: string;
	summary: string;
	rule: string;
	subjectKind: string;
	subjectId: string | null;
	fixActionUrl?: string | null;
	suppressedUntil?: string | null;
}

export function PostureFindingCard({
	id,
	severity,
	title,
	summary,
	rule,
	subjectKind,
	subjectId,
	fixActionUrl,
	suppressedUntil,
}: PostureCardProps) {
	const [showSuppress, setShowSuppress] = useState(false);
	const canSuppress = useCan('security:suppress');
	const queryClient = useQueryClient();

	const suppressMutation = useMutation({
		mutationFn: async () => {
			const expiresAt = new Date();
			expiresAt.setDate(expiresAt.getDate() + 7); // 7 days default
			await apiFetch('/v1/posture/actions/suppress', {
				method: 'POST',
				body: JSON.stringify({
					finding_id: id,
					reason: 'User suppressed',
					expires_at: expiresAt.toISOString(),
				}),
			});
		},
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ['posture'] });
		},
	});

	const colors = SEVERITY_COLORS[severity] || SEVERITY_COLORS.low;
	const Icon = colors.icon;

	return (
		<div className="rounded border border-hairline bg-surface p-4">
			<div className="flex items-start justify-between gap-3">
				<div className="flex-1">
					<div className="flex items-center gap-2">
						<Icon className={`h-5 w-5 ${colors.bg.replace('bg-', 'text-')}`} />
						<h3 className="font-semibold text-text">{title}</h3>
						<span className={`rounded px-2 py-1 text-tiny font-semibold ${colors.bg}`}>
							{severity}
						</span>
					</div>
					<p className="mt-2 text-small text-text-dim">{summary}</p>
					<div className="mt-3 flex flex-wrap gap-2 text-tiny text-text-dim">
						<span>Rule: {rule}</span>
						{subjectKind && <span>Subject: {subjectKind}</span>}
						{subjectId && <span className="font-mono text-accent">{subjectId}</span>}
					</div>
				</div>
				{fixActionUrl && (
					<a
						href={fixActionUrl}
						target="_blank"
						rel="noopener noreferrer"
						className="whitespace-nowrap rounded bg-accent px-2 py-1 text-tiny font-semibold text-canvas hover:bg-accent-dim"
					>
						Fix →
					</a>
				)}
			</div>
			{suppressedUntil && (
				<div className="mt-3 rounded bg-surface-2 px-3 py-2 text-tiny text-text-dim">
					Suppressed until {new Date(suppressedUntil).toLocaleDateString()}
				</div>
			)}
			{canSuppress && !suppressedUntil && (
				<div className="mt-3">
					{!showSuppress ? (
						<button
							type="button"
							onClick={() => setShowSuppress(true)}
							className="text-tiny text-text-dim hover:text-text"
						>
							Suppress 7 days
						</button>
					) : (
						<button
							type="button"
							onClick={() => suppressMutation.mutate()}
							disabled={suppressMutation.isPending}
							className="rounded bg-surface-2 px-2 py-1 text-tiny text-text hover:bg-hairline disabled:opacity-50"
						>
							{suppressMutation.isPending ? 'Suppressing...' : 'Confirm suppress'}
						</button>
					)}
				</div>
			)}
		</div>
	);
}
