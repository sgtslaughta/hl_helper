'use client';

import { Copy, ChevronDown, ChevronRight } from 'lucide-react';
import { Fragment, useState } from 'react';

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
		} else if (obj.every((v) => typeof v !== 'object' || v === null)) {
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
	const [expanded, setExpanded] = useState(false);
	const isLong = field.value.length > 60;

	return (
		<Fragment key={field.key}>
			<button
				className="text-text-dim truncate cursor-pointer hover:bg-surface transition-colors px-2 py-1 rounded text-left text-xs font-mono text-left"
				title={field.key}
				onClick={() => onCopy(field.key, field.value)}
				type="button"
			>
				{field.key}
			</button>
			<div className="flex items-start gap-2 px-2 py-1">
				<button
					type="button"
					onClick={() => onCopy(field.key, field.value)}
					onKeyDown={(e) => {
						if (e.key === 'Enter' || e.key === ' ') {
							onCopy(field.key, field.value);
						}
					}}
					className={`flex-1 break-all ${getFieldTypeClass(field.type)} ${isLong && !expanded ? 'line-clamp-2' : ''} cursor-pointer hover:bg-surface/50 px-1 rounded transition-colors text-xs text-left`}
				>
					{field.value}
				</button>
				{isLong && (
					<button
						type="button"
						onClick={() => setExpanded(!expanded)}
						className="flex-shrink-0 text-text-dim hover:text-text transition-colors"
						title={expanded ? 'Collapse' : 'Expand'}
					>
						{expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
					</button>
				)}
			</div>
		</Fragment>
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
		<div className="space-y-3">
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
						<div className="text-xs text-red-700 dark:text-red-300 break-all">{errorObj.message}</div>
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

			{/* Fields grouped by top-level prefix */}
			{Array.from(groups.entries()).map(([groupName, groupFields]) => {
				const isExpanded = expandedGroups.has(groupName);
				const hasMultipleFields = groupFields.length > 1;

				return (
					<div key={groupName}>
						{/* Group header */}
						{hasMultipleFields && groupName !== '_root' && (
							<button
								type="button"
								onClick={() => toggleGroup(groupName)}
								className="flex items-center gap-2 text-xs font-semibold text-text-dim mb-1 hover:text-text transition-colors px-2"
							>
								{isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
								{groupName}
							</button>
						)}

						{/* Fields grid */}
						{(hasMultipleFields ? isExpanded : true) && (
							<div className="font-mono text-xs leading-relaxed">
								<div className="grid grid-cols-[minmax(140px,260px)_1fr] gap-x-3 gap-y-1 ml-2">
									{groupFields.map((f) => (
										<FieldRow key={f.key} field={f} onCopy={handleCopy} />
									))}
								</div>
							</div>
						)}

						{/* Hairline divider between groups */}
						{groupName !== Array.from(groups.keys()).pop() && (
							<div className="border-t border-hairline my-2" />
						)}
					</div>
				);
			})}

			{/* Copy feedback */}
			{copiedKey && (
				<div className="text-xs text-accent px-2 py-1 rounded bg-surface animate-pulse">{copiedKey} copied!</div>
			)}
		</div>
	);
}
