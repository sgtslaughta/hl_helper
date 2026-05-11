'use client';

export const dynamic = 'force-dynamic';

import { DetailDrawer } from '@/components/logs/detail-drawer';
import { FacetsPanel } from '@/components/logs/facets-panel';
import { FilterRail, type LogFilters } from '@/components/logs/filter-rail';
import { ResultsTable } from '@/components/logs/results-table';
import { TimelineHistogram } from '@/components/logs/timeline-histogram';
import { listLogs, type FacetBucket, type LogRow } from '@/lib/api/logs';
import { useDensity } from '@/lib/mission-control/density';
import NumberFlow from '@number-flow/react';
import { AlertTriangle, BarChart3, Lock, TrendingDown } from 'lucide-react';
import { useEffect, useState } from 'react';

export default function LogsHubPage() {
	const { density } = useDensity();
	const [rows, setRows] = useState<LogRow[]>([]);
	const [facets, setFacets] = useState<Record<string, FacetBucket[]>>();
	const [selectedRow, setSelectedRow] = useState<LogRow | null>(null);
	const [loading, setLoading] = useState(true);
	const [filters, setFilters] = useState<LogFilters>({});
	const [cursor, setCursor] = useState<string | null>(null);

	// Hero metrics
	const errorCount = rows.filter(r => r.level === 'error' || r.level === 'critical').length;
	const failureCount = rows.filter(r => r.outcome === 'failure').length;
	const successRate =
		rows.length > 0
			? Math.round(
					((rows.length - failureCount) / rows.length) * 100,
				)
			: 100;
	const uniqueHosts = new Set(rows.map(r => r.host_id)).size;

	// Build histogram bins from rows
	const bins = Array.from({ length: 60 }).map((_, i) => {
		const bucketStart = cursor ? new Date(cursor).getTime() : Date.now();
		const bucketTime = bucketStart - (60 - i) * 1000 * 60; // 60-minute window, 1-minute buckets
		const bucketEnd = bucketTime + 1000 * 60;

		const bucketRows = rows.filter(r => {
			const ts = new Date(r.ts).getTime();
			return ts >= bucketTime && ts < bucketEnd;
		});

		const errors = bucketRows.filter(r => r.level === 'error' || r.level === 'critical').length;
		return { total: bucketRows.length, errors };
	});

	useEffect(() => {
		(async () => {
			setLoading(true);
			try {
				const args = { ...filters, limit: 100 };
				const resp = await listLogs(args);
				setRows(resp.items);
				setFacets(resp.facets);
				if (resp.next_cursor) {
					setCursor(resp.next_cursor);
				}
			} catch (e) {
				console.error('Failed to load logs', e);
			} finally {
				setLoading(false);
			}
		})();
	}, [filters]);

	return (
		<div className="flex h-full flex-col bg-surface">
			{/* Header */}
			<div className="border-b border-hairline px-6 py-4">
				<h1 className="text-h1 text-text">Logs Hub</h1>
				<p className="text-sm text-text-dim mt-1">Search and analyze activity logs across all hosts</p>

				{/* Hero metrics */}
				<div className={`grid gap-3 mt-4 ${density === 'lean' ? 'grid-cols-2 sm:grid-cols-4' : 'grid-cols-2 sm:grid-cols-4'}`}>
					{/* Total Events */}
					<div className="rounded border border-hairline bg-surface-2 px-3 py-2">
						<div className="flex items-baseline justify-between gap-2">
							<span className="text-xs text-text-dim font-semibold uppercase tracking-wider">Events</span>
							<BarChart3 size={14} className="text-text-dim" />
						</div>
						<div className="text-lg font-bold text-text mt-1">
							<NumberFlow value={rows.length} format={{ notation: 'compact' }} />
						</div>
					</div>

					{/* Errors */}
					<div className="rounded border border-hairline bg-surface-2 px-3 py-2">
						<div className="flex items-baseline justify-between gap-2">
							<span className="text-xs text-danger font-semibold uppercase tracking-wider">Errors</span>
							<AlertTriangle size={14} className="text-danger" />
						</div>
						<div className="text-lg font-bold text-danger mt-1">
							<NumberFlow value={errorCount} format={{ notation: 'compact' }} />
						</div>
					</div>

					{/* Success Rate */}
					<div className="rounded border border-hairline bg-surface-2 px-3 py-2">
						<div className="flex items-baseline justify-between gap-2">
							<span className="text-xs text-ok font-semibold uppercase tracking-wider">Success</span>
							<TrendingDown size={14} className={successRate < 90 ? 'text-warn' : 'text-ok'} />
						</div>
						<div className={`text-lg font-bold mt-1 ${successRate < 90 ? 'text-warn' : 'text-ok'}`}>
							<NumberFlow value={successRate} suffix="%" />
						</div>
					</div>

					{/* Unique Hosts */}
					<div className="rounded border border-hairline bg-surface-2 px-3 py-2">
						<div className="flex items-baseline justify-between gap-2">
							<span className="text-xs text-accent font-semibold uppercase tracking-wider">Hosts</span>
							<Lock size={14} className="text-accent" />
						</div>
						<div className="text-lg font-bold text-accent mt-1">
							<NumberFlow value={uniqueHosts} format={{ notation: 'compact' }} />
						</div>
					</div>
				</div>
			</div>

			{/* Main Content */}
			<div className="flex flex-1 overflow-hidden">
				{/* Filter Rail */}
				<FilterRail onChange={setFilters} />

				{/* Center: Timeline + Results */}
				<div className="flex-1 flex flex-col gap-4 overflow-hidden p-4">
					{/* Timeline Histogram */}
					<div>
						<div className="text-xs text-text-dim mb-1 px-1">Activity Timeline (60 min)</div>
						<TimelineHistogram bins={bins} />
					</div>

					{/* Results Table */}
					{loading && <div className="text-sm text-text-dim p-6">Loading logs…</div>}
					{!loading && rows.length === 0 && <div className="text-sm text-text-dim p-6">No logs found</div>}
					{!loading && rows.length > 0 && (
						<div className="flex-1 overflow-auto">
							<ResultsTable rows={rows} onRowClick={setSelectedRow} />
						</div>
					)}
				</div>

				{/* Facets Panel */}
				<FacetsPanel facets={facets} />
			</div>

			{/* Detail Drawer */}
			<DetailDrawer row={selectedRow} onClose={() => setSelectedRow(null)} />
		</div>
	);
}
