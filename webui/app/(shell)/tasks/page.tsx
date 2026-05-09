'use client';

export const dynamic = 'force-dynamic';

import { EmptyState } from '@/components/empty-states/empty-state';
import { Badge } from '@/components/primitives/badge';
import { BlueprintSkeleton } from '@/components/skeletons/blueprint-skeleton';
import { TaskResultPreview } from '@/components/tasks/task-result-preview';
import { TasksNewTaskModal } from '@/components/tasks/tasks-new-task-modal';
import { apiFetch } from '@/lib/api-client';
import { type AuditUserLookup, auditActorLabel, extractActorUserId } from '@/lib/audit-format';
import { useCanPerform } from '@/lib/rbac';
import { relTime } from '@/lib/time';
import { useQueries, useQuery } from '@tanstack/react-query';
import {
	ArrowDown,
	ArrowUp,
	ArrowUpDown,
	CheckCircle2,
	ChevronLeft,
	ChevronRight,
	ChevronsLeft,
	ChevronsRight,
	CircleDashed,
	CircleDot,
	ExternalLink,
	Plus,
	Search,
	XCircle,
} from 'lucide-react';
import Link from 'next/link';
import { type ComponentType, Fragment, useCallback, useMemo, useState } from 'react';

interface TaskListItem {
	id: string;
	kind: string;
	kind_display?: string;
	status: string;
	created_at: string;
	risk: string;
	summary?: string;
	payload?: Record<string, unknown> | null;
	host_ids?: string[];
	created_by?: string | null;
}

interface TasksPageResponse {
	items: TaskListItem[];
	next_cursor: string | null;
}

interface HostMin {
	id: string;
	hostname: string;
}

const STATUS_META: Record<
	string,
	{ tone: string; icon: ComponentType<{ size?: number; className?: string }>; pulse?: boolean }
> = {
	completed: { tone: 'text-ok', icon: CheckCircle2 },
	succeeded: { tone: 'text-ok', icon: CheckCircle2 },
	running: { tone: 'text-accent', icon: CircleDot, pulse: true },
	pending: { tone: 'text-text-dim', icon: CircleDashed },
	failed: { tone: 'text-danger', icon: XCircle },
	partial: { tone: 'text-warn', icon: CircleDot },
	cancelled: { tone: 'text-warn', icon: XCircle },
	expired: { tone: 'text-text-dim', icon: XCircle },
	approved: { tone: 'text-accent', icon: CircleDashed },
};

const RISK_TONE: Record<string, string> = {
	low: 'text-text-dim border-hairline',
	medium: 'text-accent border-accent/40',
	high: 'text-warn border-warn/40',
	critical: 'text-danger border-danger/40',
	irreversible: 'text-danger border-danger/40',
};

const PAGE_SIZES = [10, 25, 50, 100] as const;

type SortKey = 'created_at' | 'kind' | 'status' | 'risk' | 'host' | 'creator';
type SortDir = 'asc' | 'desc';

function displayKind(t: TaskListItem): string {
	return t.kind_display?.trim() || t.kind;
}

function taskAction(t: TaskListItem): string | null {
	const p = t.payload;
	if (!p || typeof p !== 'object') return null;
	const a = (p as Record<string, unknown>).action;
	return typeof a === 'string' ? a : null;
}

function taskHostId(t: TaskListItem): string | null {
	if (t.host_ids && t.host_ids.length > 0) return t.host_ids[0];
	const p = t.payload;
	if (!p || typeof p !== 'object') return null;
	const h = (p as Record<string, unknown>).host_id;
	return typeof h === 'string' ? h : null;
}

