'use client';

import { apiFetch } from '@/lib/api-client';
import { useCan } from '@/lib/rbac-helpers';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle } from 'lucide-react';

interface AdvisoryCardProps {
	id: string;
	severity: string;
	title: string;
	summary: string;
	affectedHosts: number;
	patchUrl?: string | null;
}

export function AdvisoryCard({
	id,
	severity,
	title,
	summary,
	affectedHosts,
	patchUrl,
}: AdvisoryCardProps) {
	const canPatch = useCan('advisories:patch');
	const queryClient = useQueryClient();

	const patchMutation = useMutation({
		mutationFn: async () => {
			await apiFetch(`/v1/advisories/${id}/patch`, { method: 'POST' });
		},
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ['advisories'] });
		},
	});

	const severityColors: Record<string, string> = {
		critical: 'text-danger bg-danger/20',
		high: 'text-warn bg-warn/20',
		medium: 'text-warn/70 bg-warn/10',
		low: 'text-ok bg-ok/20',
	};

	return (
		<div className="rounded border border-hairline bg-surface p-4">
			<div className="flex items-start justify-between gap-3">
				<div className="flex-1">
					<div className="flex items-center gap-2">
						<AlertTriangle className={`h-5 w-5 ${severityColors[severity]?.split(' ')[0]}`} />
						<h3 className="font-semibold text-text">{title}</h3>
						<span
							className={`rounded px-2 py-1 text-tiny font-semibold ${severityColors[severity]}`}
						>
							{severity}
						</span>
					</div>
					<p className="mt-2 text-small text-text-dim">{summary}</p>
					<div className="mt-3 flex gap-4 text-tiny text-text-dim">
						<span>{affectedHosts} host(s) affected</span>
						{patchUrl && (
							<a
								href={patchUrl}
								target="_blank"
								rel="noopener noreferrer"
								className="text-accent hover:text-accent-dim"
							>
								Details →
							</a>
						)}
					</div>
				</div>
				{canPatch && (
					<button
						type="button"
						onClick={() => patchMutation.mutate()}
						disabled={patchMutation.isPending}
						className="whitespace-nowrap rounded bg-ok px-3 py-2 text-small font-semibold text-canvas hover:bg-ok/80 disabled:opacity-50"
					>
						{patchMutation.isPending ? 'Patching...' : 'Patch All'}
					</button>
				)}
			</div>
		</div>
	);
}
