'use client';

import { EmptyState } from '@/components/empty-states/empty-state';
import { BlueprintSkeleton } from '@/components/skeletons/blueprint-skeleton';
import { apiFetch } from '@/lib/api-client';
import { type Host, getHost } from '@/lib/api/hosts';
import {
	type AuditUserLookup,
	auditActionHref,
	auditActorLabel,
	extractActorUserId,
	humanizeAuditAction,
	shortAuditId,
} from '@/lib/audit-format';
import { relTime } from '@/lib/time';
import { useQueries, useQuery } from '@tanstack/react-query';
import {
	ArrowDown,
	ArrowUp,
	ArrowUpDown,
	ChevronLeft,
	ChevronRight,
	ChevronsLeft,
	ChevronsRight,
	ExternalLink,
	Search,
} from 'lucide-react';
import Link from 'next/link';
import { useMemo, useState } from 'react';

interface AuditEntryOut {
	sequence: number;
	timestamp: string;
	actor: string;
	action: string;
	subject: string | null;
	payload: Record<string, unknown>;
	prev_hash: string;
	entry_hash: string;
}

interface AuditPageResponse {
	items: AuditEntryOut[];
	next_cursor: string | null;
}

type SortKey = 'timestamp' | 'actor' | 'action' | 'subject';
type SortDir = 'asc' | 'desc';

const PAGE_SIZES = [10, 25, 50] as const;

interface EnrichedEntry {
	raw: AuditEntryOut;
	actorDisplay: string;
	actionDisplay: string;
	targetDisplay: string;
}

