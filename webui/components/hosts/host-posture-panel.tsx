'use client';

import { EmptyState } from '@/components/empty-states/empty-state';
import { Disclosure } from '@/components/primitives/disclosure';
import { BlueprintSkeleton } from '@/components/skeletons/blueprint-skeleton';
import { apiFetch } from '@/lib/api-client';
import { useQuery } from '@tanstack/react-query';

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
	const q = useQuery<PostureResponse>({
		queryKey: ['hosts', hostId, 'posture'],
		queryFn: () =>
			apiFetch<PostureResponse>(
				`/v1/posture?subject_kind=host&subject_id=${encodeURIComponent(hostId)}`,
			),
	});

	if (q.isLoading) return <BlueprintSkeleton rows={4} />;
	if (q.isError) return <EmptyState title="Failed to load posture" description="Try again." />;

	const findings = q.data?.findings ?? [];
	if (findings.length === 0)
		return <EmptyState title="No findings" description="This host has no open posture issues." />;

	const counts = findings.reduce<Record<string, number>>((a, f) => {
		a[f.severity] = (a[f.severity] ?? 0) + 1;
		return a;
	}, {});

	return (
		<div className="space-y-4">
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
