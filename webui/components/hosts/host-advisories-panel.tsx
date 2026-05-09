'use client';

import { EmptyState } from '@/components/empty-states/empty-state';
import { BlueprintSkeleton } from '@/components/skeletons/blueprint-skeleton';
import {
	useHostAdvisories,
	useSuppressHostAdvisory,
	useUnsuppressHostAdvisory,
	type HostAdvisory,
} from '@/lib/api/advisories';
import { Fragment, useMemo, useState } from 'react';
import { AlertCircle, ChevronDown, ChevronRight } from 'lucide-react';
import Link from 'next/link';

const SEVERITY_COLORS: Record<string, string> = {
	critical: 'bg-red-500/15 text-red-400 border-red-500/40',
	high: 'bg-orange-500/15 text-orange-400 border-orange-500/40',
	medium: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/40',
	low: 'bg-blue-500/15 text-blue-400 border-blue-500/40',
	unknown: 'bg-text-dim/10 text-text-dim border-text-dim/30',
	info: 'bg-text-dim/10 text-text-dim border-text-dim/30',
};

const SEVERITY_RANK: Record<string, number> = {
	critical: 4,
	high: 3,
	medium: 2,
	low: 1,
	unknown: 0,
};

const ALL_SEVERITIES = ['critical', 'high', 'medium', 'low', 'unknown'] as const;

type SortKey = 'severity' | 'package' | 'count';

interface AggregatedRow {
	key: string;
	package: string;
	severity: string;
	count: number;
	currentVersion: string;
	fixedVersion: string | null;
	kev: boolean;
	maxEpss: number | null;
	advisories: HostAdvisory[];
}

interface SuppressDialogState {
	open: boolean;
	advisoryId: string;
	hostId: string;
	reason: string;
	expiresInDays: number;
}

function aggregate(rows: HostAdvisory[]): AggregatedRow[] {
	const map = new Map<string, AggregatedRow>();
	for (const r of rows) {
		const sev = r.severity || 'unknown';
		const key = `${r.package_name}::${sev}`;
		const cur = map.get(key);
		if (!cur) {
			map.set(key, {
				key,
				package: r.package_name,
				severity: sev,
				count: 1,
				currentVersion: r.current_version,
				fixedVersion: r.fixed_version,
				kev: !!r.kev,
				maxEpss: r.epss ?? null,
				advisories: [r],
			});
		} else {
			cur.count += 1;
			cur.kev = cur.kev || !!r.kev;
			if (r.epss != null && (cur.maxEpss == null || r.epss > cur.maxEpss)) {
				cur.maxEpss = r.epss;
			}
			// Prefer a non-null fixed version
			if (!cur.fixedVersion && r.fixed_version) cur.fixedVersion = r.fixed_version;
			cur.advisories.push(r);
		}
	}
	return Array.from(map.values());
}

function sortRows(rows: AggregatedRow[], key: SortKey, dir: 'asc' | 'desc'): AggregatedRow[] {
	const m = dir === 'asc' ? 1 : -1;
	const sorted = [...rows];
	sorted.sort((a, b) => {
		switch (key) {
			case 'severity': {
				const ra = SEVERITY_RANK[a.severity] ?? 0;
				const rb = SEVERITY_RANK[b.severity] ?? 0;
				if (ra !== rb) return (ra - rb) * m;
				return a.package.localeCompare(b.package);
			}
			case 'package':
				return a.package.localeCompare(b.package) * m;
			case 'count':
				return (a.count - b.count) * m;
		}
	});
	return sorted;
}

