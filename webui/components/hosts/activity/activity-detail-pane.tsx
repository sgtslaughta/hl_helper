'use client';

import type { LogRow } from '@/lib/api/logs';
import { formatDuration, glyphForOutcome, humanize } from '@/lib/event-humanizer';
import { relTime } from '@/lib/time';
import { Copy } from 'lucide-react';
import { useState } from 'react';
import { FieldsTable } from '@/components/logs/fields-table';

interface ActivityDetailPaneProps {
	row: LogRow | null;
}

export function ActivityDetailPane({ row }: ActivityDetailPaneProps) {
	const [copied, setCopied] = useState<string | null>(null);

	if (!row) {
		return (
			<div className="flex-1 flex items-center justify-center text-text-dim">
				<div className="text-center">
					<div className="text-sm">Select a row to inspect details</div>
				</div>
			</div>
		);
	}

	const flash = (label: string) => {
		setCopied(label);
		setTimeout(() => setCopied(null), 1500);
	};

	const handleCopyFields = async () => {
		const lines: string[] = [];
		const walk = (obj: unknown, prefix = '') => {
			if (obj === null || obj === undefined) return;
			if (typeof obj !== 'object') {
				lines.push(`${prefix || '_'}=${String(obj)}`);
				return;
			}
			if (Array.isArray(obj)) {
				if (obj.every(v => typeof v !== 'object' || v === null)) {
					lines.push(`${prefix}=${obj.map(String).join(',')}`);
				} else {
					obj.forEach((v, i) => walk(v, `${prefix}[${i}]`));
				}
				return;
			}
			for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
				const nk = prefix ? `${prefix}.${k}` : k;
				if (v !== null && typeof v === 'object') walk(v, nk);
				else lines.push(`${nk}=${v === null ? 'null' : String(v)}`);
			}
		};
		walk(row);
		await navigator.clipboard.writeText(lines.join('\n'));
		flash('Fields copied');
	};

	const handleCopyJSON = async () => {
		await navigator.clipboard.writeText(JSON.stringify(row, null, 2));
		flash('JSON copied');
	};

	const glyph = glyphForOutcome(row.outcome);
	const action = humanize(row);
	const duration = formatDuration(row.duration_ns);
	const relTimeStr = relTime(row.ts);
	const absTime = new Date(row.ts).toISOString();

	const LEVEL_COLORS: Record<string, string> = {
		debug: 'bg-blue-500/10 text-blue-700 dark:text-blue-400',
		info: 'bg-slate-500/10 text-slate-700 dark:text-slate-400',
		warn: 'bg-amber-500/10 text-amber-700 dark:text-amber-600',
		error: 'bg-red-500/10 text-red-700 dark:text-red-500',
		critical: 'bg-red-600/10 text-red-800 dark:text-red-400',
	};

	const levelColor = LEVEL_COLORS[row.level] || 'bg-slate-500/10 text-slate-700';

	return (
		<div className="flex flex-col h-full overflow-hidden">
			{/* Header */}
			<div className="flex items-center gap-2 px-4 py-3 border-b border-hairline bg-surface-alt flex-shrink-0">
				<span className="text-sm font-semibold">{glyph}</span>
				<span className="text-sm text-text truncate flex-1">{action}</span>
				{duration && <span className="text-xs text-text-dim font-mono">{duration}</span>}
				<span
					title={absTime}
					className="text-xs text-text-dim font-mono"
				>
					{relTimeStr}
				</span>
				<span
					className={`px-2 py-1 rounded text-xs font-mono font-semibold ${levelColor}`}
				>
					{row.level.toUpperCase()}
				</span>
				{row.agent_session_id && (
					<div className="px-2 py-1 rounded text-xs bg-surface border border-hairline text-text-dim font-mono truncate max-w-xs">
						{row.agent_session_id.slice(0, 12)}
					</div>
				)}
			</div>

			{/* Fields table (scrollable) */}
			<div className="flex-1 overflow-auto p-4 bg-surface-2">
				<div className="rounded bg-surface border border-hairline p-3">
					<FieldsTable obj={row} errorObj={row.error} />
				</div>
			</div>

			{/* Footer with copy buttons */}
			<div className="border-t border-hairline px-4 py-2 flex items-center gap-2 bg-surface-alt flex-shrink-0">
				<button
					onClick={handleCopyFields}
					className="flex items-center gap-2 px-3 py-1.5 text-xs rounded border border-hairline hover:bg-surface transition-colors text-text-dim hover:text-text"
					type="button"
					title="Copy all fields as key=value lines"
				>
					<Copy size={14} />
					Copy fields
				</button>
				<button
					onClick={handleCopyJSON}
					className="flex items-center gap-2 px-3 py-1.5 text-xs rounded border border-hairline hover:bg-surface transition-colors text-text-dim hover:text-text"
					type="button"
					title="Copy raw JSON"
				>
					<Copy size={14} />
					Copy JSON
				</button>
				{copied && (
					<span className="text-xs text-accent animate-pulse ml-auto" aria-live="polite">
						{copied}
					</span>
				)}
			</div>
		</div>
	);
}
