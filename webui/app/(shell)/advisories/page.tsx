'use client';

export const dynamic = 'force-dynamic';

import { EmptyState } from '@/components/empty-states/empty-state';
import { Select } from '@/components/primitives/select';
import { apiFetch } from '@/lib/api-client';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, ChevronDown, ChevronRight } from 'lucide-react';
import Link from 'next/link';
import { Fragment, useMemo, useState } from 'react';

interface FleetRow {
	id: string;
	severity: string;
	summary: string;
	kev: boolean;
	epss: number | null;
	affected_hosts: number;
	open_count: number;
	suppressed_count: number;
	fixed_count: number;
}

interface RollupResponse {
	items: FleetRow[];
	total: number;
	severity_counts?: Record<string, number>;
	kev_count?: number;
}

interface AdvisoryHostRow {
	host_id: string;
	hostname: string;
	status: string;
	package: string | null;
	installed_version: string | null;
}

interface AdvisoryHostsResponse {
	items: AdvisoryHostRow[];
}

interface AdvisoryDetail {
	id: string;
	severity: string;
	summary: string;
	description_md: string | null;
	kev: boolean;
	epss: number | null;
}

interface HostMin {
	id: string;
	hostname: string;
}

const SEVERITY_BADGE: Record<string, string> = {
	critical: 'bg-red-500/15 text-red-400 border-red-500/40',
	high: 'bg-orange-500/15 text-orange-400 border-orange-500/40',
	medium: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/40',
	low: 'bg-blue-500/15 text-blue-400 border-blue-500/40',
	unknown: 'bg-text-dim/10 text-text-dim border-text-dim/30',
};

type SortKey = 'affected' | 'severity' | 'epss' | 'id';

const PAGE_SIZE = 100;

