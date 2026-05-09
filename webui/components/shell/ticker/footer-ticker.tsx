'use client';

import {
	isNewEvent,
	loadTickerPrefs,
	saveTickerPrefs,
	useTickerStream,
} from '@/hooks/use-ticker-stream';
import {
	DEFAULT_TICKER_PREFS,
	TICKER_NEW_WINDOW_MS,
	type TickerEvent,
	type TickerPrefs,
} from '@/lib/ticker-types';
import { useReducedMotion } from 'framer-motion';
import { useEffect, useMemo, useRef, useState } from 'react';
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

function filterEvents(events: TickerEvent[], prefs: TickerPrefs): TickerEvent[] {
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

	// Track when each event id first appeared in this session so the "new"
	// LED only fires for events that arrived AFTER the page mounted, not for
	// any event whose timestamp happens to be < 5min old. Without this, every
	// recent event in the buffer shows the amber LED on first render.
	const firstSeenRef = useRef<Map<string, number>>(new Map());
	const mountTimeRef = useRef<number>(Date.now());

	useEffect(() => {
		setPrefs(loadTickerPrefs());
	}, []);

	// Tighter cadence so the amber LED fades out within the new-window
	// (currently 60s, see ticker-types.ts) instead of lingering for minutes.
	useEffect(() => {
		const id = setInterval(() => setNow(Date.now()), 5_000);
		return () => clearInterval(id);
	}, []);

	// Stamp first-seen time for any event id we haven't seen yet.
	useEffect(() => {
		const map = firstSeenRef.current;
		const t = Date.now();
		for (const e of events) {
			if (!map.has(e.id)) map.set(e.id, t);
		}
	}, [events]);

	const visible = useMemo(() => filterEvents(events, prefs), [events, prefs]);

	const onPrefsChange = (next: TickerPrefs) => {
		setPrefs(next);
		saveTickerPrefs(next);
	};

	const motionPaused = prefs.paused || prefersReducedMotion || visible.length === 0;
	const duration = SPEED_DURATION_S[prefs.speed] ?? 60;

	const placeholder =
		visible.length === 0 ? (connected ? 'Awaiting system events…' : 'Connecting…') : null;

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
						{[...visible, ...visible].map((e, i) => {
							// "new" only when:
							//  - id was first seen AFTER mount (i.e. arrived live, not from
							//    initial buffer)
							//  - first-seen-at is within the new-window
							//  - event timestamp itself is also within the window (server
							//    may replay older events on reconnect; don't flash those)
							const firstSeen = firstSeenRef.current.get(e.id);
							const liveArrival = firstSeen != null && firstSeen >= mountTimeRef.current;
							const recentlyArrived = firstSeen != null && now - firstSeen < TICKER_NEW_WINDOW_MS;
							const isNew =
								liveArrival && recentlyArrived && isNewEvent(e, now, TICKER_NEW_WINDOW_MS);
							return <TickerMessage key={`${e.id}-${i}`} event={e} isNew={isNew} />;
						})}
					</div>
				)}
			</div>

			<TickerControls prefs={prefs} onChange={onPrefsChange} />
		</footer>
	);
}
