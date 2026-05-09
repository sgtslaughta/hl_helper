import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
	appendCapped,
	isNewEvent,
	loadTickerPrefs,
	saveTickerPrefs,
	useTickerStream,
} from '@/hooks/use-ticker-stream';
import type { TickerEvent } from '@/lib/ticker-types';

function mkEvent(over: Partial<TickerEvent> = {}): TickerEvent {
	return {
		v: 1,
		id: Math.random().toString(36).slice(2),
		ts: new Date().toISOString(),
		type: 'system',
		severity: 'info',
		text: 'test',
		...over,
	};
}

describe('appendCapped', () => {
	it('prepends new event and keeps under cap', () => {
		const start = Array.from({ length: 5 }, () => mkEvent());
		const next = appendCapped(start, mkEvent({ text: 'newest' }), 5);
		expect(next).toHaveLength(5);
		expect(next[0].text).toBe('newest');
	});

	it('drops oldest when over cap', () => {
		const oldest = mkEvent({ text: 'oldest' });
		let acc: TickerEvent[] = [oldest, ...Array.from({ length: 4 }, () => mkEvent())];
		// Push 5 more events; oldest should be evicted past cap=5
		for (let i = 0; i < 5; i++) acc = appendCapped(acc, mkEvent({ text: `n${i}` }), 5);
		expect(acc).toHaveLength(5);
		expect(acc.find(e => e.text === 'oldest')).toBeUndefined();
	});

	it('dedupes by id', () => {
		const e = mkEvent({ id: 'dup', text: 'first' });
		const out = appendCapped([e], { ...e, text: 'second' }, 5);
		expect(out).toHaveLength(1);
		expect(out[0].text).toBe('first');
	});
});

describe('isNewEvent', () => {
	it('true within window', () => {
		const e = mkEvent({ ts: new Date(Date.now() - 60_000).toISOString() });
		expect(isNewEvent(e, Date.now(), 5 * 60_000)).toBe(true);
	});
	it('false past window', () => {
		const e = mkEvent({ ts: new Date(Date.now() - 10 * 60_000).toISOString() });
		expect(isNewEvent(e, Date.now(), 5 * 60_000)).toBe(false);
	});
});

describe('ticker prefs', () => {
	it('round-trips through localStorage', () => {
		saveTickerPrefs({ paused: true, speed: 'fast', types: ['host'], severities: ['warn'] });
		const loaded = loadTickerPrefs();
		expect(loaded.paused).toBe(true);
		expect(loaded.speed).toBe('fast');
		expect(loaded.types).toEqual(['host']);
		expect(loaded.severities).toEqual(['warn']);
	});

	it('returns defaults if absent', () => {
		localStorage.clear();
		const loaded = loadTickerPrefs();
		expect(loaded.paused).toBe(false);
		expect(loaded.speed).toBe('normal');
		expect(loaded.types).toEqual([]);
		expect(loaded.severities).toEqual([]);
	});
});

class MockSource {
	static instances: MockSource[] = [];
	url: string;
	onopen: (() => void) | null = null;
	onmessage: ((ev: { data: string }) => void) | null = null;
	onerror: ((ev?: unknown) => void) | null = null;
	closed = false;
	constructor(url: string) {
		this.url = url;
		MockSource.instances.push(this);
	}
	open() {
		this.onopen?.();
	}
	emit(payload: unknown) {
		this.onmessage?.({ data: JSON.stringify(payload) });
	}
	close() {
		this.closed = true;
	}
}

describe('useTickerStream', () => {
	it('returns empty when no url given', () => {
		const { result } = renderHook(() => useTickerStream({ url: null }));
		expect(result.current.events).toEqual([]);
		expect(result.current.connected).toBe(false);
	});

	it('connects via EventSource and accumulates ticker events', async () => {
		MockSource.instances = [];
		const { result } = renderHook(() =>
			useTickerStream({
				url: '/api/proxy/v1/events/sse?channels=ticker',
				sourceFactory: (u: string) => new MockSource(u),
			}),
		);
		await act(async () => {
			MockSource.instances[0].open();
		});
		expect(result.current.connected).toBe(true);

		await act(async () => {
			MockSource.instances[0].emit({
				type: 'event',
				channel: 'ticker',
				sequence: 1,
				payload: mkEvent({ text: 'hello world' }),
				timestamp: new Date().toISOString(),
			});
		});
		expect(result.current.events).toHaveLength(1);
		expect(result.current.events[0].text).toBe('hello world');
	});
});
