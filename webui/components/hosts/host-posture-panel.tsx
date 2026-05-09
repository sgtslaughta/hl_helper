'use client';

import { EmptyState } from '@/components/empty-states/empty-state';
import { Disclosure } from '@/components/primitives/disclosure';
import { BlueprintSkeleton } from '@/components/skeletons/blueprint-skeleton';
import { apiFetch } from '@/lib/api-client';
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
	info: 'bg-text-dim/10 text-text-dim border-text-dim/30',
};

export function HostPosturePanel({ hostId }: { hostId: string }) {
	const qc = useQueryClient();
	const [scanMsg, setScanMsg] = useState<string | null>(null);
	const q = useQuery<PostureResponse>({
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

	if (q.isLoading) return <>{ScanBar}<BlueprintSkeleton rows={4} /></>;
	if (q.isError)
		return <>{ScanBar}<EmptyState title="Failed to load posture" description="Try again." /></>;

	const findings = q.data?.findings ?? [];
	if (findings.length === 0)
		return (
			<>
				{ScanBar}
				<EmptyState title="No findings" description="This host has no open posture issues." />
			</>
		);

	const counts = findings.reduce<Record<string, number>>((a, f) => {
		a[f.severity] = (a[f.severity] ?? 0) + 1;
		return a;
	}, {});

	return (
		<div className="space-y-4">
			{ScanBar}
			<div className="rounded border border-hairline bg-surface p-4">
				<h3 className="mb-2 text-h4 font-semibold text-text">Posture summary</h3>
				<div className="flex flex-wrap gap-3 text-sm">
					<span className="text-text-dim">
						{findings.length} finding{findings.length === 1 ? '' : 's'}
					</span>
					{Object.entries(counts).map(([sev, n]) => (
						<span
							key={sev}
							className={`inline-flex items-center rounded border px-2 py-0.5 text-xs ${
								SEVERITY_COLORS[sev] ?? SEVERITY_COLORS.info
							}`}
						>
							{n} {sev}
						</span>
					))}
				</div>
			</div>
			<div className="space-y-2">
				{findings.map(f => (
					<Disclosure
						key={f.id}
						label={`[${f.severity}] ${f.title}`}
						storageKey={`finding-${f.id}`}
					>
						<div className="space-y-2 text-sm">
							<p>{f.summary}</p>
							<p className="text-text-dim">
								Rule: <code className="text-text">{f.rule}</code>
							</p>
							{f.last_seen ? <p className="text-text-dim">Last seen: {f.last_seen}</p> : null}
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
				))}
			</div>
		</div>
	);
}
