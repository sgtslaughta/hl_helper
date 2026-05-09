'use client';

import { RiskDriversTable } from '@/components/hosts/risk/drivers-table';
import { RiskHeroCard } from '@/components/hosts/risk/hero-card';
import { RiskPillarCard } from '@/components/hosts/risk/pillar-card';
import { RiskPillarRadar } from '@/components/hosts/risk/pillar-radar';
import { RiskRecentActivity } from '@/components/hosts/risk/recent-activity';
import { RiskSeverityDonut } from '@/components/hosts/risk/severity-donut';
import { useHostAuditByAction } from '@/hooks/use-host-audit-by-action';
import { useHostAdvisories } from '@/lib/api/advisories';
import { useHostRisk } from '@/lib/api/posture-risk';
import { useParams } from 'next/navigation';

export default function HostRiskPage() {
	const params = useParams<{ id: string }>();
	const hostId = params.id;

	const riskQ = useHostRisk(hostId);
	const advQ = useHostAdvisories(hostId, { status: 'open' });
	const auditQ = useHostAuditByAction(hostId, 'risk.recomputed', 6);

	if (riskQ.isLoading) return <div className="p-6 text-text-dim">Loading…</div>;
	if (riskQ.isError || !riskQ.data)
		return <div className="p-6 text-danger">Failed to load risk</div>;
	const r = riskQ.data;

	const sortedPillars = [...r.pillars].sort((a, b) => b.score * b.weight - a.score * a.weight);

	return (
		<div className="flex flex-col gap-4 p-6">
			<div className="flex items-baseline justify-between">
				<h1 className="text-h1 text-text">Risk dashboard</h1>
				<div className="font-mono text-[10px] uppercase tracking-wider text-text-dim">
					host {hostId.slice(0, 12)}
				</div>
			</div>

			{/* Hero row */}
			<div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
				<RiskHeroCard risk={r} hostId={hostId} />
				<RiskPillarRadar pillars={sortedPillars} />
				<RiskRecentActivity entries={auditQ.data ?? []} />
			</div>

			{/* Pillar grid */}
			<div className="grid grid-cols-1 gap-3 md:grid-cols-2">
				{sortedPillars.map(p => (
					<RiskPillarCard key={p.name} p={p} hostId={hostId} />
				))}
				{sortedPillars.length === 0 ? (
					<div className="col-span-full rounded border border-hairline bg-surface p-4 text-center font-mono text-xs text-text-dim">
						No pillar data — recompute or scan host.
					</div>
				) : null}
			</div>

			{/* Insights row */}
			<div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
				<RiskSeverityDonut advisories={advQ.data?.items ?? []} hostId={hostId} />
				<RiskDriversTable pillars={r.pillars} />
			</div>
		</div>
	);
}
