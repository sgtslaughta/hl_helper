// Parse server timestamps as UTC. SQLite returns naive ISO strings like
// "2026-05-07 16:30:03" which `new Date()` interprets in local time and
// yields wildly wrong deltas. Append "Z" when no offset is present.
export function parseServerTime(s: string): Date {
	if (/[zZ]$|[+-]\d{2}:?\d{2}$/.test(s)) return new Date(s);
	return new Date(s.replace(' ', 'T') + 'Z');
}

export function fmtDuration(secs: number): string {
	if (!Number.isFinite(secs)) return '—';
	const s = Math.max(0, Math.floor(secs));
	if (s < 60) return `${s}s`;
	if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`;
	if (s < 86400) {
		const h = Math.floor(s / 3600);
		const m = Math.floor((s % 3600) / 60);
		return `${h}h ${m}m`;
	}
	const d = Math.floor(s / 86400);
	const h = Math.floor((s % 86400) / 3600);
	return `${d}d ${h}h`;
}

export function relTime(iso: string): string {
	const t = parseServerTime(iso).getTime();
	if (Number.isNaN(t)) return '';
	const s = Math.max(0, Math.floor((Date.now() - t) / 1000));
	if (s < 60) return `${s}s ago`;
	if (s < 3600) return `${Math.floor(s / 60)}m ago`;
	if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
	return `${Math.floor(s / 86400)}d ago`;
}