export default function TasksPage() {
	const [showNew, setShowNew] = useState(false);
	const cap = useCanPerform('shell-exec');

	const [search, setSearch] = useState('');
	const [kindFilter, setKindFilter] = useState('all');
	const [statusFilter, setStatusFilter] = useState('all');
	const [riskFilter, setRiskFilter] = useState('all');
	const [hostFilter, setHostFilter] = useState('all');
	const [creatorFilter, setCreatorFilter] = useState('all');
	const [sortKey, setSortKey] = useState<SortKey>('created_at');
	const [sortDir, setSortDir] = useState<SortDir>('desc');
	const [page, setPage] = useState(0);
	const [pageSize, setPageSize] = useState<(typeof PAGE_SIZES)[number]>(25);
	const [expandedId, setExpandedId] = useState<string | null>(null);

	const { data, isLoading, isError } = useQuery<TasksPageResponse>({
		queryKey: ['tasks'],
		queryFn: () => apiFetch<TasksPageResponse>('/v1/tasks?limit=200'),
		refetchInterval: 3_000,
	});

	const tasks: TaskListItem[] = data?.items ?? [];

	const hostsQ = useQuery<HostMin[]>({
		queryKey: ['hosts', 'min'],
		queryFn: () => apiFetch<HostMin[]>('/v1/hosts'),
		staleTime: 60_000,
	});

	const hostNameMap = useMemo(() => {
		const m: Record<string, string> = {};
		for (const h of hostsQ.data ?? []) m[h.id] = h.hostname || h.id;
		return m;
	}, [hostsQ.data]);

	// Resolve user UUIDs from created_by ("user:<uuid>") to usernames
	const userIds = useMemo(
		() =>
			Array.from(
				new Set(
					tasks
						.map(t => (t.created_by ? extractActorUserId(t.created_by) : null))
						.filter((x): x is string => !!x),
				),
			),
		[tasks],
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

	const creatorLabel = useCallback(
		(t: TaskListItem): string => {
			if (!t.created_by) return 'system';
			return auditActorLabel(t.created_by, userMap);
		},
		[userMap],
	);

	const hostLabel = useCallback(
		(t: TaskListItem): string => {
			const ids = t.host_ids ?? [];
			if (ids.length === 0) return '—';
			if (ids.length === 1) return hostNameMap[ids[0]] || ids[0].slice(0, 8);
			return `${hostNameMap[ids[0]] || ids[0].slice(0, 8)} +${ids.length - 1}`;
		},
		[hostNameMap],
	);

	const kindOptions = useMemo(() => {
		const set = new Set<string>();
		for (const t of tasks) set.add(displayKind(t));
		return Array.from(set).sort();
	}, [tasks]);

	const statusOptions = useMemo(() => {
		const set = new Set<string>();
		for (const t of tasks) set.add(t.status);
		return Array.from(set).sort();
	}, [tasks]);

	const creatorOptions = useMemo(() => {
		const map = new Map<string, string>();
		for (const t of tasks) {
			const key = t.created_by ?? 'system';
			map.set(key, creatorLabel(t));
		}
		return Array.from(map.entries()).sort((a, b) => a[1].localeCompare(b[1]));
	}, [tasks, creatorLabel]);

	const filtered = useMemo(() => {
		const needle = search.trim().toLowerCase();
		return tasks.filter(t => {
			if (kindFilter !== 'all' && displayKind(t) !== kindFilter) return false;
			if (statusFilter !== 'all' && t.status !== statusFilter) return false;
			if (riskFilter !== 'all' && t.risk !== riskFilter) return false;
			if (hostFilter !== 'all' && !(t.host_ids ?? []).includes(hostFilter)) return false;
			if (creatorFilter !== 'all' && (t.created_by ?? 'system') !== creatorFilter) return false;
			if (!needle) return true;
			return (
				displayKind(t).toLowerCase().includes(needle) ||
				(t.summary ?? '').toLowerCase().includes(needle) ||
				t.id.toLowerCase().includes(needle) ||
				hostLabel(t).toLowerCase().includes(needle) ||
				creatorLabel(t).toLowerCase().includes(needle)
			);
		});
	}, [
		tasks,
		search,
		kindFilter,
		statusFilter,
		riskFilter,
		hostFilter,
		creatorFilter,
		hostLabel,
		creatorLabel,
	]);

	const sorted = useMemo(() => {
		const arr = [...filtered];
		const dir = sortDir === 'asc' ? 1 : -1;
		arr.sort((a, b) => {
			let av: string | number = '';
			let bv: string | number = '';
			switch (sortKey) {
				case 'created_at':
					av = Date.parse(a.created_at) || 0;
					bv = Date.parse(b.created_at) || 0;
					break;
				case 'kind':
					av = displayKind(a).toLowerCase();
					bv = displayKind(b).toLowerCase();
					break;
				case 'status':
					av = a.status;
					bv = b.status;
					break;
				case 'risk':
					av = a.risk;
					bv = b.risk;
					break;
				case 'host':
					av = hostLabel(a).toLowerCase();
					bv = hostLabel(b).toLowerCase();
					break;
				case 'creator':
					av = creatorLabel(a).toLowerCase();
					bv = creatorLabel(b).toLowerCase();
					break;
			}
			if (av < bv) return -1 * dir;
			if (av > bv) return 1 * dir;
			return 0;
		});
		return arr;
	}, [filtered, sortKey, sortDir, hostLabel, creatorLabel]);

	const total = sorted.length;
	const totalPages = Math.max(1, Math.ceil(total / pageSize));
	const safePage = Math.min(page, totalPages - 1);
	const startIdx = safePage * pageSize;
	const pageItems = sorted.slice(startIdx, startIdx + pageSize);

	const running = tasks.filter(t => t.status === 'running').length;

	function toggleSort(key: SortKey) {
		if (sortKey === key) {
			setSortDir(d => (d === 'asc' ? 'desc' : 'asc'));
		} else {
			setSortKey(key);
			setSortDir(key === 'created_at' ? 'desc' : 'asc');
		}
		setPage(0);
	}

	function SortIcon({ k }: { k: SortKey }) {
		if (sortKey !== k) return <ArrowUpDown size={10} className="opacity-40" />;
		return sortDir === 'asc' ? <ArrowUp size={10} /> : <ArrowDown size={10} />;
	}

	function toggle(id: string) {
		setExpandedId(prev => (prev === id ? null : id));
	}

	const headerBar = (
		<div className="mb-3 flex items-center justify-between gap-2">
			<div className="flex items-center gap-2">
				<span className="mc-heading">Tasks</span>
				{running > 0 ? (
					<span className="mc-pip text-accent border-accent/40">
						<span className="mc-led mc-led-pulse" />
						{running} RUNNING
					</span>
				) : null}
				<span className="font-mono text-[10px] uppercase tracking-wider text-text-dim">
					[{total} of {tasks.length}]
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
					value={kindFilter}
					onChange={e => {
						setKindFilter(e.target.value);
						setPage(0);
					}}
					className="rounded-sm border border-hairline bg-surface-2 px-1.5 py-1 font-mono text-[11px] text-text outline-none focus:border-accent"
					aria-label="Filter by kind"
				>
					<option value="all">All kinds</option>
					{kindOptions.map(k => (
						<option key={k} value={k}>
							{k}
						</option>
					))}
				</select>
				<select
					value={statusFilter}
					onChange={e => {
						setStatusFilter(e.target.value);
						setPage(0);
					}}
					className="rounded-sm border border-hairline bg-surface-2 px-1.5 py-1 font-mono text-[11px] text-text outline-none focus:border-accent"
					aria-label="Filter by status"
				>
					<option value="all">All statuses</option>
					{statusOptions.map(s => (
						<option key={s} value={s}>
							{s}
						</option>
					))}
				</select>
				<select
					value={riskFilter}
					onChange={e => {
						setRiskFilter(e.target.value);
						setPage(0);
					}}
					className="rounded-sm border border-hairline bg-surface-2 px-1.5 py-1 font-mono text-[11px] text-text outline-none focus:border-accent"
					aria-label="Filter by risk"
				>
					<option value="all">All risk</option>
					{Object.keys(RISK_TONE).map(r => (
						<option key={r} value={r}>
							{r}
						</option>
					))}
				</select>
				<select
					value={hostFilter}
					onChange={e => {
						setHostFilter(e.target.value);
						setPage(0);
					}}
					className="rounded-sm border border-hairline bg-surface-2 px-1.5 py-1 font-mono text-[11px] text-text outline-none focus:border-accent max-w-[150px]"
					aria-label="Filter by host"
				>
					<option value="all">All hosts</option>
					{(hostsQ.data ?? []).map(h => (
						<option key={h.id} value={h.id}>
							{h.hostname || h.id}
						</option>
					))}
				</select>
				<select
					value={creatorFilter}
					onChange={e => {
						setCreatorFilter(e.target.value);
						setPage(0);
					}}
					className="rounded-sm border border-hairline bg-surface-2 px-1.5 py-1 font-mono text-[11px] text-text outline-none focus:border-accent max-w-[150px]"
					aria-label="Filter by creator"
				>
					<option value="all">All users</option>
					{creatorOptions.map(([key, label]) => (
						<option key={key} value={key}>
							{label}
						</option>
					))}
				</select>
				<button
					type="button"
					disabled={!cap.allowed}
					title={cap.allowed ? '' : cap.reason}
					onClick={() => setShowNew(true)}
					className="flex items-center gap-1.5 rounded-sm border border-accent bg-accent/15 px-2.5 py-1 font-mono text-[11px] font-semibold uppercase tracking-wider text-accent hover:bg-accent/25 disabled:cursor-not-allowed disabled:opacity-40"
				>
					<Plus size={12} />
					New Task
				</button>
			</div>
		</div>
	);

	const modal = showNew ? <TasksNewTaskModal onClose={() => setShowNew(false)} /> : null;

	if (isLoading)
		return (
			<div className="p-4">
				{headerBar}
				<BlueprintSkeleton rows={8} />
				{modal}
			</div>
		);
	if (isError)
		return (
			<div className="p-4">
				{headerBar}
				<EmptyState title="Failed to load tasks" description="Please try again" />
				{modal}
			</div>
		);

	if (tasks.length === 0)
		return (
			<div className="p-4">
				{headerBar}
				<EmptyState title="No tasks yet" description="Click + New Task to dispatch one." />
				{modal}
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
		<div className="p-4">
			{headerBar}
			<div className="mc-bezel overflow-hidden">
				<table className="w-full">
					<thead>
						<tr className="border-b border-hairline bg-bezel/40 font-mono text-[10px] uppercase tracking-[0.14em] text-text-dim">
							<th className="px-3 py-2 text-left font-semibold w-8" aria-label="Expand" />
							{headerCell('status', 'Status')}
							{headerCell('kind', 'Kind')}
							{headerCell('host', 'Host')}
							{headerCell('creator', 'By')}
							<th className="px-3 py-2 text-left font-semibold">Detail</th>
							{headerCell('risk', 'Risk')}
							{headerCell('created_at', 'Created')}
							<th className="px-3 py-2 text-right font-semibold w-10" aria-label="Open" />
						</tr>
					</thead>
					<tbody className="font-mono text-[12px]">
						{pageItems.length === 0 ? (
							<tr>
								<td
									colSpan={9}
									className="px-3 py-6 text-center font-mono text-[11px] uppercase tracking-wider text-text-dim"
								>
									No tasks match filters
								</td>
							</tr>
						) : (
							pageItems.map((t, i) => {
								const expanded = expandedId === t.id;
								const meta = STATUS_META[t.status] ?? STATUS_META.pending;
								const StatusIcon = meta.icon;
								const riskTone = RISK_TONE[t.risk?.toLowerCase()] ?? RISK_TONE.low;
								const action = taskAction(t);
								const hostId = taskHostId(t);
								return (
									<Fragment key={t.id}>
										<tr
											tabIndex={0}
											aria-expanded={expanded}
											onClick={() => toggle(t.id)}
											onKeyDown={e => {
												if (e.key === 'Enter' || e.key === ' ') {
													e.preventDefault();
													toggle(t.id);
												} else if (e.key === 'Escape' && expanded) {
													e.preventDefault();
													toggle(t.id);
												}
											}}
											className={`cursor-pointer border-b border-hairline transition-colors ${
												expanded
													? 'bg-accent/5'
													: i % 2 === 0
														? 'hover:bg-surface-2'
														: 'bg-bezel/20 hover:bg-surface-2'
											}`}
										>
											<td className="px-3 py-2">
												<ChevronRight
													size={12}
													className={`text-text-dim transition-transform ${expanded ? 'rotate-90' : ''}`}
												/>
											</td>
											<td className="px-3 py-2">
												<span className={`inline-flex items-center gap-1.5 ${meta.tone}`}>
													<StatusIcon size={11} className={meta.pulse ? 'mc-led-pulse' : ''} />
													<span className="uppercase tracking-wider text-[10px]">{t.status}</span>
												</span>
											</td>
											<td className="px-3 py-2 text-text">{displayKind(t)}</td>
											<td
												className="px-3 py-2 text-text-dim text-[11px]"
												title={(t.host_ids ?? []).join(', ')}
											>
												{hostId ? (
													<Link
														href={`/hosts/${hostId}`}
														onClick={e => e.stopPropagation()}
														className="hover:text-accent"
													>
														{hostLabel(t)}
													</Link>
												) : (
													hostLabel(t)
												)}
											</td>
											<td
												className="px-3 py-2 text-text-dim text-[11px]"
												title={t.created_by ?? ''}
											>
												{creatorLabel(t)}
											</td>
											<td
												className="px-3 py-2 text-text-dim max-w-[320px] truncate"
												title={t.summary ?? ''}
											>
												{t.summary || <Badge size="sm">no detail</Badge>}
											</td>
											<td className="px-3 py-2">
												<span
													className={`mc-pip border ${riskTone}`}
													style={{ padding: '2px 6px' }}
												>
													{t.risk}
												</span>
											</td>
											<td className="px-3 py-2 text-text-dim text-[11px]" title={t.created_at}>
												{relTime(t.created_at)}
											</td>
											<td className="px-3 py-2 text-right">
												<Link
													href={`/tasks/${t.id}`}
													aria-label="Open task detail"
													onClick={e => e.stopPropagation()}
													onKeyDown={e => e.stopPropagation()}
													className="inline-flex items-center justify-center rounded-sm p-1 text-text-dim hover:bg-surface-2 hover:text-accent"
												>
													<ExternalLink size={12} />
												</Link>
											</td>
										</tr>
										{expanded ? (
											<tr>
												<td colSpan={9} className="border-b border-hairline bg-bezel/40 px-4 py-3">
													{hostId ? (
														<TaskResultPreview taskId={t.id} hostId={hostId} taskAction={action} />
													) : (
														<div className="text-xs text-text-dim">
															No host context — open task detail for full result.
														</div>
													)}
												</td>
											</tr>
										) : null}
									</Fragment>
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
							onChange={e => {
								setPageSize(Number(e.target.value) as (typeof PAGE_SIZES)[number]);
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

			{modal}
		</div>
	);
}
