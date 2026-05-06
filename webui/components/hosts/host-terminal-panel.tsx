'use client';

import { TerminalPane } from '@/components/terminal/terminal-pane';

interface HostTerminalPanelProps {
	hostId: string;
}

export function HostTerminalPanel({ hostId }: HostTerminalPanelProps) {
	return (
		<div className="h-[60vh] rounded border border-hairline bg-surface overflow-hidden">
			<TerminalPane hostId={hostId} />
		</div>
	);
}
