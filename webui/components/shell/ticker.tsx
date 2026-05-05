'use client';

import { getWSClient } from '@/lib/ws-client';
import { useQueryClient } from '@tanstack/react-query';
import { useReducedMotion } from 'framer-motion';
import { useEffect, useState } from 'react';

interface Signal {
	id: string;
	status: string;
	timestamp: number;
}

export function StatusTicker() {
	const [signals, setSignals] = useState<Signal[]>([]);
	const [index, setIndex] = useState(0);
	const [isPaused, setIsPaused] = useState(false);
	const prefersReducedMotion = useReducedMotion();
	const queryClient = useQueryClient();

	useEffect(() => {
		// WS auto-connect is opt-in. The Next.js /api/proxy route handler can't
		// upgrade HTTP → WebSocket, so the events stream needs a direct path that
		// doesn't exist in dev. Re-enable with NEXT_PUBLIC_FLEET_WS=1 once a
		// reverse proxy or sidecar provides /v1/events.
		if (process.env.NEXT_PUBLIC_FLEET_WS !== '1') return;

		const wsClient = getWSClient(queryClient);
		wsClient.connect().catch(() => {
			// reconnect logic bounded; dropped silently here
		});
		wsClient.subscribe('signals');

		const _handleSignal = (signal: Signal) => {
			setSignals(prev => [signal, ...prev].slice(0, 20));
		};
		void _handleSignal;

		return () => {
			wsClient.unsubscribe('signals');
		};
	}, [queryClient]);

	useEffect(() => {
		if (signals.length === 0 || isPaused || prefersReducedMotion) {
			return;
		}

		const interval = setInterval(() => {
			setIndex(i => (i + 1) % signals.length);
		}, 4000);

		return () => clearInterval(interval);
	}, [signals.length, isPaused, prefersReducedMotion]);

	if (signals.length === 0) return null;

	const current = signals[index];

	return (
		<div
			className="flex items-center gap-2 border-b border-hairline bg-surface px-4 py-2 text-sm"
			onMouseEnter={() => setIsPaused(true)}
			onMouseLeave={() => setIsPaused(false)}
			onFocus={() => setIsPaused(true)}
			onBlur={() => setIsPaused(false)}
		>
			<div className="h-2 w-2 rounded-full bg-ok" />
			<span className="text-text-dim">{current.status}</span>
		</div>
	);
}
