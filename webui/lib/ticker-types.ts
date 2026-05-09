// Ticker envelope shape — must match server/app/events/ticker.py.
export type TickerType = 'host' | 'advisory' | 'posture' | 'task' | 'audit' | 'system';
export type TickerSeverity = 'info' | 'warn' | 'error' | 'ok';

export interface TickerEvent {
	v: number;
	id: string;
	ts: string;
	type: TickerType;
	severity: TickerSeverity;
	text: string;
	link?: string;
	meta?: Record<string, unknown>;
}

export type TickerSpeed = 'slow' | 'normal' | 'fast';

export interface TickerPrefs {
	paused: boolean;
	speed: TickerSpeed;
	types: TickerType[]; // empty = all
	severities: TickerSeverity[]; // empty = all
}

export const DEFAULT_TICKER_PREFS: TickerPrefs = {
	paused: false,
	speed: 'normal',
	types: [],
	severities: [],
};

export const TICKER_NEW_WINDOW_MS = 5 * 60 * 1000;
