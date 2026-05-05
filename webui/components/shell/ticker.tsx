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
		const wsClient = getWSClient(queryClient);

		// Subscribe to signals channel
		wsClient.subscribe('signals');

		// Simulate initial connection and event handling
		const _handleSignal = (signal: Signal) => {
			setSignals(prev => {
				const updated = [signal, ...prev];
				return updated.slice(0, 20); // Keep last 20 signals
			});
		};

		// In a real scenario, this would be driven by WS messages
		// For now, just set up the subscription
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
