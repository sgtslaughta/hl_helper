'use client';

export const dynamic = 'force-dynamic';

import { EmptyState } from '@/components/empty-states/empty-state';
import { apiFetch } from '@/lib/api-client';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft } from 'lucide-react';
import Link from 'next/link';
import { use } from 'react';

interface AffectedPackage {
	ecosystem: string;
	package: string;
	introduced: string | null;
	fixed: string | null;
	range_kind: string;
}

interface AdvisoryDetail {
	id: string;
	severity: string;
	summary: string;
	kev: boolean;
	epss: number | null;
	modified: string | null;
	affected_packages: AffectedPackage[];
}

const SEVERITY_BADGE: Record<string, string> = {
	critical: 'bg-red-500/15 text-red-400 border-red-500/40',
	high: 'bg-orange-500/15 text-orange-400 border-orange-500/40',
	medium: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/40',
	low: 'bg-blue-500/15 text-blue-400 border-blue-500/40',
	unknown: 'bg-text-dim/10 text-text-dim border-text-dim/30',
};

export default function AdvisoryDetailPage({
	params,
}: {
	params: Promise<{ id: string }>;
}) {
	const { id } = use(params);
	const advisoryId = decodeURIComponent(id);

	const { data, isLoading, isError } = useQuery<AdvisoryDetail>({
		queryKey: ['advisories', advisoryId],
		queryFn: () =>
			apiFetch<AdvisoryDetail>(`/v1/advisories/${encodeURIComponent(advisoryId)}`),
	});

	if (isLoading) {
		return <div className="p-6 text-text-dim">Loading...</div>;
	}
	if (isError || !data) {
		return (
			<div className="p-6">
				<Link
					href="/advisories"
					className="mb-4 inline-flex items-center gap-1 text-sm text-accent hover:text-accent-dim"
				>
					<ArrowLeft className="h-4 w-4" /> Back to advisories
				</Link>
				<EmptyState
					title="Advisory not found"
					description={`No advisory in the catalog with id ${advisoryId}.`}
				/>
			</div>
		);
	}

	return (
		<div className="flex flex-col gap-6 p-6">
			<Link
				href="/advisories"
				className="inline-flex items-center gap-1 text-sm text-accent hover:text-accent-dim"
			>
				<ArrowLeft className="h-4 w-4" /> Back to advisories
			</Link>

			<div>
				<div className="flex items-center gap-3">
					<h1 className="font-mono text-h2 text-text">{data.id}</h1>
					<span
						className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-semibold ${
							SEVERITY_BADGE[data.severity] ?? SEVERITY_BADGE.unknown
						}`}
					>
						{data.severity}
					</span>
					{data.kev && (
						<span className="inline-flex items-center rounded bg-danger/20 px-2 py-0.5 text-xs font-semibold text-danger">
							KEV
						</span>
					)}
				</div>
				<p className="mt-3 max-w-4xl text-text-dim">{data.summary}</p>
			</div>

			<div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
				<div
					className="rounded border border-hairline bg-surface p-3"
					title="EPSS — Exploit Prediction Scoring System. 0.0–1.0 probability of in-the-wild exploitation within 30 days. Empty when the EPSS feed has no entry for this id or its aliases."
				>
					<div className="text-xs uppercase text-text-dim">EPSS</div>
					<div className="mt-1 font-mono text-text">
						{data.epss != null ? data.epss.toFixed(3) : '—'}
					</div>
				</div>
				<div
					className="rounded border border-hairline bg-surface p-3"
					title="Last modification timestamp from the advisory feed."
				>
					<div className="text-xs uppercase text-text-dim">Modified</div>
					<div className="mt-1 font-mono text-text text-xs">
						{data.modified ? new Date(data.modified).toLocaleString() : '—'}
					</div>
				</div>
				<div
					className="rounded border border-hairline bg-surface p-3"
					title="Number of distinct (ecosystem, package) entries marked vulnerable by this advisory."
				>
					<div className="text-xs uppercase text-text-dim">Affected packages</div>
					<div className="mt-1 font-mono text-text">{data.affected_packages.length}</div>
				</div>
				<div
					className="rounded border border-hairline bg-surface p-3"
					title="KEV — CISA Known Exploited Vulnerabilities catalog. Confirmed exploited in the wild."
				>
					<div className="text-xs uppercase text-text-dim">KEV</div>
					<div className="mt-1 font-mono text-text">{data.kev ? 'Yes' : 'No'}</div>
				</div>
			</div>

			<div>
				<h2 className="mb-2 text-h4 font-semibold text-text">Affected packages</h2>
				{data.affected_packages.length === 0 ? (
					<div className="text-text-dim">No package ranges recorded.</div>
				) : (
					<div className="overflow-x-auto rounded border border-hairline">
						<table className="w-full text-sm">
							<thead className="border-b border-hairline bg-surface-hover">
								<tr>
									<th
										className="px-4 py-2 text-left font-semibold text-text-dim"
										title="Package ecosystem identifier (e.g. PyPI, npm, Ubuntu:24.04:LTS, Debian:12). Determines how the version comparison is performed."
									>
										Ecosystem
									</th>
									<th className="px-4 py-2 text-left font-semibold text-text-dim">Package</th>
									<th
										className="px-4 py-2 text-left font-semibold text-text-dim"
										title="First version that contains the vulnerability. '0' means 'all versions from the very first release'."
									>
										Introduced
									</th>
									<th
										className="px-4 py-2 text-left font-semibold text-text-dim"
										title="First upstream version that fixes the vulnerability. 'No fix' means upstream has not published a patched release yet — only mitigations are available."
									>
										Fixed
									</th>
									<th
										className="px-4 py-2 text-left font-semibold text-text-dim"
										title="Range kind: ECOSYSTEM (use ecosystem-native version comparison), SEMVER (semantic versioning), GIT (commit hashes), VERSIONS (explicit list)."
									>
										Range kind
									</th>
								</tr>
							</thead>
							<tbody className="divide-y divide-hairline">
								{data.affected_packages.map((p, idx) => {
									const noRange = !p.introduced && !p.fixed;
									return (
										<tr key={`${p.ecosystem}:${p.package}:${idx}`}>
											<td className="px-4 py-2 text-text-dim">{p.ecosystem}</td>
											<td className="px-4 py-2 font-mono text-text">{p.package}</td>
											<td className="px-4 py-2">
												{p.introduced ? (
													<span className="font-mono text-text-dim">{p.introduced}</span>
												) : noRange ? (
													<span
														className="inline-flex items-center rounded border border-orange-500/40 bg-orange-500/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-orange-400"
														title="Feed does not specify a version range — treat all installed versions as potentially affected until upstream publishes more detail."
													>
														All versions
													</span>
												) : (
													<span className="text-text-dim">—</span>
												)}
											</td>
											<td className="px-4 py-2">
												{p.fixed ? (
													<span className="font-mono text-ok">{p.fixed}</span>
												) : (
													<span
														className="inline-flex items-center rounded border border-text-dim/40 bg-text-dim/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-text-dim"
														title="No upstream fix is published yet for this advisory."
													>
														No fix
													</span>
												)}
											</td>
											<td className="px-4 py-2 text-text-dim">{p.range_kind}</td>
										</tr>
									);
								})}
							</tbody>
						</table>
					</div>
				)}
			</div>
		</div>
	);
}
