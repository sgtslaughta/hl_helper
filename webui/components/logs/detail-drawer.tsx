'use client';

import { type LogRow } from '@/lib/api/logs';
import { Copy, X } from 'lucide-react';
import { useState } from 'react';

interface DetailDrawerProps {
	row: LogRow | null;
	onClose: () => void;
}

export function DetailDrawer({ row, onClose }: DetailDrawerProps) {
	const [copied, setCopied] = useState(false);

	if (!row) return null;

	const handleCopy = () => {
		navigator.clipboard.writeText(JSON.stringify(row, null, 2));
		setCopied(true);
		setTimeout(() => setCopied(false), 2000);
	};

	return (
		<div className="fixed inset-y-0 right-0 w-96 bg-surface border-l border-hairline flex flex-col z-40">
			{/* Header */}
			<div className="flex items-center justify-between border-b border-hairline px-4 py-3">
				<h2 className="text-sm font-semibold text-text">Log Details</h2>
				<button
					onClick={onClose}
					className="p-1 hover:bg-surface-alt rounded transition-colors"
					title="Close"
				>
					<X size={16} className="text-text-dim" />
				</button>
			</div>

			{/* Content */}
			<div className="flex-1 overflow-auto p-4">
				<pre className="text-xs font-mono text-text-dim whitespace-pre-wrap break-words rounded bg-surface-alt p-3 border border-hairline">
					{JSON.stringify(row, null, 2)}
				</pre>
			</div>

			{/* Footer */}
			<div className="border-t border-hairline px-4 py-3 flex gap-2">
				<button
					onClick={handleCopy}
					className="flex items-center gap-2 px-3 py-1.5 text-xs rounded border border-hairline hover:bg-surface-alt transition-colors text-text-dim hover:text-text"
				>
					<Copy size={14} />
					{copied ? 'Copied!' : 'Copy JSON'}
				</button>
			</div>
		</div>
	);
}