export function HostAdvisoriesPanel({ hostId }: { hostId: string }) {
	const [statusFilter, setStatusFilter] = useState<string>('open');
	const [sevFilter, setSevFilter] = useState<Set<string>>(new Set());
	const [sortKey, setSortKey] = useState<SortKey>('severity');
	const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
	const [expanded, setExpanded] = useState<Set<string>>(new Set());
	const [search, setSearch] = useState('');
	const [dialogState, setDialogState] = useState<SuppressDialogState>({
		open: false,
		advisoryId: '',
		hostId: '',
		reason: '',
		expiresInDays: 30,
	});

	const q = useHostAdvisories(hostId, {
		status: statusFilter !== 'all' ? statusFilter : undefined,
	});

	const suppressMutation = useSuppressHostAdvisory();
	const unsuppressMutation = useUnsuppressHostAdvisory();

	const advisories = q.data?.items ?? [];

	const sevCounts = useMemo(() => {
		const c: Record<string, number> = {};
		for (const a of advisories) c[a.severity || 'unknown'] = (c[a.severity || 'unknown'] ?? 0) + 1;
		return c;
	}, [advisories]);

	const filtered = useMemo(() => {
		const s = search.trim().toLowerCase();
		return advisories.filter(a => {
			if (sevFilter.size > 0 && !sevFilter.has(a.severity || 'unknown')) return false;
			if (s) {
				const hay = `${a.package_name} ${a.advisory_id}`.toLowerCase();
				if (!hay.includes(s)) return false;
			}
			return true;
		});
	}, [advisories, sevFilter, search]);

	const aggregated = useMemo(
		() => sortRows(aggregate(filtered), sortKey, sortDir),
		[filtered, sortKey, sortDir],
	);

	const openCount = advisories.filter(a => a.status === 'open').length;
	const suppressedCount = advisories.filter(a => a.status === 'suppressed').length;
	const fixedCount = advisories.filter(a => a.status === 'fixed').length;

	const toggleExpanded = (key: string) => {
		setExpanded(prev => {
			const next = new Set(prev);
			if (next.has(key)) next.delete(key);
			else next.add(key);
			return next;
		});
	};

	const toggleSevFilter = (sev: string) => {
		setSevFilter(prev => {
			const next = new Set(prev);
			if (next.has(sev)) next.delete(sev);
			else next.add(sev);
			return next;
		});
	};

	const cycleSort = (key: SortKey) => {
		if (sortKey !== key) {
			setSortKey(key);
			setSortDir(key === 'package' ? 'asc' : 'desc');
		} else {
			setSortDir(d => (d === 'asc' ? 'desc' : 'asc'));
		}
	};

	const handleSuppressClick = (advisory: HostAdvisory) => {
		setDialogState({
			open: true,
			advisoryId: advisory.id,
			hostId,
			reason: '',
			expiresInDays: 30,
		});
	};

	const handleSuppressConfirm = async () => {
		const expiresAt = new Date();
		expiresAt.setDate(expiresAt.getDate() + dialogState.expiresInDays);

		await suppressMutation.mutateAsync({
			id: dialogState.advisoryId,
			hostId,
			reason: dialogState.reason,
			expiresAt: expiresAt.toISOString(),
		});

		setDialogState(prev => ({ ...prev, open: false }));
	};

	const handleUnsuppressClick = async (advisory: HostAdvisory) => {
		await unsuppressMutation.mutateAsync({
			id: advisory.id,
			hostId,
		});
	};

	if (q.isLoading) return <BlueprintSkeleton rows={4} />;
	if (q.isError) return <EmptyState title="Failed to load advisories" description="Try again." />;

	if (advisories.length === 0) {
		return (
			<EmptyState
				title="No open advisories"
				description="This host has no open advisories."
			/>
		);
	}

	const sortIndicator = (key: SortKey) =>
		sortKey === key ? (sortDir === 'asc' ? ' ↑' : ' ↓') : '';

	return (
		<div className="space-y-4">
			{/* Status filter chips */}
			<div className="flex flex-wrap gap-2">
				{['all', 'open', 'suppressed', 'fixed'].map(status => (
					<button
						key={status}
						onClick={() => setStatusFilter(status)}
						className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
							statusFilter === status
								? 'bg-accent text-canvas'
								: 'border border-hairline bg-surface text-text-dim hover:bg-surface-hover'
						}`}
					>
						{status === 'all' ? 'All' : status.charAt(0).toUpperCase() + status.slice(1)} (
						{status === 'all'
							? advisories.length
							: advisories.filter(a => a.status === status).length}
						)
					</button>
				))}
			</div>

			{/* Summary card */}
			<div className="rounded border border-hairline bg-surface p-4">
				<div className="mb-2 flex items-center justify-between">
					<h3 className="text-h4 font-semibold text-text">Advisory summary</h3>
					<div className="text-xs text-text-dim">
						{aggregated.length} package/severity groups · {filtered.length} CVEs
					</div>
				</div>
				<div className="flex flex-wrap gap-3 text-sm">
					{openCount > 0 && (
						<span className={`inline-flex items-center rounded border px-2 py-0.5 text-xs ${SEVERITY_COLORS.critical}`}>
							{openCount} Open
						</span>
					)}
					{suppressedCount > 0 && (
						<span className={`inline-flex items-center rounded border px-2 py-0.5 text-xs ${SEVERITY_COLORS.medium}`}>
							{suppressedCount} Suppressed
						</span>
					)}
					{fixedCount > 0 && (
						<span className={`inline-flex items-center rounded border px-2 py-0.5 text-xs ${SEVERITY_COLORS.low}`}>
							{fixedCount} Fixed
						</span>
					)}
				</div>
			</div>

			{/* Filters */}
			<div className="flex flex-wrap items-center gap-2">
				<input
					type="text"
					value={search}
					onChange={e => setSearch(e.target.value)}
					placeholder="Search package or CVE..."
					className="w-64 rounded border border-hairline bg-canvas px-3 py-1.5 text-sm text-text placeholder-text-dim focus:border-accent focus:outline-none"
				/>
				<div className="flex flex-wrap gap-1">
					{ALL_SEVERITIES.map(sev => {
						const active = sevFilter.has(sev);
						const count = sevCounts[sev] ?? 0;
						if (count === 0) return null;
						return (
							<button
								key={sev}
								onClick={() => toggleSevFilter(sev)}
								className={`rounded border px-2 py-0.5 text-xs font-semibold transition ${
									active
										? SEVERITY_COLORS[sev]
										: 'border-hairline bg-surface text-text-dim hover:bg-surface-hover'
								}`}
							>
								{sev} ({count})
							</button>
						);
					})}
					{sevFilter.size > 0 && (
						<button
							onClick={() => setSevFilter(new Set())}
							className="rounded border border-hairline px-2 py-0.5 text-xs text-text-dim hover:bg-surface-hover"
						>
							Clear
						</button>
					)}
				</div>
			</div>

			{/* Aggregated table with row expansion */}
			<div className="overflow-x-auto rounded border border-hairline">
				<table className="w-full text-sm">
					<thead className="border-b border-hairline bg-surface-hover">
						<tr>
							<th className="w-8 px-2 py-2"></th>
							<th
								className="cursor-pointer px-4 py-2 text-left font-semibold text-text-dim hover:text-text"
								onClick={() => cycleSort('package')}
							>
								Package{sortIndicator('package')}
							</th>
							<th
								className="px-4 py-2 text-left font-semibold text-text-dim"
								title="Installed package version on this host → upstream version that fixes the advisory. 'No fix' means upstream has not published a fixed release yet."
							>
								Current → Fixed
							</th>
							<th
								className="cursor-pointer px-4 py-2 text-left font-semibold text-text-dim hover:text-text"
								onClick={() => cycleSort('severity')}
								title="Severity classification from the advisory feed (critical/high/medium/low). Distro feeds publish their own severity; OSV records derive from CVSS when no distro rating is available."
							>
								Severity{sortIndicator('severity')}
							</th>
							<th
								className="cursor-pointer px-4 py-2 text-left font-semibold text-text-dim hover:text-text"
								onClick={() => cycleSort('count')}
								title="Number of distinct CVEs in this package + severity group. Click a row to expand the list."
							>
								CVEs{sortIndicator('count')}
							</th>
							<th
								className="px-4 py-2 text-left font-semibold text-text-dim"
								title="EPSS = Exploit Prediction Scoring System. 0.0–1.0 estimate of the probability that a CVE will be exploited in the wild within 30 days. Empty means EPSS feed has not yet scored this advisory id (only CVE-* ids and their aliases are scored)."
							>
								Max EPSS
							</th>
							<th
								className="px-4 py-2 text-left font-semibold text-text-dim"
								title="KEV = CISA Known Exploited Vulnerabilities catalog. Marked when CISA has confirmed exploitation in the wild. Most advisories are not on the KEV list."
							>
								KEV
							</th>
						</tr>
					</thead>
					<tbody className="divide-y divide-hairline">
						{aggregated.map(row => {
							const isOpen = expanded.has(row.key);
							return (
								<Fragment key={row.key}>
									<tr
										onClick={() => toggleExpanded(row.key)}
										className="cursor-pointer hover:bg-surface-hover/50"
									>
										<td className="px-2 py-2 text-text-dim">
											{isOpen ? (
												<ChevronDown className="h-4 w-4" />
											) : (
												<ChevronRight className="h-4 w-4" />
											)}
										</td>
										<td className="px-4 py-2 font-mono text-text">{row.package}</td>
										<td className="px-4 py-2 text-text-dim">
											<span className="font-mono">{row.currentVersion}</span>{' '}
											<span className="text-text-dim/60">→</span>{' '}
											{row.fixedVersion ? (
												<span className="font-mono text-ok">{row.fixedVersion}</span>
											) : (
												<span
													className="inline-flex items-center rounded border border-text-dim/40 bg-text-dim/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-text-dim"
													title="No upstream fix is published yet for this advisory."
												>
													No fix
												</span>
											)}
										</td>
										<td className="px-4 py-2">
											<span
												className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-semibold ${
													SEVERITY_COLORS[row.severity] ?? SEVERITY_COLORS.unknown
												}`}
											>
												{row.severity}
											</span>
										</td>
										<td className="px-4 py-2 font-mono text-text">{row.count}</td>
										<td className="px-4 py-2 font-mono text-text">
											{row.maxEpss != null ? row.maxEpss.toFixed(3) : '—'}
										</td>
										<td className="px-4 py-2">
											{row.kev && (
												<span className="inline-flex items-center rounded bg-danger/20 px-2 py-0.5 text-xs font-semibold text-danger">
													KEV
												</span>
											)}
										</td>
									</tr>
									{isOpen && (
										<tr className="bg-canvas/40">
											<td></td>
											<td colSpan={6} className="px-4 py-3">
												<table className="w-full text-xs">
													<thead className="text-text-dim">
														<tr>
															<th className="px-2 py-1 text-left font-semibold">Advisory</th>
															<th className="px-2 py-1 text-left font-semibold">Fix</th>
															<th className="px-2 py-1 text-left font-semibold">EPSS</th>
															<th className="px-2 py-1 text-left font-semibold">KEV</th>
															<th className="px-2 py-1 text-left font-semibold">Status</th>
															<th className="px-2 py-1 text-right font-semibold">Action</th>
														</tr>
													</thead>
													<tbody className="divide-y divide-hairline/40">
														{row.advisories.map(a => (
															<tr key={a.id}>
																<td className="px-2 py-1 font-mono text-accent">
																	<Link
																		href={`/advisories/${encodeURIComponent(a.advisory_id)}`}
																		className="hover:text-accent-dim"
																	>
																		{a.advisory_id}
																	</Link>
																</td>
																<td className="px-2 py-1">
																	{a.fixed_version ? (
																		<span className="font-mono text-ok">{a.fixed_version}</span>
																	) : (
																		<span
																			className="inline-flex items-center rounded border border-text-dim/40 bg-text-dim/10 px-1 py-0.5 text-[10px] font-semibold uppercase text-text-dim"
																			title="No upstream fix is published yet for this advisory."
																		>
																			No fix
																		</span>
																	)}
																</td>
																<td className="px-2 py-1 font-mono text-text-dim">
																	{a.epss != null ? a.epss.toFixed(3) : '—'}
																</td>
																<td className="px-2 py-1 text-text-dim">
																	{a.kev ? 'yes' : '—'}
																</td>
																<td className="px-2 py-1 text-text-dim">{a.status}</td>
																<td className="px-2 py-1 text-right">
																	{a.status === 'open' ? (
																		<button
																			onClick={(e) => {
																				e.stopPropagation();
																				handleSuppressClick(a);
																			}}
																			disabled={suppressMutation.isPending}
																			className="rounded bg-warn/20 px-2 py-0.5 text-xs font-semibold text-warn hover:bg-warn/30 disabled:opacity-50"
																		>
																			Suppress
																		</button>
																	) : a.status === 'suppressed' ? (
																		<button
																			onClick={(e) => {
																				e.stopPropagation();
																				handleUnsuppressClick(a);
																			}}
																			disabled={unsuppressMutation.isPending}
																			className="rounded bg-blue-500/20 px-2 py-0.5 text-xs font-semibold text-blue-400 hover:bg-blue-500/30 disabled:opacity-50"
																		>
																			Unsuppress
																		</button>
																	) : (
																		<span className="text-text-dim">Fixed</span>
																	)}
																</td>
															</tr>
														))}
													</tbody>
												</table>
											</td>
										</tr>
									)}
								</Fragment>
							);
						})}
					</tbody>
				</table>
			</div>

			{/* Suppress dialog */}
			{dialogState.open && (
				<div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
					<div className="w-full max-w-md rounded-lg border border-hairline bg-surface p-6 shadow-xl">
						<div className="mb-4 flex items-center gap-3">
							<AlertCircle className="h-5 w-5 text-warn" />
							<h2 className="text-h3 font-semibold text-text">Suppress Advisory</h2>
						</div>

						<p className="mb-4 text-text-dim">
							Suppressing this advisory will hide it from reports for the specified duration.
						</p>

						<div className="space-y-4">
							<div>
								<label className="block text-sm font-semibold text-text-dim">Reason (optional)</label>
								<textarea
									value={dialogState.reason}
									onChange={e =>
										setDialogState(prev => ({ ...prev, reason: e.target.value }))
									}
									placeholder="e.g., Patch scheduled for next maintenance window"
									className="mt-1 w-full rounded border border-hairline bg-canvas px-3 py-2 text-sm text-text placeholder-text-dim focus:border-accent focus:outline-none"
									rows={3}
								/>
							</div>

							<div>
								<label className="block text-sm font-semibold text-text-dim">
									Suppress for (days)
								</label>
								<input
									type="number"
									min="1"
									max="365"
									value={dialogState.expiresInDays}
									onChange={e =>
										setDialogState(prev => ({
											...prev,
											expiresInDays: parseInt(e.target.value) || 30,
										}))
									}
									className="mt-1 w-full rounded border border-hairline bg-canvas px-3 py-2 text-sm text-text focus:border-accent focus:outline-none"
								/>
							</div>
						</div>

						<div className="mt-6 flex gap-3">
							<button
								onClick={() => setDialogState(prev => ({ ...prev, open: false }))}
								className="flex-1 rounded border border-hairline bg-surface px-4 py-2 font-semibold text-text hover:bg-surface-hover"
							>
								Cancel
							</button>
							<button
								onClick={handleSuppressConfirm}
								disabled={suppressMutation.isPending}
								className="flex-1 rounded bg-warn px-4 py-2 font-semibold text-canvas hover:bg-warn/80 disabled:opacity-50"
							>
								{suppressMutation.isPending ? 'Suppressing...' : 'Suppress'}
							</button>
						</div>
					</div>
				</div>
			)}
		</div>
	);
}