export default function AdvisoriesPage() {
	const [severity, setSeverity] = useState('all');
	const [kevOnly, setKevOnly] = useState(false);
	const [hostId, setHostId] = useState('');
	const [packageQ, setPackageQ] = useState('');
	const [search, setSearch] = useState('');
	const [statusFilter, setStatusFilter] = useState('open');
	const [sort, setSort] = useState<SortKey>('affected');
	const [offset, setOffset] = useState(0);
	const [expanded, setExpanded] = useState<Set<string>>(new Set());

	const hostsQ = useQuery<HostMin[]>({
		queryKey: ['hosts', 'min'],
		queryFn: async () => apiFetch<HostMin[]>('/v1/hosts'),
		staleTime: 60_000,
	});

	const rollupQ = useQuery<RollupResponse>({
		queryKey: [
			'advisories-rollup',
			{ severity, kevOnly, hostId, packageQ, search, statusFilter, sort, offset },
		],
		queryFn: async () => {
			const p = new URLSearchParams();
			if (severity !== 'all') p.set('severity', severity);
			if (kevOnly) p.set('kev', 'true');
			if (hostId) p.set('host_id', hostId);
			if (packageQ) p.set('package', packageQ);
			if (search) p.set('q', search);
			if (statusFilter) p.set('status', statusFilter);
			p.set('sort', sort);
			p.set('limit', String(PAGE_SIZE));
			p.set('offset', String(offset));
			return apiFetch<RollupResponse>(`/v1/advisories/fleet/rollup?${p.toString()}`);
		},
	});

	const items = rollupQ.data?.items ?? [];
	const total = rollupQ.data?.total ?? 0;

	// Prefer server-provided severity_counts (full filtered set, deduped per
	// CVE). Falls back to per-page tally for older servers.
	const totals = useMemo(() => {
		const sc = rollupQ.data?.severity_counts;
		if (sc) {
			return {
				critical: sc.critical ?? 0,
				high: sc.high ?? 0,
				medium: sc.medium ?? 0,
				low: sc.low ?? 0,
				unknown: sc.unknown ?? 0,
				kev: rollupQ.data?.kev_count ?? 0,
			};
		}
		const t = { critical: 0, high: 0, medium: 0, low: 0, unknown: 0, kev: 0 };
		for (const r of items) {
			t[(r.severity as keyof typeof t) ?? 'unknown'] =
				(t[(r.severity as keyof typeof t) ?? 'unknown'] ?? 0) + 1;
			if (r.kev) t.kev += 1;
		}
		return t;
	}, [items, rollupQ.data?.severity_counts, rollupQ.data?.kev_count]);

	const toggleExpanded = (id: string) =>
		setExpanded(prev => {
			const next = new Set(prev);
			if (next.has(id)) next.delete(id);
			else next.add(id);
			return next;
		});

	const clearFilters = () => {
		setSeverity('all');
		setKevOnly(false);
		setHostId('');
		setPackageQ('');
		setSearch('');
		setStatusFilter('open');
		setSort('affected');
		setOffset(0);
	};

	return (
		<div className="flex flex-col gap-6 p-6">
			<div className="flex items-end justify-between gap-3">
				<div>
					<h1 className="text-h1 text-text">Advisories</h1>
					<p className="mt-2 text-text-dim">
						Fleet-wide rollup of host advisories. One row per CVE; counts reflect hosts matching the
						current filters.
					</p>
				</div>
				<Link
					href="/security"
					className="rounded border border-hairline px-3 py-1.5 text-sm text-text-dim hover:bg-surface-hover"
				>
					Posture overview →
				</Link>
			</div>

			{/* Stat strip */}
			<div className="grid grid-cols-2 gap-3 sm:grid-cols-6">
				<StatPill label="CVEs" value={total} tone="neutral" />
				<StatPill label="Critical" value={totals.critical} tone="critical" />
				<StatPill label="High" value={totals.high} tone="high" />
				<StatPill label="Medium" value={totals.medium} tone="medium" />
				<StatPill label="Low" value={totals.low} tone="low" />
				<StatPill label="KEV" value={totals.kev} tone="critical" />
			</div>

			{/* Controls */}
			<div className="flex flex-wrap items-center gap-3 rounded border border-hairline bg-surface p-3">
				<input
					type="text"
					value={search}
					onChange={e => {
						setSearch(e.target.value);
						setOffset(0);
					}}
					placeholder="Search CVE / summary..."
					className="w-56 rounded border border-hairline bg-canvas px-3 py-1.5 text-sm text-text placeholder-text-dim focus:border-accent focus:outline-none"
				/>
				<input
					type="text"
					value={packageQ}
					onChange={e => {
						setPackageQ(e.target.value);
						setOffset(0);
					}}
					placeholder="Package name..."
					className="w-44 rounded border border-hairline bg-canvas px-3 py-1.5 text-sm text-text placeholder-text-dim focus:border-accent focus:outline-none"
				/>
				<Select
					value={hostId || 'all'}
					onValueChange={v => {
						setHostId(v === 'all' ? '' : v);
						setOffset(0);
					}}
					options={[
						{ value: 'all', label: 'All hosts' },
						...(hostsQ.data ?? []).map(h => ({
							value: h.id,
							label: h.hostname || h.id,
						})),
					]}
				/>
				<Select
					value={severity}
					onValueChange={v => {
						setSeverity(v);
						setOffset(0);
					}}
					options={[
						{ value: 'all', label: 'All severities' },
						{ value: 'critical', label: 'Critical' },
						{ value: 'high', label: 'High' },
						{ value: 'medium', label: 'Medium' },
						{ value: 'low', label: 'Low' },
						{ value: 'unknown', label: 'Unknown' },
					]}
				/>
				<Select
					value={statusFilter}
					onValueChange={v => {
						setStatusFilter(v);
						setOffset(0);
					}}
					options={[
						{ value: 'open', label: 'Open' },
						{ value: 'suppressed', label: 'Suppressed' },
						{ value: 'fixed', label: 'Fixed' },
						{ value: 'all', label: 'All statuses' },
					]}
				/>
				<Select
					value={sort}
					onValueChange={v => setSort(v as SortKey)}
					options={[
						{ value: 'affected', label: 'Sort: affected hosts' },
						{ value: 'severity', label: 'Sort: severity' },
						{ value: 'epss', label: 'Sort: EPSS' },
						{ value: 'id', label: 'Sort: CVE id' },
					]}
				/>
				<label className="flex items-center gap-2 text-sm text-text-dim">
					<input
						type="checkbox"
						checked={kevOnly}
						onChange={e => {
							setKevOnly(e.target.checked);
							setOffset(0);
						}}
					/>
					KEV only
				</label>
				<button
					type="button"
					onClick={clearFilters}
					className="rounded border border-hairline px-3 py-1.5 text-xs text-text-dim hover:bg-surface-hover"
				>
					Reset
				</button>
			</div>

			{/* Table */}
			{rollupQ.isLoading ? (
				<div className="text-center text-text-dim">Loading...</div>
			) : rollupQ.isError ? (
				<EmptyState title="Failed to load advisories" description="Try again." />
			) : items.length === 0 ? (
				<EmptyState
					title="No advisories"
					description="No advisories match these filters."
					icon={<AlertTriangle className="h-8 w-8 text-text-dim" />}
				/>
			) : (
				<div className="overflow-x-auto rounded border border-hairline">
					<table className="w-full text-sm">
						<thead className="border-b border-hairline bg-surface-hover">
							<tr>
								<th className="w-8 px-2 py-2" />
								<th
									className="px-4 py-2 text-left font-semibold text-text-dim"
									title="Severity classification from the advisory feed. Distro feeds publish their own; OSV derives from CVSS when no distro rating is available."
								>
									Severity
								</th>
								<th className="px-4 py-2 text-left font-semibold text-text-dim">CVE</th>
								<th
									className="px-4 py-2 text-left font-semibold text-text-dim"
									title="Distinct hosts in the fleet with this CVE matched against an installed package."
								>
									Hosts
								</th>
								<th
									className="px-4 py-2 text-left font-semibold text-text-dim"
									title="Host advisories in 'open' state — not yet suppressed or marked fixed."
								>
									Open
								</th>
								<th
									className="px-4 py-2 text-left font-semibold text-text-dim"
									title="Host advisories suppressed by an admin (with reason + expiry)."
								>
									Suppr.
								</th>
								<th
									className="px-4 py-2 text-left font-semibold text-text-dim"
									title="Host advisories closed because the installed package version no longer matches the vulnerable range."
								>
									Fixed
								</th>
								<th
									className="px-4 py-2 text-left font-semibold text-text-dim"
									title="EPSS — Exploit Prediction Scoring System. 0.0–1.0 probability of in-the-wild exploitation within 30 days. Empty when the EPSS feed has no entry for this id or its aliases."
								>
									EPSS
								</th>
								<th
									className="px-4 py-2 text-left font-semibold text-text-dim"
									title="KEV — CISA Known Exploited Vulnerabilities catalog. Confirmed exploited in the wild."
								>
									KEV
								</th>
								<th className="px-4 py-2 text-left font-semibold text-text-dim">Summary</th>
							</tr>
						</thead>
						<tbody className="divide-y divide-hairline">
							{items.map(r => {
								const isOpen = expanded.has(r.id);
								return (
									<Fragment key={r.id}>
										<tr
											tabIndex={0}
											aria-expanded={isOpen}
											onClick={() => toggleExpanded(r.id)}
											onKeyDown={e => {
												if (e.key === 'Enter' || e.key === ' ') {
													e.preventDefault();
													toggleExpanded(r.id);
												}
											}}
											className="cursor-pointer hover:bg-surface-hover/50"
										>
											<td className="px-2 py-2 text-text-dim">
												{isOpen ? (
													<ChevronDown className="h-4 w-4" />
												) : (
													<ChevronRight className="h-4 w-4" />
												)}
											</td>
											<td className="px-4 py-2">
												<span
													className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-semibold ${
														SEVERITY_BADGE[r.severity] ?? SEVERITY_BADGE.unknown
													}`}
												>
													{r.severity}
												</span>
											</td>
											<td className="px-4 py-2 font-mono text-accent hover:text-accent-dim">
												<Link
													href={`/advisories/${encodeURIComponent(r.id)}`}
													onClick={e => e.stopPropagation()}
												>
													{r.id}
												</Link>
											</td>
											<td className="px-4 py-2 font-mono text-text">{r.affected_hosts}</td>
											<td className="px-4 py-2 font-mono text-text">{r.open_count}</td>
											<td className="px-4 py-2 font-mono text-text-dim">{r.suppressed_count}</td>
											<td className="px-4 py-2 font-mono text-text-dim">{r.fixed_count}</td>
											<td className="px-4 py-2 font-mono text-text">
												{r.epss != null ? r.epss.toFixed(3) : '—'}
											</td>
											<td className="px-4 py-2">
												{r.kev && (
													<span className="inline-flex items-center rounded bg-danger/20 px-2 py-0.5 text-xs font-semibold text-danger">
														KEV
													</span>
												)}
											</td>
											<td
												className="px-4 py-2 text-text-dim max-w-[420px] truncate"
												title={r.summary}
											>
												{r.summary || <span className="text-text-dim/60">—</span>}
											</td>
										</tr>
										{isOpen && (
											<tr className="bg-canvas/40">
												<td />
												<td colSpan={9} className="px-4 py-3">
													<AdvisoryExpandedRow
														id={r.id}
														summary={r.summary}
														onFilter={() => setSearch(r.id)}
													/>
												</td>
											</tr>
										)}
									</Fragment>
								);
							})}
						</tbody>
					</table>
				</div>
			)}

			{/* Pagination */}
			{total > PAGE_SIZE && (
				<div className="flex items-center justify-between text-sm text-text-dim">
					<span>
						Showing {offset + 1}–{Math.min(offset + items.length, total)} of {total}
					</span>
					<div className="flex gap-2">
						<button
							type="button"
							disabled={offset === 0}
							onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
							className="rounded border border-hairline px-3 py-1 disabled:opacity-40"
						>
							Prev
						</button>
						<button
							type="button"
							disabled={offset + items.length >= total}
							onClick={() => setOffset(offset + PAGE_SIZE)}
							className="rounded border border-hairline px-3 py-1 disabled:opacity-40"
						>
							Next
						</button>
					</div>
				</div>
			)}
		</div>
	);
}

function AdvisoryExpandedRow({
	id,
	summary,
	onFilter,
}: {
	id: string;
	summary: string;
	onFilter: () => void;
}) {
	const detailQ = useQuery<AdvisoryDetail>({
		queryKey: ['advisory', id],
		queryFn: () => apiFetch<AdvisoryDetail>(`/v1/advisories/${encodeURIComponent(id)}`),
		staleTime: 5 * 60_000,
	});
	const hostsQ = useQuery<AdvisoryHostsResponse>({
		queryKey: ['advisory-hosts', id, 'open'],
		queryFn: () =>
			apiFetch<AdvisoryHostsResponse>(`/v1/advisories/${encodeURIComponent(id)}/hosts?status=all`),
	});

	const description = detailQ.data?.description_md?.trim() || summary || '';
	const hosts = hostsQ.data?.items ?? [];
	const hostsByStatus = {
		open: hosts.filter(h => h.status === 'open'),
		suppressed: hosts.filter(h => h.status === 'suppressed'),
		fixed: hosts.filter(h => h.status === 'fixed'),
	};

	const statusTone: Record<string, string> = {
		open: 'border-orange-500/40 bg-orange-500/10 text-orange-400',
		suppressed: 'border-text-dim/30 bg-text-dim/10 text-text-dim',
		fixed: 'border-green-500/40 bg-green-500/10 text-green-400',
	};

	return (
		<div className="space-y-3 text-sm">
			<div className="flex flex-wrap items-center gap-3 text-xs text-text-dim">
				<Link
					href={`/advisories/${encodeURIComponent(id)}`}
					className="text-accent hover:text-accent-dim"
				>
					Open advisory detail →
				</Link>
				<button
					type="button"
					onClick={onFilter}
					className="rounded border border-hairline px-2 py-0.5 hover:bg-surface-hover"
				>
					Filter to this CVE
				</button>
			</div>

			<div>
				<div className="mb-1 text-xs font-semibold uppercase tracking-wider text-text-dim">
					Description
				</div>
				{detailQ.isLoading ? (
					<div className="text-xs text-text-dim">Loading…</div>
				) : description ? (
					<p className="whitespace-pre-wrap text-text-dim">{description}</p>
				) : (
					<p className="text-text-dim/60 italic">No description provided.</p>
				)}
			</div>

			<div>
				<div className="mb-1 text-xs font-semibold uppercase tracking-wider text-text-dim">
					Affected hosts ({hosts.length})
				</div>
				{hostsQ.isLoading ? (
					<div className="text-xs text-text-dim">Loading…</div>
				) : hosts.length === 0 ? (
					<div className="text-xs text-text-dim/60 italic">No hosts.</div>
				) : (
					<div className="space-y-1.5">
						{(['open', 'suppressed', 'fixed'] as const).map(s => {
							const list = hostsByStatus[s];
							if (list.length === 0) return null;
							return (
								<div key={s} className="flex flex-wrap items-center gap-1.5">
									<span className="text-[10px] uppercase tracking-wider text-text-dim/70 w-20 shrink-0">
										{s} ({list.length})
									</span>
									{list.map(h => (
										<Link
											key={h.host_id}
											href={`/hosts/${h.host_id}`}
											className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-mono ${statusTone[s]} hover:opacity-80`}
											title={
												h.installed_version
													? `${h.package ?? ''} @ ${h.installed_version}`
													: (h.package ?? '')
											}
										>
											{h.hostname}
										</Link>
									))}
								</div>
							);
						})}
					</div>
				)}
			</div>
		</div>
	);
}

function StatPill({
	label,
	value,
	tone,
}: {
	label: string;
	value: number;
	tone: 'neutral' | 'critical' | 'high' | 'medium' | 'low';
}) {
	const palette: Record<string, string> = {
		neutral: 'border-hairline bg-surface text-text',
		critical: 'border-red-500/40 bg-red-500/10 text-red-400',
		high: 'border-orange-500/40 bg-orange-500/10 text-orange-400',
		medium: 'border-yellow-500/40 bg-yellow-500/10 text-yellow-400',
		low: 'border-blue-500/40 bg-blue-500/10 text-blue-400',
	};
	return (
		<div className={`rounded border ${palette[tone]} p-3`}>
			<div className="text-xs uppercase opacity-80">{label}</div>
			<div className="mt-1 text-h3 font-semibold">{value}</div>
		</div>
	);
}
