'use client';

import { EmptyState } from '@/components/empty-states/empty-state';
import { RiskPillarBar } from '@/components/hosts/mission-control/risk-pillar-bar';
import { Disclosure } from '@/components/primitives/disclosure';
import { BlueprintSkeleton } from '@/components/skeletons/blueprint-skeleton';
import { apiFetch } from '@/lib/api-client';
import { useHostRisk, useRiskRecompute } from '@/lib/api/posture-risk';
import { relTime } from '@/lib/time';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { RefreshCw, RotateCw } from 'lucide-react';
import Link from 'next/link';
import { useState } from 'react';

interface Finding {
	id: string;
	severity: string;
	title: string;
	summary: string;
	fix_action_url: string | null;
	docs_url: string | null;
	rule: string;
	subject_kind: string;
	subject_id: string | null;
	first_seen: string | null;
	last_seen: string | null;
	suppressed_until: string | null;
}
interface PostureResponse {
	findings: Finding[];
}

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

// Rules that are pure aggregators of host_advisories — their detail row is
// redundant with the per-CVE Advisories tab. We hide their rule label and
// raw timestamps to keep the display human-readable.
const AGGREGATE_RULES = new Set(['host_advisory_summary']);

export function HostPosturePanel({ hostId }: { hostId: string }) {
	const qc = useQueryClient();
	const [scanMsg, setScanMsg] = useState<string | null>(null);

	const riskQ = useHostRisk(hostId);
	const recompute = useRiskRecompute();

	const postureQ = useQuery<PostureResponse>({
		queryKey: ['hosts', hostId, 'posture'],
		queryFn: () =>
			apiFetch<PostureResponse>(
				`/v1/posture?subject_kind=host&subject_id=${encodeURIComponent(hostId)}`,
			),
	});

	const scan = useMutation({
		mutationFn: () =>
			apiFetch<{ status: string; task_id: string }>(
				`/v1/hosts/${encodeURIComponent(hostId)}/rescan`,
				{ method: 'POST' },
			),
		onSuccess: () => {
			setScanMsg('Scan queued — refreshing in ~5s');
			setTimeout(() => {
				qc.invalidateQueries({ queryKey: ['hosts', hostId, 'posture'] });
				qc.invalidateQueries({ queryKey: ['hosts', hostId, 'advisories'] });
				qc.invalidateQueries({ queryKey: ['hosts', hostId, 'risk'] });
				setScanMsg(null);
			}, 5000);
		},
		onError: (e: Error) => setScanMsg(`Scan failed: ${e.message}`),
	});

	const ActionBar = (
		<div className="mb-3 flex items-center justify-between gap-2 rounded border border-hairline bg-surface px-3 py-2">
			<div className="text-xs text-text-dim">
				{scanMsg ??
					'Posture is computed from advisories, configuration findings, identity posture, and operational hygiene.'}
			</div>
			<div className="flex items-center gap-1.5">
				<button
					type="button"
					onClick={() => recompute.mutate(hostId)}
					disabled={recompute.isPending}
					title="Recompute risk score now (uses cached scan inputs)"
					className="flex items-center gap-1.5 rounded border border-hairline bg-surface-2 px-2.5 py-1 font-mono text-[11px] uppercase tracking-wider text-text-dim hover:text-text disabled:opacity-50"
				>
					<RotateCw size={11} className={recompute.isPending ? 'animate-spin' : ''} />
					{recompute.isPending ? 'Computing…' : 'Recompute'}
				</button>
				<button
					type="button"
					onClick={() => scan.mutate()}
					disabled={scan.isPending}
					title="Trigger fresh inventory + advisory match (slower)"
					className="flex items-center gap-1.5 rounded border border-accent bg-accent/15 px-3 py-1 font-mono text-[11px] font-semibold uppercase tracking-wider text-accent hover:bg-accent/25 disabled:opacity-50"
				>
					<RefreshCw size={11} className={scan.isPending ? 'animate-spin' : ''} />
					{scan.isPending ? 'Scanning…' : 'Scan host'}
				</button>
			</div>
		</div>
	);

	if (riskQ.isLoading || postureQ.isLoading)
		return (
			<>
				{ActionBar}
				<BlueprintSkeleton rows={5} />
			</>
		);

	const r = riskQ.data;
	const findings = postureQ.data?.findings ?? [];
	const sortedPillars = r
		? [...r.pillars].sort((a, b) => b.score * b.weight - a.score * a.weight)
		: [];

	const color = r ? (LEVEL_COLOR[r.level] ?? 'var(--color-text-dim)') : 'var(--color-text-dim)';
	const label = r ? (LEVEL_LABEL[r.level] ?? r.level) : '—';

	if (!r && postureQ.isError)
		return (
			<>
				{ActionBar}
				<EmptyState title="Failed to load posture" description="Try again." />
			</>
		);

	return (
		<div className="space-y-4">
			{ActionBar}

			{/* Risk summary card */}
			{r ? (
				<div className="rounded border border-hairline bg-surface p-4">
					<div className="flex items-baseline justify-between gap-3">
						<div>
							<div className="font-mono text-[10px] uppercase tracking-[0.18em] text-text-dim">
								Risk score
							</div>
							<div className="flex items-baseline gap-3">
								<span
									className="font-mono text-[40px] font-semibold leading-none tabular-nums"
									style={{ color }}
								>
									{r.score ?? '—'}
								</span>
								<span className="font-mono text-[12px] uppercase tracking-wider" style={{ color }}>
									{label}
								</span>
							</div>
						</div>
						<div className="text-right font-mono text-[10px] text-text-dim/80">
							<div>conf {Math.round(r.confidence * 100)}%</div>
							<div title={r.computed_at}>computed {relTime(r.computed_at)}</div>
							{r.floor_triggered ? (
								<div className="text-warn">floor lifted (hot pillar)</div>
							) : null}
						</div>
					</div>

					<div className="mt-4 space-y-2.5">
						{sortedPillars.map(p => (
							<div key={p.name}>
								<RiskPillarBar p={p} />
								{p.coverage_notes.length > 0 ? (
									<ul className="mt-0.5 ml-2 list-disc font-mono text-[10px] text-text-dim/70">
										{p.coverage_notes.map(n => (
											<li key={n}>{n}</li>
										))}
									</ul>
								) : null}
							</div>
						))}
					</div>

					<div className="mt-3 border-t border-hairline pt-2 text-[11px] text-text-dim">
						<Link href={`/hosts/${hostId}/risk`} className="text-accent hover:underline">
							Open full breakdown →
						</Link>
					</div>
				</div>
			) : null}

			{/* Findings detail (raw posture findings — secondary now) */}
			{findings.length === 0 ? (
				<EmptyState
					title="No posture findings"
					description="Vulnerability + configuration + identity drivers above are the canonical view."
				/>
			) : (
				<div>
					<div className="mb-2 font-mono text-[10px] uppercase tracking-[0.14em] text-text-dim">
						Findings ({findings.length})
					</div>
					<div className="space-y-2">
						{findings.map(f => {
							const isAggregate = AGGREGATE_RULES.has(f.rule);
							return (
								<Disclosure
									key={f.id}
									label={`[${f.severity}] ${f.title}`}
									storageKey={`finding-${f.id}`}
								>
									<div className="space-y-2 text-sm">
										{isAggregate ? (
											<p className="text-text-dim">
												See the Advisories tab for the per-CVE breakdown across this host.
											</p>
										) : (
											<>
												<p>{f.summary}</p>
												<p className="text-text-dim">
													Rule: <code className="text-text">{f.rule}</code>
												</p>
											</>
										)}
										{f.last_seen ? (
											<p className="text-text-dim">
												Last detected: <span title={f.last_seen}>{relTime(f.last_seen)}</span>
											</p>
										) : null}
										<div className="flex gap-3 text-xs">
											{f.fix_action_url ? (
												<a href={f.fix_action_url} className="text-blue-400 hover:underline">
													Fix
												</a>
											) : null}
											{f.docs_url ? (
												<a href={f.docs_url} className="text-blue-400 hover:underline">
													Docs
												</a>
											) : null}
										</div>
									</div>
								</Disclosure>
							);
						})}
					</div>
				</div>
			)}
		</div>
	);
}
