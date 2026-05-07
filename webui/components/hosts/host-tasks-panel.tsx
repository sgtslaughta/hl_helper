'use client';

import { EmptyState } from '@/components/empty-states/empty-state';
import { ActionConfirmDialog } from '@/components/hosts/action-confirm-dialog';
import { BlueprintSkeleton } from '@/components/skeletons/blueprint-skeleton';
import { TaskResultPreview } from '@/components/tasks/task-result-preview';
import { Badge } from '@/components/primitives/badge';
import { apiFetch } from '@/lib/api-client';
import { type Host, shellExecHost } from '@/lib/api/hosts';
import { useCanPerform } from '@/lib/rbac';
import { relTime } from '@/lib/time';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
	CheckCircle2,
	ChevronLeft,
	ChevronRight,
	ChevronsLeft,
	ChevronsRight,
	CircleDashed,
	CircleDot,
	ExternalLink,
	Plus,
	XCircle,
} from 'lucide-react';
import Link from 'next/link';
import type { ComponentType } from 'react';
import { Fragment, useState } from 'react';

interface TaskListItem {
	id: string;
	kind: string;
	status: string;
	created_at: string;
	risk: string;
	summary?: string;
	payload?: Record<string, unknown>;
	result?: { status: string };
	host_update_status?: string;
}
interface TasksPage {
	items: TaskListItem[];
	next_cursor: string | null;
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
};

const RISK_TONE: Record<string, string> = {
	low: 'text-text-dim border-hairline',
	medium: 'text-accent border-accent/40',
	high: 'text-warn border-warn/40',
	critical: 'text-danger border-danger/40',
	irreversible: 'text-danger border-danger/40',
};

const PAGE_SIZES = [10, 25, 50] as const;

function renderTaskDetail(task: TaskListItem): React.ReactNode {
	switch (task.kind) {
		case 'agent_update': {
			const p = task.payload as { release_id: string; force?: boolean; reason?: string };
			const status = task.result?.status ?? task.host_update_status ?? 'queued';
			return (
				<div className="space-y-1">
					<div className="text-xs text-text-dim">Update to release {p.release_id.slice(0, 8)}</div>
					<Badge size="sm">{status}</Badge>
					{p.reason && <div className="text-xs">{p.reason}</div>}
				</div>
			);
		}
		default:
			return task.summary ?? '—';
	}
}

interface PanelProps {
	hostId: string;
	host?: Host;
}

