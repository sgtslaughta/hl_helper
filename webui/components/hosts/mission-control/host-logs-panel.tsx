'use client';

import { listLogs, type LogLevel, type LogRow, type Outcome } from '@/lib/api/logs';
import { FieldsTable } from '@/components/logs/fields-table';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { ChevronDown } from 'lucide-react';

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
	const containerRef = useRef<HTMLDivElement>(null);
	const dragRef = useRef(false);

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
		const ago = new Date(now.getTime() - (timeRange === '1h' ? 3600000 : timeRange === '6h' ? 21600000 : 86400000));
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
			className="flex flex-col bg-surface/30 rounded border border-hairline min-h-0"
			style={{ height: 'calc(100vh - 240px)' }}
			onMouseMove={handleDragMove}
			onMouseLeave={handleDragEnd}
			onMouseUp={handleDragEnd}
		>
			{/* Filter Row */}
			<div className="flex items-center gap-2 border-b border-hairline px-2 py-2 bg-surface/50 flex-shrink-0">
				{/* Time range */}
				<select
					value={timeRange}
					onChange={e => {
						setTimeRange(e.target.value);
						setSelectedLog(null);
					}}
					className="px-2 py-1 rounded text-xs bg-surface border border-hairline text-text hover:bg-surface/70"
				>
					<option value="1h">1h</option>
					<option value="6h">6h</option>
					<option value="24h">24h</option>
				</select>

				{/* Level filter */}
				<select
					value={levelFilter}
					onChange={e => {
						setLevelFilter(e.target.value as LogLevel | 'all');
						setSelectedLog(null);
					}}
					className="px-2 py-1 rounded text-xs bg-surface border border-hairline text-text hover:bg-surface/70"
				>
					<option value="all">All Levels</option>
					<option value="debug">Debug</option>
					<option value="info">Info</option>
					<option value="warn">Warn</option>
					<option value="error">Error</option>
					<option value="critical">Critical</option>
				</select>

				{/* Outcome chips */}
				<div className="flex gap-1">
					{(['all', 'success', 'failure', 'unknown'] as const).map(outcome => (
						<button
							key={outcome}
							type="button"
							onClick={() => {
								setOutcomeFilter(outcome);
								setSelectedLog(null);
							}}
							className={`px-2 py-1 rounded text-xs font-mono transition-colors ${
								outcomeFilter === outcome
									? outcome === 'all'
										? 'bg-accent/30 text-accent border border-accent/50'
										: OUTCOME_COLORS[outcome]
									: 'bg-surface border border-hairline text-text-dim hover:text-text'
							}`}
						>
							{outcome}
						</button>
					))}
				</div>

				{/* Search */}
				<input
					type="text"
					placeholder="Search message, action, category…"
					value={searchTerm}
					onChange={e => {
						setSearchTerm(e.target.value);
						setSelectedLog(null);
					}}
					className="flex-1 px-2 py-1 rounded text-xs bg-surface border border-hairline text-text placeholder-text-dim focus:outline-none focus:ring-1 focus:ring-accent"
				/>
			</div>

			{/* Table Section — independent vertical scroll */}
			<div
				style={{ flex: `${topFlex} 1 0` }}
				className="overflow-y-auto border-b border-hairline min-h-0"
			>
				{q.isLoading ? (
					<div className="p-3 text-xs text-text-dim">Loading…</div>
				) : filteredLogs.length === 0 ? (
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
							{filteredLogs.map((log, i) => (
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
									<span className={`font-semibold ${LEVEL_COLORS[log.level]}`}>
										{log.level}
									</span>
									<span className="text-text truncate">{log.action}</span>
									<span className="text-text-dim truncate">{log.message ?? '—'}</span>
									{log.outcome && (
										<span className={`px-1 rounded text-[10px] font-semibold whitespace-nowrap ${OUTCOME_COLORS[log.outcome]}`}>
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
			<div
				style={{ flex: `${bottomFlex} 1 0` }}
				className="overflow-y-auto min-h-0 p-3"
			>
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
