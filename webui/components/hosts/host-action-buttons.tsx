'use client';

import { ActionConfirmDialog } from '@/components/hosts/action-confirm-dialog';
import type { Host } from '@/lib/api/hosts';
import { rebootHost } from '@/lib/api/hosts';
import { type CanPerform, useCanPerform } from '@/lib/rbac';
import type { ActionType } from '@/lib/risk-catalog';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

const ACTIONS: { type: ActionType; label: string }[] = [
	{ type: 'reboot', label: 'Reboot' },
	{ type: 'shell-exec', label: 'Shell exec' },
	{ type: 'pkg-update', label: 'Pkg update' },
	{ type: 'revoke-host', label: 'Revoke' },
];

export function HostActionButtons({ host }: { host: Host }) {
	const [pendingAction, setPendingAction] = useState<ActionType | null>(null);
	const qc = useQueryClient();

	// Hooks must be called in stable order. Each useCanPerform call corresponds to a fixed action slot.
	const reboot = useCanPerform('reboot');
	const shellExec = useCanPerform('shell-exec');
	const pkgUpdate = useCanPerform('pkg-update');
	const revokeHostCap = useCanPerform('revoke-host');

	const caps: Record<ActionType, CanPerform> = useMemo(
		() => ({
			reboot,
			'shell-exec': shellExec,
			'pkg-update': pkgUpdate,
			'revoke-host': revokeHostCap,
			'delete-host': { allowed: false, reason: 'Use Revoke first.' },
			'mint-enrollment-token': { allowed: false },
			'revoke-enrollment-token': { allowed: false },
		}),
		[reboot, shellExec, pkgUpdate, revokeHostCap],
	);

	const rebootMut = useMutation({
		mutationFn: (principal: string) => rebootHost(host.id, { delay_s: 0, reason: '' }, principal),
		onSuccess: () => qc.invalidateQueries({ queryKey: ['hosts', host.id, 'tasks'] }),
	});

	function dispatch(action: ActionType, principal: string) {
		if (action === 'reboot') rebootMut.mutate(principal);
		// shell-exec, pkg-update, revoke-host: forms wired in follow-up tasks.
		setPendingAction(null);
	}

	const pendingCap = pendingAction ? caps[pendingAction] : null;

	return (
		<div className="flex flex-wrap gap-2">
			{ACTIONS.map(a => {
				const cap = caps[a.type];
				return (
					<button
						key={a.type}
						type="button"
						disabled={!cap.allowed}
						title={cap.allowed ? '' : cap.reason}
						onClick={() => setPendingAction(a.type)}
						className="rounded border border-hairline px-3 py-1.5 text-sm text-text hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-50"
					>
						{a.label}
					</button>
				);
			})}

			{pendingAction && pendingCap ? (
				<ActionConfirmDialog
					action={pendingAction}
					host={{ id: host.id, hostname: host.hostname }}
					principal={pendingCap.principal ?? ''}
					onClose={() => setPendingAction(null)}
					onConfirm={() => dispatch(pendingAction, pendingCap.principal ?? '')}
				/>
			) : null}
		</div>
	);
}
