'use client';

import type { LogRow } from '@/lib/api/logs';
import { Copy, X } from 'lucide-react';
import { useState } from 'react';
import { FieldsTable } from './fields-table';

interface DetailDrawerProps {
	row: LogRow | null;
	onClose: () => void;
}

// Simple JSON syntax highlighter
function HighlightedJSON({ data }: { data: unknown }) {
	const json = JSON.stringify(data, null, 2);
	const lines = json.split('\n');

	const getTokens = (line: string): Array<{ type: string; value: string; idx: number }> => {
		const regex = /("(?:[^"\\]|\\.)*")|(:)|([0-9.-]+)|(\btrue\b|\bfalse\b|\bnull\b)|([{}[\],])/g;
		const tokens: Array<{ type: string; value: string; idx: number }> = [];
		const matches = Array.from(line.matchAll(regex));
		for (const match of matches) {
			tokens.push({
				type: match[1]
					? 'string'
					: match[2]
						? 'colon'
						: match[3]
							? 'number'
							: match[4]
								? 'bool'
								: 'bracket',
				value: match[0],
				idx: match.index,
			});
		}
		return tokens;
	};

	const highlightLine = (line: string): React.ReactNode[] => {
		const parts: React.ReactNode[] = [];
		const tokens = getTokens(line);

		tokens.forEach((token, i) => {
			if (i === 0 && token.idx > 0) {
				parts.push(
					<span key={`pre-${token.idx}`} className="text-text-dim">
						{line.slice(0, token.idx)}
					</span>,
				);
			} else if (i > 0 && tokens[i - 1].idx + tokens[i - 1].value.length < token.idx) {
				const prev = tokens[i - 1];
				const gap = line.slice(prev.idx + prev.value.length, token.idx);
				parts.push(
					<span key={`gap-${token.idx}`} className="text-text-dim">
						{gap}
					</span>,
				);
			}

			const className =
				token.type === 'string'
					? 'text-accent'
					: token.type === 'colon'
						? 'text-text'
						: token.type === 'number'
							? 'text-ok'
							: token.type === 'bool'
								? 'text-warn'
								: 'text-text-dim';

			parts.push(
				<span key={`tok-${token.idx}`} className={className}>
					{token.value}
				</span>,
			);
		});

		if (tokens.length > 0) {
			const last = tokens[tokens.length - 1];
			if (last.idx + last.value.length < line.length) {
				parts.push(
					<span key={`end-${last.idx}`} className="text-text-dim">
						{line.slice(last.idx + last.value.length)}
					</span>,
				);
			}
		} else {
			parts.push(
				<span key="whole" className="text-text-dim">
					{line}
				</span>,
			);
		}

		return parts;
	};

	return (
		<div className="text-xs font-mono whitespace-pre-wrap break-words">
			{lines.map((line) => {
				const lineKey = `${line.slice(0, 20)}-${line.length}`;
				return (
					<div key={lineKey} className="leading-relaxed">
						{highlightLine(line)}
					</div>
				);
			})}
		</div>
	);
}

export function DetailDrawer({ row, onClose }: DetailDrawerProps) {
	const [activeTab, setActiveTab] = useState<'overview' | 'json'>('overview');

	if (!row) return null;

	const handleCopyJSON = () => {
		navigator.clipboard.writeText(JSON.stringify(row, null, 2));
	};

	return (
		<div className="fixed inset-y-0 right-0 w-96 bg-surface border-l border-hairline flex flex-col z-40 shadow-xl">
			{/* Header */}
			<div className="flex items-center justify-between border-b border-hairline px-4 py-3 bg-surface-2">
				<h2 className="text-sm font-semibold text-text">Log Details</h2>
				<button
					onClick={onClose}
					className="p-1 hover:bg-surface rounded transition-colors"
					title="Close (Esc)"
					type="button"
				>
					<X size={16} className="text-text-dim" />
				</button>
			</div>

			{/* Tabs */}
			<div className="flex gap-0 border-b border-hairline bg-surface-2 px-2">
				<button
					onClick={() => setActiveTab('overview')}
					className={`px-3 py-2 text-xs font-semibold border-b-2 transition-colors ${
						activeTab === 'overview'
							? 'border-accent text-text'
							: 'border-transparent text-text-dim hover:text-text'
					}`}
					type="button"
				>
					OVERVIEW
				</button>
				<button
					onClick={() => setActiveTab('json')}
					className={`px-3 py-2 text-xs font-semibold border-b-2 transition-colors ${
						activeTab === 'json'
							? 'border-accent text-text'
							: 'border-transparent text-text-dim hover:text-text'
					}`}
					type="button"
				>
					JSON
				</button>
			</div>

			{/* Content */}
			<div className="flex-1 overflow-auto p-4 bg-surface-2">
				{activeTab === 'overview' && (
					<div className="rounded bg-surface border border-hairline p-3">
						<FieldsTable obj={row} errorObj={row.error} />
					</div>
				)}
				{activeTab === 'json' && (
					<div className="rounded bg-surface border border-hairline p-3">
						<HighlightedJSON data={row} />
					</div>
				)}
			</div>

			{/* Footer */}
			<div className="border-t border-hairline px-4 py-3 flex gap-2 bg-surface-2">
				{activeTab === 'json' && (
					<button
						onClick={handleCopyJSON}
						className="flex items-center gap-2 px-3 py-1.5 text-xs rounded border border-hairline hover:bg-surface transition-colors text-text-dim hover:text-text"
						type="button"
					>
						<Copy size={14} />
						Copy JSON
					</button>
				)}
			</div>
		</div>
	);
}
