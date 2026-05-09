export interface AuditUserLookup {
	id: string;
	username?: string;
	email?: string;
	display_name?: string;
}

const ACTION_LABELS: Record<string, string> = {
	'exec.dispatched': 'Dispatched command',
	'exec.completed': 'Command completed',
	'exec.failed': 'Command failed',
	'host.enrolled': 'Enrolled host',
	'host.deleted': 'Deleted host',
	'host.revoked': 'Revoked host trust',
	'host.pruned': 'Pruned stale host',
	'reboot.dispatched': 'Triggered reboot',
	'pkg-update.dispatched': 'Triggered package update',
	'resurvey.dispatched': 'Triggered resurvey',
	'agent.update.dispatched': 'Triggered agent update',
	'token.minted': 'Minted enrollment token',
	'token.revoked': 'Revoked enrollment token',
};

export function humanizeAuditAction(action: string): string {
	if (ACTION_LABELS[action]) return ACTION_LABELS[action];
	return action.replace(/[._]/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

export function shortAuditId(s: string | null | undefined): string {
	if (!s) return '—';
	return s.length > 12 ? `${s.slice(0, 8)}…` : s;
}

export function auditActorLabel(
	actor: string,
	users: Record<string, AuditUserLookup | undefined>,
): string {
	const m = actor.match(/^user:([0-9a-f-]+)$/i);
	if (m) {
		const u = users[m[1]];
		if (u) return u.username || u.display_name || u.email || `user ${shortAuditId(m[1])}`;
		return `user ${shortAuditId(m[1])}`;
	}
	return actor;
}

export function extractActorUserId(actor: string): string | null {
	const m = actor.match(/^user:([0-9a-f-]+)$/i);
	return m ? m[1] : null;
}
