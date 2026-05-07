'use client';

export function HostFilesPanel({ hostId }: { hostId: string }) {
	return (
		<div className="space-y-2 text-sm text-text-dim">
			<p>Read-only file inspection for host {hostId}.</p>
			<p>Listing API not yet wired; placeholder pending backend endpoint.</p>
		</div>
	);
}
