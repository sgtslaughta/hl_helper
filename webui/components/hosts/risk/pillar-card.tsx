'use client';

import { RiskPillarBar } from '@/components/hosts/mission-control/risk-pillar-bar';
import type { PillarOut } from '@/lib/api/posture-risk';
import Link from 'next/link';
import type { ReactNode } from 'react';
import { PILLAR_DETAIL_RENDERERS } from './registry';

interface Props {
	p: PillarOut;
	hostId: string;
	renderExtra?: (p: PillarOut) => ReactNode;
}

function deepLink(name: string, hostId: string): { href: string; label: string } {
	switch (name) {
		case 'vulnerabilities':
			return {
				href: `/advisories?host_id=${encodeURIComponent(hostId)}`,
				label: 'Open advisories',
			};
		case 'configuration':
		case 'identity':
			return { href: `/hosts/${encodeURIComponent(hostId)}`, label: 'Open posture tab' };
		case 'hygiene':
			return { href: `/hosts/${encodeURIComponent(hostId)}`, label: 'Open hardware tab' };
		default:
			return { href: `/hosts/${encodeURIComponent(hostId)}`, label: 'Open host' };
	}
}

export function RiskPillarCard({ p, hostId, renderExtra }: Props) {
	const link = deepLink(p.name, hostId);
	const top = [...p.drivers].sort((a, b) => b.contrib - a.contrib).slice(0, 3);
	const extra = renderExtra ?? PILLAR_DETAIL_RENDERERS[p.name];

	return (
		<section className="flex flex-col gap-2 rounded border border-hairline bg-surface p-4">
			<div className="flex items-center justify-between">
				<div className="font-mono text-[12px] font-semibold uppercase tracking-wider text-text">
					{p.label}
				</div>
				<span className="rounded-sm border border-hairline px-1.5 py-0 font-mono text-[9px] uppercase tracking-wider text-text-dim">
					weight {p.weight.toFixed(2)}
				</span>
			</div>

			<RiskPillarBar p={p} />

			{top.length > 0 ? (
				<div className="space-y-0.5">
					<div className="font-mono text-[9px] uppercase tracking-[0.14em] text-text-dim">
						Top drivers
					</div>
					{top.map(d => (
						<div
							key={`${p.name}-${d.label}`}
							className="flex items-center gap-1.5 truncate font-mono text-[11px]"
						>
							<span className="truncate text-text">{d.label}</span>
							<span className="ml-auto shrink-0 text-text-dim tabular-nums">
								{d.contrib.toFixed(1)}
							</span>
							{d.href ? (
								<Link
									href={d.href}
									className="shrink-0 text-accent hover:underline"
									aria-label="open driver"
								>
									→
								</Link>
							) : null}
						</div>
					))}
				</div>
			) : null}

			{p.coverage_notes.length > 0 ? (
				<ul className="ml-3 list-disc space-y-0.5 font-mono text-[10px] text-text-dim/80">
					{p.coverage_notes.map(n => (
						<li key={n}>{n}</li>
					))}
				</ul>
			) : null}

			{extra ? <div className="border-t border-hairline pt-2">{extra(p)}</div> : null}

			<Link
				href={link.href}
				className="self-end font-mono text-[10px] uppercase tracking-wider text-accent hover:underline"
			>
				{link.label} →
			</Link>
		</section>
	);
}
