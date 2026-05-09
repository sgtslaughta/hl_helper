'use client';

import type { AuditEntry } from '@/hooks/use-host-audit-by-action';
import { relTime } from '@/lib/time';

const LEVEL_ORDER: Record<string, number> = {
	minimal: 0,
	stable: 1,
	moderate: 2,
	elevated: 3,
	high: 4,
	severe: 5,
	unknown: -1,
};

function deltaTone(delta: number, levelMoved: -1 | 0 | 1): string {
	if (levelMoved < 0) return 'text-ok';
	if (levelMoved > 0) return 'text-danger';
	if (delta > 0) return 'text-warn';
	if (delta < 0) return 'text-accent';
	return 'text-text-dim';
}

interface RowData {
	score: number | null;
	level: string;
	score_prev: number | null;
	level_prev: string | null;
	trigger_reason: string;
}

function readPayload(p: Record<string, unknown> | null | undefined): RowData {
	const get = (k: string): unknown => (p && typeof p === 'object' ? p[k] : undefined);
	return {
		score: typeof get('score') === 'number' ? (get('score') as number) : null,
		level: typeof get('level') === 'string' ? (get('level') as string) : 'unknown',
		score_prev: typeof get('score_prev') === 'number' ? (get('score_prev') as number) : null,
		level_prev: typeof get('level_prev') === 'string' ? (get('level_prev') as string) : null,
		trigger_reason:
			typeof get('trigger_reason') === 'string' ? (get('trigger_reason') as string) : '—',
	};
}

export function RiskRecentActivity({ entries }: { entries: AuditEntry[] }) {
	return (
		<section className="rounded border border-hairline bg-surface p-3">
			<div className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-text-dim">
				Recent activity
			</div>
			{entries.length === 0 ? (
				<div className="font-mono text-xs text-text-dim/70">No risk recomputes recorded yet.</div>
			) : (
				<ul className="space-y-1.5 font-mono text-[11px]">
					{entries.map(e => {
						const d = readPayload(e.payload);
						const delta = d.score != null && d.score_prev != null ? d.score - d.score_prev : 0;
						const levelMoved =
							d.level_prev && d.level !== d.level_prev
								? (Math.sign((LEVEL_ORDER[d.level] ?? -1) - (LEVEL_ORDER[d.level_prev] ?? -1)) as
										| -1
										| 0
										| 1)
								: 0;
						const tone = deltaTone(delta, levelMoved);
						const transition =
							d.level_prev && d.level !== d.level_prev ? `${d.level_prev} → ${d.level}` : d.level;
						return (
							<li
								key={e.sequence}
								className="flex items-center gap-2 truncate border-b border-hairline pb-1 last:border-0"
							>
								<span
									className="shrink-0 text-text-dim/70"
									title={new Date(e.timestamp).toLocaleString()}
								>
									{relTime(e.timestamp)}
								</span>
								<span className="truncate text-text">
									{transition}
									<span className="text-text-dim"> ({d.score ?? '—'})</span>
								</span>
								<span className={`shrink-0 tabular-nums ${tone}`}>
									{delta > 0 ? '+' : ''}
									{delta}
								</span>
								<span className="ml-auto shrink-0 rounded-sm border border-hairline px-1 py-0 text-[9px] uppercase tracking-wider text-text-dim/80">
									{d.trigger_reason}
								</span>
							</li>
						);
					})}
				</ul>
			)}
		</section>
	);
}
