'use client';

export const dynamic = 'force-dynamic';

import { DetailDrawer } from '@/components/logs/detail-drawer';
import { FacetsPanel } from '@/components/logs/facets-panel';
import { FilterRail, type LogFilters } from '@/components/logs/filter-rail';
import { ResultsTable } from '@/components/logs/results-table';
import { TimelineHistogram } from '@/components/logs/timeline-histogram';
import { listLogs, type LogRow } from '@/lib/api/logs';
import { useSearchParams } from 'next/navigation';
import { useEffect, useState } from 'react';

export default function LogsHubPage() {
	const searchParams = useSearchParams();
	const [rows, setRows] = useState<LogRow[]>([]);
	const [facets, setFacets] = useState<Record<string, any>>();
	const [selectedRow, setSelectedRow] = useState<LogRow | null>(null);
	const [loading, setLoading] = useState(true);
	const [filters, setFilters] = useState<LogFilters>({});
	const [cursor, setCursor] = useState<string | null>(null);

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
