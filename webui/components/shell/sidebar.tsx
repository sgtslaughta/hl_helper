'use client';

import { useState } from 'react';

export function Sidebar() {
	const [collapsed, setCollapsed] = useState(false);

	return (
		<aside
			className={`flex flex-col border-r border-hairline bg-surface transition-all duration-300 ${
				collapsed ? 'w-14' : 'w-60'
			}`}
		>
			<div className="flex items-center justify-between p-4">
				<button type="button" onClick={() => setCollapsed(!collapsed)} className="rounded hover:bg-surface-2">
					≡
				</button>
			</div>
			{!collapsed && (
				<nav className="flex-1 overflow-auto p-4">
					<div className="text-xs font-semibold uppercase tracking-wider text-text-dim">
						Navigation
					</div>
				</nav>
			)}
		</aside>
	);
}
