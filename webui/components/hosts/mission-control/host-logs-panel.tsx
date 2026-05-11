'use client';

import { FieldsTable } from '@/components/logs/fields-table';
import { type LogLevel, type LogRow, type Outcome, listLogs } from '@/lib/api/logs';
import { useQuery } from '@tanstack/react-query';
import { ArrowDownUp, ChevronDown, Search, SlidersHorizontal, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

type SortKey = 'ts' | 'level' | 'action' | 'outcome';
type SortDir = 'asc' | 'desc';
const LEVEL_ORDER: Record<LogLevel, number> = {
	debug: 10,
	info: 20,
	warn: 30,
	error: 40,
	critical: 50,
};

interface Props {
	hostId: string;
	paused: boolean;
}

const LEVEL_COLORS: Record<LogLevel, string> = {
	debug: 'text-text-dim',
	info: 'text-text-dim',
	warn: 'text-yellow-400',
	error: 'text-red-400',
	critical: 'text-red-500',
};

const OUTCOME_COLORS: Record<Outcome, string> = {
	success: 'bg-green-900/30 text-green-300 border border-green-700/50',
	failure: 'bg-red-900/30 text-red-300 border border-red-700/50',
	unknown: 'bg-gray-900/30 text-gray-400 border border-gray-700/50',
};

export function HostLogsPanel({ hostId, paused }: Props) {
	const [selectedLog, setSelectedLog] = useState<LogRow | null>(null);
	const [splitRatio, setSplitRatio] = useState(0.55);
	const [timeRange, setTimeRange] = useState('1h');
	const [levelFilter, setLevelFilter] = useState<LogLevel | 'all'>('all');
	const [outcomeFilter, setOutcomeFilter] = useState<Outcome | 'all'>('all');
	const [searchTerm, setSearchTerm] = useState('');
	const [sortKey, setSortKey] = useState<SortKey>('ts');
	const [sortDir, setSortDir] = useState<SortDir>('desc');
	const [popoverOpen, setPopoverOpen] = useState(false);
	const containerRef = useRef<HTMLDivElement>(null);
	const popoverRef = useRef<HTMLDivElement>(null);
	const dragRef = useRef(false);

	// Click-outside to dismiss popover
	useEffect(() => {
		if (!popoverOpen) return;
		const onDoc = (e: MouseEvent) => {
			if (!popoverRef.current) return;
			if (!popoverRef.current.contains(e.target as Node)) setPopoverOpen(false);
		};
		document.addEventListener('mousedown', onDoc);
		return () => document.removeEventListener('mousedown', onDoc);
	}, [popoverOpen]);

	// Load split ratio from localStorage on mount
	useEffect(() => {
		const stored = localStorage.getItem('hostpanel.logs.split');
		if (stored) {
			const parsed = Number.parseFloat(stored);
			if (!Number.isNaN(parsed) && parsed >= 0.25 && parsed <= 0.85) {
				setSplitRatio(parsed);
			}
		}
	}, []);

	// Save split ratio to localStorage when changed
	useEffect(() => {
		localStorage.setItem('hostpanel.logs.split', String(splitRatio));
	}, [splitRatio]);

	// Calculate time window (1h, 6h, 24h default to 1h)
	const getTimeWindow = () => {
		const now = new Date();
		const ago = new Date(
			now.getTime() - (timeRange === '1h' ? 3600000 : timeRange === '6h' ? 21600000 : 86400000),
		);
		return {
			from: ago.toISOString(),
			to: now.toISOString(),
		};
	};

	const timeWindow = getTimeWindow();

	const q = useQuery<LogRow[]>({
		queryKey: ['host-logs', hostId, timeRange, levelFilter, outcomeFilter, searchTerm],
		queryFn: async () => {
			const resp = await listLogs({
				hostId,
				from: timeWindow.from,
				to: timeWindow.to,
				level: levelFilter === 'all' ? undefined : levelFilter,
				outcome: outcomeFilter === 'all' ? undefined : outcomeFilter,
				q: searchTerm || undefined,
				limit: 500,
			});
			return resp.items;
		},
		refetchInterval: paused ? false : 5_000,
		retry: false,
	});

	const logs = q.data ?? [];

	// Filter logs by search term (additional client-side filtering for message/action)
	const filteredLogs = logs.filter(log => {
		if (!searchTerm) return true;
		const term = searchTerm.toLowerCase();
		return (
			log.message?.toLowerCase().includes(term) ||
			log.action?.toLowerCase().includes(term) ||
			log.category?.toLowerCase().includes(term)
		);
	});

	// Sort
	const sortedLogs = [...filteredLogs].sort((a, b) => {
		const dir = sortDir === 'asc' ? 1 : -1;
		switch (sortKey) {
			case 'ts':
				return (new Date(a.ts).getTime() - new Date(b.ts).getTime()) * dir;
			case 'level':
				return (LEVEL_ORDER[a.level] - LEVEL_ORDER[b.level]) * dir;
			case 'action':
				return a.action.localeCompare(b.action) * dir;
			case 'outcome':
				return (a.outcome || '').localeCompare(b.outcome || '') * dir;
		}
	});

	const activeFilterCount =
		(timeRange !== '1h' ? 1 : 0) +
		(levelFilter !== 'all' ? 1 : 0) +
		(outcomeFilter !== 'all' ? 1 : 0) +
		(sortKey !== 'ts' || sortDir !== 'desc' ? 1 : 0);

	const handleDragStart = () => {
		dragRef.current = true;
	};

	const handleDragEnd = () => {
		dragRef.current = false;
	};

	const handleDragMove = (e: React.MouseEvent) => {
		if (!dragRef.current || !containerRef.current) return;
		const container = containerRef.current;
		const rect = container.getBoundingClientRect();
		const y = e.clientY - rect.top;
		const newRatio = Math.max(0.25, Math.min(0.85, y / rect.height));
		setSplitRatio(newRatio);
	};

	if (q.isError) {
		return <div className="text-sm text-text-dim">Logs endpoint not available for this host.</div>;
	}

	// Use flex ratios (not %-of-parent) so the two halves work even when the
	// outer parent in action-pane.tsx (`space-y-3`) doesn't constrain height.
	const topFlex = Math.round(splitRatio * 100);
	const bottomFlex = 100 - topFlex;

	return (
		<div
			ref={containerRef}
			className="flex flex-1 h-full min-h-0 flex-col bg-surface/30 rounded border border-hairline"
			onMouseMove={handleDragMove}
			onMouseLeave={handleDragEnd}
			onMouseUp={handleDragEnd}
		>
			{/* Filter Row — condensed: search + popover trigger */}
			<div className="relative flex items-center gap-2 border-b border-hairline px-2 py-2 bg-surface/50 flex-shrink-0">
				<div className="relative flex-1 min-w-0">
					<Search
						size={12}
						className="absolute left-2 top-1/2 -translate-y-1/2 text-text-dim pointer-events-none"
					/>
					<input
						type="text"
						placeholder="Search…"
						value={searchTerm}
						onChange={e => {
							setSearchTerm(e.target.value);
							setSelectedLog(null);
						}}
						className="w-full pl-7 pr-7 py-1 rounded text-xs bg-surface border border-hairline text-text placeholder-text-dim focus:outline-none focus:ring-1 focus:ring-accent font-mono"
					/>
					{searchTerm && (
						<button
							type="button"
							onClick={() => setSearchTerm('')}
							className="absolute right-1.5 top-1/2 -translate-y-1/2 text-text-dim hover:text-text"
							title="Clear search"
							aria-label="Clear search"
						>
							<X size={12} />
						</button>
					)}
				</div>

				<button
					type="button"
					onClick={() => setPopoverOpen(o => !o)}
					className={`flex-shrink-0 flex items-center gap-1 px-2 py-1 rounded text-xs border transition-colors ${
						popoverOpen || activeFilterCount > 0
							? 'border-accent text-accent bg-accent/10'
							: 'border-hairline text-text-dim hover:text-text hover:bg-surface'
					}`}
					title="Filter & sort"
					aria-haspopup="true"
					aria-expanded={popoverOpen}
				>
					<SlidersHorizontal size={12} />
					{activeFilterCount > 0 && (
						<span className="font-mono leading-none">{activeFilterCount}</span>
					)}
				</button>

				{popoverOpen && (
					<div
						ref={popoverRef}
						className="absolute right-2 top-full mt-1 z-50 w-64 rounded border border-hairline bg-surface shadow-xl p-3 space-y-3 font-mono text-xs"
					>
						<FilterField label="TIME">
							<div className="flex gap-1">
								{(['1h', '6h', '24h'] as const).map(v => (
									<PopChip
										key={v}
										active={timeRange === v}
										onClick={() => {
											setTimeRange(v);
											setSelectedLog(null);
										}}
									>
										{v}
									</PopChip>
								))}
							</div>
						</FilterField>

						<FilterField label="LEVEL">
							<select
								value={levelFilter}
								onChange={e => {
									setLevelFilter(e.target.value as LogLevel | 'all');
									setSelectedLog(null);
								}}
								className="w-full px-2 py-1 rounded text-xs bg-surface-2 border border-hairline text-text"
							>
								<option value="all">All</option>
								<option value="debug">Debug</option>
								<option value="info">Info</option>
								<option value="warn">Warn</option>
								<option value="error">Error</option>
								<option value="critical">Critical</option>
							</select>
						</FilterField>

						<FilterField label="OUTCOME">
							<div className="flex flex-wrap gap-1">
								{(['all', 'success', 'failure', 'unknown'] as const).map(o => (
									<PopChip
										key={o}
										active={outcomeFilter === o}
										onClick={() => {
											setOutcomeFilter(o);
											setSelectedLog(null);
										}}
									>
										{o}
									</PopChip>
								))}
							</div>
						</FilterField>

						<FilterField label="SORT BY">
							<div className="flex items-center gap-2">
								<select
									value={sortKey}
									onChange={e => setSortKey(e.target.value as SortKey)}
									className="flex-1 px-2 py-1 rounded text-xs bg-surface-2 border border-hairline text-text"
								>
									<option value="ts">Time</option>
									<option value="level">Level</option>
									<option value="action">Action</option>
									<option value="outcome">Outcome</option>
								</select>
								<button
									type="button"
									onClick={() => setSortDir(d => (d === 'asc' ? 'desc' : 'asc'))}
									className="flex items-center gap-1 px-2 py-1 rounded border border-hairline text-text-dim hover:text-text"
									title={`Sort ${sortDir === 'asc' ? 'ascending' : 'descending'}`}
								>
									<ArrowDownUp size={12} />
									<span>{sortDir}</span>
								</button>
							</div>
						</FilterField>

						<div className="pt-2 border-t border-hairline flex justify-between">
							<button
								type="button"
								onClick={() => {
									setTimeRange('1h');
									setLevelFilter('all');
									setOutcomeFilter('all');
									setSortKey('ts');
									setSortDir('desc');
								}}
								className="text-text-dim hover:text-text"
							>
								Reset
							</button>
							<button
								type="button"
								onClick={() => setPopoverOpen(false)}
								className="text-accent hover:text-text"
							>
								Done
							</button>
						</div>
					</div>
				)}
			</div>

			{/* Table Section — independent vertical scroll */}
			<div
				style={{ flex: `${topFlex} 1 0` }}
				className="overflow-y-auto border-b border-hairline min-h-0"
			>
				{q.isLoading ? (
					<div className="p-3 text-xs text-text-dim">Loading…</div>
				) : sortedLogs.length === 0 ? (
					<div className="p-3 text-xs text-text-dim">No logs match filters.</div>
				) : (
					<div className="w-full">
						<div className="sticky top-0 bg-surface/70 border-b border-hairline grid grid-cols-5 gap-2 px-2 py-1 text-xs font-semibold text-text-dim">
							<div>Time</div>
							<div>Level</div>
							<div>Action</div>
							<div>Message</div>
							<div>Outcome</div>
						</div>
						<div className="space-y-0">
							{sortedLogs.map((log, i) => (
								<button
									key={`${log.id}-${i}`}
									type="button"
									onClick={() => setSelectedLog(log)}
									onKeyDown={e => {
										if (e.key === 'Enter') setSelectedLog(log);
									}}
									className={`w-full px-2 py-1 text-left text-xs font-mono border-b border-hairline/50 transition-colors hover:bg-surface/40 grid grid-cols-5 gap-2 ${
										selectedLog?.id === log.id ? 'bg-accent/10' : ''
									}`}
								>
									<span className="text-text-dim whitespace-nowrap">
										{new Date(log.ts).toLocaleTimeString()}
									</span>
									<span className={`font-semibold ${LEVEL_COLORS[log.level]}`}>{log.level}</span>
									<span className="text-text truncate">{log.action}</span>
									<span className="text-text-dim truncate">{log.message ?? '—'}</span>
									{log.outcome && (
										<span
											className={`px-1 rounded text-[10px] font-semibold whitespace-nowrap ${OUTCOME_COLORS[log.outcome]}`}
										>
											{log.outcome}
										</span>
									)}
								</button>
							))}
						</div>
					</div>
				)}
			</div>

			{/* Drag Handle */}
			<div
				onMouseDown={handleDragStart}
				className="h-1 bg-hairline hover:bg-accent/50 cursor-row-resize transition-colors flex-shrink-0"
				title="Drag to resize"
			/>

			{/* Detail Pane — independent vertical scroll */}
			<div style={{ flex: `${bottomFlex} 1 0` }} className="overflow-y-auto min-h-0 p-3">
				{selectedLog ? (
					<div className="space-y-3">
						<div className="text-xs text-text-dim">
							<span className="font-semibold text-text">{selectedLog.action}</span> at{' '}
							{new Date(selectedLog.ts).toLocaleString()}
						</div>
						<FieldsTable obj={selectedLog} errorObj={selectedLog.error} />
					</div>
				) : (
					<div className="text-xs text-text-dim text-center py-8">
						Select a log row to view details
					</div>
				)}
			</div>
		</div>
	);
}

function FilterField({ label, children }: { label: string; children: React.ReactNode }) {
	return (
		<div className="space-y-1">
			<div className="text-[10px] uppercase tracking-wider text-text-dim font-semibold">
				{label}
			</div>
			{children}
		</div>
	);
}

function PopChip({
	active,
	onClick,
	children,
}: {
	active: boolean;
	onClick: () => void;
	children: React.ReactNode;
}) {
	return (
		<button
			type="button"
			onClick={onClick}
			className={`px-2 py-1 rounded text-xs transition-colors ${
				active
					? 'bg-accent/20 text-accent border border-accent/50'
					: 'bg-surface-2 border border-hairline text-text-dim hover:text-text'
			}`}
		>
			{children}
		</button>
	);
}
