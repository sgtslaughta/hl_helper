'use client';

import type { LogRow as LogRowData } from '@/lib/api/logs';
import { formatDuration, glyphForOutcome, humanize } from '@/lib/event-humanizer';
import { relTime } from '@/lib/time';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { useState } from 'react';

const LEVEL_COLORS: Record<string, string> = {
	debug: 'bg-blue-500/10 text-blue-700 dark:text-blue-400',
	info: 'bg-slate-500/10 text-slate-700 dark:text-slate-400',
	warn: 'bg-amber-500/10 text-amber-700 dark:text-amber-600',
	error: 'bg-red-500/10 text-red-700 dark:text-red-500',
	critical: 'bg-red-600/10 text-red-800 dark:text-red-400',
};

export function LogRow({ row }: { row: LogRowData }) {
	const [expanded, setExpanded] = useState(false);

	const levelLabel = row.level.toUpperCase();
	const levelColor = LEVEL_COLORS[row.level] || 'bg-slate-500/10 text-slate-700';
	const glyph = glyphForOutcome(row.outcome);
	const durationStr = formatDuration(row.duration_ns);
	const action = humanize(row);

	const absTime = new Date(row.ts).toISOString();
	const relTimeStr = relTime(row.ts);

	return (
		<>
			<div className="flex items-center gap-2 px-4 py-2 border-b border-hairline hover:bg-surface-2 transition-colors">
				{/* Expand button */}
				<button
					data-testid="expand-button"
					onClick={() => setExpanded(!expanded)}
					className="flex-shrink-0 text-text-dim hover:text-text"
					type="button"
					aria-label="Toggle details"
				>
					{expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
				</button>

				{/* Outcome glyph */}
				<div className="flex-shrink-0 w-5 text-center font-semibold text-sm">{glyph}</div>

				{/* Level badge */}
				<span className={`flex-shrink-0 px-2 py-1 rounded text-xs font-mono font-semibold ${levelColor}`}>
					{levelLabel}
				</span>

				{/* Action */}
				<span className="flex-1 text-sm text-text truncate">{action}</span>

				{/* Duration */}
				{durationStr && <span className="flex-shrink-0 text-xs text-text-dim font-mono">{durationStr}</span>}

				{/* Timestamp */}
				<span
					title={absTime}
					className="flex-shrink-0 text-xs text-text-dim font-mono hover:text-text cursor-help"
				>
					{relTimeStr}
				</span>
			</div>

			{/* Expanded details */}
			{expanded && (
				<div className="px-4 py-3 bg-surface-2 border-b border-hairline">
					<div className="rounded bg-surface border border-hairline p-3 font-mono text-xs text-text-dim overflow-x-auto max-h-48 overflow-y-auto">
						<pre>{JSON.stringify(row, null, 2)}</pre>
					</div>
				</div>
			)}
		</>
	);
}
