'use client';

import type { PillarOut } from '@/lib/api/posture-risk';
import { ArrowDown, ArrowUp, ArrowUpDown, ExternalLink } from 'lucide-react';
import Link from 'next/link';
import { useMemo, useState } from 'react';

interface FlatDriver {
	pillarName: string;
	pillarLabel: string;
	label: string;
	contrib: number;
	href: string | null | undefined;
}

type SortKey = 'pillar' | 'label' | 'contrib';
type SortDir = 'asc' | 'desc';

export function RiskDriversTable({ pillars }: { pillars: PillarOut[] }) {
	const [sortKey, setSortKey] = useState<SortKey>('contrib');
	const [sortDir, setSortDir] = useState<SortDir>('desc');

	const rows: FlatDriver[] = useMemo(() => {
		const flat: FlatDriver[] = [];
		for (const p of pillars) {
			for (const d of p.drivers) {
				flat.push({
					pillarName: p.name,
					pillarLabel: p.label,
					label: d.label,
					contrib: d.contrib,
					href: d.href,
				});
			}
		}
		return flat;
	}, [pillars]);

	const sorted = useMemo(() => {
		const arr = [...rows];
		const dir = sortDir === 'asc' ? 1 : -1;
		arr.sort((a, b) => {
			let av: string | number = '';
			let bv: string | number = '';
			switch (sortKey) {
				case 'pillar':
					av = a.pillarLabel.toLowerCase();
					bv = b.pillarLabel.toLowerCase();
					break;
				case 'label':
					av = a.label.toLowerCase();
					bv = b.label.toLowerCase();
					break;
				case 'contrib':
					av = a.contrib;
					bv = b.contrib;
					break;
			}
			if (av < bv) return -1 * dir;
			if (av > bv) return 1 * dir;
			return 0;
		});
		return arr;
	}, [rows, sortKey, sortDir]);

	const toggle = (k: SortKey) => {
		if (sortKey === k) setSortDir(d => (d === 'asc' ? 'desc' : 'asc'));
		else {
			setSortKey(k);
			setSortDir(k === 'contrib' ? 'desc' : 'asc');
		}
	};
	const Icon = ({ k }: { k: SortKey }) => {
		if (sortKey !== k) return <ArrowUpDown size={10} className="opacity-40" />;
		return sortDir === 'asc' ? <ArrowUp size={10} /> : <ArrowDown size={10} />;
	};

	return (
		<section className="rounded border border-hairline bg-surface p-4">
			<div className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-text-dim">
				Drivers ({sorted.length})
			</div>
			{sorted.length === 0 ? (
				<div className="font-mono text-xs text-text-dim/70">No driver detail available.</div>
			) : (
				<div className="overflow-x-auto">
					<table className="w-full font-mono text-[11px]">
						<thead>
							<tr className="border-b border-hairline text-[10px] uppercase tracking-[0.14em] text-text-dim">
								<th className="px-2 py-1.5 text-left">
									<button
										type="button"
										onClick={() => toggle('pillar')}
										className="inline-flex items-center gap-1 hover:text-text"
									>
										Pillar <Icon k="pillar" />
									</button>
								</th>
								<th className="px-2 py-1.5 text-left">
									<button
										type="button"
										onClick={() => toggle('label')}
										className="inline-flex items-center gap-1 hover:text-text"
									>
										Driver <Icon k="label" />
									</button>
								</th>
								<th className="px-2 py-1.5 text-right">
									<button
										type="button"
										onClick={() => toggle('contrib')}
										className="inline-flex items-center gap-1 hover:text-text"
									>
										Contrib <Icon k="contrib" />
									</button>
								</th>
								<th className="w-10 px-2 py-1.5 text-right" aria-label="open" />
							</tr>
						</thead>
						<tbody>
							{sorted.map((d, i) => (
								<tr
									key={`${d.pillarName}-${d.label}-${i}`}
									className="border-b border-hairline last:border-0 hover:bg-surface-2"
								>
									<td className="px-2 py-1 text-text-dim">{d.pillarLabel}</td>
									<td className="px-2 py-1 text-text truncate">{d.label}</td>
									<td className="px-2 py-1 text-right text-text tabular-nums">
										{d.contrib.toFixed(1)}
									</td>
									<td className="px-2 py-1 text-right">
										{d.href ? (
											<Link
												href={d.href}
												className="inline-flex items-center justify-end text-accent hover:underline"
												aria-label="open driver"
											>
												<ExternalLink size={11} />
											</Link>
										) : null}
									</td>
								</tr>
							))}
						</tbody>
					</table>
				</div>
			)}
		</section>
	);
}
