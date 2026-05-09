'use client';

import type { PillarOut } from '@/lib/api/posture-risk';

const TONE: Record<'low' | 'mid' | 'hi', string> = {
	low: 'bg-ok',
	mid: 'bg-warn',
	hi: 'bg-danger',
};

function band(score: number): keyof typeof TONE {
	if (score > 65) return 'hi';
	if (score > 35) return 'mid';
	return 'low';
}

export function RiskPillarBar({ p }: { p: PillarOut }) {
	const w = Math.max(2, Math.min(100, p.score));
	const tone = TONE[band(p.score)];
	return (
		<div>
			<div className="flex items-center justify-between font-mono text-[10px]">
				<span className="text-text">{p.label}</span>
				<span className="text-text-dim">
					{Math.round(p.score)} · conf {Math.round(p.confidence * 100)}%
				</span>
			</div>
			<div className="mt-0.5 h-1.5 w-full rounded-sm bg-surface-2">
				<div className={`h-full rounded-sm ${tone}`} style={{ width: `${w}%` }} />
			</div>
			{p.drivers[0] ? (
				<div className="mt-0.5 truncate font-mono text-[9px] text-text-dim">
					{p.drivers[0].label}
				</div>
			) : null}
		</div>
	);
}
