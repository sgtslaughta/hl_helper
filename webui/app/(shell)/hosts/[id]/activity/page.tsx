'use client';

export const dynamic = 'force-dynamic';

import { listLogs, listCategories, type ListLogsResp, type LogRow } from '@/lib/api/logs';
import { TempPolicyPill } from '@/components/hosts/activity/temp-policy-pill';
import { getPolicy } from '@/lib/api/logs';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import useSWR from 'swr';
import { ActivityFilterBar, type ActivityFilters } from '@/components/hosts/activity/activity-filter-bar';
import { DensitySparkline } from '@/components/hosts/activity/density-sparkline';
import { ActivityResultsTable } from '@/components/hosts/activity/activity-results-table';
import { ActivityDetailPane } from '@/components/hosts/activity/activity-detail-pane';
import { ActivitySplit } from '@/components/hosts/activity/activity-split';

export default function HostActivityPage() {
	const params = useParams<{ id: string }>();
	const hostId = params.id;
	const router = useRouter();
	const searchParams = useSearchParams();

	const [selectedRow, setSelectedRow] = useState<LogRow | null>(null);
	const [pauseTail, setPauseTail] = useState(false);
	const [filters, setFilters] = useState<ActivityFilters>({
		timeRange: (searchParams.get('timeRange') as any) || '1h',
		level: (searchParams.get('level') as any) || 'info',
		outcome: searchParams.get('outcome')?.split(',').filter(Boolean) as any,
		categories: searchParams.get('categories')?.split(',').filter(Boolean),
		q: searchParams.get('q') || '',
	});

	const { data: policy, mutate: refetchPolicy } = useSWR(
		['policy', hostId],
		async () => {
			try {
				return await getPolicy(`host:${hostId}`);
			} catch (e) {
				return null;
			}
		},
		{
			revalidateOnFocus: false,
			refreshInterval: 10_000,
		},
	);

	const { data: categoriesResp = [] } = useSWR(['categories'], listCategories);
	const categories = categoriesResp.map(c => c.name);

	// Compute time range
	const getFromTime = useCallback((): string => {
		const now = new Date();
		const range = filters.timeRange || '1h';
		switch (range) {
			case '15m':
				return new Date(now.getTime() - 15 * 60 * 1000).toISOString();
			case '1h':
				return new Date(now.getTime() - 60 * 60 * 1000).toISOString();
			case '6h':
				return new Date(now.getTime() - 6 * 60 * 60 * 1000).toISOString();
			case '24h':
				return new Date(now.getTime() - 24 * 60 * 60 * 1000).toISOString();
			case '7d':
				return new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000).toISOString();
			default:
				return new Date(now.getTime() - 60 * 60 * 1000).toISOString();
		}
	}, [filters.timeRange]);

	const { data: logResp, isLoading, error } = useSWR<ListLogsResp>(
		['logs', hostId, filters.timeRange, filters.level, filters.categories?.join(','), filters.q],
		async () => {
			const from = getFromTime();
			// API filters by outcome array would require multiple requests
			// For now, just pass undefined and filter on client if needed
			return listLogs({
				hostId,
				from,
				level: filters.level,
				categories: filters.categories?.length ? filters.categories : undefined,
				q: filters.q || undefined,
				limit: 500,
			});
		},
		{
			revalidateOnFocus: false,
			revalidateOnReconnect: false,
		},
	);

	// Update URL search params when filters change
	useEffect(() => {
		const params = new URLSearchParams();
		if (filters.timeRange) params.set('timeRange', filters.timeRange);
		if (filters.level) params.set('level', filters.level);
		if (filters.outcome?.length) params.set('outcome', filters.outcome.join(','));
		if (filters.categories?.length) params.set('categories', filters.categories.join(','));
		if (filters.q) params.set('q', filters.q);
		router.push(`?${params.toString()}`, { scroll: false });
	}, [filters, router]);

	// Filter rows by outcome on client if filters applied
	let rows = logResp?.items || [];
	if (filters.outcome?.length) {
		rows = rows.filter(r => r.outcome && filters.outcome!.includes(r.outcome));
	}

	// Build histogram for sparkline
	const from = getFromTime();
	const fromTime = new Date(from);
	const now = new Date();
	const rangeMs = now.getTime() - fromTime.getTime();
	const binMs = rangeMs / 60;

	const histogram = Array(60)
		.fill(null)
		.map(() => ({ total: 0, errors: 0 }));

	for (const row of rows) {
		const rowTime = new Date(row.ts);
		const offsetMs = rowTime.getTime() - fromTime.getTime();
		const binIdx = Math.floor(offsetMs / binMs);
		if (binIdx >= 0 && binIdx < 60) {
			histogram[binIdx].total += 1;
			if (row.outcome === 'failure' || row.level === 'error' || row.level === 'critical') {
				histogram[binIdx].errors += 1;
			}
		}
	}

	const hasActiveTempPolicy = policy?.expires_at && new Date(policy.expires_at).getTime() > Date.now();

	const topPane = (
		<div className="flex flex-col h-full overflow-hidden">
			{/* Sparkline */}
			<div className="px-4 py-2 border-b border-hairline bg-surface">
				<div className="h-6 bg-surface-2 rounded p-1">
					<DensitySparkline bins={histogram} />
				</div>
				<p className="text-xs text-text-dim mt-1">
					Activity density ({rows.length} events)
				</p>
			</div>

			{/* Results table */}
			<div className="flex-1 overflow-hidden">
				{isLoading ? (
					<div className="p-6 text-center text-text-dim">Loading logs…</div>
				) : error ? (
					<div className="p-6 text-center text-danger">Failed to load logs</div>
				) : (
					<ActivityResultsTable
						rows={rows}
						onRowClick={setSelectedRow}
						selectedRowId={selectedRow?.id}
					/>
				)}
			</div>
		</div>
	);

	const bottomPane = <ActivityDetailPane row={selectedRow} />;

	return (
		<div className="flex flex-col gap-0 h-screen overflow-hidden">
			{/* Header */}
			<div className="flex items-baseline justify-between px-6 py-4 border-b border-hairline bg-surface">
				<h1 className="text-h1 text-text">Host Activity</h1>
				<div className="flex items-center gap-3">
					{hasActiveTempPolicy && policy?.expires_at && (
						<TempPolicyPill
							hostId={hostId}
							expiresAt={policy.expires_at}
							onDeleted={() => refetchPolicy()}
						/>
					)}
					<div className="font-mono text-[10px] uppercase tracking-wider text-text-dim">
						host {hostId.slice(0, 12)}
					</div>
				</div>
			</div>

			{/* Filter bar */}
			<ActivityFilterBar
				onChange={setFilters}
				onTogglePauseTail={setPauseTail}
				isPausedTail={pauseTail}
				categories={categories}
			/>

			{/* Split panes */}
			<div className="flex-1 overflow-hidden px-6 py-4">
				<ActivitySplit top={topPane} bottom={bottomPane} />
			</div>
		</div>
	);
}
