'use client';

import { ActionConfirmDialog } from '@/components/hosts/action-confirm-dialog';
import {
	type Host,
	deleteHost,
	pkgUpdateHost,
	rebootHost,
	resurveyHost,
	revokeHostCert,
	shellExecHost,
} from '@/lib/api/hosts';
import { type CanPerform, useCanPerform } from '@/lib/rbac';
import type { ActionType } from '@/lib/risk-catalog';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { PackageCheck, Power, RefreshCw, Skull, Terminal, Trash2 } from 'lucide-react';
import type { ComponentType, ReactNode } from 'react';
import { useEffect, useMemo, useState } from 'react';

interface ActionDef {
	type: ActionType;
	short: string;
	label: string;
	desc: string;
	icon: ComponentType<{ className?: string; size?: number }>;
	tone: 'safe' | 'warn' | 'danger' | 'critical';
}

const ACTIONS: ActionDef[] = [
	{
		type: 'reboot',
		short: 'REBOOT',
		label: 'Power Cycle',
		desc: 'graceful restart',
		icon: Power,
		tone: 'warn',
	},
	{
		type: 'shell-exec',
		short: 'EXEC',
		label: 'Shell Command',
		desc: 'remote run',
		icon: Terminal,
		tone: 'safe',
	},
	{
		type: 'pkg-update',
		short: 'PATCH',
		label: 'Package Update',
		desc: 'apt upgrade',
		icon: PackageCheck,
		tone: 'safe',
	},
	{
		type: 'resurvey',
		short: 'SURVEY',
		label: 'Resurvey',
		desc: 'refresh hardware',
		icon: RefreshCw,
		tone: 'safe',
	},
	{
		type: 'revoke-host',
		short: 'REVOKE',
		label: 'Revoke Trust',
		desc: 'offboard cert',
		icon: Skull,
		tone: 'danger',
	},
	{
		type: 'delete-host',
		short: 'DELETE',
		label: 'Delete Host',
		desc: 'remove record',
		icon: Trash2,
		tone: 'critical',
	},
];

const TONE_LED: Record<ActionDef['tone'], string> = {
	safe: 'text-ok',
	warn: 'text-warn',
	danger: 'text-danger',
	critical: 'text-danger',
};

const TONE_DATA: Record<ActionDef['tone'], string | undefined> = {
	safe: undefined,
	warn: 'warn',
	danger: 'danger',
	critical: 'danger',
};

