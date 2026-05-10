import type { Outcome } from '@/lib/api/logs';

export interface HumanizableEvent {
	action: string;
	outcome?: Outcome;
	duration_ns?: number;
	details?: Record<string, unknown>;
	message?: string;
}

const ACTION_LABELS: Record<string, string> = {
	'task.exec.completed': 'Task exec completed',
	'task.exec.dispatched': 'Task exec dispatched',
	'host.enrolled': 'Enrolled host',
	'host.deleted': 'Deleted host',
	'host.revoked': 'Revoked host trust',
	'host.pruned': 'Pruned stale host',
	'reboot.dispatched': 'Rebooted host',
	'pkg-update.dispatched': 'Started package update',
	'resurvey.dispatched': 'Started hardware resurvey',
	'rescan.dispatched': 'Started inventory rescan',
	'agent.update.dispatched': 'Started agent update',
	'token.minted': 'Minted enrollment token',
	'token.revoked': 'Revoked enrollment token',
	'heartbeat.interval.set': 'Updated heartbeat interval',
	'risk.recomputed': 'Recomputed posture risk',
};

export function humanize(ev: HumanizableEvent): string {
	const baseLabel = ACTION_LABELS[ev.action]
		? ACTION_LABELS[ev.action]
		: ev.action.replace(/[._]/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

	const parts: string[] = [baseLabel];

	// Add outcome glyph if present
	if (ev.outcome) {
		const glyph = glyphForOutcome(ev.outcome);
		parts.push(glyph);
	}

	// Add return code if present in details
	if (ev.details?.rc !== undefined) {
		parts.push(`rc=${ev.details.rc}`);
	}

	// Add duration if present
	if (ev.duration_ns !== undefined) {
		const dur = formatDuration(ev.duration_ns);
		if (dur) {
			parts.push(dur);
		}
	}

	// Add message if present and no other details were added
	if (ev.message && !ev.details?.rc) {
		return `${baseLabel}: ${ev.message}`;
	}

	return parts.join(' ');
}

export function glyphForOutcome(o?: Outcome): string {
	switch (o) {
		case 'success':
			return '✓';
		case 'failure':
			return '✗';
		default:
			return '◐';
	}
}

export function formatDuration(ns?: number): string {
	if (ns === undefined || ns === null) return '';
	if (ns === 0) return '0ms';

	const ms = ns / 1_000_000;
	if (ms < 1000) {
		return `${Math.round(ms)}ms`;
	}

	const s = ms / 1000;
	return `${s.toFixed(1)}s`;
}
