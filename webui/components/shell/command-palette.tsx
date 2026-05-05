'use client';

import { useEffect, useState } from 'react';

export function CommandPalette() {
	const [open, setOpen] = useState(false);

	useEffect(() => {
		const handler = (e: KeyboardEvent) => {
			if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
				e.preventDefault();
				setOpen(!open);
			}
		};

		document.addEventListener('keydown', handler);
		return () => document.removeEventListener('keydown', handler);
	}, [open]);

	if (!open) return null;

	return (
		<div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 pt-20">
			<div className="w-96 rounded-lg border border-hairline bg-surface shadow-lg">
				<input
					type="text"
					placeholder="Search..."
					className="w-full border-b border-hairline bg-surface p-4 text-text outline-none placeholder:text-text-dim"
				/>
				<div className="max-h-96 overflow-auto">
					<div className="p-4 text-text-dim text-small">Type to search...</div>
				</div>
			</div>
		</div>
	);
}
