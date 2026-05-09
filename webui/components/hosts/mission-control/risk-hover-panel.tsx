'use client';

import type { HostRiskOut } from '@/lib/api/posture-risk';
import { RiskPillarBar } from './risk-pillar-bar';

export function RiskHoverPanel({ risk }: { risk: HostRiskOut }) {
	const sorted = [...risk.pillars].sort((a, b) => b.score * b.weight - a.score * a.weight);
	return (
		<>
			<div className="mb-1.5 flex items-center justify-between font-mono text-[9px] uppercase tracking-[0.14em] text-text-dim">
				<span>Pillars</span>
				<span>conf {Math.round(risk.confidence * 100)}%</span>
			</div>
			<div className="space-y-1.5">
				{sorted.map(p => (
					<RiskPillarBar key={p.name} p={p} />
				))}
			</div>
			<div className="mt-1.5 border-t border-hairline pt-1 font-mono text-[9px] text-text-dim/70">
				Click gauge to open risk dashboard →
			</div>
		</>
	);
}
