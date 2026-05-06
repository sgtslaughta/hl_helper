'use client';

import { type ReactNode, useEffect, useState } from 'react';

const GLOBAL_OVERRIDE_KEY = 'hlh.alwaysShowDetails';

interface Props {
	label: string;
	storageKey?: string;
	children: ReactNode;
}

export function Disclosure({ label, storageKey, children }: Props) {
	const [open, setOpen] = useState(false);

	useEffect(() => {
		if (typeof window === 'undefined') return;
		if (window.localStorage.getItem(GLOBAL_OVERRIDE_KEY) === 'true') {
			setOpen(true);
			return;
		}
		if (storageKey) {
			const v = window.localStorage.getItem(`hlh.disclosure.${storageKey}`);
			if (v === '1') setOpen(true);
		}
	}, [storageKey]);

	function toggle() {
		const next = !open;
		setOpen(next);
		if (storageKey && typeof window !== 'undefined') {
			window.localStorage.setItem(`hlh.disclosure.${storageKey}`, next ? '1' : '0');
		}
	}

	return (
		<div className="rounded border border-hairline bg-surface-2/40">
			<button
				type="button"
				onClick={toggle}
				aria-expanded={open}
				className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm font-medium text-text hover:bg-surface-2"
			>
				<span>{label}</span>
				<span aria-hidden>{open ? '▾' : '▸'}</span>
			</button>
			{open ? (
				// biome-ignore lint/a11y/useSemanticElements: <section> would require an aria-label or visible heading; role="region" matches existing tests
				<div role="region" className="border-t border-hairline px-3 py-2 text-sm text-text-dim">
					{children}
				</div>
			) : null}
		</div>
	);
}
