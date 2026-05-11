'use client';

import { listLogs, streamLogs, type ListLogsResp, type LogRow as LogRowData } from '@/lib/api/logs';
import { useDensity } from '@/lib/mission-control/density';
import { ChevronDown, ChevronUp, Zap } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import useSWR from 'swr';
import { DensitySparkline } from './density-sparkline';
import { LogRow } from './log-row';

interface ActivityTimelineProps {
	hostId: string;
}

type SortColumn = 'ts' | 'level' | 'action' | 'outcome';
type SortDirection = 'asc' | 'desc';

export function ActivityTimeline({ hostId }: ActivityTimelineProps) {
	const { density, cycle: cycleDensity } = useDensity();
	const [timeRange, setTimeRange] = useState<'1h' | '24h' | '7d'>('1h');
	const [minLevel, setMinLevel] = useState<'debug' | 'info' | 'warn' | 'error' | 'critical'>('info');
	const [selectedCategories] = useState<string[]>([]);
	const [searchQ, setSearchQ] = useState('');
	const [sortColumn, setSortColumn] = useState<SortColumn>('ts');
	const [sortDir, setSortDir] = useState<SortDirection>('desc');

	// Compute time range
	const getFromTime = useCallback((): string => {
		const now = new Date();
		switch (timeRange) {
			case '1h':
				return new Date(now.getTime() - 60 * 60 * 1000).toISOString();
			case '24h':
				return new Date(now.getTime() - 24 * 60 * 60 * 1000).toISOString();
			case '7d':
				return new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000).toISOString();
		}
	}, [timeRange]);

	const { data: logResp, isLoading, error } = useSWR<ListLogsResp>(
		['logs', hostId, timeRange, minLevel, selectedCategories.join(','), searchQ],
		async () => {
			const from = getFromTime();
			return listLogs({
				hostId,
				from,
				level: minLevel,
				categories: selectedCategories.length > 0 ? selectedCategories : undefined,
				q: searchQ || undefined,
				limit: 50,
			});
		},
		{
			revalidateOnFocus: false,
			revalidateOnReconnect: false,
		},
	);

	// Live tail with streamLogs
	const [liveRows] = useState<LogRowData[]>([]);
	useEffect(() => {
		const from = getFromTime();
		streamLogs(
			{
				hostId,
				from,
				level: minLevel,
				categories: selectedCategories.length > 0 ? selectedCategories : undefined,
			},
			() => {
				// onRow callback - update liveRows here in full implementation
			},
		)
			.then(closeWs => {
				return () => closeWs?.();
			})
			.catch(e => console.warn('streamLogs failed:', e));

		return () => {
			// closeWs would be called here if implemented
		};
	}, [hostId, minLevel, selectedCategories, getFromTime]);

	const rows = logResp?.items || [];
	const allRows = [...liveRows, ...rows];

	// Sort rows
	const levelOrder: Record<string, number> = { debug: 0, info: 1, warn: 2, error: 3, critical: 4 };
	const sortedRows = [...allRows].sort((a, b) => {
		let aVal: string | number = String(a[sortColumn] || '');
		let bVal: string | number = String(b[sortColumn] || '');

		if (sortColumn === 'level') {
			const aLevel = a[sortColumn] as unknown as keyof typeof levelOrder;
			const bLevel = b[sortColumn] as unknown as keyof typeof levelOrder;
			aVal = levelOrder[aLevel] || 0;
			bVal = levelOrder[bLevel] || 0;
		} else {
			aVal = String(aVal).toLowerCase();
			bVal = String(bVal).toLowerCase();
		}

		if (aVal < bVal) return sortDir === 'asc' ? -1 : 1;
		if (aVal > bVal) return sortDir === 'asc' ? 1 : -1;
		return 0;
	});

	const handleSort = (col: SortColumn) => {
		if (sortColumn === col) {
			setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
		} else {
			setSortColumn(col);
			setSortDir('desc');
		}
	};

	// Build histogram for sparkline
	const from = getFromTime();
	const fromTime = new Date(from);
	const now = new Date();
	const rangeMs = now.getTime() - fromTime.getTime();
	const binMs = rangeMs / 60; // 60 bins

	const histogram = Array(60)
		.fill(null)
		.map(() => ({
			total: 0,
			errors: 0,
		}));

	for (const row of sortedRows) {
		const rowTime = new Date(row.ts);
		const offsetMs = rowTime.getTime() - fromTime.getTime();
		const binIdx = Math.floor(offsetMs / binMs);
		if (binIdx >= 0 && binIdx < 60) {
			histogram[binIdx].total += 1;
			if (row.outcome === 'failure') {
				histogram[binIdx].errors += 1;
			}
		}
	}

	// Hero metrics
	const errorCount = sortedRows.filter(r => r.level === 'error' || r.level === 'critical').length;
	const failureCount = sortedRows.filter(r => r.outcome === 'failure').length;

	if (isLoading) return <div className="p-6 text-text-dim">Loading logs…</div>;
	if (error) return <div className="p-6 text-danger">Failed to load logs</div>;

	return (
		<div className="flex flex-col gap-4">
			{/* Toolbar */}
			<div className="px-4 py-3 border border-hairline bg-surface-2 rounded flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between">
				{/* Left side: Time range + Level */}
				<div className="flex gap-2 items-center flex-wrap">
					{/* Time range buttons */}
					<div className="flex gap-1">
						{(['1h', '24h', '7d'] as const).map(tr => (
							<button
								key={tr}
								type="button"
								onClick={() => setTimeRange(tr)}
								className={`px-2 py-1 rounded text-xs font-semibold transition-colors ${
									timeRange === tr
										? 'bg-primary text-primary-fg'
										: 'bg-surface hover:bg-surface-2 text-text-dim hover:text-text'
								}`}
							>
								{tr === '1h' ? '1h' : tr === '24h' ? '24h' : '7d'}
							</button>
						))}
					</div>

					{/* Level filter */}
					<select
						value={minLevel}
						onChange={e => setMinLevel(e.target.value as 'debug' | 'info' | 'warn' | 'error' | 'critical')}
						className="px-2 py-1 rounded text-xs bg-surface border border-hairline text-text"
					>
						<option value="debug">Debug+</option>
						<option value="info">Info+</option>
						<option value="warn">Warn+</option>
						<option value="error">Error+</option>
						<option value="critical">Critical+</option>
					</select>

					{/* Live indicator LED */}
					<div className="flex items-center gap-1 ml-2 px-2 py-1 text-xs text-text-dim">
						<span className="w-2 h-2 rounded-full bg-ok animate-pulse" />
						<span>Live</span>
					</div>
				</div>

				{/* Right side: Search + Density */}
				<div className="flex gap-2 items-center flex-1 sm:flex-none">
					{/* Search */}
					<input
						type="text"
						placeholder="Search…"
						value={searchQ}
						onChange={e => setSearchQ(e.target.value)}
						className="px-2 py-1 rounded text-xs bg-surface border border-hairline text-text placeholder:text-text-dim flex-1 sm:flex-none sm:w-40"
					/>

					{/* Density toggle */}
					<button
						type="button"
						onClick={() => cycleDensity()}
						title={`Density: ${density}`}
						className="px-2 py-1 rounded text-xs bg-surface border border-hairline text-text-dim hover:text-text hover:bg-surface-2 transition-colors"
					>
						<Zap size={14} />
					</button>
				</div>
			</div>

			{/* Density sparkline */}
			<div className="px-4 pt-2">
				<div className="h-6 bg-surface rounded p-1">
					<DensitySparkline bins={histogram} />
				</div>
				<p className="text-xs text-text-dim mt-1">
					Activity density ({sortedRows.length} events, {errorCount} errors, {failureCount} failures)
				</p>
			</div>

			{/* Status LED row */}
			<div className="flex gap-3 px-4 text-xs">
				<div className="flex items-center gap-1.5">
					<span className="w-2 h-2 rounded-full bg-danger" />
					<span className="text-text-dim">Errors: {errorCount}</span>
				</div>
				<div className="flex items-center gap-1.5">
					<span className="w-2 h-2 rounded-full bg-warn" />
					<span className="text-text-dim">Failures: {failureCount}</span>
				</div>
				<div className="flex items-center gap-1.5">
					<span className="w-2 h-2 rounded-full bg-ok" />
					<span className="text-text-dim">Success: {sortedRows.length - failureCount}</span>
				</div>
			</div>

			{/* Column header for sorting */}
			<div className="px-4 py-2 bg-surface-2 rounded flex gap-4 text-xs text-text-dim font-semibold">
				<button
					type="button"
					onClick={() => handleSort('ts')}
					className="flex items-center gap-1 hover:text-text transition-colors flex-1"
				>
					Timestamp {sortColumn === 'ts' && (sortDir === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />)}
				</button>
				<button
					type="button"
					onClick={() => handleSort('level')}
					className="flex items-center gap-1 hover:text-text transition-colors"
				>
					Level {sortColumn === 'level' && (sortDir === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />)}
				</button>
				<button
					type="button"
					onClick={() => handleSort('action')}
					className="flex items-center gap-1 hover:text-text transition-colors flex-1"
				>
					Action {sortColumn === 'action' && (sortDir === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />)}
				</button>
				<button
					type="button"
					onClick={() => handleSort('outcome')}
					className="flex items-center gap-1 hover:text-text transition-colors"
				>
					Outcome {sortColumn === 'outcome' && (sortDir === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />)}
				</button>
			</div>

			{/* Logs list */}
			<div className="border border-hairline rounded overflow-hidden">
				{sortedRows.length === 0 ? (
					<div className="p-6 text-center text-text-dim">No logs in selected range</div>
				) : (
					<div className="divide-y divide-hairline">
						{sortedRows.map(row => (
							<LogRow key={`${row.id}-${row.seq}`} row={row} />
						))}
					</div>
				)}
			</div>

			{/* Pagination - placeholder for future implementation */}
			{logResp?.next_cursor && (
				<div className="flex justify-center pt-2">
					<button
						type="button"
						disabled
						className="px-4 py-2 rounded text-sm bg-surface-2 text-text-dim opacity-50 cursor-not-allowed"
					>
						Load more (coming soon)
					</button>
				</div>
			)}
		</div>
	);
}
