'use client';

import { listLogs, streamLogs, type ListLogsResp, type LogRow as LogRowData } from '@/lib/api/logs';
import { useCallback, useEffect, useState } from 'react';
import useSWR from 'swr';
import { LogRow } from './log-row';
import { DensitySparkline } from './density-sparkline';

interface ActivityTimelineProps {
	hostId: string;
}

export function ActivityTimeline({ hostId }: ActivityTimelineProps) {
	const [timeRange, setTimeRange] = useState<'1h' | '24h' | '7d'>('1h');
	const [minLevel, setMinLevel] = useState<'debug' | 'info' | 'warn' | 'error' | 'critical'>('info');
	const [selectedCategories] = useState<string[]>([]);
	const [searchQ, setSearchQ] = useState('');

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

	for (const row of allRows) {
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

	if (isLoading) return <div className="p-6 text-text-dim">Loading logs…</div>;
	if (error) return <div className="p-6 text-danger">Failed to load logs</div>;

	return (
		<div className="flex flex-col gap-4">
			{/* Filter bar */}
			<div className="px-4 py-3 border-b border-hairline bg-surface-2 rounded flex flex-col sm:flex-row gap-3 items-stretch sm:items-center">
				{/* Time range */}
				<div className="flex gap-2">
					{(['1h', '24h', '7d'] as const).map(tr => (
						<button
							key={tr}
							type="button"
							onClick={() => setTimeRange(tr)}
							className={`px-3 py-1 rounded text-xs font-semibold transition-colors ${
								timeRange === tr
									? 'bg-primary text-primary-fg'
									: 'bg-surface hover:bg-surface-2 text-text-dim hover:text-text'
							}`}
						>
							{tr === '1h' ? 'Last 1h' : tr === '24h' ? 'Last 24h' : 'Last 7d'}
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

				{/* Search */}
				<input
					type="text"
					placeholder="Search…"
					value={searchQ}
					onChange={e => setSearchQ(e.target.value)}
					className="px-2 py-1 rounded text-xs bg-surface border border-hairline text-text placeholder:text-text-dim flex-1"
				/>
			</div>

			{/* Density sparkline */}
			<div className="px-4 pt-2">
				<div className="h-6 bg-surface rounded p-1">
					<DensitySparkline bins={histogram} />
				</div>
				<p className="text-xs text-text-dim mt-1">Activity density (red = high error rate)</p>
			</div>

			{/* Logs list */}
			<div className="border border-hairline rounded overflow-hidden">
				{allRows.length === 0 ? (
					<div className="p-6 text-center text-text-dim">No logs in selected range</div>
				) : (
					<div className="divide-y divide-hairline">
						{allRows.map(row => (
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
