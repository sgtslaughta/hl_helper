'use client';

import { apiFetch } from '@/lib/api-client';
import { type HostRiskOut, useRiskRecompute } from '@/lib/api/posture-risk';
import { relTime } from '@/lib/time';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { RefreshCw, RotateCw } from 'lucide-react';

const LEVEL_COLOR: Record<string, string> = {
	minimal: 'var(--color-ok)',
	stable: 'var(--color-ok)',
	moderate: 'var(--color-accent)',
	elevated: 'var(--color-warn)',
	high: '#ff8400',
	severe: 'var(--color-danger)',
	unknown: 'var(--color-text-dim)',
};

const LEVEL_LABEL: Record<string, string> = {
	minimal: 'All clear',
	stable: 'Stable — monitor',
	moderate: 'Moderate — review',
	elevated: 'Elevated — patch this week',
	high: 'High — patch now',
	severe: 'Severe — under active risk',
	unknown: 'Insufficient signal — scan host',
};

const BANDS = [
	{ from: 0, to: 20, color: 'var(--color-ok)' },
	{ from: 20, to: 40, color: 'var(--color-accent)' },
	{ from: 40, to: 65, color: 'var(--color-warn)' },
	{ from: 65, to: 85, color: '#ff8400' },
	{ from: 85, to: 100, color: 'var(--color-danger)' },
];

export function RiskHeroCard({ risk, hostId }: { risk: HostRiskOut; hostId: string }) {
	const recompute = useRiskRecompute();
	const qc = useQueryClient();
	const scan = useMutation({
		mutationFn: () =>
			apiFetch(`/v1/hosts/${encodeURIComponent(hostId)}/rescan`, { method: 'POST' }),
		onSuccess: () => {
			setTimeout(() => {
				qc.invalidateQueries({ queryKey: ['hosts', hostId, 'risk'] });
				qc.invalidateQueries({ queryKey: ['hosts', hostId, 'advisories'] });
			}, 5000);
		},
	});

	const color = LEVEL_COLOR[risk.level] ?? 'var(--color-text-dim)';
	const label = LEVEL_LABEL[risk.level] ?? risk.level;
	const score = risk.score ?? 0;

	const W = 200;
	const H = 100;
	const cx = W / 2;
	const cy = H - 6;
	const r = 78;

	const polar = (deg: number) => {
		const a = (deg * Math.PI) / 180;
		return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
	};
	const scoreToAngle = (s: number) => 180 + (Math.min(100, Math.max(0, s)) / 100) * 180;
	const arc = (from: number, to: number) => {
		const a1 = scoreToAngle(from);
		const a2 = scoreToAngle(to);
		const [x1, y1] = polar(a1);
		const [x2, y2] = polar(a2);
		return `M ${x1} ${y1} A ${r} ${r} 0 0 1 ${x2} ${y2}`;
	};
	const needleAngle = scoreToAngle(score);
	const [nx, ny] = polar(needleAngle);
	// Inner end of needle at 70% of radius so it traces only the outer
	// band and doesn't pierce the centered score readout.
	const innerR = r * 0.7;
	const innerA = (needleAngle * Math.PI) / 180;
	const innerX = cx + innerR * Math.cos(innerA);
	const innerY = cy + innerR * Math.sin(innerA);

	return (
		<section className="rounded border border-hairline bg-surface p-3">
			<div className="flex items-center justify-between">
				<div className="font-mono text-[10px] uppercase tracking-[0.18em] text-text-dim">
					Risk hero
				</div>
				<div className="flex items-center gap-1">
					<button
						type="button"
						onClick={() => recompute.mutate(hostId)}
						disabled={recompute.isPending}
						title="Recompute risk now"
						className="rounded border border-hairline bg-surface-2 px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-text-dim hover:text-text disabled:opacity-50"
					>
						<RotateCw
							size={11}
							className={recompute.isPending ? 'animate-spin inline' : 'inline'}
						/>{' '}
						Recompute
					</button>
					<button
						type="button"
						onClick={() => scan.mutate()}
						disabled={scan.isPending}
						title="Trigger fresh inventory + advisory match"
						className="rounded border border-accent bg-accent/15 px-2 py-1 font-mono text-[10px] font-semibold uppercase tracking-wider text-accent hover:bg-accent/25 disabled:opacity-50"
					>
						<RefreshCw size={11} className={scan.isPending ? 'animate-spin inline' : 'inline'} />{' '}
						{scan.isPending ? 'Scanning…' : 'Scan host'}
					</button>
				</div>
			</div>

			<div className="relative mt-2">
				<svg width="100%" viewBox={`0 0 ${W} ${H}`} aria-label="Risk gauge">
					<title>Risk gauge</title>
					{BANDS.map(b => (
						<path
							key={`${b.from}-${b.to}`}
							d={arc(b.from, b.to)}
							stroke={b.color}
							strokeOpacity={0.35}
							strokeWidth={9}
							fill="none"
						/>
					))}
					{score > 0 ? (
						<path
							d={arc(0, score)}
							stroke={color}
							strokeWidth={9}
							strokeLinecap="round"
							fill="none"
							style={{ filter: `drop-shadow(0 0 6px ${color})` }}
						/>
					) : null}
					<line
						x1={innerX}
						y1={innerY}
						x2={nx}
						y2={ny}
						stroke={color}
						strokeWidth={2.5}
						strokeLinecap="round"
						style={{ filter: `drop-shadow(0 0 3px ${color})` }}
					/>
					<circle cx={nx} cy={ny} r={2.5} fill={color} />
				</svg>
				<div className="pointer-events-none absolute inset-x-0 bottom-0 flex flex-col items-center font-mono leading-none">
					<span
						className="rounded-sm bg-surface/80 px-1.5 text-[22px] font-semibold tabular-nums backdrop-blur-sm"
						style={{ color }}
					>
						{risk.score ?? '—'}
					</span>
				</div>
			</div>

			<div className="mt-2 text-center">
				<div className="font-mono text-[12px] uppercase tracking-wider" style={{ color }}>
					{label}
				</div>
				<div className="mt-1 font-mono text-[10px] text-text-dim/80">
					conf {Math.round(risk.confidence * 100)}% ·{' '}
					<span title={risk.computed_at}>computed {relTime(risk.computed_at)}</span>
				</div>
				{risk.floor_triggered ? (
					<div className="mt-1 inline-flex items-center rounded-sm border border-warn/40 bg-warn/10 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-warn">
						Floor lifted — hot pillar
					</div>
				) : null}
			</div>
		</section>
	);
}
