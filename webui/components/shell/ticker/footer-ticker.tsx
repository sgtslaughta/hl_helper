'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useReducedMotion } from 'framer-motion';
import {
	isNewEvent,
	loadTickerPrefs,
	saveTickerPrefs,
	useTickerStream,
} from '@/hooks/use-ticker-stream';
import {
	DEFAULT_TICKER_PREFS,
	type TickerEvent,
	type TickerPrefs,
	TICKER_NEW_WINDOW_MS,
} from '@/lib/ticker-types';
import { TickerControls } from './ticker-controls';
import { TickerMessage } from './ticker-message';

const SPEED_DURATION_S: Record<string, number> = {
	slow: 120,
	normal: 60,
	fast: 30,
};

function getSseUrl(): string | null {
	// SSE flows through the standard Next.js HTTP proxy (cookies + CSRF auth).
	if (typeof window === 'undefined') return null;
	return '/api/proxy/v1/events/sse?channels=ticker';
}

function filterEvents(
	events: TickerEvent[],
	prefs: TickerPrefs,
): TickerEvent[] {
	return events.filter(e => {
		if (prefs.types.length > 0 && !prefs.types.includes(e.type)) return false;
		if (prefs.severities.length > 0 && !prefs.severities.includes(e.severity)) return false;
		return true;
	});
}

export function FooterTicker() {
	const [prefs, setPrefs] = useState<TickerPrefs>(DEFAULT_TICKER_PREFS);
	const [now, setNow] = useState(() => Date.now());
	const prefersReducedMotion = useReducedMotion();
	const sseUrl = useMemo(getSseUrl, []);
	const { events, connected } = useTickerStream({ url: sseUrl });
	const trackRef = useRef<HTMLDivElement | null>(null);

	useEffect(() => {
		setPrefs(loadTickerPrefs());
	}, []);

	useEffect(() => {
		const id = setInterval(() => setNow(Date.now()), 30_000);
		return () => clearInterval(id);
	}, []);

	const visible = useMemo(() => filterEvents(events, prefs), [events, prefs]);

	const onPrefsChange = (next: TickerPrefs) => {
		setPrefs(next);
		saveTickerPrefs(next);
	};

	const motionPaused = prefs.paused || prefersReducedMotion || visible.length === 0;
	const duration = SPEED_DURATION_S[prefs.speed] ?? 60;

	const placeholder =
		visible.length === 0
			? connected
				? 'Awaiting system events…'
				: 'Connecting…'
			: null;

	return (
		<footer
			className="mc-bezel relative flex items-center gap-2 border-t border-hairline overflow-hidden"
			style={{ minHeight: 28 }}
			aria-label="System ticker"
		>
			<div className="flex items-center gap-2 pl-3 pr-2 border-r border-hairline">
				<span
					className="mc-led"
					style={{ color: connected ? 'var(--color-ok)' : 'var(--color-text-dim)' }}
				/>
				<span className="mc-heading">SYS</span>
			</div>

			<div className="relative flex-1 overflow-hidden">
				{placeholder ? (
					<div className="px-3 text-[11px] mc-readout text-text-dim">{placeholder}</div>
				) : (
					<div
						ref={trackRef}
						className="flex whitespace-nowrap"
						style={{
							animation: `ticker-marquee ${duration}s linear infinite`,
							animationPlayState: motionPaused ? 'paused' : 'running',
						}}
					>
						{[...visible, ...visible].map((e, i) => (
							<TickerMessage
								key={`${e.id}-${i}`}
								event={e}
								isNew={isNewEvent(e, now, TICKER_NEW_WINDOW_MS)}
							/>
						))}
					</div>
				)}
			</div>

			<TickerControls prefs={prefs} onChange={onPrefsChange} />
		</footer>
	);
}
