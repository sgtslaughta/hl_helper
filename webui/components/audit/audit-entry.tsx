'use client';

import { formatRelative } from 'date-fns';
import { ChevronDown } from 'lucide-react';
import { useState } from 'react';

interface AuditEntryProps {
	sequence: number;
	timestamp: string;
	actor: string;
	action: string;
	subject: string | null;
	payload: Record<string, unknown>;
}

export function AuditEntry({
	sequence,
	timestamp,
	actor,
	action,
	subject,
	payload,
}: AuditEntryProps) {
	const [expanded, setExpanded] = useState(false);
	const date = new Date(timestamp);

	return (
		<div className="border-b border-hairline py-3">
			<button
				type="button"
				onClick={() => setExpanded(!expanded)}
				className="flex w-full items-center justify-between rounded px-3 py-2 hover:bg-surface-2"
			>
				<div className="flex flex-1 items-center gap-4 text-small">
					<span className="font-mono text-text-dim">#{sequence}</span>
					<span className="font-semibold text-text">{action}</span>
					<span className="text-text-dim">{actor}</span>
					{subject && <span className="text-accent">{subject}</span>}
					<span className="text-text-dim">{formatRelative(date, new Date())}</span>
				</div>
				<ChevronDown className={`h-4 w-4 transition-transform ${expanded ? 'rotate-180' : ''}`} />
			</button>
			{expanded && (
				<div className="ml-4 mt-2 rounded bg-surface px-3 py-2">
					<pre className="overflow-x-auto font-mono text-tiny text-text-dim">
						{JSON.stringify(payload, null, 2)}
					</pre>
				</div>
			)}
		</div>
	);
}
