'use client';

import { EmptyState } from '@/components/empty-states/empty-state';
import { Disclosure } from '@/components/primitives/disclosure';
import { BlueprintSkeleton } from '@/components/skeletons/blueprint-skeleton';
import { apiFetch } from '@/lib/api-client';
import { useHostAdvisories } from '@/lib/api/advisories';
import { relTime } from '@/lib/time';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
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

const SEVERITY_COLORS: Record<string, string> = {
	critical: 'bg-red-500/15 text-red-400 border-red-500/40',
	high: 'bg-orange-500/15 text-orange-400 border-orange-500/40',
	medium: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/40',
	low: 'bg-blue-500/15 text-blue-400 border-blue-500/40',
	unknown: 'bg-text-dim/10 text-text-dim border-text-dim/30',
	info: 'bg-text-dim/10 text-text-dim border-text-dim/30',
};

const SEVERITY_ORDER = ['critical', 'high', 'medium', 'low', 'unknown'] as const;

// Rules that are pure aggregators of host_advisories — their detail row is
// redundant with the per-CVE Advisories tab. We hide their rule label and
// raw timestamps to keep the display human-readable.
const AGGREGATE_RULES = new Set(['host_advisory_summary']);

export function HostPosturePanel({ hostId }: { hostId: string }) {
	const qc = useQueryClient();
	const [scanMsg, setScanMsg] = useState<string | null>(null);

	const postureQ = useQuery<PostureResponse>({
		queryKey: ['hosts', hostId, 'posture'],
		queryFn: () =>
			apiFetch<PostureResponse>(
				`/v1/posture?subject_kind=host&subject_id=${encodeURIComponent(hostId)}`,
			),
	});

	// Pull actual host advisories so severity counts reflect the per-CVE
	// distribution (4 high, 2 medium, ...) rather than the count of
	// posture-finding rows (often just 1 aggregate row).
	const advisoriesQ = useHostAdvisories(hostId, { status: 'open' });

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
				setScanMsg(null);
			}, 5000);
		},
		onError: (e: Error) => setScanMsg(`Scan failed: ${e.message}`),
	});

	const ScanBar = (
		<div className="mb-3 flex items-center justify-between rounded border border-hairline bg-surface px-3 py-2">
			<div className="text-xs text-text-dim">
				{scanMsg ?? 'Trigger fresh inventory + advisory match on this host.'}
			</div>
			<button
				type="button"
				onClick={() => scan.mutate()}
				disabled={scan.isPending}
				className="rounded border border-hairline bg-bg-2 px-3 py-1 font-mono text-xs text-text hover:bg-bg-3 disabled:opacity-50"
			>
				{scan.isPending ? '…scanning' : 'Run Posture Scan'}
			</button>
		</div>
	);

	if (postureQ.isLoading)
		return (
			<>
				{ScanBar}
				<BlueprintSkeleton rows={4} />
			</>
		);
	if (postureQ.isError)
		return (
			<>
				{ScanBar}
				<EmptyState title="Failed to load posture" description="Try again." />
			</>
		);

	const findings = postureQ.data?.findings ?? [];
	const advisories = advisoriesQ.data?.items ?? [];

	if (findings.length === 0 && advisories.length === 0)
		return (
			<>
				{ScanBar}
				<EmptyState title="No findings" description="This host has no open posture issues." />
			</>
		);

	// Severity counts: prefer real advisory distribution; fall back to posture
	// findings if advisories endpoint failed/empty.
	const advisoryCounts = advisories.reduce<Record<string, number>>((a, ha) => {
		const sev = ha.severity?.toLowerCase() || 'unknown';
		a[sev] = (a[sev] ?? 0) + 1;
		return a;
	}, {});
	const findingCounts = findings.reduce<Record<string, number>>((a, f) => {
		const sev = f.severity?.toLowerCase() || 'unknown';
		a[sev] = (a[sev] ?? 0) + 1;
		return a;
	}, {});
	const useAdvisoryDist = advisories.length > 0;
	const counts = useAdvisoryDist ? advisoryCounts : findingCounts;
	const totalForCounts = useAdvisoryDist ? advisories.length : findings.length;

	return (
		<div className="space-y-4">
			{ScanBar}
			<div className="rounded border border-hairline bg-surface p-4">
				<h3 className="mb-2 text-h4 font-semibold text-text">Posture summary</h3>
				<div className="flex flex-wrap items-center gap-3 text-sm">
					<span className="text-text-dim">
						{totalForCounts} {useAdvisoryDist ? 'open advisory' : 'finding'}
						{totalForCounts === 1 ? '' : useAdvisoryDist ? ' advisories' : 's'}
					</span>
					{SEVERITY_ORDER.map(sev => {
						const n = counts[sev] ?? 0;
						if (n === 0) return null;
						return (
							<span
								key={sev}
								className={`inline-flex items-center rounded border px-2 py-0.5 text-xs ${
									SEVERITY_COLORS[sev] ?? SEVERITY_COLORS.info
								}`}
							>
								{n} {sev}
							</span>
						);
					})}
					{!useAdvisoryDist && findings.length > 0 ? (
						<span className="text-text-dim/60 text-xs italic">(advisory data unavailable)</span>
					) : null}
				</div>
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
	);
}
