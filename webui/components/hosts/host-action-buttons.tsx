'use client';

import { ActionConfirmDialog } from '@/components/hosts/action-confirm-dialog';
import type { Host } from '@/lib/api/hosts';
import { pkgUpdateHost, rebootHost, revokeHostCert, shellExecHost } from '@/lib/api/hosts';
import { type CanPerform, useCanPerform } from '@/lib/rbac';
import type { ActionType } from '@/lib/risk-catalog';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { type ReactNode, useEffect, useMemo, useState } from 'react';

const ACTIONS: { type: ActionType; label: string }[] = [
	{ type: 'reboot', label: 'Reboot' },
	{ type: 'shell-exec', label: 'Shell exec' },
	{ type: 'pkg-update', label: 'Pkg update' },
	{ type: 'revoke-host', label: 'Revoke' },
];

export function HostActionButtons({ host }: { host: Host }) {
	const [pendingAction, setPendingAction] = useState<ActionType | null>(null);
	const [command, setCommand] = useState('');
	const [timeout_s, setTimeout_s] = useState(60);
	const [classes, setClasses] = useState<string[]>([]);
	const [reason, setReason] = useState('');
	const qc = useQueryClient();

	// Reset form state whenever the pending action changes (or dialog closes)
	// biome-ignore lint/correctness/useExhaustiveDependencies: setters are stable
	useEffect(() => {
		setCommand('');
		setTimeout_s(60);
		setClasses(['security']);
		setReason('');
	}, [pendingAction]);

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

	const shellExecMut = useMutation({
		mutationFn: (principal: string) => shellExecHost(host.id, { command, timeout_s }, principal),
		onSuccess: () => {
			qc.invalidateQueries({ queryKey: ['hosts', host.id, 'tasks'] });
			qc.invalidateQueries({ queryKey: ['hosts', host.id] });
		},
	});

	const pkgUpdateMut = useMutation({
		mutationFn: (principal: string) => pkgUpdateHost(host.id, { classes }, principal),
		onSuccess: () => {
			qc.invalidateQueries({ queryKey: ['hosts', host.id, 'tasks'] });
			qc.invalidateQueries({ queryKey: ['hosts', host.id] });
		},
	});

	const revokeHostMut = useMutation({
		mutationFn: (principal: string) => revokeHostCert(host.id, { reason }, principal),
		onSuccess: () => {
			qc.invalidateQueries({ queryKey: ['hosts'] });
			qc.invalidateQueries({ queryKey: ['hosts', host.id] });
			qc.invalidateQueries({ queryKey: ['hosts', host.id, 'tasks'] });
		},
	});

	function dispatch(action: ActionType, principal: string) {
		if (action === 'reboot') rebootMut.mutate(principal);
		else if (action === 'shell-exec') shellExecMut.mutate(principal);
		else if (action === 'pkg-update') pkgUpdateMut.mutate(principal);
		else if (action === 'revoke-host') revokeHostMut.mutate(principal);
		setPendingAction(null);
	}

	function getFormChildren(): ReactNode {
		if (pendingAction === 'shell-exec') {
			return (
				<div className="mb-3 space-y-2">
					<div>
						<label htmlFor="cmd" className="block text-sm font-medium text-text">
							Command
						</label>
						<input
							id="cmd"
							type="text"
							value={command}
							onChange={e => setCommand(e.target.value)}
							className="mt-1 w-full rounded border border-hairline bg-surface-2 px-2 py-1.5 text-sm text-text"
							placeholder="e.g., systemctl restart service"
						/>
					</div>
					<div>
						<label htmlFor="timeout" className="block text-sm font-medium text-text">
							Timeout (seconds)
						</label>
						<input
							id="timeout"
							type="number"
							value={timeout_s}
							onChange={e => setTimeout_s(Math.max(1, Number.parseInt(e.target.value) || 1))}
							min="1"
							className="mt-1 w-full rounded border border-hairline bg-surface-2 px-2 py-1.5 text-sm text-text"
						/>
					</div>
				</div>
			);
		}
		if (pendingAction === 'pkg-update') {
			const opts = ['security', 'bugfix', 'enhancement'];
			return (
				<div className="mb-3 space-y-2">
					<fieldset>
						<legend className="block text-sm font-medium text-text">Update classes</legend>
						<div className="mt-1 space-y-1">
							{opts.map(opt => (
								<label key={opt} className="flex items-center gap-2">
									<input
										type="checkbox"
										checked={classes.includes(opt)}
										onChange={e => {
											if (e.target.checked) setClasses([...classes, opt]);
											else setClasses(classes.filter(c => c !== opt));
										}}
										className="rounded border border-hairline"
									/>
									<span className="text-sm text-text">{opt}</span>
								</label>
							))}
						</div>
					</fieldset>
				</div>
			);
		}
		if (pendingAction === 'revoke-host') {
			return (
				<div className="mb-3">
					<label htmlFor="reason" className="block text-sm font-medium text-text">
						Reason
					</label>
					<textarea
						id="reason"
						value={reason}
						onChange={e => setReason(e.target.value)}
						className="mt-1 w-full rounded border border-hairline bg-surface-2 px-2 py-1.5 text-sm text-text"
						placeholder="Why is this host being revoked?"
						rows={3}
					/>
				</div>
			);
		}
		return null;
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
					formChildren={getFormChildren()}
				/>
			) : null}
		</div>
	);
}
