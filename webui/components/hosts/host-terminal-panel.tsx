'use client';

import { TerminalPane } from '@/components/terminal/terminal-pane';
import { Power } from 'lucide-react';
import { useState } from 'react';

interface HostTerminalPanelProps {
	hostId: string;
}

export function HostTerminalPanel({ hostId }: HostTerminalPanelProps) {
	const [connected, setConnected] = useState(false);

	if (!connected) {
		return (
			<div className="flex h-[60vh] flex-col items-center justify-center gap-3 rounded border border-hairline bg-surface text-text-dim">
				<Power size={32} className="text-text-dim/60" />
				<div className="font-mono text-xs uppercase tracking-wider">Terminal idle</div>
				<button
					type="button"
					onClick={() => setConnected(true)}
					className="rounded-sm border border-accent bg-accent/15 px-3 py-1.5 font-mono text-[11px] font-semibold uppercase tracking-wider text-accent hover:bg-accent/25"
				>
					Connect
				</button>
				<div className="font-mono text-[10px] text-text-dim/60">
					Connection established only on demand.
				</div>
			</div>
		);
	}

	return (
		<div className="relative h-[60vh] rounded border border-hairline bg-surface overflow-hidden">
			<button
				type="button"
				onClick={() => setConnected(false)}
				title="Disconnect terminal"
				className="absolute right-2 top-2 z-10 rounded-sm border border-hairline bg-surface/80 px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-text-dim hover:border-warn hover:text-warn"
			>
				Disconnect
			</button>
			<TerminalPane hostId={hostId} />
		</div>
	);
}
