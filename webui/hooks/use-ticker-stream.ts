'use client';

import { useEffect, useRef, useState } from 'react';
import {
	DEFAULT_TICKER_PREFS,
	type TickerEvent,
	type TickerPrefs,
} from '@/lib/ticker-types';

const PREFS_STORAGE_KEY = 'ticker.prefs.v1';
const RING_CAP = 100;
const TICKER_CHANNEL = 'ticker';

export function appendCapped(
	events: TickerEvent[],
	incoming: TickerEvent,
	cap: number = RING_CAP,
): TickerEvent[] {
	if (events.some(e => e.id === incoming.id)) return events;
	const next = [incoming, ...events];
	if (next.length > cap) next.length = cap;
	return next;
}

export function isNewEvent(event: TickerEvent, now: number, windowMs: number): boolean {
	const t = Date.parse(event.ts);
	if (Number.isNaN(t)) return false;
	return now - t < windowMs;
}

export function loadTickerPrefs(): TickerPrefs {
	if (typeof window === 'undefined') return DEFAULT_TICKER_PREFS;
	try {
		const raw = window.localStorage.getItem(PREFS_STORAGE_KEY);
		if (!raw) return DEFAULT_TICKER_PREFS;
		const parsed = JSON.parse(raw);
		return {
			paused: Boolean(parsed.paused),
			speed: (parsed.speed === 'slow' || parsed.speed === 'fast' ? parsed.speed : 'normal'),
			types: Array.isArray(parsed.types) ? parsed.types : [],
			severities: Array.isArray(parsed.severities) ? parsed.severities : [],
		};
	} catch {
		return DEFAULT_TICKER_PREFS;
	}
}

export function saveTickerPrefs(prefs: TickerPrefs): void {
	if (typeof window === 'undefined') return;
	try {
		window.localStorage.setItem(PREFS_STORAGE_KEY, JSON.stringify(prefs));
	} catch {
		/* quota or disabled storage — ignore */
	}
}

// Minimal EventSource-like interface for transport injection in tests.
export interface TickerSource {
	close(): void;
	onmessage: ((ev: { data: string }) => void) | null;
	onopen: (() => void) | null;
	onerror: ((ev?: unknown) => void) | null;
}

export interface UseTickerStreamOptions {
	url: string | null;
	sourceFactory?: (url: string) => TickerSource;
}

export interface UseTickerStreamResult {
	events: TickerEvent[];
	connected: boolean;
}

function defaultSourceFactory(url: string): TickerSource {
	// EventSource auto-reconnects on network errors, no manual ws plumbing.
	const es = new EventSource(url, { withCredentials: true });
	return es as unknown as TickerSource;
}

export function useTickerStream(opts: UseTickerStreamOptions): UseTickerStreamResult {
	const { url, sourceFactory } = opts;
	const [events, setEvents] = useState<TickerEvent[]>([]);
	const [connected, setConnected] = useState(false);
	const sourceRef = useRef<TickerSource | null>(null);
	const factoryRef = useRef(sourceFactory);
	factoryRef.current = sourceFactory;

	useEffect(() => {
		if (!url) return;
		const factory = factoryRef.current ?? defaultSourceFactory;
		const src = factory(url);
		sourceRef.current = src;

		src.onopen = () => setConnected(true);
		src.onerror = () => setConnected(false);
		src.onmessage = (evt: { data: string }) => {
			let data: { type?: string; channel?: string; payload?: TickerEvent } | null = null;
			try {
				data = JSON.parse(evt.data);
			} catch {
				return;
			}
			if (!data) return;
			if (data.type === 'event' && data.channel === TICKER_CHANNEL && data.payload) {
				const payload = data.payload;
				setEvents(prev => appendCapped(prev, payload));
			}
		};

		return () => {
			try {
				src.close();
			} catch {
				/* ignore */
			}
			sourceRef.current = null;
		};
	}, [url]);

	return { events, connected };
}
