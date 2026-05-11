'use client';

import type { LogRow } from '@/lib/api/logs';
import { Copy, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { FieldsTable } from './fields-table';

interface DetailDrawerProps {
	row: LogRow | null;
	onClose: () => void;
}

const WIDTH_KEY = 'logs.drawer.width';
const MIN_WIDTH = 320;
const MAX_WIDTH = 1400;
const DEFAULT_WIDTH = 480;

function flattenKV(row: LogRow): string {
	const out: string[] = [];
	const walk = (obj: unknown, prefix = '') => {
		if (obj === null || obj === undefined) return;
		if (typeof obj !== 'object') {
			out.push(`${prefix || '_'}=${String(obj)}`);
			return;
		}
		if (Array.isArray(obj)) {
			if (obj.every(v => typeof v !== 'object' || v === null)) {
				out.push(`${prefix}=${obj.map(String).join(',')}`);
			} else {
				obj.forEach((v, i) => walk(v, `${prefix}[${i}]`));
			}
			return;
		}
		for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
			const nk = prefix ? `${prefix}.${k}` : k;
			if (v !== null && typeof v === 'object') walk(v, nk);
			else out.push(`${nk}=${v === null ? 'null' : String(v)}`);
		}
	};
	walk(row);
	return out.join('\n');
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
		<pre className="text-xs font-mono leading-relaxed whitespace-pre overflow-x-auto">
			{lines.map(line => {
				const lineKey = `${line.slice(0, 20)}-${line.length}`;
				return <div key={lineKey}>{highlightLine(line)}</div>;
			})}
		</pre>
	);
}

export function DetailDrawer({ row, onClose }: DetailDrawerProps) {
	const [activeTab, setActiveTab] = useState<'overview' | 'json'>('overview');
	const [width, setWidth] = useState<number>(DEFAULT_WIDTH);
	const [copied, setCopied] = useState<string | null>(null);
	const draggingRef = useRef(false);

	// Load persisted width on mount.
	useEffect(() => {
		const stored = typeof window !== 'undefined' ? localStorage.getItem(WIDTH_KEY) : null;
		const n = stored ? Number.parseInt(stored, 10) : Number.NaN;
		if (Number.isFinite(n)) setWidth(Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, n)));
	}, []);

	// Drag-resize handlers (attached on demand to avoid global listeners).
	useEffect(() => {
		const onMove = (e: MouseEvent) => {
			if (!draggingRef.current) return;
			const next = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, window.innerWidth - e.clientX));
			setWidth(next);
		};
		const onUp = () => {
			if (!draggingRef.current) return;
			draggingRef.current = false;
			document.body.style.cursor = '';
			document.body.style.userSelect = '';
			try {
				localStorage.setItem(WIDTH_KEY, String(width));
			} catch {}
		};
		document.addEventListener('mousemove', onMove);
		document.addEventListener('mouseup', onUp);
		return () => {
			document.removeEventListener('mousemove', onMove);
			document.removeEventListener('mouseup', onUp);
		};
	}, [width]);

	const startDrag = (e: React.MouseEvent) => {
		draggingRef.current = true;
		document.body.style.cursor = 'col-resize';
		document.body.style.userSelect = 'none';
		e.preventDefault();
	};

	if (!row) return null;

	const flash = (label: string) => {
		setCopied(label);
		setTimeout(() => setCopied(null), 1500);
	};

	const handleCopyJSON = async () => {
		await navigator.clipboard.writeText(JSON.stringify(row, null, 2));
		flash('JSON copied');
	};

	const handleCopyKV = async () => {
		await navigator.clipboard.writeText(flattenKV(row));
		flash('key=value lines copied');
	};

	return (
		<div
			className="fixed inset-y-0 right-0 bg-surface border-l border-hairline flex flex-col z-40 shadow-xl"
			style={{ width: `${width}px` }}
		>
			{/* Drag handle — left edge */}
			<button
				type="button"
				aria-label="Resize drawer"
				onMouseDown={startDrag}
				className="absolute left-0 top-0 bottom-0 w-1 hover:w-1.5 cursor-col-resize bg-transparent hover:bg-accent/40 transition-all"
				style={{ zIndex: 50 }}
			/>
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
			<div className="border-t border-hairline px-4 py-2 flex items-center gap-2 bg-surface-2">
				<button
					onClick={handleCopyKV}
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
