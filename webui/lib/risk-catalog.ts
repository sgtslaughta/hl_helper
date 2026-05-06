import type { RiskClass } from '@/components/primitives/risk-badge';

export type ActionType =
	| 'reboot'
	| 'shell-exec'
	| 'pkg-update'
	| 'revoke-host'
	| 'delete-host'
	| 'mint-enrollment-token'
	| 'revoke-enrollment-token';

export interface RiskEntry {
	displayName: string;
	summary: string;
	riskClass: RiskClass;
	risks: string[];
	rollback: string;
	technical: {
		method: 'POST' | 'DELETE' | 'PUT' | 'PATCH';
		pathTemplate: string;
		samplePayload: object;
	};
}

export const riskCatalog: Record<ActionType, RiskEntry> = {
	reboot: {
		displayName: 'Reboot host',
		summary: 'Restarts the host operating system.',
		riskClass: 'destructive',
		risks: [
			'Active sessions and running processes will be terminated.',
			'In-flight tasks may fail and require retry.',
			'If the host fails to come back up, manual intervention is required.',
		],
		rollback:
			'Reboot is not reversible from this UI. If the host fails to return, use console access on the affected machine.',
		technical: {
			method: 'POST',
			pathTemplate: '/v1/hosts/{id}/actions/reboot',
			samplePayload: { delay_s: 0, reason: '' },
		},
	},
	'shell-exec': {
		displayName: 'Run shell command',
		summary: 'Executes a shell command on the host as the agent user.',
		riskClass: 'destructive',
		risks: [
			'Arbitrary commands can damage the host or exfiltrate data.',
			'Output is captured in the audit log; secrets passed inline will be visible there.',
			'Long-running commands may hit the timeout and leave partial state.',
		],
		rollback:
			'Effects depend on the command. Review command output and audit log; no automatic rollback.',
		technical: {
			method: 'POST',
			pathTemplate: '/v1/hosts/{id}/actions/shell-exec',
			samplePayload: { command: 'uname -a', timeout_s: 60 },
		},
	},
	'pkg-update': {
		displayName: 'Update packages',
		summary: 'Applies pending OS package updates on the host.',
		riskClass: 'caution',
		risks: [
			'Some package updates require a reboot to take effect.',
			'Service restarts during the upgrade can briefly interrupt traffic.',
			'A failed dependency may leave the package manager in a half-applied state.',
		],
		rollback:
			'Most package managers support pinning the previous version; rollback is host-specific and not automated here.',
		technical: {
			method: 'POST',
			pathTemplate: '/v1/hosts/{id}/actions/pkg-update',
			samplePayload: { classes: ['security'] },
		},
	},
	'revoke-host': {
		displayName: 'Revoke host certificate',
		summary: "Invalidates the host's leaf certificate; the agent loses access immediately.",
		riskClass: 'irreversible',
		risks: [
			'The agent cannot reconnect until re-enrolled with a new token.',
			'In-flight tasks will fail mid-execution.',
			'Audit history for this host is preserved, but the host disappears from active inventory.',
		],
		rollback:
			'Re-enroll the host with a fresh enrollment token. The previous certificate cannot be unrevoked.',
		technical: {
			method: 'POST',
			pathTemplate: '/v1/hosts/{id}/revoke',
			samplePayload: { reason: '' },
		},
	},
	'delete-host': {
		displayName: 'Delete host',
		summary: 'Permanently removes the host record and its history from the fleet.',
		riskClass: 'irreversible',
		risks: [
			'Audit history for the host is removed (subject to retention policy).',
			'Any saved bindings, schedules, or policies referencing this host will need to be re-targeted.',
			'The host id is freed and may be reused.',
		],
		rollback:
			'No rollback. Re-enroll to recreate, but the new host has a new id and history starts empty.',
		technical: {
			method: 'DELETE',
			pathTemplate: '/v1/hosts/{id}',
			samplePayload: {},
		},
	},
	'mint-enrollment-token': {
		displayName: 'Mint enrollment token',
		summary: 'Generates a one-time token that authorizes one host to enroll.',
		riskClass: 'caution',
		risks: [
			'Anyone holding the plaintext token before expiry can enroll a host.',
			'The token is shown once. Lost tokens cannot be recovered, only revoked.',
			'Plaintext is never persisted; only a hash is stored.',
		],
		rollback:
			'Revoke the token before redemption. After redemption the resulting host can be revoked separately.',
		technical: {
			method: 'POST',
			pathTemplate: '/v1/enrollment-tokens',
			samplePayload: { label: 'lab-router-01', ttl_seconds: 900 },
		},
	},
	'revoke-enrollment-token': {
		displayName: 'Revoke enrollment token',
		summary: 'Deletes a pending enrollment token before it is redeemed.',
		riskClass: 'destructive',
		risks: [
			'If the operator already started the install command, it will fail with an authentication error.',
			'You will need to mint a new token to retry enrollment.',
		],
		rollback: 'No rollback. Mint a new token if needed.',
		technical: {
			method: 'DELETE',
			pathTemplate: '/v1/enrollment-tokens/{id}',
			samplePayload: {},
		},
	},
};
