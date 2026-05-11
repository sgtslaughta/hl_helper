'use client';

import type { LogRow } from '@/lib/api/logs';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { useState } from 'react';

interface ActivityResultsTableProps {
	rows: LogRow[];
	onRowClick: (row: LogRow) => void;
	selectedRowId?: number;
	pageSize?: number;
}

type SortColumn = 'ts' | 'level' | 'action' | 'outcome' | 'message' | 'duration_ns';
type SortDirection = 'asc' | 'desc';

export function ActivityResultsTable({
	rows,
	onRowClick,
	selectedRowId,
	pageSize = 50,
}: ActivityResultsTableProps) {
	const [currentPage, setCurrentPage] = useState(0);
	const [sortColumn, setSortColumn] = useState<SortColumn>('ts');
	const [sortDir, setSortDir] = useState<SortDirection>('desc');

	const handleSort = (col: SortColumn) => {
		if (sortColumn === col) {
			setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
		} else {
			setSortColumn(col);
			setSortDir('desc');
		}
		setCurrentPage(0);
	};

	const levelOrder = { debug: 0, info: 1, warn: 2, error: 3, critical: 4 };

	const sortedRows = [...rows].sort((a, b) => {
		let aVal: string | number = String(a[sortColumn] || '');
		let bVal: string | number = String(b[sortColumn] || '');

		if (sortColumn === 'level') {
			const aLevel = a[sortColumn] as unknown as keyof typeof levelOrder;
			const bLevel = b[sortColumn] as unknown as keyof typeof levelOrder;
			aVal = levelOrder[aLevel] || 0;
			bVal = levelOrder[bLevel] || 0;
		} else if (sortColumn === 'duration_ns') {
			aVal = (a.duration_ns || 0) as number;
			bVal = (b.duration_ns || 0) as number;
		} else {
			aVal = String(aVal).toLowerCase();
			bVal = String(bVal).toLowerCase();
		}

		if (aVal < bVal) return sortDir === 'asc' ? -1 : 1;
		if (aVal > bVal) return sortDir === 'asc' ? 1 : -1;
		return 0;
	});

	const visibleRows = sortedRows.slice(currentPage * pageSize, (currentPage + 1) * pageSize);
	const maxPages = Math.ceil(sortedRows.length / pageSize);

	const getLevelColor = (level: string) => {
		switch (level) {
			case 'error':
			case 'critical':
				return 'text-danger';
			case 'warn':
				return 'text-warn';
			default:
				return 'text-text';
		}
	};

	const getOutcomeGlyph = (outcome?: string) => {
		switch (outcome) {
			case 'success':
				return '✓';
			case 'failure':
				return '✗';
			default:
				return '—';
		}
	};

	const formatDuration = (ns?: number) => {
		if (!ns) return '—';
		const ms = ns / 1_000_000;
		if (ms < 1000) return `${Math.round(ms)}ms`;
		return `${(ms / 1000).toFixed(1)}s`;
	};

	const SortHeader = ({ col, label }: { col: SortColumn; label: string }) => (
		<th className="px-3 py-2 text-left text-text-dim font-semibold text-xs">
			<button
				type="button"
				onClick={() => handleSort(col)}
				onKeyDown={e => {
					if (e.key === 'Enter' || e.key === ' ') {
						e.preventDefault();
						handleSort(col);
					}
				}}
				className="flex items-center gap-1 cursor-pointer hover:text-text transition-colors w-full py-1 px-1 rounded"
			>
				{label}
				{sortColumn === col &&
					(sortDir === 'asc' ? <ChevronUp size={14} /> : <ChevronDown size={14} />)}
			</button>
		</th>
	);

	if (sortedRows.length === 0) {
		return (
			<div className="flex-1 flex items-center justify-center text-text-dim">
				<div className="text-center">
					<div className="text-sm mb-1">No logs found</div>
					<div className="text-xs">Adjust filters and try again</div>
				</div>
			</div>
		);
	}

	return (
		<div className="flex flex-col h-full overflow-hidden">
			<div className="border-b border-hairline overflow-hidden flex flex-col flex-1">
				<table className="w-full text-xs font-mono">
					<thead className="sticky top-0 bg-surface-alt">
						<tr className="border-b border-hairline">
							<SortHeader col="ts" label="Timestamp" />
							<SortHeader col="level" label="Level" />
							<SortHeader col="action" label="Action" />
							<SortHeader col="outcome" label="Outcome" />
							<SortHeader col="message" label="Message" />
							<SortHeader col="duration_ns" label="Duration" />
						</tr>
					</thead>
					<tbody className="overflow-y-auto">
						{visibleRows.map(row => {
							const isSelected = row.id === selectedRowId;
							return (
								<tr
									key={`${row.id}-${row.seq}`}
									onClick={() => onRowClick(row)}
									className={`border-b border-hairline cursor-pointer transition-colors ${
										isSelected
											? 'bg-accent/10 border-l-2 border-l-accent'
											: 'hover:bg-surface-alt'
									}`}
								>
									<td
										className="px-3 py-2 text-text-dim truncate w-32"
										title={row.ts}
									>
										{new Date(row.ts).toLocaleTimeString()}
									</td>
									<td className={`px-3 py-2 font-semibold w-16 ${getLevelColor(row.level)}`}>
										{row.level.toUpperCase()}
									</td>
									<td className="px-3 py-2 text-text truncate flex-1" title={row.action}>
										{row.action}
									</td>
									<td className="px-3 py-2 text-center w-12">
										{getOutcomeGlyph(row.outcome)}
									</td>
									<td
										className="px-3 py-2 text-text-dim truncate flex-1"
										title={row.message || ''}
									>
										{row.message || ''}
									</td>
									<td className="px-3 py-2 text-text-dim w-16 text-right">
										{formatDuration(row.duration_ns)}
									</td>
								</tr>
							);
						})}
					</tbody>
				</table>
			</div>

			{/* Pagination */}
			{maxPages > 1 && (
				<div className="flex items-center justify-between text-xs text-text-dim px-3 py-2 bg-surface border-t border-hairline">
					<div>
						{sortedRows.length === 0
							? 'No rows'
							: `${currentPage * pageSize + 1}–${Math.min((currentPage + 1) * pageSize, sortedRows.length)} of ${sortedRows.length}`}
					</div>
					<div className="flex gap-1">
						<button
							type="button"
							onClick={() => setCurrentPage(Math.max(0, currentPage - 1))}
							disabled={currentPage === 0}
							className="px-2 py-1 rounded border border-hairline hover:bg-surface-2 disabled:opacity-50 transition-colors"
						>
							← Prev
						</button>
						<span className="px-2 py-1">
							{currentPage + 1} / {maxPages}
						</span>
						<button
							type="button"
							onClick={() => setCurrentPage(Math.min(maxPages - 1, currentPage + 1))}
							disabled={currentPage >= maxPages - 1}
							className="px-2 py-1 rounded border border-hairline hover:bg-surface-2 disabled:opacity-50 transition-colors"
						>
							Next →
						</button>
					</div>
				</div>
			)}
		</div>
	);
}