export function HostTasksPanel({ hostId, host }: PanelProps) {
	const [showNew, setShowNew] = useState(false);
	const [command, setCommand] = useState('');
	const [timeoutS, setTimeoutS] = useState(60);
	const [expandedId, setExpandedId] = useState<string | null>(null);
	const [page, setPage] = useState(0);
	const [pageSize, setPageSize] = useState<(typeof PAGE_SIZES)[number]>(10);
	const cap = useCanPerform('shell-exec');
	const qc = useQueryClient();
	const shellMut = useMutation({
		mutationFn: (principal: string) =>
			shellExecHost(hostId, { command, timeout_s: timeoutS }, principal),
		onSuccess: () => qc.invalidateQueries({ queryKey: ['hosts', hostId, 'tasks'] }),
	});
	const q = useQuery<TasksPage>({
		queryKey: ['hosts', hostId, 'tasks'],
		queryFn: () => apiFetch<TasksPage>(`/v1/tasks?host_id=${encodeURIComponent(hostId)}&limit=200`),
		refetchInterval: 3_000,
	});

	const items = q.data?.items ?? [];
	const running = items.filter(t => t.status === 'running').length;
	const total = items.length;
	const totalPages = Math.max(1, Math.ceil(total / pageSize));
	const safePage = Math.min(page, totalPages - 1);
	const startIdx = safePage * pageSize;
	const pageItems = items.slice(startIdx, startIdx + pageSize);

	const headerBar = (
		<div className="mb-3 flex items-center justify-between">
			<div className="flex items-center gap-2">
				<span className="mc-heading">Tasks</span>
				{running > 0 ? (
					<span className="mc-pip text-accent border-accent/40">
						<span className="mc-led mc-led-pulse" />
						{running} RUNNING
					</span>
				) : null}
				<span className="font-mono text-[10px] uppercase tracking-wider text-text-dim">
					[{total} total]
				</span>
			</div>
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
	);

	const dialogHost = host ?? { id: hostId, hostname: hostId, labels: {} };

	function dispatch() {
		shellMut.mutate(cap.principal ?? '');
		setShowNew(false);
		setCommand('');
		setTimeoutS(60);
	}

	const modal =
		showNew && cap.allowed ? (
			<ActionConfirmDialog
				action="shell-exec"
				host={{ id: dialogHost.id, hostname: dialogHost.hostname, labels: dialogHost.labels }}
				principal={cap.principal ?? ''}
				onClose={() => setShowNew(false)}
				onConfirm={dispatch}
				formChildren={
					<div className="mb-3 space-y-2">
						<label className="block font-mono text-[11px] uppercase tracking-wider text-text-dim">
							Command
							<textarea
								value={command}
								onChange={e => setCommand(e.target.value)}
								rows={6}
								spellCheck={false}
								placeholder="$ "
								className="mt-1 w-full resize-y rounded-sm border border-hairline bg-canvas px-2 py-1.5 font-mono text-[13px] leading-relaxed text-text outline-none focus:border-accent"
							/>
						</label>
						<div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-wider text-text-dim">
							<span>Timeout</span>
							<input
								type="number"
								min={1}
								value={timeoutS}
								onChange={e => setTimeoutS(Math.max(1, Number.parseInt(e.target.value) || 1))}
								aria-label="Timeout seconds"
								className="w-20 rounded-sm border border-hairline bg-bezel/60 px-2 py-1 text-right font-mono text-[12px] text-text outline-none focus:border-accent"
							/>
							<span className="text-text-dim normal-case">seconds</span>
						</div>
					</div>
				}
			/>
		) : null;

	if (q.isLoading)
		return (
			<div>
				{headerBar}
				<BlueprintSkeleton rows={5} />
				{modal}
			</div>
		);
	if (q.isError)
		return (
			<div>
				{headerBar}
				<EmptyState title="Failed to load tasks" description="Try again." />
				{modal}
			</div>
		);

	if (items.length === 0)
		return (
			<div>
				{headerBar}
				<EmptyState
					title="No tasks yet for this host"
					description="Click + New Task to dispatch one."
				/>
				{modal}
			</div>
		);

	function toggle(id: string) {
		setExpandedId(prev => (prev === id ? null : id));
	}

	return (
		<div>
			{headerBar}
			<div className="mc-bezel overflow-hidden">
				<table className="w-full">
					<thead>
						<tr className="border-b border-hairline bg-bezel/40 font-mono text-[10px] uppercase tracking-[0.14em] text-text-dim">
							<th className="px-3 py-2 text-left font-semibold w-8" aria-label="Expand" />
							<th className="px-3 py-2 text-left font-semibold">Status</th>
							<th className="px-3 py-2 text-left font-semibold">Kind</th>
							<th className="px-3 py-2 text-left font-semibold">Detail</th>
							<th className="px-3 py-2 text-left font-semibold">Risk</th>
							<th className="px-3 py-2 text-left font-semibold">Created</th>
							<th className="px-3 py-2 text-right font-semibold w-10" aria-label="Open" />
						</tr>
					</thead>
					<tbody className="font-mono text-[12px]">
						{pageItems.map((t, i) => {
							const expanded = expandedId === t.id;
							const meta = STATUS_META[t.status] ?? STATUS_META.pending;
							const StatusIcon = meta.icon;
							const riskTone = RISK_TONE[t.risk?.toLowerCase()] ?? RISK_TONE.low;
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
										<td className="px-3 py-2 text-text">{t.kind}</td>
										<td
											className="px-3 py-2 text-text-dim max-w-[320px] truncate"
											title={t.summary ?? ''}
										>
											{renderTaskDetail(t)}
										</td>
										<td className="px-3 py-2">
											<span className={`mc-pip border ${riskTone}`} style={{ padding: '2px 6px' }}>
												{t.risk}
											</span>
										</td>
										<td className="px-3 py-2 text-text-dim text-[11px]">{relTime(t.created_at)}</td>
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
											<td colSpan={7} className="border-b border-hairline bg-bezel/40 px-4 py-3">
												<section aria-label={`Result for ${t.kind}`}>
													<TaskResultPreview taskId={t.id} hostId={hostId} />
												</section>
											</td>
										</tr>
									) : null}
								</Fragment>
							);
						})}
					</tbody>
				</table>
			</div>

			{/* Pagination */}
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
