'use client';

export function Topbar() {
	return (
		<header className="flex h-12 items-center justify-between border-b border-hairline bg-surface px-4">
			<div className="flex items-center gap-4">
				<button type="button" className="rounded px-2 py-1 hover:bg-surface-2">⌘K</button>
			</div>
			<div className="flex items-center gap-4">
				<button type="button" className="rounded px-2 py-1 hover:bg-surface-2">🔔</button>
				<button type="button" className="rounded px-2 py-1 hover:bg-surface-2">User</button>
			</div>
		</header>
	);
}