export function QuickActions({ host, onDeleted }: { host: Host; onDeleted?: () => void }) {
	const [pending, setPending] = useState<ActionType | null>(null);
	const [command, setCommand] = useState('');
	const [timeout_s, setTimeout_s] = useState(60);
	const [classes, setClasses] = useState<string[]>(['security']);
	const [reason, setReason] = useState('');
	const qc = useQueryClient();

	// biome-ignore lint/correctness/useExhaustiveDependencies: setters are stable
	useEffect(() => {
		setCommand('');
		setTimeout_s(60);
		setClasses(['security']);
		setReason('');
	}, [pending]);

	const reboot = useCanPerform('reboot');
	const shellExec = useCanPerform('shell-exec');
	const pkgUpdate = useCanPerform('pkg-update');
	const revoke = useCanPerform('revoke-host');
	const del = useCanPerform('delete-host');

	const caps: Record<ActionType, CanPerform> = useMemo(
		() => ({
			reboot,
			'shell-exec': shellExec,
			'pkg-update': pkgUpdate,
			resurvey: { allowed: true },
			'revoke-host': revoke,
			'delete-host': del,
			'mint-enrollment-token': { allowed: false },
			'revoke-enrollment-token': { allowed: false },
		}),
		[reboot, shellExec, pkgUpdate, revoke, del],
	);

	const rebootMut = useMutation({
		mutationFn: (principal: string) => rebootHost(host.id, { delay_s: 0, reason: '' }, principal),
		onSuccess: () => {
			qc.invalidateQueries({ queryKey: ['hosts', host.id, 'tasks'] });
			qc.invalidateQueries({ queryKey: ['tasks'] });
		},
	});
	const shellMut = useMutation({
		mutationFn: (principal: string) => shellExecHost(host.id, { command, timeout_s }, principal),
		onSuccess: () => {
			qc.invalidateQueries({ queryKey: ['hosts', host.id] });
			qc.invalidateQueries({ queryKey: ['tasks'] });
		},
	});
	const pkgMut = useMutation({
		mutationFn: (principal: string) => pkgUpdateHost(host.id, { classes }, principal),
		onSuccess: () => {
			qc.invalidateQueries({ queryKey: ['hosts', host.id] });
			qc.invalidateQueries({ queryKey: ['tasks'] });
		},
	});
	const resurveyMut = useMutation({
		mutationFn: () => resurveyHost(host.id),
		onSuccess: () => {
			qc.invalidateQueries({ queryKey: ['hosts', host.id] });
		},
	});
	const revokeMut = useMutation({
		mutationFn: (principal: string) => revokeHostCert(host.id, { reason }, principal),
		onSuccess: () => qc.invalidateQueries({ queryKey: ['hosts'] }),
	});
	const deleteMut = useMutation({
		mutationFn: (principal: string) => deleteHost(host.id, principal),
		onSuccess: async () => {
			onDeleted?.();
			qc.removeQueries({ queryKey: ['hosts', host.id] });
			await qc.refetchQueries({ queryKey: ['hosts'], exact: true, type: 'active' });
		},
	});

	function dispatch(action: ActionType, principal: string) {
		if (action === 'reboot') rebootMut.mutate(principal);
		else if (action === 'shell-exec') shellMut.mutate(principal);
		else if (action === 'pkg-update') pkgMut.mutate(principal);
		else if (action === 'resurvey') resurveyMut.mutate();
		else if (action === 'revoke-host') revokeMut.mutate(principal);
		else if (action === 'delete-host') deleteMut.mutate(principal);
		setPending(null);
	}

	function formChildren(): ReactNode {
		if (pending === 'shell-exec') {
			return (
				<div className="mb-3 space-y-2">
					<label className="block font-mono text-[11px] uppercase tracking-wider text-text-dim">
						Command
						<textarea
							value={command}
							onChange={e => setCommand(e.target.value)}
							rows={6}
							spellCheck={false}
							placeholder="$ "
							className="mt-1 w-full resize-y rounded-sm border border-hairline bg-canvas px-2 py-1.5 font-mono text-[13px] leading-relaxed text-text outline-none focus:border-accent"
						/>
					</label>
					<div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-wider text-text-dim">
						<span>Timeout</span>
						<input
							type="number"
							min={1}
							value={timeout_s}
							onChange={e => setTimeout_s(Math.max(1, Number.parseInt(e.target.value) || 1))}
							aria-label="Timeout seconds"
							className="w-20 rounded-sm border border-hairline bg-bezel/60 px-2 py-1 text-right font-mono text-[12px] text-text outline-none focus:border-accent"
						/>
						<span className="text-text-dim normal-case">seconds</span>
					</div>
				</div>
			);
		}
		if (pending === 'pkg-update') {
			return (
				<fieldset className="mb-3">
					<legend className="font-mono text-[11px] uppercase tracking-wider text-text-dim">
						Update classes
					</legend>
					<div className="mt-1 flex gap-1.5">
						{['security', 'bugfix', 'enhancement'].map(opt => {
							const checked = classes.includes(opt);
							return (
								<button
									type="button"
									key={opt}
									onClick={() =>
										setClasses(prev => (checked ? prev.filter(c => c !== opt) : [...prev, opt]))
									}
									className={`rounded-sm border px-2 py-1 font-mono text-[11px] uppercase tracking-wider ${
										checked
											? 'border-accent bg-accent/15 text-accent'
											: 'border-hairline bg-surface-2 text-text-dim'
									}`}
								>
									{opt}
								</button>
							);
						})}
					</div>
				</fieldset>
			);
		}
		if (pending === 'revoke-host') {
			return (
				<label className="mb-3 block font-mono text-[11px] uppercase tracking-wider text-text-dim">
					Reason
					<textarea
						value={reason}
						onChange={e => setReason(e.target.value)}
						rows={3}
						className="mt-1 w-full rounded-sm border border-hairline bg-bezel/60 px-2 py-1.5 font-mono text-sm text-text outline-none focus:border-accent"
					/>
				</label>
			);
		}
		return null;
	}

	const pendingCap = pending ? caps[pending] : null;

	return (
		<>
			{/* Console label strip */}
			<div className="mb-2 flex items-center justify-between border-b border-hairline pb-1.5">
				<div className="flex items-center gap-1.5">
					<span className="mc-led mc-led-pulse text-accent" />
					<span className="mc-heading">Mission Command</span>
				</div>
				<span className="font-mono text-[9px] uppercase tracking-[0.18em] text-text-dim">
					armed
				</span>
			</div>

			{/* Action button cluster */}
			<div className="grid grid-cols-2 gap-1.5">
				{ACTIONS.map(a => {
					const cap = caps[a.type];
					const Icon = a.icon;
					const led = TONE_LED[a.tone];
					return (
						<button
							key={a.type}
							type="button"
							disabled={!cap.allowed}
							title={cap.allowed ? a.label : (cap.reason ?? '')}
							onClick={() => setPending(a.type)}
							className="mc-button group"
							data-tone={TONE_DATA[a.tone]}
						>
							<div className="flex items-center justify-between">
								<Icon className={led} size={14} />
								<span className={`mc-led ${led} group-hover:mc-led-pulse`} />
							</div>
							<div className="mt-1 font-mono text-[9px] uppercase tracking-[0.15em] text-text-dim">
								{a.short}
							</div>
							<div className="font-mono text-[12px] font-semibold text-text">{a.label}</div>
							<div className="font-mono text-[10px] text-text-dim">{a.desc}</div>
						</button>
					);
				})}
			</div>

			{/* Status readout strip */}
			<div className="mt-2 flex items-center justify-between border-t border-hairline pt-1.5 font-mono text-[10px] uppercase tracking-wider text-text-dim">
				<span>HOST {host.id.slice(0, 8)}</span>
				<span className="flex items-center gap-1">
					<span className="mc-led text-ok" /> READY
				</span>
			</div>

			{pending && pendingCap ? (
				<ActionConfirmDialog
					action={pending}
					host={{ id: host.id, hostname: host.hostname, labels: host.labels }}
					principal={pendingCap.principal ?? ''}
					onClose={() => setPending(null)}
					onConfirm={() => dispatch(pending, pendingCap.principal ?? '')}
					formChildren={formChildren()}
				/>
			) : null}
		</>
	);
}
