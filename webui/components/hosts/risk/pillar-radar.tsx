'use client';

import type { PillarOut } from '@/lib/api/posture-risk';

const W = 240;
const H = 200;
const CX = W / 2;
const CY = H / 2 + 6;
const R = 72;

function polygon(values: number[], maxValue = 100) {
	const n = values.length;
	const pts = values.map((v, i) => {
		const ang = (i / n) * Math.PI * 2 - Math.PI / 2;
		const radius = (Math.min(maxValue, Math.max(0, v)) / maxValue) * R;
		return [CX + radius * Math.cos(ang), CY + radius * Math.sin(ang)];
	});
	return pts.map(p => p.join(',')).join(' ');
}

function trunc(s: string, n: number): string {
	return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}

export function RiskPillarRadar({ pillars }: { pillars: PillarOut[] }) {
	if (pillars.length < 3) {
		return (
			<section className="rounded border border-hairline bg-surface p-3">
				<div className="font-mono text-[10px] uppercase tracking-[0.18em] text-text-dim">
					Pillar radar
				</div>
				<div className="flex h-[180px] items-center justify-center font-mono text-xs text-text-dim/70">
					Need ≥3 pillars for radar — currently {pillars.length}.
				</div>
			</section>
		);
	}

	const sorted = [...pillars].sort((a, b) => a.name.localeCompare(b.name));
	const n = sorted.length;
	const scores = sorted.map(p => p.score);
	const weighted = sorted.map(p => p.score * p.weight);

	const ringValues = [25, 50, 75, 100];
	const axes = sorted.map((_p, i) => {
		const ang = (i / n) * Math.PI * 2 - Math.PI / 2;
		return [CX + R * Math.cos(ang), CY + R * Math.sin(ang)];
	});

	return (
		<section className="rounded border border-hairline bg-surface p-3">
			<div className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-text-dim">
				Pillar radar
			</div>
			<svg width="100%" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Pillar radar chart">
				<title>Pillar radar — score vs weighted contribution</title>
				{/* Concentric rings */}
				{ringValues.map(rv => (
					<polygon
						key={rv}
						points={polygon(Array(n).fill(rv))}
						fill="none"
						stroke="var(--color-hairline)"
						strokeWidth={0.6}
						strokeOpacity={rv === 100 ? 0.6 : 0.3}
					/>
				))}
				{/* Axes */}
				{axes.map(([x, y], i) => (
					<line
						key={`axis-${sorted[i].name}`}
						x1={CX}
						y1={CY}
						x2={x}
						y2={y}
						stroke="var(--color-hairline)"
						strokeWidth={0.6}
						strokeOpacity={0.5}
					/>
				))}
				{/* Score polygon (filled) */}
				<polygon
					points={polygon(scores)}
					fill="var(--color-accent)"
					fillOpacity={0.18}
					stroke="var(--color-accent)"
					strokeWidth={1.5}
				/>
				{/* Weighted contribution (dashed outline) */}
				<polygon
					points={polygon(weighted)}
					fill="none"
					stroke="var(--color-warn)"
					strokeWidth={1.2}
					strokeDasharray="3 3"
					strokeOpacity={0.85}
				/>
				{/* Score dots */}
				{sorted.map((p, i) => {
					const ang = (i / n) * Math.PI * 2 - Math.PI / 2;
					const radius = (p.score / 100) * R;
					return (
						<circle
							key={`dot-${p.name}`}
							cx={CX + radius * Math.cos(ang)}
							cy={CY + radius * Math.sin(ang)}
							r={2.5}
							fill="var(--color-accent)"
						/>
					);
				})}
				{/* Axis labels */}
				{sorted.map((p, i) => {
					const ang = (i / n) * Math.PI * 2 - Math.PI / 2;
					const lx = CX + (R + 14) * Math.cos(ang);
					const ly = CY + (R + 14) * Math.sin(ang);
					return (
						<text
							key={`label-${p.name}`}
							x={lx}
							y={ly}
							textAnchor="middle"
							dominantBaseline="middle"
							className="font-mono"
							fontSize="9"
							fill="var(--color-text-dim)"
						>
							{trunc(p.label, 14)}
						</text>
					);
				})}
				{/* Center 100 ring label */}
				<text
					x={CX + 2}
					y={CY - R}
					fontSize="8"
					fill="var(--color-text-dim)"
					opacity={0.6}
					className="font-mono"
				>
					100
				</text>
			</svg>
			<div className="mt-2 flex items-center justify-center gap-4 font-mono text-[9px] uppercase tracking-wider text-text-dim">
				<span className="flex items-center gap-1">
					<span className="h-2 w-3 rounded-sm bg-accent/60" /> raw score
				</span>
				<span className="flex items-center gap-1">
					<span className="h-2 w-3 border border-dashed border-warn" /> weighted
				</span>
			</div>
		</section>
	);
}
