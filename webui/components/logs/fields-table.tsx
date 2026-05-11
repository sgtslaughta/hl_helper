'use client';

import { ChevronDown, ChevronRight, Copy } from 'lucide-react';
import { useState } from 'react';

export type Field = {
	key: string;
	value: string;
	type: 'string' | 'number' | 'boolean' | 'null' | 'array';
};

function flatten(obj: unknown, prefix = ''): Field[] {
	const out: Field[] = [];

	if (obj === null || obj === undefined) {
		return out;
	}

	if (typeof obj !== 'object') {
		out.push({
			key: prefix || '_',
			value: String(obj),
			type: typeof obj === 'number' ? 'number' : typeof obj === 'boolean' ? 'boolean' : 'string',
		});
		return out;
	}

	if (Array.isArray(obj)) {
		if (obj.length === 0) {
			out.push({ key: prefix, value: '[]', type: 'array' });
		} else if (obj.every(v => typeof v !== 'object' || v === null)) {
			out.push({ key: prefix, value: obj.map(String).join(', '), type: 'array' });
		} else {
			obj.forEach((v, i) => out.push(...flatten(v, `${prefix}[${i}]`)));
		}
		return out;
	}

	for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
		const nextKey = prefix ? `${prefix}.${k}` : k;
		if (v === null) {
			out.push({ key: nextKey, value: 'null', type: 'null' });
		} else if (typeof v === 'object') {
			out.push(...flatten(v, nextKey));
		} else {
			out.push({
				key: nextKey,
				value: String(v),
				type: typeof v === 'number' ? 'number' : typeof v === 'boolean' ? 'boolean' : 'string',
			});
		}
	}

	return out;
}

// Humanize a dot-path key for display. Keeps full path in title attr.
// Examples:
//   "details.command_id"   → "Command Id"
//   "labels.host_name"     → "Host Name"
//   "details.cpu_pct"      → "CPU Pct"
//   "ecs.version"          → "ECS Version"
//   "details.items[3].id"  → "Items › Id  (item 3)" — keep array index inline.
// Short tail-only label so the column stays scannable; full path in tooltip.
const ACRONYMS = new Set([
	'id',
	'cpu',
	'gpu',
	'ram',
	'os',
	'pid',
	'ip',
	'ipv4',
	'ipv6',
	'url',
	'uri',
	'ecs',
	'json',
	'ts',
	'rc',
	'tls',
	'ssh',
	'http',
	'https',
	'api',
	'ui',
	'db',
]);

export function humanizeKey(rawKey: string): string {
	// Use last meaningful segment so labels stay compact.
	const segs = rawKey.split('.');
	const tail = segs[segs.length - 1].replace(/\[\d+\]$/, '');
	const parts = tail.split(/[_-]/).filter(Boolean);
	return parts
		.map(p =>
			ACRONYMS.has(p.toLowerCase()) ? p.toUpperCase() : p.charAt(0).toUpperCase() + p.slice(1),
		)
		.join(' ');
}

// Path prefix shown above the label as a tiny breadcrumb when nested.
export function keyPrefix(rawKey: string): string {
	const segs = rawKey.split('.');
	if (segs.length <= 1) return '';
	return segs.slice(0, -1).join(' › ');
}

function getFieldTypeClass(type: Field['type']): string {
	switch (type) {
		case 'number':
			return 'text-accent';
		case 'boolean':
			return 'text-warn';
		case 'null':
			return 'text-text-dim italic';
		case 'array':
			return 'text-text';
		default:
			return 'text-text';
	}
}

function useFieldGroups(fields: Field[]): Map<string, Field[]> {
	const groups = new Map<string, Field[]>();

	for (const field of fields) {
		const topLevel = field.key.split('.')[0].split('[')[0];
		if (!groups.has(topLevel)) {
			groups.set(topLevel, []);
		}
		groups.get(topLevel)?.push(field);
	}

	return groups;
}

