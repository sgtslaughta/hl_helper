export interface AuditUserLookup {
	id: string;
	username?: string;
	email?: string;
	display_name?: string;
}

const ACTION_LABELS: Record<string, string> = {
	'exec.dispatched': 'Executed shell command',
	'exec.elevated.dispatched': 'Executed privileged shell command',
	'exec.completed': 'Shell command completed',
	'exec.failed': 'Shell command failed',
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
};

/** Pull a navigable target href out of an audit entry's payload, if any.
 *  Returns null when the entry has no associated action detail page.
 *  Currently surfaces task_id (→ /tasks/{id}) for exec/dispatch entries.
 *
 *  `_action` is reserved for future per-action routing (e.g. token mint →
 *  /security) but unused for now.
 */
export function auditActionHref(
	_action: string,
	payload: Record<string, unknown> | null | undefined,
): string | null {
	if (!payload || typeof payload !== 'object') return null;
	const taskId = (payload as Record<string, unknown>).task_id;
	if (typeof taskId === 'string' && taskId) return `/tasks/${taskId}`;
	return null;
}

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
