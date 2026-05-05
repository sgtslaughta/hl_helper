'use client';

import { AlertCircle, CheckCircle2 } from 'lucide-react';

interface AuditChainBadgeProps {
	ok: boolean;
	breakAtSeq?: number | null;
	totalEntries: number;
}

export function AuditChainBadge({ ok, breakAtSeq, totalEntries }: AuditChainBadgeProps) {
	return (
		<div
			className={`inline-flex items-center gap-2 rounded px-3 py-2 text-small font-semibold ${
				ok ? 'bg-ok/20 text-ok' : 'bg-danger/20 text-danger'
			}`}
		>
			{ok ? (
				<>
					<CheckCircle2 className="h-4 w-4" />
					<span>Chain verified ({totalEntries} entries)</span>
				</>
			) : (
				<>
					<AlertCircle className="h-4 w-4" />
					<span>Chain broken at #{breakAtSeq}</span>
				</>
			)}
		</div>
	);
}
