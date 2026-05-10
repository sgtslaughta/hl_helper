'use client';

import { type LogRow } from '@/lib/api/logs';
import { useState } from 'react';

interface ResultsTableProps {
	rows: LogRow[];
	onRowClick?: (row: LogRow) => void;
	pageSize?: number;
}

export function ResultsTable({ rows, onRowClick, pageSize = 50 }: ResultsTableProps) {
	const [currentPage, setCurrentPage] = useState(0);

	const visibleRows = rows.slice(currentPage * pageSize, (currentPage + 1) * pageSize);
	const maxPages = Math.ceil(rows.length / pageSize);

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

	return (
		<div className="flex flex-col gap-2">
			<div className="border border-hairline rounded overflow-hidden">
				<table className="w-full text-xs font-mono">
					<thead>
						<tr className="bg-surface-alt border-b border-hairline">
							<th className="px-3 py-2 text-left text-text-dim font-semibold w-32">Timestamp</th>
							<th className="px-3 py-2 text-left text-text-dim font-semibold w-20">Host</th>
							<th className="px-3 py-2 text-left text-text-dim font-semibold w-16">Level</th>
							<th className="px-3 py-2 text-left text-text-dim font-semibold flex-1">Action</th>
							<th className="px-3 py-2 text-left text-text-dim font-semibold w-12">Outcome</th>
							<th className="px-3 py-2 text-left text-text-dim font-semibold flex-1">Message</th>
						</tr>
					</thead>
					<tbody>
						{visibleRows.map(row => (
							<tr
								key={`${row.id}-${row.seq}`}
								onClick={() => onRowClick?.(row)}
								className="border-b border-hairline hover:bg-surface-alt cursor-pointer transition-colors"
							>
								<td className="px-3 py-2 text-text-dim truncate" title={row.ts}>
									{new Date(row.ts).toLocaleTimeString()}
								</td>
								<td className="px-3 py-2 text-text truncate" title={row.host_id}>
									{row.host_id}
								</td>
								<td className={`px-3 py-2 font-semibold ${getLevelColor(row.level)}`}>
									{row.level.toUpperCase()}
								</td>
								<td className="px-3 py-2 text-text truncate" title={row.action}>
									{row.action}
								</td>
								<td className="px-3 py-2 text-center">{getOutcomeGlyph(row.outcome)}</td>
								<td className="px-3 py-2 text-text-dim truncate" title={row.message || ''}>
									{row.message || ''}
								</td>
							</tr>
						))}
					</tbody>
				</table>
			</div>

			{maxPages > 1 && (
				<div className="flex items-center justify-between text-xs text-text-dim px-2 py-1">
					<div>
						{rows.length === 0 ? 'No rows' : `${currentPage * pageSize + 1}–${Math.min((currentPage + 1) * pageSize, rows.length)} of ${rows.length}`}
					</div>
					<div className="flex gap-1">
						<button
							onClick={() => setCurrentPage(Math.max(0, currentPage - 1))}
							disabled={currentPage === 0}
							className="px-2 py-1 rounded border border-hairline hover:bg-surface disabled:opacity-50"
						>
							← Prev
						</button>
						<span className="px-2 py-1">{currentPage + 1} / {maxPages}</span>
						<button
							onClick={() => setCurrentPage(Math.min(maxPages - 1, currentPage + 1))}
							disabled={currentPage >= maxPages - 1}
							className="px-2 py-1 rounded border border-hairline hover:bg-surface disabled:opacity-50"
						>
							Next →
						</button>
					</div>
				</div>
			)}
		</div>
	);
}
