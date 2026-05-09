'use client';

import { RiskPillarBar } from '@/components/hosts/mission-control/risk-pillar-bar';
import { useHostRisk, useRiskRecompute } from '@/lib/api/posture-risk';
import { relTime } from '@/lib/time';
import { useParams } from 'next/navigation';

export default function HostRiskPage() {
	const params = useParams<{ id: string }>();
	const hostId = params.id;
	const q = useHostRisk(hostId);
	const recompute = useRiskRecompute();

	if (q.isLoading) return <div className="p-6 text-text-dim">Loading…</div>;
	if (q.isError || !q.data) return <div className="p-6 text-danger">Failed to load risk</div>;
	const r = q.data;

	const sorted = [...r.pillars].sort((a, b) => b.score * b.weight - a.score * a.weight);

	return (
		<div className="flex flex-col gap-4 p-6">
			<div className="flex items-end justify-between">
				<div>
					<h1 className="text-h1 text-text">Risk</h1>
					<p className="text-text-dim font-mono text-xs">
						score {r.score ?? '—'} · {r.level} · conf {Math.round(r.confidence * 100)}%
					</p>
					<p className="text-text-dim/70 font-mono text-[10px]">
						computed {relTime(r.computed_at)}
					</p>
				</div>
				<button
					type="button"
					onClick={() => recompute.mutate(hostId)}
					disabled={recompute.isPending}
					className="rounded border border-accent bg-accent/15 px-3 py-1.5 text-sm text-accent hover:bg-accent/25 disabled:opacity-40"
				>
					{recompute.isPending ? 'Recomputing…' : 'Recompute'}
				</button>
			</div>

			<div className="rounded border border-hairline bg-surface p-4 space-y-3">
				{sorted.map(p => (
					<div key={p.name}>
						<RiskPillarBar p={p} />
						{p.coverage_notes.length > 0 ? (
							<ul className="mt-1 ml-2 list-disc font-mono text-[10px] text-text-dim/70">
								{p.coverage_notes.map(n => (
									<li key={n}>{n}</li>
								))}
							</ul>
						) : null}
					</div>
				))}
			</div>
		</div>
	);
}