export function HostAuditPanel({ hostId }: { hostId: string }) {
	const [search, setSearch] = useState('');
	const [actionFilter, setActionFilter] = useState<string>('all');
	const [actorFilter, setActorFilter] = useState<string>('all');
	const [sortKey, setSortKey] = useState<SortKey>('timestamp');
	const [sortDir, setSortDir] = useState<SortDir>('desc');
	const [page, setPage] = useState(0);
	const [pageSize, setPageSize] = useState<(typeof PAGE_SIZES)[number]>(25);

	const q = useQuery<AuditPageResponse>({
		queryKey: ['hosts', hostId, 'audit'],
		queryFn: () =>
			apiFetch<AuditPageResponse>(`/v1/audit?subject=${encodeURIComponent(hostId)}&limit=200`),
		refetchInterval: 5_000,
	});

	const hostQ = useQuery<Host>({
		queryKey: ['hosts', hostId],
		queryFn: () => getHost(hostId),
	});

	const userIds = useMemo(
		() =>
			Array.from(
				new Set(
					(q.data?.items ?? [])
						.map(e => extractActorUserId(e.actor))
						.filter((x): x is string => !!x),
				),
			),
		[q.data?.items],
	);

	const userQs = useQueries({
		queries: userIds.map(id => ({
			queryKey: ['users', id],
			queryFn: () =>
				apiFetch<AuditUserLookup>(`/v1/users/${id}`).catch(() => ({ id }) as AuditUserLookup),
			staleTime: 5 * 60_000,
		})),
	});

	const userMap = useMemo(() => {
		const map: Record<string, AuditUserLookup | undefined> = {};
		userIds.forEach((id, i) => {
			map[id] = userQs[i]?.data;
		});
		return map;
	}, [userIds, userQs]);

	const enriched: EnrichedEntry[] = useMemo(() => {
		const hostName =
			hostQ.data?.hostname || hostQ.data?.display_name || shortAuditId(hostId) || hostId;
		return (q.data?.items ?? []).map(raw => ({
			raw,
			actorDisplay: auditActorLabel(raw.actor, userMap),
			actionDisplay: humanizeAuditAction(raw.action),
			targetDisplay: raw.subject === hostId ? hostName : shortAuditId(raw.subject),
		}));
	}, [q.data?.items, userMap, hostQ.data, hostId]);

	const actionOptions = useMemo(() => {
		const set = new Set<string>();
		for (const e of enriched) set.add(e.raw.action);
		return Array.from(set).sort();
	}, [enriched]);

	const actorOptions = useMemo(() => {
		const map = new Map<string, string>();
		for (const e of enriched) map.set(e.raw.actor, e.actorDisplay);
		return Array.from(map.entries()).sort((a, b) => a[1].localeCompare(b[1]));
	}, [enriched]);

	const filtered = useMemo(() => {
		const needle = search.trim().toLowerCase();
		return enriched.filter(e => {
			if (actionFilter !== 'all' && e.raw.action !== actionFilter) return false;
			if (actorFilter !== 'all' && e.raw.actor !== actorFilter) return false;
			if (!needle) return true;
			return (
				e.actorDisplay.toLowerCase().includes(needle) ||
				e.actionDisplay.toLowerCase().includes(needle) ||
				e.targetDisplay.toLowerCase().includes(needle) ||
				e.raw.action.toLowerCase().includes(needle)
			);
		});
	}, [enriched, search, actionFilter, actorFilter]);

	const sorted = useMemo(() => {
		const arr = [...filtered];
		const dir = sortDir === 'asc' ? 1 : -1;
		arr.sort((a, b) => {
			let av: string | number = '';
			let bv: string | number = '';
			switch (sortKey) {
				case 'timestamp':
					av = Date.parse(a.raw.timestamp) || 0;
					bv = Date.parse(b.raw.timestamp) || 0;
					break;
				case 'actor':
					av = a.actorDisplay.toLowerCase();
					bv = b.actorDisplay.toLowerCase();
					break;
				case 'action':
					av = a.actionDisplay.toLowerCase();
					bv = b.actionDisplay.toLowerCase();
					break;
				case 'subject':
					av = a.targetDisplay.toLowerCase();
					bv = b.targetDisplay.toLowerCase();
					break;
			}
			if (av < bv) return -1 * dir;
			if (av > bv) return 1 * dir;
			return 0;
		});
		return arr;
	}, [filtered, sortKey, sortDir]);

	const total = sorted.length;
	const totalPages = Math.max(1, Math.ceil(total / pageSize));
	const safePage = Math.min(page, totalPages - 1);
	const startIdx = safePage * pageSize;
	const pageItems = sorted.slice(startIdx, startIdx + pageSize);

	function toggleSort(key: SortKey) {
		if (sortKey === key) {
			setSortDir(d => (d === 'asc' ? 'desc' : 'asc'));
		} else {
			setSortKey(key);
			setSortDir(key === 'timestamp' ? 'desc' : 'asc');
		}
		setPage(0);
	}

	function SortIcon({ k }: { k: SortKey }) {
		if (sortKey !== k) return <ArrowUpDown size={10} className="opacity-40" />;
		return sortDir === 'asc' ? <ArrowUp size={10} /> : <ArrowDown size={10} />;
	}

	const headerBar = (
		<div className="mb-3 flex items-center justify-between gap-2">
			<div className="flex items-center gap-2">
				<span className="mc-heading">Audit</span>
				<span className="font-mono text-[10px] uppercase tracking-wider text-text-dim">
					[{total} of {enriched.length}]
				</span>
			</div>
			<div className="flex items-center gap-1.5">
				<div className="relative">
					<Search
						size={11}
						className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-text-dim"
					/>
					<input
						type="text"
						value={search}
						onChange={e => {
							setSearch(e.target.value);
							setPage(0);
						}}
						placeholder="Search…"
						className="w-44 rounded-sm border border-hairline bg-surface-2 py-1 pl-7 pr-2 font-mono text-[11px] text-text outline-none focus:border-accent"
					/>
				</div>
				<select
					value={actionFilter}
					onChange={e => {
						setActionFilter(e.target.value);
						setPage(0);
					}}
					className="rounded-sm border border-hairline bg-surface-2 px-1.5 py-1 font-mono text-[11px] text-text outline-none focus:border-accent"
					aria-label="Filter by action"
				>
					<option value="all">All actions</option>
					{actionOptions.map(a => (
						<option key={a} value={a}>
							{humanizeAuditAction(a)}
						</option>
					))}
				</select>
				<select
					value={actorFilter}
					onChange={e => {
						setActorFilter(e.target.value);
						setPage(0);
					}}
					className="rounded-sm border border-hairline bg-surface-2 px-1.5 py-1 font-mono text-[11px] text-text outline-none focus:border-accent"
					aria-label="Filter by actor"
				>
					<option value="all">All actors</option>
					{actorOptions.map(([key, label]) => (
						<option key={key} value={key}>
							{label}
						</option>
					))}
				</select>
			</div>
		</div>
	);

	if (q.isLoading)
		return (
			<div>
				{headerBar}
				<BlueprintSkeleton rows={6} />
			</div>
		);
	if (q.isError)
		return (
			<div>
				{headerBar}
				<EmptyState title="Failed to load audit" description="Try again." />
			</div>
		);
	if (enriched.length === 0)
		return (
			<div>
				{headerBar}
				<EmptyState title="No audit entries" description="Actions on this host will appear here." />
			</div>
		);

	const headerCell = (key: SortKey, label: string) => (
		<th className="px-3 py-2 text-left font-semibold">
			<button
				type="button"
				onClick={() => toggleSort(key)}
				className={`inline-flex items-center gap-1 hover:text-text ${
					sortKey === key ? 'text-text' : ''
				}`}
			>
				{label}
				<SortIcon k={key} />
			</button>
		</th>
	);

	return (
		<div>
			{headerBar}
			<div className="mc-bezel overflow-hidden">
				<table className="w-full">
					<thead>
						<tr className="border-b border-hairline bg-bezel/40 font-mono text-[10px] uppercase tracking-[0.14em] text-text-dim">
							{headerCell('timestamp', 'When')}
							{headerCell('actor', 'Who')}
							{headerCell('action', 'Action')}
							{headerCell('subject', 'Target')}
						</tr>
					</thead>
					<tbody className="font-mono text-[12px]">
						{pageItems.length === 0 ? (
							<tr>
								<td
									colSpan={4}
									className="px-3 py-6 text-center font-mono text-[11px] uppercase tracking-wider text-text-dim"
								>
									No entries match filters
								</td>
							</tr>
						) : (
							pageItems.map((e, i) => {
								const href = auditActionHref(e.raw.action, e.raw.payload);
								return (
									<tr
										key={e.raw.sequence}
										className={`border-b border-hairline transition-colors ${
											i % 2 === 0 ? 'hover:bg-surface-2' : 'bg-bezel/20 hover:bg-surface-2'
										} ${href ? 'cursor-pointer' : ''}`}
									>
										<td
											className="px-3 py-2 text-text-dim text-[11px] whitespace-nowrap"
											title={new Date(e.raw.timestamp).toLocaleString()}
										>
											{relTime(e.raw.timestamp)}
										</td>
										<td className="px-3 py-2 text-text">{e.actorDisplay}</td>
										<td className="px-3 py-2 text-text">
											{href ? (
												<Link
													href={href}
													className="inline-flex items-center gap-1 text-accent hover:underline"
													title="Open associated action"
												>
													{e.actionDisplay}
													<ExternalLink size={10} className="opacity-60" />
												</Link>
											) : (
												e.actionDisplay
											)}
										</td>
										<td className="px-3 py-2 text-text-dim text-[11px]" title={e.raw.subject ?? ''}>
											{e.targetDisplay}
										</td>
									</tr>
								);
							})
						)}
					</tbody>
				</table>
			</div>

			<div className="mt-2 flex items-center justify-between rounded-sm border border-hairline bg-bezel/40 px-3 py-1.5 font-mono text-[10px] uppercase tracking-wider text-text-dim">
				<div className="flex items-center gap-2">
					<span>
						Showing <span className="text-text">{total === 0 ? 0 : startIdx + 1}</span>–
						<span className="text-text">{Math.min(startIdx + pageSize, total)}</span> of{' '}
						<span className="text-text">{total}</span>
					</span>
					<span className="mx-1 text-hairline">·</span>
					<label className="flex items-center gap-1">
						<span>Per page</span>
						<select
							value={pageSize}
							onChange={ev => {
								setPageSize(Number(ev.target.value) as (typeof PAGE_SIZES)[number]);
								setPage(0);
							}}
							className="rounded-sm border border-hairline bg-surface-2 px-1 py-0.5 font-mono text-[11px] text-text outline-none focus:border-accent"
						>
							{PAGE_SIZES.map(s => (
								<option key={s} value={s}>
									{s}
								</option>
							))}
						</select>
					</label>
				</div>
				<div className="flex items-center gap-1">
					<button
						type="button"
						onClick={() => setPage(0)}
						disabled={safePage === 0}
						aria-label="First page"
						className="rounded-sm p-1 text-text-dim hover:bg-surface-2 hover:text-text disabled:cursor-not-allowed disabled:opacity-30"
					>
						<ChevronsLeft size={12} />
					</button>
					<button
						type="button"
						onClick={() => setPage(p => Math.max(0, p - 1))}
						disabled={safePage === 0}
						aria-label="Previous page"
						className="rounded-sm p-1 text-text-dim hover:bg-surface-2 hover:text-text disabled:cursor-not-allowed disabled:opacity-30"
					>
						<ChevronLeft size={12} />
					</button>
					<span className="px-2 text-text">
						{safePage + 1} / {totalPages}
					</span>
					<button
						type="button"
						onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
						disabled={safePage >= totalPages - 1}
						aria-label="Next page"
						className="rounded-sm p-1 text-text-dim hover:bg-surface-2 hover:text-text disabled:cursor-not-allowed disabled:opacity-30"
					>
						<ChevronRight size={12} />
					</button>
					<button
						type="button"
						onClick={() => setPage(totalPages - 1)}
						disabled={safePage >= totalPages - 1}
						aria-label="Last page"
						className="rounded-sm p-1 text-text-dim hover:bg-surface-2 hover:text-text disabled:cursor-not-allowed disabled:opacity-30"
					>
						<ChevronsRight size={12} />
					</button>
				</div>
			</div>
		</div>
	);
}
