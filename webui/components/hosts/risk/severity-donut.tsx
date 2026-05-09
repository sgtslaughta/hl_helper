'use client';

import type { HostAdvisory } from '@/lib/api/advisories';
import { useState } from 'react';

interface Slice {
	key: string;
	label: string;
	count: number;
	color: string;
}

const SEVERITY_ORDER = ['critical', 'high', 'medium', 'low', 'unknown'] as const;
const COLOR: Record<string, string> = {
	critical: 'var(--color-danger)',
	high: '#ff8400',
	medium: 'var(--color-warn)',
	low: 'var(--color-accent)',
	unknown: 'var(--color-text-dim)',
};

export function RiskSeverityDonut({
	advisories,
	hostId,
}: {
	advisories: HostAdvisory[];
	hostId: string;
}) {
	const [hover, setHover] = useState<string | null>(null);
	const buckets: Record<string, number> = {
		critical: 0,
		high: 0,
		medium: 0,
		low: 0,
		unknown: 0,
	};
	for (const a of advisories) {
		const k = (a.severity || 'unknown').toLowerCase();
		buckets[k] = (buckets[k] ?? 0) + 1;
	}
	const slices: Slice[] = SEVERITY_ORDER.filter(s => buckets[s] > 0).map(s => ({
		key: s,
		label: s,
		count: buckets[s],
		color: COLOR[s],
	}));
	const total = slices.reduce((a, s) => a + s.count, 0);

	const navigate = (sev: string) => {
		if (typeof window !== 'undefined') {
			window.location.href = `/advisories?host_id=${encodeURIComponent(hostId)}&severity=${sev}`;
		}
	};

	const W = 160;
	const cx = W / 2;
	const cy = W / 2;
	const r = W / 2 - 4;
	const innerR = r * 0.6;

	let acc = 0;
	const paths = slices.map(s => {
		const startA = (acc / Math.max(1, total)) * Math.PI * 2 - Math.PI / 2;
		acc += s.count;
		const endA = (acc / Math.max(1, total)) * Math.PI * 2 - Math.PI / 2;
		const large = s.count / total > 0.5 ? 1 : 0;
		const x1 = cx + r * Math.cos(startA);
		const y1 = cy + r * Math.sin(startA);
		const x2 = cx + r * Math.cos(endA);
		const y2 = cy + r * Math.sin(endA);
		const xi2 = cx + innerR * Math.cos(endA);
		const yi2 = cy + innerR * Math.sin(endA);
		const xi1 = cx + innerR * Math.cos(startA);
		const yi1 = cy + innerR * Math.sin(startA);
		const d = [
			`M ${x1} ${y1}`,
			`A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`,
			`L ${xi2} ${yi2}`,
			`A ${innerR} ${innerR} 0 ${large} 0 ${xi1} ${yi1}`,
			'Z',
		].join(' ');
		return { slice: s, d };
	});

	const hovered = slices.find(s => s.key === hover) ?? null;

	return (
		<section className="rounded border border-hairline bg-surface p-4">
			<div className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-text-dim">
				Severity distribution
			</div>
			{total === 0 ? (
				<div className="flex h-[140px] items-center justify-center font-mono text-xs text-ok">
					No open advisories
				</div>
			) : (
				<div className="flex items-center gap-4">
					<div className="relative shrink-0" style={{ width: W, height: W }}>
						<svg width={W} height={W} role="img" aria-label="Severity distribution">
							<title>Open advisories by severity</title>
							{paths.map(({ slice, d }) => {
								const isHover = hover === slice.key;
								return (
									<path
										key={slice.key}
										d={d}
										fill={slice.color}
										fillOpacity={hover && !isHover ? 0.3 : 0.85}
										stroke="var(--color-bezel)"
										strokeWidth={1}
										style={{
											filter: isHover
												? 'brightness(1.4) drop-shadow(0 0 6px currentColor)'
												: undefined,
											color: slice.color,
											cursor: 'pointer',
											transition: 'fill-opacity 120ms, filter 120ms',
										}}
										onMouseEnter={() => setHover(slice.key)}
										onMouseLeave={() => setHover(null)}
										onClick={() => navigate(slice.key)}
										role="button"
										tabIndex={0}
										onKeyDown={ev => {
											if (ev.key === 'Enter' || ev.key === ' ') {
												ev.preventDefault();
												navigate(slice.key);
											}
										}}
										aria-label={`${slice.count} ${slice.key} advisories`}
									/>
								);
							})}
						</svg>
						<div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center font-mono leading-none">
							<span className="text-[18px] font-semibold text-text">
								{hovered ? hovered.count : total}
							</span>
							<span className="text-[8px] uppercase tracking-wider text-text-dim mt-0.5">
								{hovered ? hovered.label : 'open'}
							</span>
						</div>
					</div>
					<ul className="flex flex-1 flex-col gap-1 font-mono text-[11px]">
						{slices.map(s => (
							<li key={s.key}>
								<button
									type="button"
									onMouseEnter={() => setHover(s.key)}
									onMouseLeave={() => setHover(null)}
									onClick={() => navigate(s.key)}
									className={`flex w-full items-center gap-2 rounded px-1 py-0.5 text-left hover:bg-surface-2 ${
										hover === s.key ? 'bg-surface-2' : ''
									}`}
								>
									<span
										className="h-2 w-2 shrink-0 rounded-sm"
										style={{ backgroundColor: s.color }}
									/>
									<span className="text-text-dim uppercase tracking-wider w-16">{s.label}</span>
									<span className="text-text font-mono">{s.count}</span>
									<span className="ml-auto text-text-dim/70 font-mono">
										{((s.count / total) * 100).toFixed(0)}%
									</span>
								</button>
							</li>
						))}
					</ul>
				</div>
			)}
		</section>
	);
}