function FieldRow({
	field,
	onCopy,
}: {
	field: Field;
	onCopy: (key: string, value: string) => void;
}) {
	const [wrap, setWrap] = useState(false);
	const isLong = field.value.length > 80;

	const prefix = keyPrefix(field.key);
	const label = humanizeKey(field.key);

	return (
		<tr
			className="hover:bg-surface/50 align-top group focus-within:bg-surface/50"
			tabIndex={0}
			onKeyDown={e => {
				if ((e.key === 'c' || e.key === 'C') && (e.metaKey || e.ctrlKey)) {
					// allow native copy of selection; no-op
					return;
				}
				if (e.key === 'Enter') {
					e.preventDefault();
					onCopy(field.key, field.value);
				}
			}}
		>
			<td className="px-2 py-1 whitespace-nowrap select-text" title={field.key}>
				{prefix && (
					<div className="text-[10px] uppercase tracking-wider text-text-dim/70 font-mono leading-tight">
						{prefix}
					</div>
				)}
				<div className="text-text text-xs font-sans leading-tight">{label}</div>
			</td>
			<td className={`px-2 py-1 font-mono text-xs ${getFieldTypeClass(field.type)}`}>
				<div className="flex items-start gap-2">
					<span
						className={`select-text ${wrap ? 'break-all whitespace-normal' : 'whitespace-nowrap'}`}
						title={field.value}
					>
						{field.value}
					</span>
					{isLong && (
						<button
							type="button"
							onClick={() => setWrap(w => !w)}
							className="flex-shrink-0 text-text-dim hover:text-text transition-colors opacity-0 group-hover:opacity-100"
							title={wrap ? 'No-wrap' : 'Wrap'}
						>
							{wrap ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
						</button>
					)}
					<button
						type="button"
						onClick={() => onCopy(field.key, field.value)}
						className="flex-shrink-0 text-text-dim hover:text-accent transition-colors opacity-0 group-hover:opacity-100"
						title={`Copy ${field.key}=${field.value}`}
						aria-label="Copy field"
					>
						<Copy size={12} />
					</button>
				</div>
			</td>
		</tr>
	);
}

function Group({
	groupName,
	groupFields,
	isExpanded,
	showHeader,
	showDivider,
	onToggle,
	onCopy,
}: {
	groupName: string;
	groupFields: Field[];
	isExpanded: boolean;
	showHeader: boolean;
	showDivider: boolean;
	onToggle: () => void;
	onCopy: (key: string, value: string) => void;
}) {
	const visible = showHeader ? isExpanded : true;
	return (
		<>
			{showDivider && (
				<tr>
					<td colSpan={2} className="border-t border-hairline p-0" />
				</tr>
			)}
			{showHeader && (
				<tr>
					<td colSpan={2} className="px-2 py-1">
						<button
							type="button"
							onClick={onToggle}
							className="flex items-center gap-2 text-[10px] uppercase tracking-wider font-semibold text-text-dim hover:text-text transition-colors"
						>
							{isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
							{groupName}
						</button>
					</td>
				</tr>
			)}
			{visible && groupFields.map(f => <FieldRow key={f.key} field={f} onCopy={onCopy} />)}
		</>
	);
}

interface FieldsTableProps {
	obj: unknown;
	errorObj?: { code?: string; message?: string; stack_trace?: string } | null;
}

export function FieldsTable({ obj, errorObj }: FieldsTableProps) {
	const fields = flatten(obj);
	const groups = useFieldGroups(fields);
	const [copiedKey, setCopiedKey] = useState<string | null>(null);
	const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set(['_root']));

	const handleCopy = (key: string, value: string) => {
		const text = `${key}=${value}`;
		navigator.clipboard.writeText(text);
		setCopiedKey(key);
		setTimeout(() => setCopiedKey(null), 2000);
	};

	const toggleGroup = (group: string) => {
		const newSet = new Set(expandedGroups);
		if (newSet.has(group)) {
			newSet.delete(group);
		} else {
			newSet.add(group);
		}
		setExpandedGroups(newSet);
	};

	return (
		<div className="space-y-3 overflow-x-auto">
			{/* Error box if present */}
			{errorObj && (
				<div className="rounded bg-red-500/10 border border-red-500/20 p-3 mb-3">
					<div className="text-xs font-semibold text-red-600 dark:text-red-400 mb-1">Error</div>
					{errorObj.code && (
						<div className="text-xs text-red-700 dark:text-red-300 font-mono mb-1">
							Code: {errorObj.code}
						</div>
					)}
					{errorObj.message && (
						<div className="text-xs text-red-700 dark:text-red-300 break-all">
							{errorObj.message}
						</div>
					)}
					{errorObj.stack_trace && (
						<details className="mt-2">
							<summary className="text-xs cursor-pointer text-red-600 dark:text-red-400 hover:underline">
								Stack trace
							</summary>
							<pre className="text-xs text-red-700 dark:text-red-300 mt-1 overflow-x-auto whitespace-pre-wrap break-words font-mono">
								{errorObj.stack_trace}
							</pre>
						</details>
					)}
				</div>
			)}

			{/* Single table for all groups so columns align + outer wrapper
			    provides horizontal scroll uniformly across every row. */}
			<table className="w-auto text-xs leading-relaxed border-collapse">
				<tbody>
					{Array.from(groups.entries()).map(([groupName, groupFields], idx) => {
						const isExpanded = expandedGroups.has(groupName);
						const hasMultipleFields = groupFields.length > 1;
						const showHeader = hasMultipleFields && groupName !== '_root';

						return (
							<Group
								key={groupName}
								groupName={groupName}
								groupFields={groupFields}
								isExpanded={isExpanded}
								showHeader={showHeader}
								showDivider={idx > 0}
								onToggle={() => toggleGroup(groupName)}
								onCopy={handleCopy}
							/>
						);
					})}
				</tbody>
			</table>

			{/* Copy feedback */}
			{copiedKey && (
				<div className="text-xs text-accent px-2 py-1 rounded bg-surface animate-pulse">
					{copiedKey} copied!
				</div>
			)}
		</div>
	);
}
