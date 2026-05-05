'use client';

import { useReducedMotion } from 'framer-motion';
import { useEffect, useState } from 'react';

export function StatusTicker() {
	const [signals] = useState<{ id: string; status: string }[]>([]);
	const [index, setIndex] = useState(0);
	const prefersReducedMotion = useReducedMotion();

	useEffect(() => {
		if (signals.length === 0) return;

		if (prefersReducedMotion) {
			return;
		}

		const interval = setInterval(() => {
			setIndex(i => (i + 1) % signals.length);
		}, 3000);

		return () => clearInterval(interval);
	}, [signals.length, prefersReducedMotion]);

	if (signals.length === 0) return null;

	const current = signals[index];

	return (
		<div className="flex items-center gap-2 border-b border-hairline bg-surface px-4 py-2 text-mono-tiny">
			<div className="h-2 w-2 rounded-full bg-ok" />
			<span className="text-text-dim">{current.status}</span>
		</div>
	);
}
