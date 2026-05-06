'use client';

import { useEffect, useState } from 'react';

interface Props {
	to: string;
	onExpire?: () => void;
}

function format(remainingMs: number): string {
	if (remainingMs <= 0) return '00:00';
	const totalS = Math.floor(remainingMs / 1000);
	const h = Math.floor(totalS / 3600);
	const m = Math.floor((totalS % 3600) / 60);
	const s = totalS % 60;
	if (h > 0) return `${h}h ${m}m`;
	return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export function Countdown({ to, onExpire }: Props) {
	const target = new Date(to).getTime();
	const [now, setNow] = useState(() => Date.now());
	useEffect(() => {
		const id = setInterval(() => setNow(Date.now()), 1000);
		return () => clearInterval(id);
	}, []);
	const remaining = target - now;
	useEffect(() => {
		if (remaining <= 0 && onExpire) onExpire();
	}, [remaining, onExpire]);
	return <span className="font-mono tabular-nums">{format(remaining)}</span>;
}
